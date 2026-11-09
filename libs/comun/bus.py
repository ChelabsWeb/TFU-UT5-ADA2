"""Publicación de mensajes en RabbitMQ (Publisher-Subscriber).

- Mensajes persistentes (delivery_mode=2) sobre exchanges y colas durables.
- Publisher confirms: basic_publish no vuelve hasta que el broker confirma.
- Una conexión por hilo: BlockingConnection de pika no es thread-safe y FastAPI
  atiende los endpoints síncronos en un pool de hilos.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone

import pika

log = logging.getLogger(__name__)


def evento(tipo: str, datos: dict) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "ocurrido": datetime.now(timezone.utc).isoformat(),
        "datos": datos,
    }


class Publicador:
    def __init__(self, url: str, exchange: str, tipo_exchange: str = "topic"):
        self.url = url
        self.exchange = exchange
        self.tipo_exchange = tipo_exchange
        self._local = threading.local()

    def _canal(self):
        canal = getattr(self._local, "canal", None)
        if canal is None or canal.is_closed:
            conexion = pika.BlockingConnection(pika.URLParameters(self.url))
            canal = conexion.channel()
            if self.exchange:
                canal.exchange_declare(self.exchange, self.tipo_exchange, durable=True)
            canal.confirm_delivery()
            self._local.conexion = conexion
            self._local.canal = canal
        return canal

    def _cerrar(self):
        conexion = getattr(self._local, "conexion", None)
        self._local.canal = None
        self._local.conexion = None
        try:
            if conexion is not None and conexion.is_open:
                conexion.close()
        except Exception:  # noqa: BLE001 - ya estaba rota
            pass

    def publicar(self, routing_key: str, mensaje: dict, mandatory: bool = False) -> bool:
        """Publica con confirmación. Reintenta una vez reconectando; si no puede, devuelve False.

        El llamador decide qué hacer si falla: en esta demo se registra en el log
        (ver «Transactional Outbox» en el informe: es la mejora para producción).
        """
        cuerpo = json.dumps(mensaje).encode()
        props = pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            message_id=mensaje.get("id"),
            type=mensaje.get("tipo"),
        )
        for intento in (1, 2):
            try:
                self._canal().basic_publish(
                    self.exchange, routing_key, cuerpo, props, mandatory=mandatory
                )
                return True
            except Exception as e:  # noqa: BLE001
                log.warning("publicar %s falló (intento %s): %s", routing_key, intento, e)
                self._cerrar()
        return False
