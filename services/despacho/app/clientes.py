"""Clientes de las dependencias de svc-despacho.

- FlotaCliente: REST/JSON contra svc-flota (pool propio = bulkhead de conexiones).
- RuteoSoapCliente: SOAP/XML contra svc-ruteo, generado a partir del WSDL con zeep.
"""
import threading

import httpx
import requests
from zeep import Client
from zeep.transports import Transport

from .resiliencia import NoReintentable

NS_RUTEO = "http://ambulancias.ucu.edu.uy/ruteo"


class FlotaCliente:
    def __init__(self, url_base: str, max_conexiones: int):
        self._http = httpx.Client(
            base_url=url_base,
            limits=httpx.Limits(max_connections=max_conexiones, max_keepalive_connections=max_conexiones),
        )

    def disponibles(self, timeout: float) -> list[dict]:
        r = self._http.get("/ambulancias", params={"estado": "DISPONIBLE"}, timeout=timeout)
        if 400 <= r.status_code < 500:
            raise NoReintentable(f"svc-flota respondió {r.status_code}")
        r.raise_for_status()
        return r.json()

    def reservar(self, ambulancia_id: str, despacho_id: str, timeout: float) -> bool:
        """True si quedó reservada para este despacho, False si otro la tomó antes (409).

        Es seguro reintentarla: la Idempotency-Key hace que repetir el pedido
        devuelva el mismo resultado.
        """
        r = self._http.patch(
            f"/ambulancias/{ambulancia_id}/estado",
            json={"estado": "EN_SERVICIO"},
            headers={"Idempotency-Key": despacho_id},
            timeout=timeout,
        )
        if r.status_code == 409:
            return False
        if 400 <= r.status_code < 500:
            raise NoReintentable(f"svc-flota respondió {r.status_code}: {r.text}")
        r.raise_for_status()
        return True


class RuteoSoapCliente:
    """Consume la operación SOAP CalcularETAs.

    El WSDL se lee de un archivo local (contracts/ruteo.wsdl) para que svc-despacho
    arranque aunque svc-ruteo esté caído; la dirección del servicio sale de la
    configuración (RUTEO_URL). zeep no es thread-safe para cambiar timeouts, así
    que hay un cliente por hilo.
    """

    def __init__(self, wsdl: str, url: str):
        self.wsdl = wsdl
        self.url = url
        self._local = threading.local()

    def _cliente(self):
        actual = getattr(self._local, "cliente", None)
        if actual is None:
            transporte = Transport(session=requests.Session(), timeout=5, operation_timeout=1)
            cliente = Client(self.wsdl, transport=transporte)
            servicio = cliente.create_service(f"{{{NS_RUTEO}}}RuteoBinding", self.url)
            actual = (transporte, servicio)
            self._local.cliente = actual
        return actual

    def calcular_etas(self, destino: tuple[float, float], ambulancias: list[dict], timeout: float) -> dict[str, int]:
        transporte, servicio = self._cliente()
        transporte.operation_timeout = timeout
        respuesta = servicio.CalcularETAs(
            destino={"lat": destino[0], "lon": destino[1]},
            ambulancia=[{"id": a["id"], "lat": a["lat"], "lon": a["lon"]} for a in ambulancias],
        )
        if respuesta is None:
            etas = []
        elif isinstance(respuesta, list):
            etas = respuesta
        else:
            etas = getattr(respuesta, "eta", None) or []
        return {e.ambulanciaId: int(e.segundos) for e in etas}
