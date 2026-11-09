"""Patrones de resiliencia usados por svc-despacho.

Están escritos a mano (sin librerías) para que se vea qué hace cada uno:

- Plazo           -> Timeouts con presupuesto total para todo el despacho.
- reintentar      -> Retry con backoff exponencial y jitter, que respeta el plazo.
- CircuitBreaker  -> CERRADO / ABIERTO / SEMIABIERTO con ventana deslizante.
- Bulkhead        -> limita las llamadas concurrentes a una dependencia.
- eta_estimada_seg-> Fallback: ETA aproximada por distancia en línea recta.
"""
import logging
import math
import random
import threading
import time
from collections import deque
from typing import Callable, TypeVar

log = logging.getLogger("svc-despacho.resiliencia")
T = TypeVar("T")


# ---------------------------------------------------------------- Timeouts
class PlazoAgotado(Exception):
    pass


class Plazo:
    """Presupuesto de tiempo de una operación completa (p. ej. 2 s para despachar)."""

    MINIMO = 0.05

    def __init__(self, segundos: float, reloj: Callable[[], float] = time.monotonic):
        self._reloj = reloj
        self._fin = reloj() + segundos

    def restante(self) -> float:
        return self._fin - self._reloj()

    def limitar(self, timeout: float) -> float:
        """Timeout a usar en la próxima llamada: nunca más que lo que queda del presupuesto."""
        queda = self.restante()
        if queda <= self.MINIMO:
            raise PlazoAgotado("se agotó el presupuesto de tiempo")
        return min(timeout, queda)


# ---------------------------------------------------------------- Retry
class NoReintentable(Exception):
    """Error que no tiene sentido reintentar (p. ej. un 4xx)."""


def reintentar(
    fn: Callable[[], T],
    intentos: int,
    base_seg: float,
    plazo: Plazo,
    dormir: Callable[[float], None] = time.sleep,
    azar: Callable[[float, float], float] = random.uniform,
) -> T:
    """Ejecuta fn con hasta `intentos` reintentos extra.

    Solo se debe usar con operaciones idempotentes. El backoff es exponencial
    (base, 2*base, 4*base...) con jitter de +-50 % para que las réplicas no
    reintenten todas a la vez, y nunca se reintenta si no queda presupuesto.
    """
    for i in range(intentos + 1):
        try:
            return fn()
        except (NoReintentable, PlazoAgotado):
            raise
        except Exception:
            if i == intentos:
                raise
            espera = base_seg * (2**i) * azar(0.5, 1.5)
            if plazo.restante() <= espera + Plazo.MINIMO:
                raise
            dormir(espera)
    raise AssertionError("inalcanzable")


# ---------------------------------------------------------------- Circuit Breaker
class CircuitoAbierto(Exception):
    pass


class CircuitBreaker:
    CERRADO = "CERRADO"
    ABIERTO = "ABIERTO"
    SEMIABIERTO = "SEMIABIERTO"

    def __init__(
        self,
        nombre: str,
        ventana: int = 10,
        umbral_fallas: float = 0.5,
        minimo_llamadas: int = 5,
        abierto_seg: float = 30.0,
        reloj: Callable[[], float] = time.monotonic,
    ):
        self.nombre = nombre
        self.umbral_fallas = umbral_fallas
        self.minimo_llamadas = minimo_llamadas
        self.abierto_seg = abierto_seg
        self._reloj = reloj
        self._resultados: deque[bool] = deque(maxlen=ventana)
        self._estado = self.CERRADO
        self._abierto_desde = 0.0
        self._prueba_en_curso = False
        self._lock = threading.Lock()

    @property
    def estado(self) -> str:
        with self._lock:
            if self._estado == self.ABIERTO and self._reloj() - self._abierto_desde >= self.abierto_seg:
                return self.SEMIABIERTO
            return self._estado

    def _cambiar(self, nuevo: str) -> None:
        if nuevo != self._estado:
            log.warning("circuito %s: %s -> %s", self.nombre, self._estado, nuevo)
            self._estado = nuevo

    def llamar(self, fn: Callable[[], T]) -> T:
        with self._lock:
            if self._estado == self.ABIERTO:
                if self._reloj() - self._abierto_desde < self.abierto_seg:
                    raise CircuitoAbierto(self.nombre)
                self._cambiar(self.SEMIABIERTO)
                self._prueba_en_curso = False
            if self._estado == self.SEMIABIERTO:
                if self._prueba_en_curso:
                    raise CircuitoAbierto(self.nombre)  # solo una llamada de prueba a la vez
                self._prueba_en_curso = True
        try:
            resultado = fn()
        except Exception:
            self._registrar(False)
            raise
        self._registrar(True)
        return resultado

    def _registrar(self, exito: bool) -> None:
        with self._lock:
            if self._estado == self.SEMIABIERTO:
                self._prueba_en_curso = False
                if exito:
                    self._resultados.clear()
                    self._cambiar(self.CERRADO)
                else:
                    self._abierto_desde = self._reloj()
                    self._cambiar(self.ABIERTO)
                return
            self._resultados.append(exito)
            fallas = self._resultados.count(False)
            n = len(self._resultados)
            if n >= self.minimo_llamadas and fallas / n >= self.umbral_fallas:
                self._abierto_desde = self._reloj()
                self._resultados.clear()
                self._cambiar(self.ABIERTO)


# ---------------------------------------------------------------- Bulkhead
class BulkheadLleno(Exception):
    pass


class Bulkhead:
    """Limita cuántas llamadas concurrentes puede tener una dependencia.

    Si ruteo se pone lento, a lo sumo `maximo` hilos quedan esperándolo; el resto
    no se encola: falla enseguida y usa el fallback, y los hilos quedan libres para
    seguir atendiendo (y para hablar con svc-flota).
    """

    def __init__(self, nombre: str, maximo: int):
        self.nombre = nombre
        self._sem = threading.BoundedSemaphore(maximo)

    def __enter__(self):
        if not self._sem.acquire(blocking=False):
            raise BulkheadLleno(self.nombre)
        return self

    def __exit__(self, *exc):
        self._sem.release()
        return False


# ---------------------------------------------------------------- Fallback
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def eta_estimada_seg(
    lat1: float, lon1: float, lat2: float, lon2: float, velocidad_kmh: float = 40.0, factor_ruta: float = 1.3
) -> int:
    """ETA aproximada: distancia en línea recta * factor de ruta / velocidad urbana promedio."""
    km = haversine_km(lat1, lon1, lat2, lon2) * factor_ruta
    return max(1, round(km / velocidad_kmh * 3600))
