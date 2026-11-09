#!/usr/bin/env bash
# Prueba de humo: levanta el stack y ejercita cada camino una vez.
set -uo pipefail
cd "$(dirname "$0")/.."
K="X-API-Key: clave-demo-ut5"; J="Content-Type: application/json"
docker compose up -d --wait 2>&1 | tail -3
echo "--- despacho"
curl -s -X POST localhost:8080/api/despachos -H "$K" -H "$J" -d '{"lat":-34.90,"lon":-56.16}'; echo
echo "--- sin API key"; curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/api/ambulancias
echo "--- ambulancias disponibles"; curl -s localhost:8080/api/ambulancias?estado=DISPONIBLE -H "$K" | python -c 'import sys,json; print(len(json.load(sys.stdin)))'
echo "--- reporte"
R=$(curl -s -X POST localhost:8080/api/reportes -H "$K" -H "$J" -d '{"tipo":"despachos"}'); echo "$R"
ID=$(echo "$R" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])'); sleep 5
curl -s localhost:8080/api/reportes/$ID -H "$K"; echo
echo "--- SOAP"; bash scripts/demo-soap.sh 2>&1 | tail -12
echo "--- proveedor caído"
docker compose stop ruteo-mock >/dev/null 2>&1
for i in 1 2 3 4 5 6 7 8; do curl -s -X POST localhost:8080/api/despachos -H "$K" -H "$J" -d '{"lat":-34.90,"lon":-56.16}' | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("eta_estimada"), d.get("replica"), d.get("detail",""))'; done
docker compose logs svc-despacho-1 svc-despacho-2 2>&1 | grep -i circuito | tail -4
docker compose start ruteo-mock >/dev/null 2>&1
echo "--- reporte defectuoso"
curl -s -X POST localhost:8080/api/reportes -H "$K" -H "$J" -d '{"tipo":"falla"}'; echo
sleep 2; curl -s -o /dev/null -w 'despacho durante la caída de reportes: %{http_code}\n' -X POST localhost:8080/api/despachos -H "$K" -H "$J" -d '{"lat":-34.90,"lon":-56.16}'
sleep 25
docker compose exec -T rabbitmq rabbitmqctl -q list_queues name messages 2>/dev/null
docker inspect -f 'reinicios svc-reportes: {{.RestartCount}}' $(docker compose ps -aq svc-reportes)
docker compose ps --format '{{.Name}} {{.Status}}'
