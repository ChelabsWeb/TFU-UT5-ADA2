"""svc-despacho: caso de uso crítico «Registrar despacho».

Flujo (ver diagrama de secuencia, Figura 3 del informe):
  1. Pide a svc-flota las ambulancias DISPONIBLES (REST, timeout + retry).
  2. Se queda con las N más cercanas y pide sus ETAs a svc-ruteo en UNA llamada
     SOAP por lote, protegida con Bulkhead + Circuit Breaker + Retry + Timeout.
     Si ruteo no responde -> Fallback: ETA estimada por distancia (eta_estimada=true).
  3. Reserva la de menor ETA en svc-flota (idempotente). Si otra réplica la tomó
     antes (409), prueba con la siguiente.
  4. Guarda el despacho y publica DespachoRegistrado.
"""
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from comun import logs
from comun.bus import Publicador, evento
from comun.db import crear_pool

from .clientes import FlotaCliente, RuteoSoapCliente
from .resiliencia import (
    Bulkhead,
    BulkheadLleno,
    CircuitBreaker,
    CircuitoAbierto,
    Plazo,
    PlazoAgotado,
    eta_estimada_seg,
    haversine_km,
    reintentar,
)

REPLICA = os.getenv("REPLICA", "svc-despacho")
log = logs.configurar(REPLICA)


def _f(nombre: str, defecto: str) -> float:
    return float(os.getenv(nombre, defecto))


# External Configuration Store: todo sale del .env del servicio.
PRESUPUESTO_SEG = _f("PRESUPUESTO_MS", "2000") / 1000
FLOTA_TIMEOUT_SEG = _f("FLOTA_TIMEOUT_MS", "500") / 1000
RUTEO_TIMEOUT_SEG = _f("RUTEO_TIMEOUT_MS", "800") / 1000
REINTENTOS = int(_f("REINTENTOS", "2"))
BACKOFF_BASE_SEG = _f("BACKOFF_BASE_MS", "100") / 1000
MAX_CANDIDATAS = int(_f("MAX_CANDIDATAS", "5"))

flota = FlotaCliente(os.environ["FLOTA_URL"], max_conexiones=int(_f("FLOTA_POOL", "20")))
ruteo = RuteoSoapCliente(os.getenv("RUTEO_WSDL", "/app/contracts/ruteo.wsdl"), os.environ["RUTEO_URL"])
cb_ruteo = CircuitBreaker(
    "ruteo",
    ventana=int(_f("CB_VENTANA", "10")),
    umbral_fallas=_f("CB_UMBRAL_FALLAS", "0.5"),
    minimo_llamadas=int(_f("CB_MINIMO_LLAMADAS", "5")),
    abierto_seg=_f("CB_ABIERTO_SEG", "30"),
)
bulkhead_ruteo = Bulkhead("ruteo", int(_f("RUTEO_MAX_CONCURRENTES", "10")))
pool = crear_pool(os.environ["DATABASE_URL"], "despacho", max_size=int(_f("DB_POOL", "10")))
bus = Publicador(os.environ["AMQP_URL"], "flota.eventos")

