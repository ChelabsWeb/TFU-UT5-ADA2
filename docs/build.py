"""Arma el informe completo de la UT5 sobre el .docx original (conserva formato, tablas y figuras)."""
import copy, re, sys
import docx
from docx.shared import Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC, SEQ_PNG, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
RESUMEN_JSON, GRAFICO = sys.argv[4], sys.argv[5]
d = docx.Document(SRC)
body = d.element.body

def text_of(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))

def children():
    return list(body.iterchildren())

def find_heading(prefix):
    for el in children():
        if el.tag == qn('w:p') and text_of(el).strip().startswith(prefix):
            return el
    raise KeyError(prefix)

# ---------- plantillas tomadas del propio documento ----------
H_TPL = copy.deepcopy(find_heading('1.4.'))
paras = d.paragraphs
BODY_TPL = copy.deepcopy(paras[16]._p)          # párrafo normal
BULLET_TPL = copy.deepcopy(paras[19]._p)        # viñeta con negrita inicial
CAPTION_TPL = copy.deepcopy(paras[47]._p)       # pie de figura centrado itálica
TBL_PR = copy.deepcopy(body.xpath('.//w:tbl')[0].find(qn('w:tblPr')))

def strip_runs(p):
    for r in list(p):
        if r.tag != qn('w:pPr'):
            p.remove(r)
    return p

def make_run(text, bold=False, italic=False, highlight=False, rpr_src=None):
    r = OxmlElement('w:r')
    rpr = copy.deepcopy(rpr_src) if rpr_src is not None else OxmlElement('w:rPr')
    for tag in ('w:b', 'w:bCs', 'w:i', 'w:iCs', 'w:highlight'):
        for x in rpr.findall(qn(tag)):
            rpr.remove(x)
    def flag(tag):
        e = OxmlElement(tag); e.set(qn('w:val'), '1'); rpr.insert(0, e)
    if italic: flag('w:iCs'); flag('w:i')
    if bold: flag('w:bCs'); flag('w:b')
    if highlight:
        h = OxmlElement('w:highlight'); h.set(qn('w:val'), 'yellow'); rpr.append(h)
    ORDER = ['rStyle','rFonts','b','bCs','i','iCs','caps','smallCaps','strike','dstrike','outline','shadow','emboss','imprint','noProof','snapToGrid','vanish','webHidden','color','spacing','w','kern','position','sz','szCs','highlight','u','effect','bdr','shd','fitText','vertAlign','rtl','cs','em','lang','eastAsianLayout','specVanish','oMath']
    kids = sorted(list(rpr), key=lambda e: ORDER.index(e.tag.split('}')[1]) if e.tag.split('}')[1] in ORDER else 99)
    for k in list(rpr): rpr.remove(k)
    for k in kids: rpr.append(k)
    r.append(rpr)
    t = OxmlElement('w:t'); t.set(qn('xml:space'), 'preserve'); t.text = text
    r.append(t)
    return r

TOKEN = re.compile(r'(\*\*.+?\*\*|\*.+?\*|\[[A-ZÁÉÍÓÚ]+[^\]]*\])')

def fill(p, text, base_bold=False, rpr_src=None):
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith('**'):
            p.append(make_run(part[2:-2], bold=True, rpr_src=rpr_src))
        elif part.startswith('*') and len(part) > 2:
            p.append(make_run(part[1:-1], bold=base_bold, italic=True, rpr_src=rpr_src))
        elif part.startswith('[') and re.match(r'\[(COMPLETAR|AJUSTAR)', part):
            p.append(make_run(part, bold=True, highlight=True, rpr_src=rpr_src))
        else:
            p.append(make_run(part, bold=base_bold, rpr_src=rpr_src))
    return p

def H(text):
    p = strip_runs(copy.deepcopy(H_TPL))
    rpr = H_TPL.find(qn('w:pPr')).find(qn('w:rPr'))
    p.append(make_run(text, bold=True, rpr_src=rpr))
    return [p]

def P(text):
    return [fill(strip_runs(copy.deepcopy(BODY_TPL)), text)]

def B(text):
    """Viñeta. 'Título: resto' -> título en negrita, como en el resto del documento."""
    p = strip_runs(copy.deepcopy(BULLET_TPL))
    if text.startswith('**'):
        fill(p, text)
    else:
        fill(p, text)
    return [p]

def BL(items):
    out = []
    for it in items:
        out += B(it)
    # espacio después de la lista
    out += P('')
    return out

def CAP(text):
    p = strip_runs(copy.deepcopy(CAPTION_TPL))
    p.append(make_run(text, italic=True))
    return [p]

