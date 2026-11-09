"""Narración del video en UNA toma (ElevenLabs v3, voz Valeria) + tiempos por frase.

La toma se dice de corrido (frase por frase suena a IA), se transcribe con scribe,
se verifica que diga lo que tiene que decir y se guardan inicio/fin de cada frase.
El video se ajusta a la voz: cada escena arranca cuando arranca su primera frase.

Salida: public/voz/toma.mp3 y src/voz.json
Uso:    ELEVENLABS_API_KEY=... python scripts/voz.py [--nueva]
"""
import difflib
import json
import os
import re
import sys
import unicodedata
import urllib.request
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOZ = "9oPKasc15pfAbMr7N6Gs"  # Valeria (rioplatense)
KEY = os.environ["ELEVENLABS_API_KEY"]

# (escena, lo que se dice, subtítulo). Si el subtítulo es None, es igual a lo dicho.
GUION = [
    ("portada", "Este es el trabajo de la unidad cinco del grupo cuatro: la flota de ambulancias, ahora en microservicios.", None),
    ("antes", "En la unidad cuatro todo vivía en un monolito.", None),
    ("antes", "Si una parte fallaba, se caía el despacho entero.", None),
    ("ahora", "Ahora son cuatro servicios detrás de un gateway: despacho, con dos réplicas, flota, ruteo y reportes.", None),
    ("ahora", "Se hablan por REST, por SOAP y por eventos en Rabbit eme cu, y cada uno tiene su propio esquema en la base.",
     "Se hablan por REST, por SOAP y por eventos en RabbitMQ, y cada uno tiene su propio esquema en la base."),
    ("arriba", "Esto es el sistema corriendo de verdad. Lo levantamos con docker compose, y todos los servicios quedan sanos.", None),
    ("despacho", "Pedimos una ambulancia: despacho elige la más cercana y la reserva.", None),
    ("despacho", "La ETA viene exacta: la calculó el servicio de ruteo.", None),
    ("codigo-soap", "Ese cálculo lo migramos de REST a SOAP.", None),
    ("codigo-soap", "El contrato está escrito en este archivo, y despacho lo consume con un cliente generado desde ese contrato.", None),
    ("soap", "Y esta es la respuesta real: un tiempo, en segundos, para cada ambulancia.", None),
    ("codigo-cb", "Ruteo depende de un proveedor externo, y la red no es confiable.", None),
    ("codigo-cb", "Por eso la llamada pasa por un circuit breaker: si falla la mitad de las últimas llamadas, el circuito se abre.", None),
    ("codigo-cb", "Y mientras está abierto, la ETA se estima por distancia.", None),
    ("cae", "Ahora apagamos el proveedor.", None),
    ("cae", "Los despachos siguen saliendo, con la ETA estimada, y en los logs se ve el circuito abrirse.", None),
    ("vuelve", "Lo volvemos a prender. A los treinta segundos, el circuito prueba de nuevo, se cierra, y la ETA vuelve a ser exacta.", None),
    ("codigo-dlq", "Los reportes van por una cola.", None),
    ("codigo-dlq", "Si un mensaje tira abajo al servicio, Rabbit lo reintenta, y después lo manda a una cola de mensajes muertos.", None),
    ("reporte", "Pedimos un reporte defectuoso, que mata el proceso.", None),
    ("reporte", "El despacho sigue respondiendo, y después de los reintentos, el reporte queda como fallido, sin trancar la cola.", None),
    ("replica", "Por último, matamos una de las dos réplicas de despacho.", None),
    ("replica", "El gateway manda todo a la otra, y los veinte pedidos salen bien.", None),
    ("resultados", "También lo medimos con carga: veinte despachos por segundo, durante un minuto.", None),
    ("resultados", "Con el proveedor caído, el monolito atendió la mitad. Los microservicios, el cien por ciento.", None),
    ("resultados", "Y si se cae una instancia: cuarenta y ocho por ciento, contra casi cien.", None),
    ("cierre", "El costo es un poco más de latencia, y más piezas para operar.", None),
    ("cierre", "A cambio, el despacho sigue andando cuando algo falla.", None),
]


