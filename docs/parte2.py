# Se ejecuta dentro de build.py (exec): usa H, P, BL, T, IMG, CAP, make_run, strip_runs, BODY_TPL, content.
import json as _json

RES = _json.load(open(RESUMEN_JSON, encoding='utf-8'))
_G = {(r['arq'], r['escenario']): r for r in RES['resumen']}


def _pct(v):
    return f"{v * 100:.1f} %".replace('.', ',')


def _ms(v):
    return '–' if v is None else f"{round(v)} ms"


def _seg(v):
    return '–' if v is None else (f"{v:.1f} s".replace('.', ',') if v < 10 else f"{round(v)} s")


def CODE(texto):
    """Bloque de código: Consolas 8,5 pt sobre gris claro, un párrafo por línea."""
    out = []
    for linea in texto.strip('\n').split('\n'):
        p = strip_runs(copy.deepcopy(BODY_TPL))
        ppr = p.find(qn('w:pPr'))
        sp = OxmlElement('w:spacing'); sp.set(qn('w:before'), '0'); sp.set(qn('w:after'), '0'); sp.set(qn('w:line'), '240'); sp.set(qn('w:lineRule'), 'auto')
        shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), 'F2F4F7')
        ind = OxmlElement('w:ind'); ind.set(qn('w:left'), '200')
        for e in (shd, sp, ind):
            ppr.append(e)
        rpr = OxmlElement('w:rPr')
        f = OxmlElement('w:rFonts')
        for a in ('ascii', 'hAnsi', 'cs', 'eastAsia'):
            f.set(qn(f'w:{a}'), 'Consolas')
        rpr.append(f)
        for tag in ('w:sz', 'w:szCs'):
            e = OxmlElement(tag); e.set(qn('w:val'), '17'); rpr.append(e)
        p.append(make_run(linea if linea else ' ', rpr_src=rpr))
        out.append(p)
    return out + P('')


m = lambda esc: _G[('micro', esc)]
u = lambda esc: _G[('ut4', esc)]

content += H('Parte 2 – Implementación y validación')
content += P('El código está en el repositorio TFU-UT5-ADA2 [COMPLETAR: enlace al repositorio]. Implementamos la arquitectura completa de la Parte 1 (no solo un caso de uso): los cuatro microservicios, el gateway, el broker y el proveedor de ruteo simulado, con el caso de uso «Registrar despacho» de punta a punta y los reportes asíncronos.')

content += H('2.1. Implementación distribuida')
content += P('Todos los servicios están escritos en Python 3.12 con FastAPI y cada uno es una imagen Docker propia. La comunicación usa el mecanismo que definimos para cada interacción: REST/JSON para consultas y comandos síncronos, SOAP/XML para el cálculo de ETA y AMQP (RabbitMQ) para eventos y colas.')
content += T([
    ['Contenedor', 'Responsabilidad', 'Comunicación', 'Datos'],
    ['gateway (nginx)', 'Único punto de entrada: API key, rate limiting, ruteo por prefijo y balanceo entre las réplicas de despacho', 'HTTP :8080 hacia afuera; REST hacia los servicios', '–'],
    ['svc-despacho-1 y -2', 'Registrar despacho: candidatas, ETAs, reserva, persistencia y evento. Patrones de resiliencia', 'REST (provee y consume), SOAP (consume), AMQP (publica)', 'esquema despacho'],
    ['svc-flota', 'Estado de las ambulancias, reserva condicional e idempotente, caché', 'REST (provee), AMQP (publica)', 'esquema flota + Redis'],
    ['svc-ruteo', 'CalcularETAs por lote; adapta el formato del proveedor externo', 'SOAP 1.1 (provee), REST (consume al proveedor)', 'sin estado'],
    ['svc-reportes', 'Proyección por eventos y reportes asíncronos', 'REST (provee), AMQP (consume)', 'esquema reportes'],
    ['RabbitMQ, Redis, PostgreSQL', 'Broker, caché y base (un esquema y un usuario por servicio)', 'AMQP, RESP, SQL', '–'],
    ['ruteo-mock', 'Proveedor de ruteo externo simulado, con su propio formato y latencia', 'REST, en una red aislada', '–'],
], [1900, 3000, 2232, 1600])
content += P('Las redes de Docker reflejan el diagrama de despliegue: solo el gateway publica un puerto; los servicios viven en una red interna, y el proveedor de ruteo, en otra red a la que solo accede svc-ruteo. Toda la configuración (URLs, timeouts, umbrales del circuito, TTL de caché) sale de un archivo .env por servicio (External Configuration Store).')

