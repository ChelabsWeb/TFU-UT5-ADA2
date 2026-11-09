"""Corre la demo contra el stack levantado y guarda cada comando con su salida REAL.

El video (video/src/demo.json) reproduce esta grabación: nada de la terminal está inventado.
Uso:  python scripts/grabar-demo.py            (con `docker compose up -d --wait` hecho)
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "video" / "src" / "demo.json"
H = "-H 'X-API-Key: clave-demo-ut5' -H 'Content-Type: application/json'"
DESPACHO = f"curl -s -X POST localhost:8080/api/despachos {H} -d '{{\"lat\":-34.90,\"lon\":-56.16}}'"


def sh(cmd: str) -> str:
    r = subprocess.run(["bash", "-c", cmd], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    return (r.stdout + r.stderr).rstrip()


def bonito(texto: str, campos: list[str] | None = None) -> str:
    d = json.loads(texto)
    if campos:
        d = {k: d[k] for k in campos if k in d}
    return json.dumps(d, indent=2, ensure_ascii=False)


pasos: list[dict] = []


def paso(escena: str, mostrar: str, salida: str, nota: str | None = None) -> None:
    pasos.append({"escena": escena, "cmd": mostrar, "out": salida, "nota": nota, "t": datetime.now().strftime("%H:%M:%S")})
    print(f"$ {mostrar}\n{salida}\n")


CAMPOS = ["ambulancia_id", "eta_seg", "eta_estimada", "replica"]

# 1 · el sistema levantado
estado = sh("docker compose ps --format '{{.Service}}\\t{{.Status}}' | sort")
paso("arriba", "docker compose ps", estado)

# 2 · un despacho normal (ETA exacta por SOAP)
paso("despacho", "curl -X POST localhost:8080/api/despachos -d '{\"lat\":-34.90,\"lon\":-56.16}'", bonito(sh(DESPACHO), CAMPOS))

# 3 · SOAP por dentro: la respuesta real de svc-ruteo
soap = sh("bash scripts/demo-soap.sh 2>/dev/null | sed -n '/== Respuesta ==/,/== Consumo/p' | sed '1d;$d'")
soap = soap.replace("><", ">\n<")
paso("soap", "POST svc-ruteo:8000/soap   (CalcularETAs)", soap)

# 4 · cae el proveedor
t_cae = time.time()
paso("cae", "docker compose stop ruteo-mock", sh("docker compose stop ruteo-mock"))
lineas = []
for _ in range(10):
    cuerpo, cod = sh(DESPACHO + " -w '\\n%{http_code}'").rsplit("\n", 1)
    d = json.loads(cuerpo)
    lineas.append(f"{cod}  {d['ambulancia_id'][:8]}…  eta={d['eta_seg']:>4}s  eta_estimada={str(d['eta_estimada']).lower()}  {d['replica']}")
paso("cae", "for i in $(seq 10); do curl -X POST .../api/despachos; done", "\n".join(lineas))
logs = sh(f"docker compose logs --since {int(time.time()-t_cae)+2}s --no-log-prefix svc-despacho-1 svc-despacho-2 2>&1 | grep -i 'circuito ruteo' | sort | tail -2")
paso("cae", "docker compose logs svc-despacho | grep circuito | sort", logs)

# 5 · vuelve el proveedor: el circuito se cierra solo
t_vuelve = time.time()
paso("vuelve", "docker compose start ruteo-mock", sh("docker compose start ruteo-mock"))
time.sleep(32)  # abierto_seg = 30
for _ in range(6):
    sh(DESPACHO)
paso("vuelve", "curl -X POST localhost:8080/api/despachos ...", bonito(sh(DESPACHO), CAMPOS), nota="30 s después")
logs = sh(f"docker compose logs --since {int(time.time()-t_vuelve)+2}s --no-log-prefix svc-despacho-1 svc-despacho-2 2>&1 | grep -i 'circuito ruteo' | sort | tail -4")
paso("vuelve", "docker compose logs svc-despacho | grep circuito | sort", logs)

# 6 · reporte defectuoso: muere svc-reportes, el despacho sigue
REINICIOS = "docker inspect -f '{{.RestartCount}}' $(docker compose ps -aq svc-reportes)"
antes = int(sh(REINICIOS))
r = json.loads(sh(f"curl -s -X POST localhost:8080/api/reportes {H} -d '{{\"tipo\":\"falla\"}}'"))
paso("reporte", "curl -X POST localhost:8080/api/reportes -d '{\"tipo\":\"falla\"}'", json.dumps(r, indent=2, ensure_ascii=False))
time.sleep(2)
cod = sh(f"curl -s -o /dev/null -w '%{{http_code}}' -X POST localhost:8080/api/despachos {H} -d '{{\"lat\":-34.90,\"lon\":-56.16}}'")
paso("reporte", "curl -X POST .../api/despachos   # mientras reportes se cae", f"HTTP {cod}")
est = {}
for _ in range(40):
    try:
        est = json.loads(sh(f"curl -s localhost:8080/api/reportes/{r['id']} {H}"))
    except json.JSONDecodeError:  # 502 del gateway mientras svc-reportes reinicia
        est = {}
    if est.get("estado") == "FALLIDO":
        break
    time.sleep(2)
reinicios = str(int(sh(REINICIOS)) - antes)
paso("reporte", f"curl localhost:8080/api/reportes/{r['id'][:8]}…", json.dumps({k: est[k] for k in ("id", "tipo", "estado") if k in est}, indent=2, ensure_ascii=False))
paso("reporte", "docker inspect -f '{{.RestartCount}}' svc-reportes   # reinicios en esta prueba", reinicios)

# 7 · cae una réplica de despacho
sh("docker compose up -d --wait svc-reportes >/dev/null 2>&1")
paso("replica", "docker kill svc-despacho-2", sh("docker kill $(docker compose ps -q svc-despacho-2) >/dev/null && echo svc-despacho-2"))
codigos = sh(
    f"for i in $(seq 20); do curl -s -o /dev/null -w '%{{http_code}} ' -X POST localhost:8080/api/despachos {H} "
    f"-d '{{\"lat\":-34.90,\"lon\":-56.16}}'; done"
)
paso("replica", "for i in $(seq 20); do curl -X POST .../api/despachos; done", codigos)
sh("docker compose up -d --wait svc-despacho-2 >/dev/null 2>&1")

SALIDA.write_text(json.dumps(pasos, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"guardado {SALIDA} ({len(pasos)} pasos)")
