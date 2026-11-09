"""svc-ruteo: expone CalcularETAs por SOAP 1.1 (contrato contracts/ruteo.wsdl).

Es un adaptador (Anti-Corruption Layer) del proveedor externo de ruteo: traduce
el formato del proveedor ([lon, lat], duraciones en segundos con decimales) al
contrato propio, para poder cambiar de proveedor sin tocar svc-despacho.
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response

from comun import logs

from .soap import SolicitudInvalida, armar_fault, armar_respuesta, leer_solicitud

log = logs.configurar("svc-ruteo")

PROVEEDOR_URL = os.environ["PROVEEDOR_URL"]
PROVEEDOR_TIMEOUT_SEG = float(os.getenv("PROVEEDOR_TIMEOUT_MS", "700")) / 1000
URL_PUBLICA = os.getenv("URL_PUBLICA", "http://svc-ruteo:8000/soap")
WSDL = Path(os.getenv("RUTEO_WSDL", "/app/contracts/ruteo.wsdl")).read_text(encoding="utf-8")
WSDL = WSDL.replace("http://svc-ruteo:8000/soap", URL_PUBLICA)
XML = "text/xml; charset=utf-8"

app = FastAPI(title="svc-ruteo")
proveedor = httpx.AsyncClient(base_url=PROVEEDOR_URL, timeout=PROVEEDOR_TIMEOUT_SEG)


@app.get("/health")
def health():
    return {"status": "ok", "servicio": "svc-ruteo"}


@app.get("/soap")
def wsdl(request: Request):
    if "wsdl" not in {k.lower() for k in request.query_params.keys()}:
        return Response(armar_fault("soap:Client", "Use POST para invocar o ?wsdl para el contrato"), 400, media_type=XML)
    return Response(WSDL, media_type=XML)


@app.post("/soap")
async def calcular_etas(request: Request):
    try:
        destino, ambulancias = leer_solicitud(await request.body())
    except SolicitudInvalida as e:
        return Response(armar_fault("soap:Client", str(e)), 500, media_type=XML)

    # Adaptación al formato del proveedor externo.
    pedido = {
        "sources": [[a["lon"], a["lat"]] for a in ambulancias],
        "destination": [destino["lon"], destino["lat"]],
    }
    try:
        r = await proveedor.post("/v1/matrix", json=pedido)
        r.raise_for_status()
        duraciones = r.json()["durations"]
        if len(duraciones) != len(ambulancias):
            raise ValueError("el proveedor devolvió una cantidad distinta de duraciones")
    except Exception as e:  # noqa: BLE001
        log.warning("proveedor de ruteo no disponible: %s", e)
        return Response(armar_fault("soap:Server", "Proveedor de ruteo no disponible"), 500, media_type=XML)

    etas = [(a["id"], round(d)) for a, d in zip(ambulancias, duraciones)]
    return Response(armar_respuesta(etas), media_type=XML)