def IMG(path, width_in=6.0):
    tmp = d.add_paragraph()
    tmp.alignment = 1
    tmp.add_run().add_picture(path, width=Inches(width_in))
    el = tmp._p
    body.remove(el)
    return [el]

def T(rows, widths=None):
    ncols = len(rows[0])
    tbl = d.add_table(rows=len(rows), cols=ncols)
    el = tbl._tbl
    body.remove(el)
    old = el.find(qn('w:tblPr'))
    el.replace(old, copy.deepcopy(TBL_PR))
    total = 8732
    widths = widths or [total // ncols] * ncols
    grid = el.find(qn('w:tblGrid'))
    for gc, w in zip(grid.findall(qn('w:gridCol')), widths):
        gc.set(qn('w:w'), str(w))
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.rows[ri].cells[ci]
            cell.width = Inches(widths[ci] / 1440)
            tcpr = cell._tc.get_or_add_tcPr()
            mar = OxmlElement('w:tcMar')
            for side in ('top', 'left', 'bottom', 'right'):
                m = OxmlElement(f'w:{side}'); m.set(qn('w:w'), '100'); m.set(qn('w:type'), 'dxa'); mar.append(m)
            if ri == 0:
                shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), 'D9E2F3'); tcpr.append(shd)
            tcpr.append(mar)
            p = cell.paragraphs[0]._p
            fill(p, val, base_bold=(ri == 0))
    return [el] + P('')

def insert_after(anchor, elements):
    idx = list(body).index(anchor)
    for i, e in enumerate(elements):
        body.insert(idx + 1 + i, e)

def remove_until_next_heading(anchor, stop_prefixes):
    """Borra lo que hay entre anchor y el próximo heading que empiece con alguno de stop_prefixes."""
    els = children()
    i = els.index(anchor) + 1
    while i < len(els):
        el = els[i]
        if el.tag == qn('w:sectPr'):
            break
        if el.tag == qn('w:p') and any(text_of(el).strip().startswith(s) for s in stop_prefixes):
            break
        body.remove(el)
        i += 1

# ---------- correcciones de texto en todo el documento ----------
FIXES = [
    ('TFU – UT4 · Patrones de arquitectura', 'TFU – UT5 · Estilos de arquitectura'),
    ('Patrones de arquitectura:', 'Estilos de arquitectura'),
    ('1. identificación de estilo arquitectónico:', '1. Identificación del estilo arquitectónico:'),
    ('1.1. microservicios con comunicación asíncrona por eventos:', '1.1. Nuevo estilo: microservicios con comunicación asíncrona por eventos:'),
    ('1.1.2. Por qué microservicios', '1.1.1. Por qué microservicios'),
    ('1.3.1.Diferencias', '1.3.1. Diferencias'),
    ('1.3.3 Compromisos', '1.3.3. Compromisos'),
    ('y de despliega', 'y se despliega'),
    ('Event-Driven es util', 'Event-Driven es útil'),
    ('La forma de los  reportes cambian', 'La forma de los reportes cambia'),
    ('afecte una parte critica', 'afecte una parte crítica'),
    ('Mecanismos de comunicacion', 'Mecanismos de comunicación'),
    ('Un compromiso  que', 'Un compromiso que'),
    ('para la demo. mantiene', 'para la demo. Mantiene'),
    ('Es aceptable para un reporte. no lo sería', 'Es aceptable para un reporte; no lo sería'),
    ('vertical y horizontal pero en bloque.', 'Vertical y horizontal, pero en bloque.'),
]
def apply_fixes(root):
    for p in root.iter(qn('w:p')):
        ts = list(p.iter(qn('w:t')))
        full = ''.join(t.text or '' for t in ts)
        new = full
        for a, b in FIXES:
            new = new.replace(a, b)
        if new != full and ts:
            ts[0].text = new
            for t in ts[1:]:
                t.text = ''
apply_fixes(body)
for s in d.sections:
    for part in (s.header, s.first_page_header, s.even_page_header):
        apply_fixes(part._element)

# ---------- Introducción ----------
intro = find_heading('Introducción')
remove_until_next_heading(intro, ['1. '])
insert_after(intro,
    P('En las unidades anteriores desarrollamos un sistema de gestión de flota de ambulancias: alta y consulta de ambulancias, despacho ante emergencias con cálculo del tiempo estimado de llegada (ETA) a través de un proveedor de ruteo externo, y generación de reportes. En la UT4 el sistema se desplegaba como un monolito en capas detrás de un gateway, con caché y un mock del proveedor de ruteo.')
    + P('En esta unidad evolucionamos esa solución hacia un estilo arquitectónico distribuido: microservicios alineados a capacidades de negocio, con comunicación síncrona (REST y SOAP) en el camino crítico del despacho y comunicación asíncrona por eventos (RabbitMQ) para lo que admite consistencia eventual. Este documento corresponde a la Parte 1: justifica el cambio de estilo, modela la nueva arquitectura, la compara con la anterior, analiza las falacias de la computación distribuida y los patrones con que las abordamos, y define el atributo de calidad que vamos a validar en la Parte 2.')
    + P(''))

