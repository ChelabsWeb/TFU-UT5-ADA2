"""Lectura y armado de mensajes SOAP 1.1 de la operación CalcularETAs."""
from lxml import etree

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS = "http://ambulancias.ucu.edu.uy/ruteo"
MAX_AMBULANCIAS = 50

# Parser seguro: sin entidades externas ni red (evita XXE).
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=True)


class SolicitudInvalida(Exception):
    pass


def _texto(nodo, ruta: str) -> str:
    valor = nodo.findtext(ruta, namespaces={"t": NS})
    if valor is None or not valor.strip():
        raise SolicitudInvalida(f"falta el elemento {ruta}")
    return valor.strip()


def _num(nodo, ruta: str, minimo: float, maximo: float) -> float:
    try:
        v = float(_texto(nodo, ruta))
    except ValueError as e:
        raise SolicitudInvalida(f"{ruta} no es numérico") from e
    if not minimo <= v <= maximo:
        raise SolicitudInvalida(f"{ruta} fuera de rango")
    return v


def leer_solicitud(xml: bytes) -> tuple[dict, list[dict]]:
    try:
        raiz = etree.fromstring(xml, _PARSER)
    except etree.XMLSyntaxError as e:
        raise SolicitudInvalida(f"XML mal formado: {e}") from e
    cuerpo = raiz.find(f"{{{NS_SOAP}}}Body")
    if cuerpo is None:
        raise SolicitudInvalida("no es un sobre SOAP 1.1")
    pedido = cuerpo.find(f"{{{NS}}}CalcularETAsRequest")
    if pedido is None:
        raise SolicitudInvalida("operación desconocida")
    destino_nodo = pedido.find(f"{{{NS}}}destino")
    if destino_nodo is None:
        raise SolicitudInvalida("falta destino")
    destino = {"lat": _num(destino_nodo, "t:lat", -90, 90), "lon": _num(destino_nodo, "t:lon", -180, 180)}
    ambulancias = []
    for a in pedido.findall(f"{{{NS}}}ambulancia"):
        ambulancias.append(
            {"id": _texto(a, "t:id"), "lat": _num(a, "t:lat", -90, 90), "lon": _num(a, "t:lon", -180, 180)}
        )
    if not 1 <= len(ambulancias) <= MAX_AMBULANCIAS:
        raise SolicitudInvalida(f"se esperan entre 1 y {MAX_AMBULANCIAS} ambulancias")
    return destino, ambulancias


def _sobre():
    sobre = etree.Element(f"{{{NS_SOAP}}}Envelope", nsmap={"soap": NS_SOAP, "r": NS})
    cuerpo = etree.SubElement(sobre, f"{{{NS_SOAP}}}Body")
    return sobre, cuerpo


def armar_respuesta(etas: list[tuple[str, int]]) -> bytes:
    sobre, cuerpo = _sobre()
    resp = etree.SubElement(cuerpo, f"{{{NS}}}CalcularETAsResponse")
    for amb_id, segundos in etas:
        eta = etree.SubElement(resp, f"{{{NS}}}eta")
        etree.SubElement(eta, f"{{{NS}}}ambulanciaId").text = amb_id
        etree.SubElement(eta, f"{{{NS}}}segundos").text = str(int(segundos))
    return etree.tostring(sobre, xml_declaration=True, encoding="UTF-8")


def armar_fault(codigo: str, mensaje: str) -> bytes:
    """codigo: 'soap:Client' (culpa del que llama) o 'soap:Server' (culpa nuestra o del proveedor)."""
    sobre, cuerpo = _sobre()
    fault = etree.SubElement(cuerpo, f"{{{NS_SOAP}}}Fault")
    etree.SubElement(fault, "faultcode").text = codigo
    etree.SubElement(fault, "faultstring").text = mensaje
    return etree.tostring(sobre, xml_declaration=True, encoding="UTF-8")
