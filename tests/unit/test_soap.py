"""El servidor SOAP (svc-ruteo) y el cliente zeep (svc-despacho) cumplen el mismo WSDL."""
import importlib.util
from pathlib import Path

import pytest
from lxml import etree
from zeep import Client
from zeep.transports import Transport

RAIZ = Path(__file__).resolve().parents[2]
WSDL = str(RAIZ / "contracts" / "ruteo.wsdl")


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


soap = _cargar("soap", "services/ruteo/app/soap.py")


def _mensaje_zeep(destino, ambulancias):
    """Arma el sobre exactamente como lo enviaría svc-despacho."""
    cliente = Client(WSDL, transport=Transport())
    return etree.tostring(
        cliente.create_message(cliente.service, "CalcularETAs", destino=destino, ambulancia=ambulancias)
    )


def test_el_servidor_entiende_lo_que_manda_el_cliente_zeep():
    xml = _mensaje_zeep({"lat": -34.9, "lon": -56.16}, [{"id": "a1", "lat": -34.88, "lon": -56.17}])
    destino, ambulancias = soap.leer_solicitud(xml)
    assert destino == {"lat": -34.9, "lon": -56.16}
    assert ambulancias == [{"id": "a1", "lat": -34.88, "lon": -56.17}]


def test_la_respuesta_del_servidor_valida_contra_el_esquema_del_wsdl():
    cliente = Client(WSDL, transport=Transport())
    xml = soap.armar_respuesta([("a1", 312), ("a2", 95)])
    sobre = etree.fromstring(xml)
    cuerpo = sobre.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")[0]
    elemento = cliente.get_element("{http://ambulancias.ucu.edu.uy/ruteo}CalcularETAsResponse")
    resp = elemento.parse(cuerpo, cliente.wsdl.types)
    assert [(e.ambulanciaId, e.segundos) for e in resp.eta] == [("a1", 312), ("a2", 95)]


@pytest.mark.parametrize(
    "xml",
    [
        b"no es xml",
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body/></soap:Envelope>',
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>&e;</soap:Body></soap:Envelope>',
    ],
)
def test_solicitudes_invalidas_se_rechazan(xml):
    with pytest.raises(soap.SolicitudInvalida):
        soap.leer_solicitud(xml)


def test_rechaza_coordenadas_fuera_de_rango():
    xml = _mensaje_zeep({"lat": 200, "lon": 0}, [{"id": "a1", "lat": 0, "lon": 0}])
    with pytest.raises(soap.SolicitudInvalida):
        soap.leer_solicitud(xml)


def test_el_fault_es_un_sobre_soap_valido():
    sobre = etree.fromstring(soap.armar_fault("soap:Server", "Proveedor de ruteo no disponible"))
    fault = sobre.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
    assert fault.findtext("faultcode") == "soap:Server"