# ---------- 1.2.3 Diagrama de secuencia ----------
seq = find_heading('1.2.3.')
remove_until_next_heading(seq, ['1.3.'])
insert_after(seq,
    P('La Figura 3 muestra el caso de uso más significativo del sistema, «Registrar despacho». Incluye el camino normal y el camino de falla del ruteo (circuito abierto o timeout), en el que se aplican los patrones descritos en la sección 1.4.')
    + IMG(SEQ_PNG, 6.2)
    + CAP('Figura 3 – Diagrama de secuencia UML «Registrar despacho», con Circuit Breaker y Fallback (generado a partir de PlantUML con apoyo de IA)')
    + P(''))

# ---------- 1.4 en adelante: se reemplaza todo lo que había ----------
h14 = find_heading('1.4.')
els = children()
for el in els[els.index(h14) + 1:]:
    if el.tag != qn('w:sectPr'):
        body.remove(el)

C3 = [2400, 3000, 3332]
content = []
content += P('Al pasar de un monolito a microservicios, varias llamadas que antes eran invocaciones a funciones en memoria pasan a viajar por la red. Ahí empiezan a importar las falacias de la computación distribuida, es decir, los supuestos falsos que se suelen asumir sin darse cuenta al diseñar un sistema distribuido. Identificamos dos como las más relevantes para nuestra solución, porque afectan directamente al caso de uso crítico (registrar un despacho), y una tercera de menor impacto.')

content += H('1.4.1. Falacia 1: «La red es confiable»')
content += P('**Dónde nos afecta.** Para registrar un despacho, svc-despacho depende de tres llamadas por red: a svc-flota (candidatas), a svc-ruteo (ETAs, que a su vez llama al proveedor externo) y otra vez a svc-flota (reserva). Además, svc-flota y svc-despacho publican eventos hacia RabbitMQ. Cualquiera de esos tramos puede fallar: un servicio caído, un paquete perdido, una respuesta que nunca llega o un proveedor externo que tarda o devuelve error.')
content += P('**Problemas que podría ocasionar si la ignoráramos:**')
content += BL([
    '**Fallas en cascada.** Si el proveedor de ruteo deja de responder y svc-despacho espera sin límite, sus hilos o conexiones quedan bloqueados, el despacho deja de atender pedidos nuevos y la falla de un componente no crítico (ruteo externo) termina tirando la función más crítica del sistema.',
    '**Reservas duplicadas o inconsistentes.** Si la reserva de la ambulancia se ejecuta en svc-flota pero la respuesta se pierde en el camino, svc-despacho no sabe si la reserva se hizo. Si reintenta a ciegas puede reservar dos veces; si no reintenta, puede quedar una ambulancia EN_SERVICIO sin despacho asociado.',
    '**Eventos perdidos.** Si el despacho se guarda en la base pero la publicación del evento falla, svc-reportes nunca se entera y la proyección queda desactualizada para siempre.',
])
content += P('**Decisiones de diseño y patrones aplicados:**')
content += T([
    ['Patrón / decisión', 'Dónde se aplica', 'Qué problema resuelve'],
    ['**Timeout**', 'Todas las llamadas salientes de svc-despacho (flota: 500 ms; ruteo: 800 ms) y de svc-ruteo al proveedor.', 'Ninguna llamada espera indefinidamente; el despacho tiene un presupuesto de tiempo acotado.'],
    ['**Retry con backoff exponencial y jitter**', 'Solo en operaciones idempotentes: GET /ambulancias y CalcularETAs. Máximo 2 reintentos (100 ms y 200 ms + jitter).', 'Absorbe fallas transitorias (un paquete perdido, un contenedor reiniciándose) sin que el operador lo note. El jitter evita que todas las réplicas reintenten al mismo tiempo.'],
    ['**Circuit Breaker**', 'En svc-despacho, alrededor de la llamada SOAP a svc-ruteo. Se abre con el 50 % de fallas en una ventana de 10 llamadas, queda abierto 30 s y luego pasa a semiabierto con una llamada de prueba. Los umbrales se leen del .env (External Configuration Store).', 'Cuando ruteo está caído, svc-despacho deja de llamarlo y falla rápido en lugar de acumular esperas. Le da tiempo al servicio para recuperarse sin recibir más carga.'],
    ['**Fallback (degradación controlada)**', 'Con el circuito abierto o el timeout agotado, svc-despacho calcula una ETA aproximada con la distancia en línea recta (Haversine) y una velocidad urbana promedio, y la marca como eta_estimada = true.', 'El despacho se completa igual. Se prefiere una ETA menos precisa a no despachar: en este dominio, no enviar una ambulancia es mucho peor que enviar la segunda mejor.'],
    ['**Bulkhead**', 'En svc-despacho, un semáforo limita a 10 las llamadas concurrentes a svc-ruteo; svc-flota tiene su propio pool de conexiones.', 'Si ruteo se vuelve lento, a lo sumo 10 hilos quedan esperándolo; el resto usa el fallback enseguida y los hilos siguen libres para hablar con svc-flota.'],
    ['**Reserva idempotente (Idempotency Key)**', 'El PATCH de reserva lleva el id del despacho como Idempotency-Key. svc-flota guarda qué despacho reservó cada ambulancia y, ante la misma clave, devuelve el mismo resultado. La transición sigue siendo condicional (solo DISPONIBLE → EN_SERVICIO).', 'Permite reintentar la reserva de forma segura cuando se pierde la respuesta, sin reservar dos veces ni dejar ambulancias «colgadas».'],
    ['**Mensajería confiable**', 'Colas y exchange durables (quorum queues), mensajes persistentes, publisher confirms, ack manual y Dead Letter Queue con límite de entregas. Consumidor idempotente en svc-reportes. Para producción proponemos además Transactional Outbox (guardar el evento en la misma transacción que el dato y publicarlo después); en la demo no está implementado (ver 2.3).', 'Un evento no se pierde si el broker o svc-reportes se caen; se entrega al menos una vez y, como el consumidor es idempotente, procesarlo dos veces no corrompe la proyección.'],
], C3)
content += P('**Por qué estos patrones y no otros.** El Circuit Breaker y el Fallback se ubican donde está la dependencia más inestable (el proveedor externo, detrás de svc-ruteo) y donde el costo de fallar es más alto (el despacho). El Retry se limita a operaciones idempotentes porque reintentar una operación que modifica estado sin control es justamente lo que genera reservas duplicadas; para la única escritura del camino crítico (la reserva) primero la hacemos idempotente y recién ahí se puede reintentar. Retry y Circuit Breaker se usan juntos y en ese orden: el Retry resuelve las fallas transitorias y el Circuit Breaker evita que los reintentos castiguen a un servicio que ya está caído.')

