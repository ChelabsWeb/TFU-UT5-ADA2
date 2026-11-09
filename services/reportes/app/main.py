"""svc-reportes: proyección de la flota por eventos + reportes asíncronos.

- Suscriptor de flota.eventos (Publisher-Subscriber): mantiene su propia copia
  de los datos (consistencia eventual). El consumidor es idempotente: guarda los
  ids de eventos ya procesados, así que una entrega repetida no duplica nada.
- POST /reportes responde 202 y encola la solicitud (Asynchronous Request-Reply +
  Queue-Based Load Leveling). Un worker la procesa a su ritmo.
- Las colas son quorum queues durables con límite de entregas: un mensaje que
  hace fallar al worker repetidas veces termina en la Dead Letter Queue en vez
  de tirar el servicio para siempre.
- El tipo de reporte «falla» simula un reporte defectuoso que mata el proceso
  (como un OOM). Sirve para la prueba P2.
"""
import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import pika
from fastapi import FastAPI, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from comun import logs
from comun.bus import Publicador
from comun.db import crear_pool

log = logs.configurar("svc-reportes")

AMQP_URL = os.environ["AMQP_URL"]
REPORTE_SEG = float(os.getenv("REPORTE_SEG", "3"))
COLA_EVENTOS = "reportes.eventos"
COLA_SOLICITUDES = "reportes.solicitudes"
COLA_DLQ = "reportes.solicitudes.dlq"

pool = crear_pool(os.environ["DATABASE_URL"], "reportes", max_size=int(os.getenv("DB_POOL", "10")))
cola_solicitudes = Publicador(AMQP_URL, "")  # exchange por defecto: routing key = nombre de la cola

DDL = """
CREATE TABLE IF NOT EXISTS proyeccion_ambulancias (
    id TEXT PRIMARY KEY, estado TEXT NOT NULL, actualizado TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS despachos (
    id TEXT PRIMARY KEY, ambulancia_id TEXT NOT NULL, eta_seg INTEGER NOT NULL,
    eta_estimada BOOLEAN NOT NULL, replica TEXT, registrado TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos_procesados (id TEXT PRIMARY KEY, procesado TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS reportes (
    id TEXT PRIMARY KEY, tipo TEXT NOT NULL, estado TEXT NOT NULL,
    resultado JSONB, creado TIMESTAMPTZ DEFAULT now(), terminado TIMESTAMPTZ
);
"""


def declarar_topologia(canal) -> None:
    canal.exchange_declare("flota.eventos", "topic", durable=True)
    canal.exchange_declare("reportes.dlx", "fanout", durable=True)
    canal.exchange_declare("eventos.dlx", "fanout", durable=True)
    canal.queue_declare(COLA_DLQ, durable=True, arguments={"x-queue-type": "quorum"})
    canal.queue_bind(COLA_DLQ, "reportes.dlx")
    canal.queue_declare("reportes.eventos.dlq", durable=True, arguments={"x-queue-type": "quorum"})
    canal.queue_bind("reportes.eventos.dlq", "eventos.dlx")
    canal.queue_declare(
        COLA_SOLICITUDES,
        durable=True,
        arguments={"x-queue-type": "quorum", "x-delivery-limit": 2, "x-dead-letter-exchange": "reportes.dlx"},
    )
    canal.queue_declare(
        COLA_EVENTOS,
        durable=True,
        arguments={"x-queue-type": "quorum", "x-delivery-limit": 5, "x-dead-letter-exchange": "eventos.dlx"},
    )
    canal.queue_bind(COLA_EVENTOS, "flota.eventos", "#")


