#!/usr/bin/env bash
# Corre todos los escenarios (P0-P3) sobre las dos arquitecturas, CORRIDAS veces cada uno.
set -uo pipefail
cd "$(dirname "$0")/.."
CORRIDAS=${CORRIDAS:-3}
for esc in ${ESCENARIOS:-P0 P1 P2 P3}; do
  for arq in ${ARQUITECTURAS:-micro ut4}; do
    for i in $(seq 1 "$CORRIDAS"); do
      bash scripts/escenario.sh "$arq" "$esc" "$i" || echo "!! $arq $esc $i falló"
    done
  done
done
PY=${PY:-python}; [[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe; [[ -x .venv/bin/python ]] && PY=.venv/bin/python
"$PY" scripts/resumir.py
