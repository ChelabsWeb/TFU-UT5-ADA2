#!/usr/bin/env bash
# Ejecuta un escenario de prueba de disponibilidad sobre una arquitectura.
#   scripts/escenario.sh <micro|ut4> <P0|P1|P2|P3> <corrida>
# Deja en results/<arq>-<esc>-<corrida>.{json,csv,meta.json} el resumen de k6,
# las muestras por request y los tiempos de las fallas inyectadas.
set -euo pipefail
cd "$(dirname "$0")/.."

ARQ=$1 ESC=$2 RUN=$3
DURACION=${DURACION:-60}
RPS=${RPS:-20}
T_FALLA=${T_FALLA:-15}        # segundo en que se inyecta la falla
T_VUELVE=${T_VUELVE:-45}      # segundo en que se repara (P1 y P3 del monolito)
KEY="X-API-Key: clave-demo-ut5"
NOMBRE="$ARQ-$ESC-$RUN"
RES="$(pwd)/results"
mkdir -p "$RES"

if [[ $ARQ == micro ]]; then
  COMPOSE=(docker compose -f docker-compose.yml)
  BASE_HOST=http://localhost:8080; BASE_K6=http://host.docker.internal:8080
  MOCK=ruteo-mock; CAIDA_P3=svc-despacho-2; REPORTES=svc-reportes
else
  COMPOSE=(docker compose -f docker-compose.ut4.yml)
  BASE_HOST=http://localhost:18090; BASE_K6=http://host.docker.internal:18090
  MOCK=ruteo-mock; CAIDA_P3=monolito; REPORTES=monolito
fi

ahora() { python -c 'import time; print(f"{time.time():.3f}")'; }
log() { echo "[$(date +%T)] $NOMBRE: $*"; }

log "levantando stack limpio"
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --wait >/dev/null
sleep 3

WIN_RES=$(cygpath -w "$RES" 2>/dev/null || echo "$RES")
WIN_K6=$(cygpath -w "$(pwd)/tests/k6" 2>/dev/null || echo "$(pwd)/tests/k6")

log "carga: $RPS despachos/s durante ${DURACION}s"
T0=$(ahora)
MSYS_NO_PATHCONV=1 docker run --rm --add-host=host.docker.internal:host-gateway \
  -v "$WIN_RES:/resultados" -v "$WIN_K6:/scripts:ro" grafana/k6:0.55.0 run --quiet \
  --out "csv=/resultados/$NOMBRE.csv" \
  -e BASE=$BASE_K6 -e RPS=$RPS -e DURACION=${DURACION}s -e SALIDA=/resultados/$NOMBRE.json \
  /scripts/despachos.js >/dev/null 2>&1 &
K6=$!

T_INYECCION="" T_REPARACION="" REPORTE_OK="" REPORTE_FALLA=""
esperar_hasta() { python -c "import time; time.sleep(max(0, $T0 + $1 - time.time()))"; }

case $ESC in
  P1)
    esperar_hasta "$T_FALLA";  T_INYECCION=$(ahora); "${COMPOSE[@]}" stop $MOCK >/dev/null 2>&1; log "proveedor de ruteo detenido"
    esperar_hasta "$T_VUELVE"; T_REPARACION=$(ahora); "${COMPOSE[@]}" start $MOCK >/dev/null 2>&1; log "proveedor de ruteo de vuelta"
    ;;
  P2)
    esperar_hasta $((T_FALLA - 1))
    REPORTE_OK=$(curl -s -X POST -H "$KEY" -H 'Content-Type: application/json' -d '{"tipo":"despachos"}' "$BASE_HOST/api/reportes" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])' || true)
    esperar_hasta "$T_FALLA"; T_INYECCION=$(ahora)
    REPORTE_FALLA=$(curl -s -X POST -H "$KEY" -H 'Content-Type: application/json' -d '{"tipo":"falla"}' "$BASE_HOST/api/reportes" | python -c 'import sys,json; print(json.load(sys.stdin)["id"])' || true)
    log "reporte normal $REPORTE_OK + reporte defectuoso $REPORTE_FALLA"
    ;;
  P3)
    esperar_hasta "$T_FALLA"; T_INYECCION=$(ahora); docker kill "$("${COMPOSE[@]}" ps -q $CAIDA_P3)" >/dev/null; log "$CAIDA_P3 muerto"
    if [[ $ARQ == ut4 ]]; then
      esperar_hasta "$T_VUELVE"; T_REPARACION=$(ahora); "${COMPOSE[@]}" start $CAIDA_P3 >/dev/null 2>&1; log "$CAIDA_P3 reiniciado"
    fi
    ;;
esac

wait $K6 || true
log "carga terminada"

# Estado final de lo que importa para el escenario
sleep 12   # que terminen reportes en curso / redeliveries
ESTADO_OK="" ESTADO_FALLA="" DLQ="" REINICIOS=""
if [[ -n $REPORTE_OK ]]; then
  ESTADO_OK=$(curl -s -H "$KEY" "$BASE_HOST/api/reportes/$REPORTE_OK" | python -c 'import sys,json; print(json.load(sys.stdin).get("estado"))' || echo "?")
  ESTADO_FALLA=$(curl -s -H "$KEY" "$BASE_HOST/api/reportes/$REPORTE_FALLA" | python -c 'import sys,json; print(json.load(sys.stdin).get("estado"))' || echo "?")
fi
if [[ $ARQ == micro ]]; then
  DLQ=$("${COMPOSE[@]}" exec -T rabbitmq rabbitmqctl -q list_queues name messages 2>/dev/null | awk '$1=="reportes.solicitudes.dlq"{print $2}')
fi
REINICIOS=$(docker inspect -f '{{.RestartCount}}' "$("${COMPOSE[@]}" ps -aq $REPORTES)" 2>/dev/null || echo "?")
"${COMPOSE[@]}" logs --no-color > "$RES/$NOMBRE.logs.txt" 2>&1 || true

cat > "$RES/$NOMBRE.meta.json" <<EOF
{"arq":"$ARQ","escenario":"$ESC","corrida":$RUN,"t0":$T0,"duracion":$DURACION,"rps":$RPS,
 "t_inyeccion":${T_INYECCION:-null},"t_reparacion":${T_REPARACION:-null},
 "reporte_normal":"$ESTADO_OK","reporte_defectuoso":"$ESTADO_FALLA",
 "dlq":"${DLQ}","reinicios_$REPORTES":"$REINICIOS"}
EOF
log "listo -> results/$NOMBRE.*"
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
