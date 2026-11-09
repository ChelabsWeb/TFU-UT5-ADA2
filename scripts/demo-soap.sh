#!/usr/bin/env bash
# Muestra el contrato WSDL y una invocación SOAP real a svc-ruteo (desde dentro de la red backend).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== WSDL (GET /soap?wsdl) =="
docker compose exec -T svc-despacho-1 python -c "
import urllib.request; print(urllib.request.urlopen('http://svc-ruteo:8000/soap?wsdl').read().decode()[:600], '...')"
echo
echo "== Petición SOAP CalcularETAs =="
cat > /tmp/ut5-soap.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:r="http://ambulancias.ucu.edu.uy/ruteo">
  <soap:Body>
    <r:CalcularETAsRequest>
      <r:destino><r:lat>-34.9011</r:lat><r:lon>-56.1645</r:lon></r:destino>
      <r:ambulancia><r:id>AMB-001</r:id><r:lat>-34.8800</r:lat><r:lon>-56.1500</r:lon></r:ambulancia>
      <r:ambulancia><r:id>AMB-002</r:id><r:lat>-34.9200</r:lat><r:lon>-56.1900</r:lon></r:ambulancia>
    </r:CalcularETAsRequest>
  </soap:Body>
</soap:Envelope>
EOF
cat /tmp/ut5-soap.xml
echo
echo "== Respuesta =="
docker compose exec -T svc-despacho-1 python -c "
import sys, urllib.request
req = urllib.request.Request('http://svc-ruteo:8000/soap', data=sys.stdin.buffer.read(),
      headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': 'http://ambulancias.ucu.edu.uy/ruteo/CalcularETAs'})
print(urllib.request.urlopen(req).read().decode())" < /tmp/ut5-soap.xml
echo
echo "== Consumo desde svc-despacho con el cliente zeep generado del WSDL =="
docker compose exec -T svc-despacho-1 python -c "
from app.clientes import RuteoSoapCliente
c = RuteoSoapCliente('/app/contracts/ruteo.wsdl', 'http://svc-ruteo:8000/soap')
print(c.calcular_etas((-34.9011, -56.1645), [{'id': 'AMB-001', 'lat': -34.88, 'lon': -56.15}], timeout=2))"