def norm(s):
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, method="POST", headers={"xi-api-key": KEY, **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def tts(texto, ruta):
    body = {"text": texto, "model_id": "eleven_v3", "voice_settings": {"stability": 0.5}}
    audio = post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}?output_format=mp3_44100_128",
                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    open(ruta, "wb").write(audio)


def stt(ruta):
    b = uuid.uuid4().hex
    partes = []
    for k, v in {"model_id": "scribe_v1", "language_code": "es", "timestamps_granularity": "word"}.items():
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="t.mp3"\r\n'
                  f"Content-Type: audio/mpeg\r\n\r\n".encode() + open(ruta, "rb").read() + b"\r\n")
    partes.append(f"--{b}--\r\n".encode())
    out = post("https://api.elevenlabs.io/v1/speech-to-text", b"".join(partes),
               {"Content-Type": f"multipart/form-data; boundary={b}"})
    return [w for w in json.loads(out)["words"] if w.get("type") == "word"]


def cortar(lineas, palabras):
    esp, limites = "", []
    for l in lineas:
        limites.append(len(esp))
        esp += norm(l)
    oido, duenio = "", []
    for i, w in enumerate(palabras):
        n = norm(w["text"])
        oido += n
        duenio += [i] * len(n)
    sm = difflib.SequenceMatcher(None, esp, oido, autojunk=False)
    m = {}
    for a, b2, n in sm.get_matching_blocks():
        for k in range(n):
            m[a + k] = b2 + k
    tramos = []
    for i, ini in enumerate(limites):
        fin = limites[i + 1] if i + 1 < len(limites) else len(esp)
        hit = [m[c] for c in range(ini, fin) if c in m]
        tramos.append((palabras[duenio[hit[0]]]["start"], palabras[duenio[hit[-1]]]["end"]))
    return tramos, sm.ratio()


# lo que scribe escribe distinto sin que esté mal dicho
IGUAL = {"rabbitmq": "rabbitemecu", "eta": "eta", "soap": "soap"}


def mal_dichas(lineas, palabras):
    esp = [norm(w) for l in lineas for w in l.split()]
    esp = [w for w in esp if w]
    oido = [norm(w["text"]) for w in palabras]
    malas = []
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, esp, oido, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            g = oido[b0:b1]
            if any(re.search(r"\d", x) for x in g):  # «cinco» → «5» no cuenta
                continue
            if "".join(esp[a0:a1]) == "".join(g) or {"rabbit", "eme", "cu"} & set(esp[a0:a1]):
                continue
            malas.append((esp[a0:a1], g))
    return malas


carpeta = os.path.join(RAIZ, "public", "voz")
os.makedirs(carpeta, exist_ok=True)
toma = os.path.join(carpeta, "toma.mp3")
if "--nueva" in sys.argv and os.path.exists(toma):
    os.remove(toma)
lineas = [g[1] for g in GUION]
texto = "[tono claro y tranquilo, explicando] " + " ".join(lineas)
print(f"{len(texto)} caracteres")
for intento in range(4):
    if not os.path.exists(toma):
        tts(texto, toma)
    palabras = stt(toma)
    tramos, ratio = cortar(lineas, palabras)
    malas = mal_dichas(lineas, palabras)
    print(f"toma {intento}: parecido {ratio:.3f}, mal dichas: {malas}")
    if ratio > 0.93 and len(malas) <= 2:
        break
    os.rename(toma, os.path.join(carpeta, f"descartada-{intento}.mp3"))
else:
    sys.exit("ninguna toma pasó la verificación")

salida = {
    "frases": [
        {"escena": e, "texto": sub or dicho, "a": round(a, 3), "b": round(b, 3)}
        for (e, dicho, sub), (a, b) in zip(GUION, tramos)
    ],
    "fin": round(palabras[-1]["end"], 3),
    "palabras": [[w["text"], round(w["start"], 3), round(w["end"], 3)] for w in palabras],
}
json.dump(salida, open(os.path.join(RAIZ, "src", "voz.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for f in salida["frases"]:
    print(f"{f['a']:7.2f} {f['b']:7.2f}  {f['escena']:12} {f['texto'][:60]}")