content += H('1.4.2. Falacia 2: «La latencia es cero»')
content += P('**Dónde nos afecta.** En el monolito, obtener las candidatas y sus ETAs eran llamadas en memoria de microsegundos. Ahora cada paso es un viaje por la red con serialización y, en el caso de ruteo, con mensajes XML más pesados que JSON. Además, svc-ruteo depende del proveedor externo, cuya latencia no controlamos.')
content += P('**Problemas que podría ocasionar si la ignoráramos:**')
content += BL([
    '**Llamadas en cadena (N+1).** Si svc-despacho pidiera la ETA de cada ambulancia por separado, con 10 candidatas haría 10 llamadas SOAP en serie y el tiempo de respuesta crecería linealmente con la flota.',
    '**Tiempo de respuesta impredecible.** En un despacho de emergencia el operador necesita una respuesta en pocos segundos; sumar latencias sin control puede superar ese límite.',
    '**Trabajo pesado en el camino crítico.** Si la generación de reportes fuera síncrona, el cliente quedaría esperando y ocuparía recursos durante toda la generación.',
])
content += P('**Decisiones de diseño y patrones aplicados:**')
content += T([
    ['Patrón / decisión', 'Dónde se aplica', 'Qué problema resuelve'],
    ['**Operación por lote**', 'La operación SOAP CalcularETAs recibe todas las candidatas y un destino, y devuelve todas las ETAs en una sola respuesta.', 'Una sola llamada por despacho en lugar de N. Además compensa el mayor costo de SOAP/XML.'],
    ['**Cache-Aside**', 'svc-flota consulta primero Redis para las ambulancias disponibles (TTL de pocos segundos) y, si no están, va a db-flota y guarda el resultado. Toda reserva o cambio de estado invalida la entrada.', 'Las consultas de flota son las más frecuentes; la caché reduce latencia y carga sobre la base. La invalidación evita ofrecer una ambulancia que ya salió, y la reserva condicional en la base es la garantía final.'],
    ['**Timeouts con presupuesto total**', 'El despacho tiene un presupuesto de 2 s; los timeouts de cada llamada (incluidos los reintentos) están dimensionados para no superarlo.', 'La latencia del despacho queda acotada aunque una dependencia se ponga lenta, porque antes de excederla se usa el fallback.'],
    ['**Asynchronous Request-Reply**', 'POST /reportes responde 202 Accepted con un id; el cliente consulta GET /reportes/{id} hasta que esté listo.', 'El cliente no espera la generación completa y la conexión se libera enseguida.'],
    ['**Queue-Based Load Leveling**', 'Las solicitudes de reportes se encolan en reportes.solicitudes y svc-reportes las consume a su ritmo.', 'Un pico de pedidos no satura el servicio ni compite con el despacho; como la cola es durable, un reporte en curso ya no se pierde si el contenedor se reinicia (problema señalado en la UT4).'],
    ['**Publisher-Subscriber**', 'svc-flota publica AmbulanciaEstadoCambiado y svc-despacho publica DespachoRegistrado; svc-reportes se suscribe.', 'Mantener actualizada la proyección de reportes no agrega llamadas ni latencia al despacho.'],
], C3)
content += P('**Por qué estos patrones.** La regla que seguimos es sacar del camino crítico todo lo que no lo necesita (reportes y proyecciones: Publisher-Subscriber, colas, Asynchronous Request-Reply) y, para lo que sí lo necesita (candidatas y ETAs), minimizar la cantidad de viajes por la red (lote, caché) y acotar el peor caso (timeouts con presupuesto).')