DDL = """
CREATE TABLE IF NOT EXISTS despachos (
    id             TEXT PRIMARY KEY,
    lat            DOUBLE PRECISION NOT NULL,
    lon            DOUBLE PRECISION NOT NULL,
    prioridad      TEXT NOT NULL,
    ambulancia_id  TEXT NOT NULL,
    eta_seg        INTEGER NOT NULL,
    eta_estimada   BOOLEAN NOT NULL,
    replica        TEXT NOT NULL,
    creado         TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    with pool.connection() as c:
        c.execute("SELECT pg_advisory_lock(42)")  # dos réplicas arrancan a la vez
        c.execute(DDL)
        c.execute("SELECT pg_advisory_unlock(42)")
    yield


app = FastAPI(title="svc-despacho", lifespan=lifespan)


class NuevoDespacho(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    prioridad: Literal["ALTA", "MEDIA", "BAJA"] = "ALTA"


@app.get("/health")
def health():
    return {"status": "ok", "replica": REPLICA, "circuito_ruteo": cb_ruteo.estado}


def _obtener_etas(candidatas: list[dict], destino: tuple[float, float], plazo: Plazo):
    """Devuelve (etas, estimada, motivo). Nunca lanza: si ruteo falla, usa el fallback."""

    def llamada_soap():
        return reintentar(
            lambda: ruteo.calcular_etas(destino, candidatas, timeout=plazo.limitar(RUTEO_TIMEOUT_SEG)),
            intentos=REINTENTOS,
            base_seg=BACKOFF_BASE_SEG,
            plazo=plazo,
        )

    motivo = None
    try:
        with bulkhead_ruteo:
            etas = cb_ruteo.llamar(llamada_soap)
        if all(a["id"] in etas for a in candidatas):
            return etas, False, None
        motivo = "respuesta incompleta de ruteo"
    except CircuitoAbierto:
        motivo = "circuito abierto"
    except BulkheadLleno:
        motivo = "bulkhead de ruteo lleno"
    except PlazoAgotado:
        motivo = "presupuesto agotado"
    except Exception as e:  # noqa: BLE001 - cualquier falla de ruteo activa el fallback
        motivo = f"falla de ruteo ({type(e).__name__})"
    etas = {a["id"]: eta_estimada_seg(a["lat"], a["lon"], *destino) for a in candidatas}
    return etas, True, motivo


@app.post("/despachos", status_code=201)
def registrar_despacho(req: NuevoDespacho):
    plazo = Plazo(PRESUPUESTO_SEG)
    despacho_id = str(uuid.uuid4())
    destino = (req.lat, req.lon)

    # 1. Candidatas (lectura idempotente: se puede reintentar)
    try:
        candidatas = reintentar(
            lambda: flota.disponibles(timeout=plazo.limitar(FLOTA_TIMEOUT_SEG)),
            intentos=REINTENTOS,
            base_seg=BACKOFF_BASE_SEG,
            plazo=plazo,
        )
    except Exception as e:  # noqa: BLE001
        log.error("svc-flota no disponible: %s", e)
        raise HTTPException(503, "svc-flota no disponible") from e
    if not candidatas:
        raise HTTPException(409, "No hay ambulancias disponibles")
    candidatas.sort(key=lambda a: haversine_km(a["lat"], a["lon"], *destino))
    candidatas = candidatas[:MAX_CANDIDATAS]

    # 2. ETAs por SOAP (con fallback)
    etas, estimada, motivo = _obtener_etas(candidatas, destino, plazo)
    if estimada:
        log.info("despacho %s con ETA estimada: %s", despacho_id, motivo)

    # 3. Reserva (idempotente gracias a la Idempotency-Key = despacho_id)
    elegida = None
    for amb in sorted(candidatas, key=lambda a: etas[a["id"]]):
        try:
            reservada = reintentar(
                lambda: flota.reservar(amb["id"], despacho_id, timeout=plazo.limitar(FLOTA_TIMEOUT_SEG)),
                intentos=REINTENTOS,
                base_seg=BACKOFF_BASE_SEG,
                plazo=plazo,
            )
        except Exception as e:  # noqa: BLE001
            log.error("no se pudo reservar: %s", e)
            raise HTTPException(503, "svc-flota no disponible") from e
        if reservada:
            elegida = amb
            break
    if elegida is None:
        raise HTTPException(409, "Las candidatas fueron tomadas por otros despachos")

    # 4. Persistir y avisar
    despacho = {
        "id": despacho_id,
        "lat": req.lat,
        "lon": req.lon,
        "prioridad": req.prioridad,
        "ambulancia_id": elegida["id"],
        "ambulancia_codigo": elegida.get("codigo"),
        "eta_seg": etas[elegida["id"]],
        "eta_estimada": estimada,
        "replica": REPLICA,
    }
    with pool.connection() as c:
        c.execute(
            """INSERT INTO despachos (id, lat, lon, prioridad, ambulancia_id, eta_seg, eta_estimada, replica)
               VALUES (%(id)s, %(lat)s, %(lon)s, %(prioridad)s, %(ambulancia_id)s, %(eta_seg)s,
                       %(eta_estimada)s, %(replica)s)""",
            despacho,
        )
    if not bus.publicar("despacho.registrado", evento("DespachoRegistrado", despacho)):
        log.error("evento DespachoRegistrado %s NO publicado (broker caído)", despacho_id)
    return despacho


@app.get("/despachos/{despacho_id}")
def obtener_despacho(despacho_id: str):
    with pool.connection() as c:
        fila = c.execute("SELECT * FROM despachos WHERE id=%s", (despacho_id,)).fetchone()
    if not fila:
        raise HTTPException(404, "Despacho no encontrado")
    return fila
