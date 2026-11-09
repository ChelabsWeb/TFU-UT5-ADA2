import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r = _cargar("resiliencia", "services/despacho/app/resiliencia.py")


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def falla():
    raise ConnectionError("caído")


# ------------------------------------------------------------ Circuit Breaker
def _cb(reloj):
    return r.CircuitBreaker("x", ventana=10, umbral_fallas=0.5, minimo_llamadas=5, abierto_seg=30, reloj=reloj)


def test_cb_no_abre_antes_del_minimo_de_llamadas():
    cb = _cb(Reloj())
    for _ in range(4):
        with pytest.raises(ConnectionError):
            cb.llamar(falla)
    assert cb.estado == r.CircuitBreaker.CERRADO


def test_cb_abre_al_superar_el_umbral_y_falla_rapido():
    cb = _cb(Reloj())
    for _ in range(5):
        with pytest.raises(ConnectionError):
            cb.llamar(falla)
    assert cb.estado == r.CircuitBreaker.ABIERTO
    llamado = []
    with pytest.raises(r.CircuitoAbierto):
        cb.llamar(lambda: llamado.append(1))
    assert llamado == []  # con el circuito abierto ni siquiera se intenta


def test_cb_semiabierto_cierra_si_la_prueba_sale_bien():
    reloj = Reloj()
    cb = _cb(reloj)
    for _ in range(5):
        with pytest.raises(ConnectionError):
            cb.llamar(falla)
    reloj.t = 30
    assert cb.estado == r.CircuitBreaker.SEMIABIERTO
    assert cb.llamar(lambda: "ok") == "ok"
    assert cb.estado == r.CircuitBreaker.CERRADO


def test_cb_semiabierto_vuelve_a_abrir_si_la_prueba_falla():
    reloj = Reloj()
    cb = _cb(reloj)
    for _ in range(5):
        with pytest.raises(ConnectionError):
            cb.llamar(falla)
    reloj.t = 31
    with pytest.raises(ConnectionError):
        cb.llamar(falla)
    assert cb.estado == r.CircuitBreaker.ABIERTO
    reloj.t = 40  # el contador de 30 s arranca de nuevo
    with pytest.raises(r.CircuitoAbierto):
        cb.llamar(lambda: "ok")


def test_cb_tolera_fallas_aisladas():
    cb = _cb(Reloj())
    for i in range(20):
        if i % 4 == 0:
            with pytest.raises(ConnectionError):
                cb.llamar(falla)
        else:
            cb.llamar(lambda: None)
    assert cb.estado == r.CircuitBreaker.CERRADO  # 25 % de fallas < 50 %


# ------------------------------------------------------------ Retry + Plazo
def test_reintentar_recupera_falla_transitoria_con_backoff():
    esperas, intentos = [], []

    def a_veces():
        intentos.append(1)
        if len(intentos) < 3:
            raise ConnectionError()
        return "ok"

    res = r.reintentar(a_veces, 2, 0.1, r.Plazo(10), dormir=esperas.append, azar=lambda a, b: 1.0)
    assert res == "ok" and len(intentos) == 3
    assert esperas == [0.1, 0.2]  # backoff exponencial


def test_reintentar_no_reintenta_errores_no_reintentables():
    intentos = []

    def cuatrocientos():
        intentos.append(1)
        raise r.NoReintentable("400")

    with pytest.raises(r.NoReintentable):
        r.reintentar(cuatrocientos, 2, 0.1, r.Plazo(10), dormir=lambda s: None)
    assert len(intentos) == 1


def test_reintentar_respeta_el_presupuesto():
    reloj = Reloj()
    plazo = r.Plazo(0.3, reloj=reloj)
    intentos = []

    def siempre_falla():
        intentos.append(1)
        raise ConnectionError()

    with pytest.raises(ConnectionError):
        r.reintentar(siempre_falla, 5, 0.1, plazo, dormir=lambda s: setattr(reloj, "t", reloj.t + s),
                     azar=lambda a, b: 1.0)
    # 0.3 s de presupuesto: entra la espera de 0.1; después quedan 0.2 y no entra la de 0.2 (+ margen)
    assert len(intentos) == 2


def test_plazo_limita_el_timeout_y_se_agota():
    reloj = Reloj()
    plazo = r.Plazo(1.0, reloj=reloj)
    assert plazo.limitar(0.8) == 0.8
    reloj.t = 0.7
    assert plazo.limitar(0.8) == pytest.approx(0.3)
    reloj.t = 0.99
    with pytest.raises(r.PlazoAgotado):
        plazo.limitar(0.8)


# ------------------------------------------------------------ Bulkhead y Fallback
def test_bulkhead_rechaza_sin_esperar_cuando_esta_lleno():
    b = r.Bulkhead("ruteo", 1)
    with b:
        with pytest.raises(r.BulkheadLleno):
            with b:
                pass
    with b:  # al salir libera el lugar
        pass


def test_eta_estimada_es_razonable():
    # ~5 km en línea recta en Montevideo -> 6.5 km de ruta a 40 km/h ~ 10 min
    seg = r.eta_estimada_seg(-34.90, -56.19, -34.90, -56.135)
    assert 500 < seg < 700