content += H('1.4.3. Falacia 3: «La topología no cambia»')
content += P('Con dos réplicas de svc-despacho y contenedores que pueden reiniciarse o cambiar de IP, no se pueden fijar direcciones en el código. Los servicios se encuentran por nombre con el DNS de Docker y sus URLs se leen de la configuración externa (External Configuration Store). El API Gateway aplica **Gateway Routing** por prefijo y balancea entre las réplicas, y cada servicio expone un endpoint /health (**Health Endpoint Monitoring**) que usan los healthchecks de Docker y el gateway para sacar del balanceo una réplica que no responde.')

content += H('1.4.4. Representación en los modelos')
content += BL([
    '**Diagrama de componentes (Figura 1):** el Circuit Breaker, el Retry y el Bulkhead se ubican en svc-despacho, sobre la dependencia hacia IRuteoService; la caché, como dependencia de svc-flota hacia Redis; la cola de reportes y la DLQ, dentro del Broker.',
    '**Diagrama de despliegue (Figura 2):** las dos réplicas de svc-despacho detrás del gateway y la red aislada del proveedor de ruteo.',
    '**Diagrama de secuencia (Figura 3):** el caso de uso «Registrar despacho» con el camino normal y el de falla del ruteo, donde se ven el Timeout, el Retry, el Circuit Breaker, el Fallback, la caché, la reserva idempotente y la publicación de eventos.',
])

content += H('1.5. Atributo de calidad a mejorar: disponibilidad')
content += H('1.5.1. Atributo seleccionado y justificación')
content += P('Elegimos la **disponibilidad** de la funcionalidad de despacho, entendida como la capacidad del sistema de seguir registrando despachos correctamente aunque alguno de sus componentes falle. Es el atributo más importante del dominio: si el sistema no puede despachar, una emergencia queda sin ambulancia. Y es justamente la debilidad principal del monolito, que tenía un único dominio de falla: si el proceso caía por cualquier motivo (por ejemplo, un reporte que agotara la memoria), se caían todos los endpoints.')
content += P('**Escenario de calidad:**')
content += T([
    ['Elemento', 'Descripción'],
    ['Fuente', 'Falla interna (svc-reportes o una réplica de svc-despacho) o externa (proveedor de ruteo).'],
    ['Estímulo', 'El componente deja de responder o se cae.'],
    ['Artefacto', 'Funcionalidad de registrar despacho (POST /api/despachos).'],
    ['Entorno', 'Operación normal, con carga sostenida de despachos.'],
    ['Respuesta', 'El sistema sigue registrando despachos; si falta el ruteo, lo hace con ETA estimada y lo indica. Cuando el componente vuelve, el sistema se recupera solo.'],
    ['Medida', '≥ 99 % de despachos exitosos durante la falla; p95 de respuesta ≤ 2 s; recuperación automática en ≤ 30 s (tiempo de semiapertura del circuito); 0 reportes ni eventos perdidos.'],
], [2000, 6732])

