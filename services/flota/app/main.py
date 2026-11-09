"""svc-flota: dueño del estado de las ambulancias.

- Reserva con control de concurrencia: solo pasa a EN_SERVICIO si estaba DISPONIBLE.
- Reserva idempotente: la Idempotency-Key es el id del despacho; repetir el mismo
  pedido devuelve el mismo resultado en vez de 409 (permite reintentar sin miedo).
- Cache-Aside sobre Redis para la lista de ambulancias por estado.
- Publica AmbulanciaEstadoCambiado (Publisher-Subscriber) en el exchange flota.eventos.
- Simula la duración de una misión: libera ambulancias EN_SERVICIO tras MISION_SEG.
"""
import json
import os
import random
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal, Optional

import redis
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from comun import logs
from comun.bus import Publicador, evento
from comun.db import crear_pool

log = logs.configurar("svc-flota")

N_AMBULANCIAS = int(os.getenv("N_AMBULANCIAS", "200"))
MISION_SEG = float(os.getenv("MISION_SEG", "5"))
CACHE_TTL_SEG = int(os.getenv("CACHE_TTL_SEG", "2"))
ESTADOS = ("DISPONIBLE", "EN_SERVICIO", "FUERA_DE_SERVICIO")
COLUMNAS = "id, codigo, lat, lon, estado, despacho_id"

pool = crear_pool(os.environ["DATABASE_URL"], "flota", max_size=int(os.getenv("DB_POOL", "20")))
cache = redis.Redis.from_url(
    os.environ["REDIS_URL"], socket_timeout=0.2, socket_connect_timeout=0.2, decode_responses=True
)
bus = Publicador(os.environ["AMQP_URL"], "flota.eventos")

DDL = """
CREATE TABLE IF NOT EXISTS ambulancias (
    id          TEXT PRIMARY KEY,
    codigo      TEXT UNIQUE NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    estado      TEXT NOT NULL CHECK (estado IN ('DISPONIBLE','EN_SERVICIO','FUERA_DE_SERVICIO')),
    despacho_id TEXT,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ambulancias_estado ON ambulancias (estado);
"""


def _publicar_cambio(amb: dict) -> None:
    ev = evento(
        "AmbulanciaEstadoCambiado",
        {"ambulancia_id": amb["id"], "estado": amb["estado"], "despacho_id": amb.get("despacho_id")},
    )
    if not bus.publicar("ambulancia.estado_cambiado", ev):
        log.error("evento %s NO publicado (broker caído)", ev["id"])


def _invalidar_cache() -> None:
    try:
        cache.delete(*[f"ambulancias:{e}" for e in (*ESTADOS, "todas")])
    except redis.RedisError as e:
        log.warning("no se pudo invalidar la caché: %s", e)


def _inicializar() -> None:
    with pool.connection() as c:
        c.execute(DDL)
        n = c.execute("SELECT count(*) AS n FROM ambulancias").fetchone()["n"]
        if n:
            return
        rnd = random.Random(42)
        filas = []
        for i in range(N_AMBULANCIAS):
            filas.append(
                (
                    str(uuid.uuid4()),
                    f"AMB-{i + 1:03d}",
                    -34.88 + rnd.uniform(-0.05, 0.05),
                    -56.16 + rnd.uniform(-0.08, 0.08),
                )
            )
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO ambulancias (id, codigo, lat, lon, estado) VALUES (%s,%s,%s,%s,'DISPONIBLE')",
                filas,
            )
    log.info("flota inicial cargada: %s ambulancias", N_AMBULANCIAS)
    for f in filas:
        _publicar_cambio({"id": f[0], "estado": "DISPONIBLE"})