content += H('2.2. Migración de REST a SOAP')
content += P('La operación migrada es el **cálculo de ETA**. En la UT4 se exponía como GET /api/ambulancias/{id}/eta con respuesta JSON (la conservamos en el monolito de comparación). Ahora la expone svc-ruteo como operación SOAP 1.1 document/literal **CalcularETAs**, con el contrato contracts/ruteo.wsdl, que también se publica en GET /soap?wsdl. La operación conserva su funcionalidad (tiempo estimado de llegada de una ambulancia a un destino) y, como mejora, pasó a ser por lote: recibe todas las candidatas en un solo mensaje.')
content += P('**Consumo por otro componente.** svc-despacho consume el servicio con zeep, un cliente SOAP que se genera a partir del WSDL: la estructura de los mensajes sale del contrato, no de código escrito a mano. El WSDL se carga desde una copia local para que svc-despacho arranque aunque svc-ruteo esté caído, y la dirección del servicio se toma de la configuración. Si el proveedor no responde, svc-ruteo devuelve un SOAP Fault (soap:Server), que el Circuit Breaker de svc-despacho cuenta como falla.')
content += P('Petición y respuesta reales, capturadas con scripts/demo-soap.sh:')
content += CODE('''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:r="http://ambulancias.ucu.edu.uy/ruteo">
  <soap:Body>
    <r:CalcularETAsRequest>
      <r:destino><r:lat>-34.9011</r:lat><r:lon>-56.1645</r:lon></r:destino>
      <r:ambulancia><r:id>AMB-001</r:id><r:lat>-34.8800</r:lat><r:lon>-56.1500</r:lon></r:ambulancia>
      <r:ambulancia><r:id>AMB-002</r:id><r:lat>-34.9200</r:lat><r:lon>-56.1900</r:lon></r:ambulancia>
    </r:CalcularETAsRequest>
  </soap:Body>
</soap:Envelope>''')
content += CODE('''<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:r="http://ambulancias.ucu.edu.uy/ruteo">
  <soap:Body>
    <r:CalcularETAsResponse>
      <r:eta><r:ambulanciaId>AMB-001</r:ambulanciaId><r:segundos>427</r:segundos></r:eta>
      <r:eta><r:ambulanciaId>AMB-002</r:ambulanciaId><r:segundos>463</r:segundos></r:eta>
    </r:CalcularETAsResponse>
  </soap:Body>
</soap:Envelope>''')
content += P('Además, hay pruebas automáticas que verifican el contrato en los dos sentidos: el servidor entiende el mensaje que arma el cliente zeep a partir del WSDL, y la respuesta del servidor valida contra el esquema del WSDL. El parser XML no resuelve entidades externas, para evitar ataques XXE.')

content += H('2.3. Aplicación de patrones arquitectónicos')
content += P('Implementamos los patrones de la sección 1.4 sin librerías de resiliencia, para que se vea qué hace cada uno (services/despacho/app/resiliencia.py, con 11 pruebas unitarias sobre sus estados y bordes).')
content += T([
    ['Patrón', 'Dónde está', 'Falacia', 'Cómo se demuestra'],
    ['Circuit Breaker + Fallback', 'svc-despacho → svc-ruteo', 'La red es confiable', f"P1: con el proveedor caído el circuito se abre («circuito ruteo: CERRADO -> ABIERTO» en el log) y salen {round(m('P1')['eta_estimada'])} despachos con ETA estimada en vez de errores"],
    ['Timeout con presupuesto + Retry con backoff', 'svc-despacho (todas las llamadas salientes)', 'La red es confiable / la latencia es cero', 'Pruebas unitarias: el retry no reintenta si no queda presupuesto; p95 acotado en todas las corridas'],
    ['Bulkhead', 'svc-despacho → svc-ruteo (máx. 10 concurrentes)', 'La red es confiable', 'Prueba unitaria: rechaza sin esperar cuando está lleno'],
    ['Reserva idempotente', 'svc-flota (Idempotency-Key = id del despacho)', 'La red es confiable', 'UPDATE condicional (solo DISPONIBLE → EN_SERVICIO) y comparación de la clave; si otra réplica ganó la ambulancia, 409 y se prueba la siguiente candidata'],
    ['Cache-Aside', 'svc-flota con Redis', 'La latencia es cero', 'Lecturas de disponibles desde Redis; invalidación en cada cambio de estado'],
    ['Publisher-Subscriber, Queue-Based Load Leveling, Async Request-Reply, DLQ', 'svc-flota, svc-despacho, svc-reportes', 'La latencia es cero / la red es confiable', 'P2: el reporte defectuoso tira svc-reportes 3 veces y termina en la DLQ (FALLIDO); el reporte normal se completa'],
    ['Gateway Routing + Health Endpoint Monitoring', 'gateway y /health de cada servicio', 'La topología no cambia', 'P3: al morir una réplica, el gateway deriva el tráfico a la otra'],
], [2000, 2200, 1700, 2832])
content += P('**Lo que quedó como diseño.** No implementamos Transactional Outbox. Las pruebas mostraron por qué haría falta: en las primeras corridas, RabbitMQ respondía su healthcheck antes de aceptar conexiones y svc-flota perdió los eventos de la carga inicial de ambulancias, que nunca llegaron a la proyección de reportes. Es exactamente la falla de «la red es confiable» que cubre el Outbox. Lo mitigamos con un healthcheck que espera el puerto AMQP, pero el riesgo de perder un evento si el broker cae justo al publicar sigue existiendo, y lo dejamos documentado.')