content += H('1.5.2. Cómo contribuyen las decisiones arquitectónicas')
content += BL([
    '**Separación en servicios (aislamiento de fallas):** reportes corre en su propio proceso y contenedor; que se caiga o se quede sin memoria no afecta al despacho.',
    '**Dos réplicas de svc-despacho detrás del gateway, con health checks:** si una réplica cae, el gateway deriva el tráfico a la otra.',
    '**Circuit Breaker, Fallback, Timeouts y Bulkhead:** la caída o lentitud del proveedor de ruteo se convierte en un despacho con ETA estimada, en lugar de un error o una espera indefinida.',
    '**Comunicación asíncrona con colas durables:** svc-reportes no está en el camino crítico; si se cae, los eventos y solicitudes esperan en la cola y se procesan al volver.',
    '**Reserva idempotente y condicional:** los reintentos no generan estados inconsistentes, por lo que la recuperación ante fallas de red es segura.',
])
content += P('**Compromiso esperado:** en condiciones normales el tiempo de respuesta del despacho va a ser algo mayor que en el monolito, porque se agregan saltos de red. Lo aceptamos a cambio de la disponibilidad y lo vamos a medir explícitamente.')

content += H('1.5.3. Cómo lo vamos a evaluar en la Parte 2')
content += P('**Condiciones de ejecución.** Todo se levanta con Docker Compose en la misma máquina, con límites de recursos fijos por contenedor (cpus y mem_limit) para que las corridas sean comparables. La carga se genera con k6: 20 despachos por segundo durante 60 segundos, con ubicaciones aleatorias, contra el gateway. Cada prueba se corre 3 veces y se informa la mediana. Se registran la tasa de éxito (respuestas 201 sobre el total), la latencia p50 y p95, la cantidad de despachos con eta_estimada = true, el estado del circuito (logs) y el tiempo de recuperación. Cuando es posible, el mismo escenario se ejecuta contra el monolito de la UT4 para comparar.')
content += T([
    ['#', 'Escenario', 'Cómo se provoca', 'Resultado esperado (microservicios)', 'Comparación con la UT4'],
    ['P0', 'Línea base sin fallas', 'Carga normal', '100 % de éxito; p95 algo mayor que en el monolito.', 'Mide el costo en latencia de la distribución (compromiso aceptado).'],
    ['P1', 'Cae el proveedor de ruteo', 'docker stop ruteo-mock en el segundo 15 y docker start en el 45', '≥ 99 % de éxito; el circuito se abre tras las primeras fallas; ETA estimada mientras está abierto; vuelve a ETA exacta en ≤ 30 s desde que el proveedor regresa.', 'Se mide el mismo escenario en el monolito para comparar errores y tiempos de espera.'],
    ['P2', 'Un reporte defectuoso tira el proceso de reportes', 'En el segundo 14 se pide un reporte normal y en el 15 uno defectuoso que mata el proceso que lo genera (simula un OOM)', '100 % de despachos exitosos; el reporte normal se completa y el defectuoso termina en la DLQ tras agotar sus reintentos, sin tirar el servicio en bucle.', 'En el monolito, la caída del proceso deja todos los endpoints sin servicio y el reporte en curso se pierde. Es la comparación central.'],
    ['P3', 'Cae una réplica de svc-despacho', 'docker kill de una de las dos réplicas en el segundo 15 (en el monolito, de la única instancia, que se vuelve a levantar en el 45)', '≥ 99 % de éxito; solo fallan las peticiones en curso en esa réplica.', 'Con una sola API, la caída equivale a 100 % de error hasta que se reinicia.'],
], [500, 1500, 2000, 2532, 2200])
content += P('**Criterio de aceptación.** Consideramos verificada la mejora si en P1, P2 y P3 se cumplen las medidas del escenario de calidad y si en P2 el monolito queda sin servicio mientras los microservicios mantienen el despacho. Si alguna medida no se cumple (por ejemplo, si el p95 supera los 2 s durante P1 por los timeouts previos a la apertura del circuito), lo documentaremos junto con su causa y el ajuste o compromiso correspondiente.')

exec(open(__file__.replace('build.py', 'parte2.py'), encoding='utf-8').read())

# ---------- Uso de IA ----------
content += H('Uso de herramientas de Inteligencia Artificial')
content += H('Herramientas utilizadas')
content += T([
    ['Herramienta', 'Actividades'],
    ['Claude (Anthropic), vía Claude Code', 'Borradores de las secciones 1.4 (falacias y patrones) y 1.5 (atributo de calidad) a partir de la consigna y de nuestro documento; diagrama de secuencia (Figura 3) en PlantUML; redacción de la introducción; implementación de la Parte 2 (código de los servicios, pruebas unitarias, pruebas de carga con k6 y scripts); análisis de los resultados; revisión de consistencia del documento (numeración, títulos, erratas) y armado de la versión final.'],
    ['[COMPLETAR: herramienta usada para las Figuras 1 y 2]', 'Generación de los diagramas de componentes y de despliegue UML a partir de nuestra descripción de los servicios.'],
], [2800, 5932])