def _liberador() -> None:
    """Simula el fin de las misiones: vuelve a DISPONIBLE lo que lleva MISION_SEG en servicio."""
    while True:
        time.sleep(1)
        try:
            with pool.connection() as c:
                filas = c.execute(
                    f"""UPDATE ambulancias SET estado='DISPONIBLE', despacho_id=NULL, actualizado=now()
                        WHERE estado='EN_SERVICIO' AND actualizado < now() - make_interval(secs => %s)
                        RETURNING {COLUMNAS}""",
                    (MISION_SEG,),
                ).fetchall()
            if filas:
                _invalidar_cache()
                for f in filas:
                    _publicar_cambio(f)
        except Exception as e:  # noqa: BLE001
            log.warning("liberador: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _inicializar()
    threading.Thread(target=_liberador, daemon=True, name="liberador").start()
    yield


app = FastAPI(title="svc-flota", lifespan=lifespan)


class CambioEstado(BaseModel):
    estado: Literal["DISPONIBLE", "EN_SERVICIO", "FUERA_DE_SERVICIO"]


class NuevaAmbulancia(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@app.get("/health")
def health():
    with pool.connection() as c:
        c.execute("SELECT 1")
    return {"status": "ok", "servicio": "svc-flota"}


@app.get("/ambulancias")
def listar(estado: Optional[Literal["DISPONIBLE", "EN_SERVICIO", "FUERA_DE_SERVICIO"]] = Query(None)):
    clave = f"ambulancias:{estado or 'todas'}"
    # Cache-Aside: 1) buscar en caché
    try:
        en_cache = cache.get(clave)
        if en_cache is not None:
            return json.loads(en_cache)
    except redis.RedisError as e:
        log.warning("caché no disponible, se va a la base: %s", e)
    # 2) si no está, ir a la base
    with pool.connection() as c:
        if estado:
            filas = c.execute(f"SELECT {COLUMNAS} FROM ambulancias WHERE estado=%s", (estado,)).fetchall()
        else:
            filas = c.execute(f"SELECT {COLUMNAS} FROM ambulancias").fetchall()
    # 3) guardar en caché con TTL corto
    try:
        cache.set(clave, json.dumps(filas), ex=CACHE_TTL_SEG)
    except redis.RedisError:
        pass
    return filas


@app.get("/ambulancias/{amb_id}")
def obtener(amb_id: str):
    with pool.connection() as c:
        fila = c.execute(f"SELECT {COLUMNAS} FROM ambulancias WHERE id=%s", (amb_id,)).fetchone()
    if not fila:
        raise HTTPException(404, "Ambulancia no encontrada")
    return fila


@app.post("/ambulancias", status_code=201)
def crear(req: NuevaAmbulancia):
    nueva = {"id": str(uuid.uuid4()), **req.model_dump()}
    with pool.connection() as c:
        fila = c.execute(
            f"""INSERT INTO ambulancias (id, codigo, lat, lon, estado) VALUES (%s,%s,%s,%s,'DISPONIBLE')
                ON CONFLICT (codigo) DO NOTHING RETURNING {COLUMNAS}""",
            (nueva["id"], req.codigo, req.lat, req.lon),
        ).fetchone()
    if not fila:
        raise HTTPException(409, "Ya existe una ambulancia con ese código")
    _invalidar_cache()
    _publicar_cambio(fila)
    return fila


@app.patch("/ambulancias/{amb_id}/estado")
def cambiar_estado(amb_id: str, cambio: CambioEstado, idempotency_key: Optional[str] = Header(None)):
    with pool.connection() as c:
        if cambio.estado == "EN_SERVICIO":
            if not idempotency_key:
                raise HTTPException(400, "Reservar requiere el header Idempotency-Key (id del despacho)")
            fila = c.execute(
                f"""UPDATE ambulancias SET estado='EN_SERVICIO', despacho_id=%s, actualizado=now()
                    WHERE id=%s AND estado='DISPONIBLE' RETURNING {COLUMNAS}""",
                (idempotency_key, amb_id),
            ).fetchone()
            if fila is None:
                actual = c.execute(f"SELECT {COLUMNAS} FROM ambulancias WHERE id=%s", (amb_id,)).fetchone()
                if actual is None:
                    raise HTTPException(404, "Ambulancia no encontrada")
                if actual["estado"] == "EN_SERVICIO" and actual["despacho_id"] == idempotency_key:
                    # Mismo pedido repetido (se perdió la respuesta anterior): mismo resultado.
                    return {**actual, "repetido": True}
                raise HTTPException(409, f"La ambulancia no está disponible (estado {actual['estado']})")
        else:
            fila = c.execute(
                f"""UPDATE ambulancias SET estado=%s, despacho_id=NULL, actualizado=now()
                    WHERE id=%s RETURNING {COLUMNAS}""",
                (cambio.estado, amb_id),
            ).fetchone()
            if fila is None:
                raise HTTPException(404, "Ambulancia no encontrada")
    _invalidar_cache()
    _publicar_cambio(fila)
    return fila
