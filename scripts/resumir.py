"""Resume las corridas de results/ en una tabla (results/resumen.md + .json) y un gráfico.

Uso: python scripts/resumir.py
Para cada corrida lee el CSV de k6 (una fila por request) y el meta.json del escenario.
"""
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results"
NOMBRES = {"P0": "Línea base sin fallas", "P1": "Cae el proveedor de ruteo",
           "P2": "Reporte defectuoso tira reportes", "P3": "Cae una instancia de despacho"}


def percentil(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    i = int(k)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (k - i)


def analizar(nombre):
    meta = json.loads((RES / f"{nombre}.meta.json").read_text())
    durs_ok, durs_todas, por_seg, estimadas, exactas = [], [], defaultdict(lambda: [0, 0]), [], []
    with open(RES / f"{nombre}.csv", newline="") as f:
        for fila in csv.DictReader(f):
            m, t = fila["metric_name"], float(fila["timestamp"])
            if m == "http_req_duration":
                v = float(fila["metric_value"])
                ok = fila["status"] == "201"
                durs_todas.append(v)
                if ok:
                    durs_ok.append(v)
                s = int(t - meta["t0"])
                por_seg[s][0] += 1
                por_seg[s][1] += ok
            elif m == "eta_estimada":
                estimadas.append(t)
            elif m == "eta_exacta":
                exactas.append(t)
    total = len(durs_todas)
    exitos = len(durs_ok)
    # segundos «caídos»: menos de la mitad de los despachos de ese segundo salieron bien
    segs = sorted(s for s in por_seg if 0 <= s < meta["duracion"])
    caidos = [s for s in segs if por_seg[s][1] / por_seg[s][0] < 0.5]
    racha = mejor = 0
    for s in segs:
        racha = racha + 1 if s in caidos else 0
        mejor = max(mejor, racha)
    r = {
        "nombre": nombre, **meta,
        "requests": total, "exitosos": exitos, "tasa_exito": exitos / total if total else 0,
        "p50_ms": percentil(durs_ok, 0.5), "p95_ms": percentil(durs_ok, 0.95),
        "p95_todas_ms": percentil(durs_todas, 0.95),
        "eta_estimada": len(estimadas), "eta_exacta": len(exactas),
        "segundos_sin_servicio": mejor,
        "serie": [[s, por_seg[s][1] / por_seg[s][0]] for s in segs],
    }
    if meta.get("t_reparacion"):
        tr = meta["t_reparacion"]
        if meta["arq"] == "micro":
            ult = [t for t in estimadas if t >= tr]
            r["recuperacion_seg"] = (max(ult) - tr) if ult else 0.0
        else:
            prim = [s for s in segs if s >= tr - meta["t0"] and por_seg[s][1] > 0]
            r["recuperacion_seg"] = (prim[0] - (tr - meta["t0"])) if prim else None
    return r


def mediana(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def main():
    corridas = [analizar(p.name[: -len(".meta.json")]) for p in sorted(RES.glob("*.meta.json"))]
    grupos = defaultdict(list)
    for c in corridas:
        grupos[(c["arq"], c["escenario"])].append(c)

    resumen = []
    for (arq, esc), cs in sorted(grupos.items(), key=lambda kv: (kv[0][1], kv[0][0] != "ut4")):
        resumen.append({
            "arq": arq, "escenario": esc, "corridas": len(cs),
            "tasa_exito": mediana([c["tasa_exito"] for c in cs]),
            "p50_ms": mediana([c["p50_ms"] for c in cs]), "p95_ms": mediana([c["p95_ms"] for c in cs]),
            "eta_estimada": mediana([c["eta_estimada"] for c in cs]),
            "segundos_sin_servicio": mediana([c["segundos_sin_servicio"] for c in cs]),
            "recuperacion_seg": mediana([c.get("recuperacion_seg") for c in cs]),
            "reporte_normal": sorted({c.get("reporte_normal") for c in cs} - {""}),
            "reporte_defectuoso": sorted({c.get("reporte_defectuoso") for c in cs} - {""}),
            "dlq": sorted({c.get("dlq") for c in cs} - {"", None}),
        })
    (RES / "resumen.json").write_text(json.dumps({"resumen": resumen, "corridas": [
        {k: v for k, v in c.items() if k != "serie"} for c in corridas]}, indent=2, ensure_ascii=False))

    def fmt(v, suf="", dec=0):
        return "–" if v is None else f"{v:.{dec}f}{suf}"

    lineas = ["| Escenario | Arquitectura | Éxito | p50 | p95 | ETA estimadas | Seg. sin servicio | Recuperación | Reportes |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in resumen:
        rep = ""
        if r["reporte_normal"]:
            rep = f"normal: {'/'.join(r['reporte_normal'])}; defectuoso: {'/'.join(r['reporte_defectuoso'])}"
            if r["dlq"]:
                rep += f"; DLQ: {'/'.join(r['dlq'])}"
        lineas.append(
            f"| {r['escenario']} {NOMBRES[r['escenario']]} | {'Microservicios' if r['arq'] == 'micro' else 'Monolito UT4'} "
            f"| {fmt(r['tasa_exito'] * 100, ' %', 1)} | {fmt(r['p50_ms'], ' ms')} | {fmt(r['p95_ms'], ' ms')} "
            f"| {fmt(r['eta_estimada'])} | {fmt(r['segundos_sin_servicio'], ' s')} | {fmt(r['recuperacion_seg'], ' s', 1)} | {rep} |"
        )
    (RES / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(sin matplotlib: no se genera el gráfico)")
        return
    fig, ejes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for eje, esc in zip(ejes, ("P1", "P2", "P3")):
        for arq, color, etiqueta in (("ut4", "#c0392b", "Monolito UT4"), ("micro", "#1f6fb2", "Microservicios")):
            cs = sorted(grupos.get((arq, esc), []), key=lambda c: c["corrida"])
            if not cs:
                continue
            c = cs[0]
            xs, ys = zip(*c["serie"]) if c["serie"] else ([], [])
            eje.plot(xs, [y * 100 for y in ys], color=color, label=etiqueta, linewidth=2)
            if c.get("t_inyeccion"):
                eje.axvline(c["t_inyeccion"] - c["t0"], color="#555", linestyle="--", linewidth=1)
            if c.get("t_reparacion"):
                eje.axvline(c["t_reparacion"] - c["t0"], color="#555", linestyle=":", linewidth=1)
        eje.set_title(f"{esc}: {NOMBRES[esc]}", fontsize=10)
        eje.set_xlabel("segundo de la prueba")
        eje.set_ylim(-5, 105)
        eje.grid(alpha=0.3)
    ejes[0].set_ylabel("% de despachos exitosos")
    ejes[0].legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(RES / "disponibilidad.png", dpi=150)
    print("gráfico -> results/disponibilidad.png")


if __name__ == "__main__":
    main()