content += H('Prompts relevantes')
content += P('Las interacciones completas se incluyen en el Anexo A.')
content += BL([
    '**Interacción 1 – Falacias, patrones y atributo de calidad.** Le pasamos a la IA la consigna de la UT5 y nuestro documento con las secciones 1 a 1.3 terminadas, y le pedimos que completara las secciones de falacias y de atributo de calidad de forma coherente con las decisiones que ya habíamos tomado.',
    '**Interacción 2 – Diagramas UML.** [COMPLETAR con el prompt usado para generar las Figuras 1 y 2.]',
    '**Interacción 3 – Implementación de la Parte 2.** Le pedimos que implementara la arquitectura diseñada y agregara los resultados al documento.',
])

content += H('Análisis crítico')
content += P('**Lo que aceptamos.** Aceptamos las dos falacias principales que propuso («la red es confiable» y «la latencia es cero») porque coinciden con los dos cambios que introduce el nuevo estilo: las llamadas que antes eran en memoria ahora pasan por la red, y el despacho depende de un proveedor externo. Aceptamos Circuit Breaker con Fallback en la llamada a svc-ruteo porque responde al criterio del curso de aplicar el patrón donde está la dependencia inestable y donde el costo de fallar es más alto. Para el fallback, la IA planteó degradar la precisión (ETA estimada) en lugar de rechazar el despacho; lo aceptamos porque en este dominio no enviar una ambulancia es peor que enviar la segunda mejor. También aceptamos limitar el Retry a operaciones idempotentes, ya que reintentar la reserva sin control puede reservar dos veces la misma ambulancia. Por último, aceptamos la disponibilidad como atributo, porque ataca la debilidad principal del monolito (un único dominio de falla), y la comparación central contra la UT4 (caída de reportes).')
content += P('**Lo que cuestionamos o ajustamos.**')
content += BL([
    '**Alcance de los patrones.** La propuesta incluía también Transactional Outbox, Idempotency Key y Bulkhead. Son correctos conceptualmente, pero la consigna advierte que los patrones deben resolver problemas concretos y no aplicarse solo para mostrarlos. Por eso implementamos Timeout, Retry, Circuit Breaker con Fallback, Bulkhead, la reserva idempotente y colas durables con DLQ (cada uno resuelve un problema que aparece en las pruebas o en el código), y dejamos el Outbox como decisión de diseño para producción. Las pruebas confirmaron que ese riesgo es real (sección 2.3).',
    '**Valores numéricos.** Los umbrales propuestos (50 % de fallas en 10 llamadas, 30 s abierto, timeouts de 500/800 ms, presupuesto de 2 s) no salen de mediciones nuestras. Los tomamos como valores iniciales que vamos a calibrar con las pruebas de la Parte 2; por eso están en la configuración externa y no en el código.',
    '**Supuestos sobre los datos.** El fallback por distancia en línea recta supone que svc-flota guarda la ubicación de cada ambulancia, algo que la IA asumió sin verificarlo. Al implementar lo agregamos explícitamente al modelo de svc-flota (lat y lon de cada ambulancia).',
    '**Compromiso de latencia.** La IA señaló que en condiciones normales el despacho va a ser más lento que en el monolito. No lo ocultamos: lo incluimos como prueba P0 para medirlo y presentarlo como compromiso aceptado.',
    '**Línea base reconstruida.** Como no teníamos el código de la UT4, la IA propuso reconstruir un monolito mínimo para comparar. Lo aceptamos con una condición: que tuviera la misma lógica de negocio y los mismos límites de recursos, y que el documento aclarara que es una reconstrucción. Una comparación contra un monolito hecho a medida puede favorecer a la arquitectura nueva; por eso informamos también donde la mejora fue menor de lo esperado (P2).',
    '**Configuración propuesta por la IA que falló.** La primera configuración del gateway, generada por la IA, no cambiaba de réplica ante timeouts de conexión, y P3 dio 94,9 % en lugar del ≥ 99 % esperado. El healthcheck de RabbitMQ que propuso tampoco esperaba al puerto AMQP. Los dos errores aparecieron recién al probar fallas reales, lo que confirma que las recomendaciones hay que validarlas con evidencia.',
    '**Diagramas.** [COMPLETAR: qué corrigieron de los diagramas generados, por ejemplo la notación de interfaces provistas y requeridas, o nombres de nodos y servicios que no coincidían con el texto.]',
])
content += P('En todos los casos, la decisión final se tomó contrastando la propuesta con los conceptos del curso (estilos distribuidos, falacias, catálogo de patrones y escenarios de atributos de calidad). Todos los integrantes revisamos las secciones resultantes.')

