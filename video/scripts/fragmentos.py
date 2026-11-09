"""Copia al video fragmentos REALES del código (por rango de líneas) -> src/codigo.json."""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# id: (archivo, desde, hasta)  — líneas 1-indexadas, inclusive
FRAGMENTOS = {
    "wsdl": ("contracts/ruteo.wsdl", 41, 56),
    "zeep": ("services/despacho/app/clientes.py", 76, 82),
    "cb": ("services/despacho/app/resiliencia.py", 143, 160),
    "fallback": ("services/despacho/app/main.py", 115, 131),
    "cola": ("services/reportes/app/main.py", 58, 70),
    "falla": ("services/reportes/app/main.py", 116, 123),
}

salida = {}
for k, (ruta, a, b) in FRAGMENTOS.items():
    lineas = open(os.path.join(RAIZ, ruta), encoding="utf-8").read().splitlines()
    salida[k] = {"archivo": ruta, "desde": a, "lineas": lineas[a - 1 : b]}
    print(f"--- {k} {ruta}:{a}-{b}")
    for i, l in enumerate(lineas[a - 1 : b]):
        print(f"{a + i:4} {l}")
json.dump(salida, open(os.path.join(RAIZ, "video", "src", "codigo.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
