"""Mock del proveedor externo de ruteo (con su propio formato, distinto al nuestro).

POST /v1/matrix  {"sources": [[lon, lat], ...], "destination": [lon, lat]}
            ->   {"durations": [segundos, ...]}
Simula la latencia de un servicio externo con LATENCIA_MS +- JITTER_MS.
"""
import asyncio
import math
import os
import random

from fastapi import FastAPI
from pydantic import BaseModel

LATENCIA_MS = float(os.getenv("LATENCIA_MS", "60"))
JITTER_MS = float(os.getenv("JITTER_MS", "30"))
VELOCIDAD_KMH = 35.0

app = FastAPI(title="proveedor-ruteo (mock)")


class Matriz(BaseModel):
    sources: list[list[float]]
    destination: list[float]


def _km(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/matrix")
async def matriz(m: Matriz):
    await asyncio.sleep(max(0.0, LATENCIA_MS + random.uniform(-JITTER_MS, JITTER_MS)) / 1000)
    # «Ruta real»: la distancia por calles es ~1.4 veces la línea recta, con algo de tránsito.
    return {
        "durations": [_km(s, m.destination) * 1.4 / VELOCIDAD_KMH * 3600 * random.uniform(0.9, 1.2) for s in m.sources]
    }