content += H('2.4. Validación del atributo de calidad')
content += P('**Escenario evaluado:** el de la sección 1.5 (disponibilidad del despacho ante fallas), en los cuatro casos P0 a P3.')
content += P('**Condiciones de ejecución.** Una PC con Windows 11 y Docker Desktop (12 núcleos, 14 GB de RAM), con los mismos límites por contenedor en las dos arquitecturas (1 CPU y 384 MB). k6 genera una carga constante de 20 despachos por segundo durante 60 segundos, con destinos aleatorios en Montevideo. La falla se inyecta en el segundo 15 y, cuando corresponde, se repara en el 45. Cada corrida arranca con el stack recién creado; cada escenario se corrió 3 veces y se informa la mediana. Para comparar usamos un monolito «UT4» reconstruido con la misma lógica de negocio (un proceso, SQLite, reportes en BackgroundTasks, ETA por REST sin Circuit Breaker), porque no contábamos con el código original de la UT4.')
filas = [['Escenario', 'Arquitectura', 'Despachos exitosos', 'p50', 'p95', 'Seg. sin servicio', 'Observaciones']]
obs = {
    ('micro', 'P1'): f"{round(m('P1')['eta_estimada'])} con ETA estimada; ETA exacta de nuevo a {_seg(m('P1')['recuperacion_seg'])} de volver el proveedor",
    ('ut4', 'P1'): 'Sin fallback: todo despacho falla mientras el proveedor no está',
    ('micro', 'P2'): 'Reporte normal LISTO; defectuoso FALLIDO tras 3 reinicios de svc-reportes (DLQ)',
    ('ut4', 'P2'): 'El proceso se reinicia en 1–2 s; los dos reportes quedan PENDIENTE para siempre (perdidos)',
    ('micro', 'P3'): 'Solo fallan los pedidos en curso en la réplica que muere',
    ('ut4', 'P3'): 'Sin servicio hasta que se levanta la instancia (segundo 45)',
}
for esc in ('P0', 'P1', 'P2', 'P3'):
    for arq, nom in (('ut4', 'Monolito UT4'), ('micro', 'Microservicios')):
        r = _G[(arq, esc)]
        filas.append([esc, nom, ('**' if arq == 'micro' else '') + _pct(r['tasa_exito']) + ('**' if arq == 'micro' else ''),
                      _ms(r['p50_ms']), _ms(r['p95_ms']), _seg(r['segundos_sin_servicio']), obs.get((arq, esc), '–')])
content += T(filas, [500, 1250, 1100, 750, 800, 900, 3432])
content += IMG(GRAFICO, 6.3)
content += CAP('Figura 4 – Porcentaje de despachos exitosos por segundo (corrida 1 de cada escenario). Línea discontinua: falla inyectada; punteada: reparación.')