content += H('Anexo A – Interacciones con IA')
content += H('Interacción 1 – Falacias, patrones y atributo de calidad (Claude)')
content += P('**Prompt:**')
content += P('*[Se adjuntó la consigna UT5_TFU.pdf y el enlace a este documento.] «La parte 1 está casi terminada, le faltan las falacias y el atributo de calidad. Si alguien puede terminar eso, así mañana es solo el código y la presentación.»*')
content += P('**Respuesta (resumen):**')
content += BL([
    'Identifica que faltan la 1.4 (falacias y patrones) y la 1.5 (atributo de calidad).',
    '**«La red es confiable»** como falacia central, porque el despacho depende de tres llamadas por red. Propone Timeout, Retry solo en operaciones idempotentes, Circuit Breaker hacia svc-ruteo con Fallback (ETA por distancia Haversine marcada como eta_estimada), Bulkhead, reserva con Idempotency-Key y mensajería confiable (colas durables, DLQ, outbox).',
    '**«La latencia es cero»:** operación por lote CalcularETAs, Cache-Aside en Redis, timeouts con un presupuesto total de 2 s, Asynchronous Request-Reply y Queue-Based Load Leveling para los reportes.',
    '**«La topología no cambia»**, con menos detalle: DNS de Docker, External Configuration Store, Gateway Routing y Health Endpoint Monitoring.',
    'Un diagrama de secuencia en PlantUML de «Registrar despacho», con el camino normal y el de circuito abierto.',
    '**Disponibilidad** del despacho como atributo, con un escenario de calidad (≥ 99 % de éxito, p95 ≤ 2 s, recuperación ≤ 30 s) y cuatro pruebas con k6 y docker stop/kill, comparadas contra el monolito de la UT4.',
    'Advierte que el fallback supone que svc-flota guarda la ubicación, y que lo que no se implemente (outbox, idempotency key) conviene presentarlo como diseño propuesto para no prometer algo que el código no tiene. Señala además errores del documento: título duplicado, «2.5» en lugar de «1.5», encabezado de la UT4 y la falta del apartado de IA.',
])
content += H('Interacción 2 – Diagramas UML')
content += P('**Prompt:** [COMPLETAR]')
content += P('**Respuesta:** [COMPLETAR o adjuntar captura]')
content += H('Interacción 3 – Implementación de la Parte 2 (Claude)')
content += P('**Prompt:**')
content += P('*«Ahora hacé el código de la parte 2 y añadilo al doc.»*')
content += P('**Respuesta (resumen):**')
content += BL([
    'Al no encontrar el código de la UT4, pregunta cómo seguir; elegimos construir de cero e incluir un monolito de comparación.',
    'Implementa los cuatro microservicios, el gateway, RabbitMQ con colas quorum y DLQ, Redis y PostgreSQL con un esquema por servicio, la operación SOAP con su WSDL y el cliente zeep, y los patrones de la sección 1.4 escritos a mano con 18 pruebas unitarias.',
    'Escribe las pruebas de carga P0–P3 con k6 y un script que inyecta las fallas y resume los resultados.',
    'Al correrlas, detecta y corrige tres problemas: el puerto 8090 ocupado por otra aplicación (las corridas del monolito daban error), el healthcheck de RabbitMQ y el gateway que no cambiaba de réplica ante timeouts. Repite las corridas afectadas y conserva la corrida fallida como evidencia.',
])
content += H('Anexo B – Resultados por corrida')
_filas = [['Corrida', 'Éxito', 'p50', 'p95', 'ETA estimadas', 'Seg. sin servicio']]
for c in sorted(RES['corridas'], key=lambda c: (c['escenario'], c['arq'], c['corrida'])):
    _filas.append([c['nombre'], _pct(c['tasa_exito']), _ms(c['p50_ms']), _ms(c['p95_ms']), str(c['eta_estimada']), _seg(c['segundos_sin_servicio'])])
content += T(_filas, [2200, 1300, 1300, 1300, 1300, 1332])
content += P('Antes de corregir el gateway, la corrida micro-P3-1 dio 94,9 % de éxito (60 respuestas 504). Se conserva en results/evidencia/ del repositorio.')

insert_after(h14, content)
d.save(OUT)
print('ok', OUT)
