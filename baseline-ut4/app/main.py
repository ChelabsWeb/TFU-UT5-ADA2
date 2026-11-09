"""Baseline «UT4»: monolito en capas reconstruido para poder comparar en las pruebas.

Reproduce lo que el informe describe de la UT4, en un único proceso:
- Una sola base SQLite para todo el dominio.
- La ETA se expone por REST/JSON: GET /api/ambulancias/{id}/eta (la operación
  que en la UT5 se migró a SOAP).
- El despacho llama al proveedor de ruteo con timeout, sin Circuit Breaker ni
  fallback: si el proveedor no responde, el despacho falla.
- Los reportes corren con BackgroundTasks en el mismo proceso: un reporte que
  tira el proceso deja sin servicio a todos los endpoints y se pierde.
Misma lógica de negocio que la versión distribuida (candidatas, reserva, misión).
"""
import math
import os
import random
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

N_AMBULANCIAS = int(os.getenv("N_AMBULANCIAS", "200"))
MISION_SEG = float(os.getenv("MISION_SEG", "5"))
MAX_CANDIDATAS = int(os.getenv("MAX_CANDIDATAS", "5"))
PROVEEDOR_URL = os.environ["PROVEEDOR_URL"]
PROVEEDOR_TIMEOUT_SEG = float(os.getenv("PROVEEDOR_TIMEOUT_MS", "2000")) / 1000
REPORTE_SEG = float(os.getenv("REPORTE_SEG", "3"))

db = sqlite3.connect(os.getenv("DB_PATH", "/data/ut4.db"), check_same_thread=False, isolation_level=None)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
lock = threading.Lock()
proveedor = httpx.Client(base_url=PROVEEDOR_URL, timeout=PROVEEDOR_TIMEOUT_SEG)