content += P('**Análisis.**')
content += BL([
    f"**P1 – Cae el proveedor de ruteo.** Es la mejora más clara. El monolito despachó el {_pct(u('P1')['tasa_exito'])} de los pedidos y estuvo {_seg(u('P1')['segundos_sin_servicio'])} sin servicio: sin fallback, cada despacho dependía del proveedor. Con microservicios el éxito fue del {_pct(m('P1')['tasa_exito'])}: el circuito se abrió con las primeras fallas y los despachos siguieron saliendo con ETA estimada. Al volver el proveedor, el circuito pasó a semiabierto y la ETA exacta volvió en {_seg(m('P1')['recuperacion_seg'])}.",
    f"**P2 – Reporte defectuoso.** La diferencia en disponibilidad fue menor de lo que esperábamos: el monolito llegó al {_pct(u('P2')['tasa_exito'])} porque el proceso se reinicia en 1–2 s. La diferencia importante es otra: en el monolito se perdieron tanto el reporte defectuoso como el reporte normal que estaba en curso, mientras que con microservicios el despacho no se enteró ({_pct(m('P2')['tasa_exito'])}), el reporte normal se completó y el defectuoso terminó en la DLQ en vez de tirar el servicio en un bucle infinito. Con un reinicio más lento (un OOM real con mucha memoria en uso) la caída del monolito sería más larga.",
    f"**P3 – Cae una instancia.** El monolito, con una sola instancia, quedó {_seg(u('P3')['segundos_sin_servicio'])} sin servicio ({_pct(u('P3')['tasa_exito'])} de éxito). Con dos réplicas el éxito fue del {_pct(m('P3')['tasa_exito'])}. En la primera corrida obtuvimos 94,9 %: el gateway solo cambiaba de réplica ante errores de conexión, no ante timeouts, y cada 10 s volvía a probar la réplica muerta. Agregamos timeout a proxy_next_upstream (seguro aun para POST, porque el pedido nunca llegó a la réplica), bajamos el timeout de conexión a 300 ms y repetimos las tres corridas con la configuración corregida. Es el tipo de problema de configuración que solo aparece probando la falla.",
    f"**P0 – Costo en latencia.** Sin fallas, la distribución cuesta: p50 de {_ms(m('P0')['p50_ms'])} contra {_ms(u('P0')['p50_ms'])}, y p95 de {_ms(m('P0')['p95_ms'])} contra {_ms(u('P0')['p95_ms'])}. Son los saltos de red extra (gateway, flota dos veces y ruteo por SOAP). Es el compromiso que aceptamos en la sección 1.3.3, y queda muy por debajo del presupuesto de 2 s.",
])
max_p95 = max(m(e)['p95_ms'] for e in ('P1', 'P2', 'P3'))
content += P(f"**Verificación del escenario de calidad.** En P1, P2 y P3 los microservicios superaron el 99 % de despachos exitosos, con un p95 máximo de {_ms(max_p95)} (medida: ≤ 2 s) y recuperación automática en menos de 2 s (medida: ≤ 30 s). La medida «0 reportes perdidos» se cumplió en las corridas. La de «0 eventos perdidos» la cumplimos solo después de corregir el healthcheck de RabbitMQ: sin Outbox, depende de que el broker esté disponible en el momento de publicar. El criterio de que en P2 el monolito quedara sin servicio se cumplió solo en parte: perdió pedidos y reportes, pero por un tiempo corto.")
content += P('**Compromisos identificados.** Ganamos disponibilidad en todos los escenarios con falla, a cambio de unos 25 ms más de latencia sin fallas y de una operación más compleja (diez contenedores en lugar de dos). Además, aparecieron dos problemas de configuración que no existían en el monolito (el healthcheck del broker y el reintento del gateway). Tampoco probamos la caída de PostgreSQL: con una sola instancia compartida, sigue siendo un punto único de falla.')

content += H('2.5. Despliegue')
content += P('La aplicación se despliega con Docker Compose y se reproduce en cualquier máquina con Docker:')
content += CODE('''git clone [COMPLETAR: URL del repositorio] && cd TFU-UT5-ADA2
docker compose up -d --build --wait        # microservicios en http://localhost:8080
bash scripts/demo-soap.sh                  # WSDL, petición/respuesta SOAP y consumo con zeep
docker compose -f docker-compose.ut4.yml up -d --build --wait   # monolito UT4 en :18090
bash scripts/todas.sh                      # pruebas P0-P3 (k6) + resumen y gráfico''')
content += P('Los healthchecks de Docker y las dependencias depends_on con condition: service_healthy ordenan el arranque, y docker compose up --wait no termina hasta que todos los servicios están sanos.')
