import logging
import os


def configurar(nombre: str) -> logging.Logger:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=f"%(asctime)s {nombre} %(levelname)s %(message)s",
    )
    logging.getLogger("pika").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("zeep").setLevel(logging.WARNING)
    return logging.getLogger(nombre)