# ------------------------------------------------------------ manejadores
def aplicar_evento(ev: dict) -> None:
    with pool.connection() as c:
        nuevo = c.execute(
            "INSERT INTO eventos_procesados (id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id", (ev["id"],)
        ).fetchone()
        if not nuevo:
            return  # ya procesado: entrega duplicada (at-least-once)
        d = ev["datos"]
        if ev["tipo"] == "AmbulanciaEstadoCambiado":
            c.execute(
                """INSERT INTO proyeccion_ambulancias (id, estado, actualizado) VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET estado = EXCLUDED.estado, actualizado = EXCLUDED.actualizado
                   WHERE proyeccion_ambulancias.actualizado <= EXCLUDED.actualizado""",
                (d["ambulancia_id"], d["estado"], ev["ocurrido"]),
            )
        elif ev["tipo"] == "DespachoRegistrado":
            c.execute(
                """INSERT INTO despachos (id, ambulancia_id, eta_seg, eta_estimada, replica, registrado)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (d["id"], d["ambulancia_id"], d["eta_seg"], d["eta_estimada"], d.get("replica"), ev["ocurrido"]),
            )


def generar(tipo: str) -> dict:
    with pool.connection() as c:
        if tipo == "flota":
            filas = c.execute("SELECT estado, count(*) AS n FROM proyeccion_ambulancias GROUP BY estado").fetchall()
            return {"por_estado": {f["estado"]: f["n"] for f in filas}}
        f = c.execute(
            """SELECT count(*) AS total, coalesce(round(avg(eta_seg)), 0) AS eta_promedio_seg,
                      count(*) FILTER (WHERE eta_estimada) AS con_eta_estimada
               FROM despachos"""
        ).fetchone()
        return {k: (float(v) if k == "eta_promedio_seg" else v) for k, v in f.items()}


def procesar_solicitud(msg: dict) -> None:
    rid, tipo = msg["reporte_id"], msg["tipo"]
    if tipo == "falla":
        log.error("reporte %s defectuoso: el proceso termina (simula un OOM)", rid)
        os._exit(1)
    time.sleep(REPORTE_SEG)  # reporte «pesado»
    resultado = generar(tipo)
    with pool.connection() as c:
        c.execute(
            "UPDATE reportes SET estado='LISTO', resultado=%s, terminado=now() WHERE id=%s",
            (Jsonb(resultado), rid),
        )
    log.info("reporte %s listo", rid)


def marcar_fallido(msg: dict) -> None:
    with pool.connection() as c:
        c.execute("UPDATE reportes SET estado='FALLIDO', terminado=now() WHERE id=%s", (msg["reporte_id"],))
    log.warning("reporte %s enviado a la DLQ tras varios intentos: FALLIDO", msg["reporte_id"])


# ------------------------------------------------------------ consumidores
def consumir(cola: str, manejador) -> None:
    while True:
        try:
            conexion = pika.BlockingConnection(pika.URLParameters(AMQP_URL))
            canal = conexion.channel()
            declarar_topologia(canal)
            canal.basic_qos(prefetch_count=1)

            def al_recibir(ch, method, _props, cuerpo):
                try:
                    manejador(json.loads(cuerpo))
                except Exception as e:  # noqa: BLE001
                    log.error("error procesando mensaje de %s: %s", cola, e)
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    return
                ch.basic_ack(method.delivery_tag)  # ack manual: recién cuando terminó bien

            canal.basic_consume(cola, al_recibir)
            log.info("consumiendo %s", cola)
            canal.start_consuming()
        except Exception as e:  # noqa: BLE001
            log.warning("consumidor %s desconectado (%s); reintento en 2 s", cola, e)
            time.sleep(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with pool.connection() as c:
        c.execute(DDL)
    for intento in range(30):  # la topología tiene que existir antes de aceptar pedidos
        try:
            conexion = pika.BlockingConnection(pika.URLParameters(AMQP_URL))
            declarar_topologia(conexion.channel())
            conexion.close()
            break
        except Exception as e:  # noqa: BLE001
            log.warning("RabbitMQ no disponible todavía (%s)", e)
            time.sleep(1)
    for cola, manejador in (
        (COLA_EVENTOS, aplicar_evento),
        (COLA_SOLICITUDES, procesar_solicitud),
        (COLA_DLQ, marcar_fallido),
    ):
        threading.Thread(target=consumir, args=(cola, manejador), daemon=True, name=cola).start()
    yield


app = FastAPI(title="svc-reportes", lifespan=lifespan)


class SolicitudReporte(BaseModel):
    tipo: Literal["flota", "despachos", "falla"]


@app.get("/health")
def health():
    with pool.connection() as c:
        c.execute("SELECT 1")
    return {"status": "ok", "servicio": "svc-reportes"}


@app.post("/reportes", status_code=202)
def solicitar(req: SolicitudReporte):
    rid = str(uuid.uuid4())
    with pool.connection() as c:
        c.execute("INSERT INTO reportes (id, tipo, estado) VALUES (%s, %s, 'PENDIENTE')", (rid, req.tipo))
    if not cola_solicitudes.publicar(COLA_SOLICITUDES, {"id": rid, "reporte_id": rid, "tipo": req.tipo}, mandatory=True):
        with pool.connection() as c:
            c.execute("UPDATE reportes SET estado='FALLIDO' WHERE id=%s", (rid,))
        raise HTTPException(503, "No se pudo encolar el reporte")
    return {"id": rid, "estado": "PENDIENTE", "consultar": f"/api/reportes/{rid}"}


@app.get("/reportes/{rid}")
def consultar(rid: str):
    with pool.connection() as c:
        fila = c.execute("SELECT * FROM reportes WHERE id=%s", (rid,)).fetchone()
    if not fila:
        raise HTTPException(404, "Reporte no encontrado")
    return fila