def q(sql: str, args: tuple = ()) -> list[dict]:
    with lock:
        return [dict(f) for f in db.execute(sql, args).fetchall()]


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _inicializar():
    with lock:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS ambulancias (id TEXT PRIMARY KEY, codigo TEXT UNIQUE, lat REAL, lon REAL,
                estado TEXT, despacho_id TEXT, actualizado REAL);
            CREATE TABLE IF NOT EXISTS despachos (id TEXT PRIMARY KEY, lat REAL, lon REAL, prioridad TEXT,
                ambulancia_id TEXT, eta_seg INTEGER, creado REAL);
            CREATE TABLE IF NOT EXISTS reportes (id TEXT PRIMARY KEY, tipo TEXT, estado TEXT, resultado TEXT);
            """
        )
        if db.execute("SELECT count(*) FROM ambulancias").fetchone()[0]:
            return
        rnd = random.Random(42)
        db.executemany(
            "INSERT INTO ambulancias VALUES (?,?,?,?, 'DISPONIBLE', NULL, ?)",
            [
                (str(uuid.uuid4()), f"AMB-{i + 1:03d}", -34.88 + rnd.uniform(-0.05, 0.05),
                 -56.16 + rnd.uniform(-0.08, 0.08), time.time())
                for i in range(N_AMBULANCIAS)
            ],
        )


def _liberador():
    while True:
        time.sleep(1)
        with lock:
            db.execute(
                "UPDATE ambulancias SET estado='DISPONIBLE', despacho_id=NULL, actualizado=? "
                "WHERE estado='EN_SERVICIO' AND actualizado < ?",
                (time.time(), time.time() - MISION_SEG),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _inicializar()
    threading.Thread(target=_liberador, daemon=True).start()
    yield


app = FastAPI(title="Monolito UT4 (baseline)", lifespan=lifespan)


class NuevoDespacho(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    prioridad: Literal["ALTA", "MEDIA", "BAJA"] = "ALTA"


class SolicitudReporte(BaseModel):
    tipo: Literal["flota", "despachos", "falla"]


def _etas(candidatas: list[dict], lat: float, lon: float) -> list[float]:
    r = proveedor.post(
        "/v1/matrix", json={"sources": [[a["lon"], a["lat"]] for a in candidatas], "destination": [lon, lat]}
    )
    r.raise_for_status()
    return r.json()["durations"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/ambulancias")
def listar(estado: str | None = None):
    if estado:
        return q("SELECT id, codigo, lat, lon, estado FROM ambulancias WHERE estado=?", (estado,))
    return q("SELECT id, codigo, lat, lon, estado FROM ambulancias")


@app.get("/api/ambulancias/{amb_id}/eta")
def eta(amb_id: str, lat: float, lon: float):
    """Operación REST/JSON de la UT4 que en la UT5 pasa a SOAP (CalcularETAs)."""
    filas = q("SELECT id, lat, lon FROM ambulancias WHERE id=?", (amb_id,))
    if not filas:
        raise HTTPException(404, "Ambulancia no encontrada")
    try:
        return {"ambulancia_id": amb_id, "eta_seg": round(_etas(filas, lat, lon)[0])}
    except httpx.HTTPError as e:
        raise HTTPException(502, "Proveedor de ruteo no disponible") from e


@app.post("/api/despachos", status_code=201)
def despachar(req: NuevoDespacho):
    candidatas = q("SELECT id, codigo, lat, lon FROM ambulancias WHERE estado='DISPONIBLE'")
    if not candidatas:
        raise HTTPException(409, "No hay ambulancias disponibles")
    candidatas.sort(key=lambda a: _km(a["lat"], a["lon"], req.lat, req.lon))
    candidatas = candidatas[:MAX_CANDIDATAS]
    try:
        duraciones = _etas(candidatas, req.lat, req.lon)
    except httpx.HTTPError as e:
        raise HTTPException(502, "Proveedor de ruteo no disponible") from e
    despacho_id = str(uuid.uuid4())
    for amb, dur in sorted(zip(candidatas, duraciones), key=lambda x: x[1]):
        with lock:
            cur = db.execute(
                "UPDATE ambulancias SET estado='EN_SERVICIO', despacho_id=?, actualizado=? "
                "WHERE id=? AND estado='DISPONIBLE'",
                (despacho_id, time.time(), amb["id"]),
            )
            if cur.rowcount == 1:
                db.execute(
                    "INSERT INTO despachos VALUES (?,?,?,?,?,?,?)",
                    (despacho_id, req.lat, req.lon, req.prioridad, amb["id"], round(dur), time.time()),
                )
                return {"id": despacho_id, "ambulancia_id": amb["id"], "ambulancia_codigo": amb["codigo"],
                        "eta_seg": round(dur), "eta_estimada": False}
    raise HTTPException(409, "Las candidatas fueron tomadas por otros despachos")


def _generar_reporte(rid: str, tipo: str):
    if tipo == "falla":
        os._exit(1)  # mismo reporte defectuoso que en la versión distribuida
    time.sleep(REPORTE_SEG)
    total = q("SELECT count(*) AS n FROM despachos")[0]["n"]
    with lock:
        db.execute("UPDATE reportes SET estado='LISTO', resultado=? WHERE id=?", (f'{{"total": {total}}}', rid))


@app.post("/api/reportes", status_code=202)
def solicitar_reporte(req: SolicitudReporte, tareas: BackgroundTasks):
    rid = str(uuid.uuid4())
    with lock:
        db.execute("INSERT INTO reportes VALUES (?,?, 'PENDIENTE', NULL)", (rid, req.tipo))
    tareas.add_task(_generar_reporte, rid, req.tipo)
    return {"id": rid, "estado": "PENDIENTE"}


@app.get("/api/reportes/{rid}")
def consultar_reporte(rid: str):
    filas = q("SELECT * FROM reportes WHERE id=?", (rid,))
    if not filas:
        raise HTTPException(404, "Reporte no encontrado")
    return filas[0]
