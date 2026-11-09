# TFU UT5 · ADA II · Grupo 4 — Flota de ambulancias en microservicios

Evolución del sistema de flota de ambulancias de las unidades anteriores: de un **monolito en capas** (UT4) a **microservicios con comunicación asíncrona por eventos**.

## Arquitectura

```
                 ┌──────────────── frontend ────────────────┐
  cliente ──────▶│ gateway (nginx :8080)  API key · rate limit · ruteo por prefijo
                 └──────┬────────────┬──────────────┬───────┘
                        │ backend (red interna)     │
     /api/despachos     │            │ /api/ambulancias          /api/reportes
   ┌────────────────────▼─┐   ┌──────▼──────┐               ┌──────▼───────┐
   │ svc-despacho-1 / -2  │──▶│  svc-flota  │──▶ Redis      │ svc-reportes │
   │ CB · Retry · Timeout │   │ Cache-Aside │               │ proyección   │
   │ Bulkhead · Fallback  │   │ reserva     │               │ por eventos  │
   └───────┬──────────┬───┘   │ idempotente │               └──────▲───────┘
      SOAP │          │       └──────┬──────┘                      │ AMQP
   ┌───────▼──────┐   │              └──── flota.eventos ──▶ RabbitMQ (colas quorum + DLQ)
   │  svc-ruteo   │   └──── DespachoRegistrado ─────────────▶
   │ (WSDL, ACL)  │
   └───────┬──────┘ red «proveedor» (interna)
   ┌───────▼──────┐
   │  ruteo-mock  │  proveedor externo simulado
   └──────────────┘
          PostgreSQL: un esquema y un usuario por servicio (Database per Service)
```

| Servicio | Responsabilidad | Interfaz |
|---|---|---|
| `svc-despacho` (×2) | Caso de uso crítico: elegir y reservar la ambulancia con menor ETA | REST `POST /despachos`, `GET /despachos/{id}` |
| `svc-flota` | Dueño del estado de las ambulancias; reserva condicional e idempotente | REST `/ambulancias`; publica `AmbulanciaEstadoCambiado` |
| `svc-ruteo` | ETAs por lote; adapta el formato del proveedor externo | **SOAP 1.1** `CalcularETAs` ([WSDL](contracts/ruteo.wsdl)) |
| `svc-reportes` | Proyección por eventos + reportes asíncronos | REST `POST /reportes` (202), `GET /reportes/{id}` |

### Migración REST → SOAP

La operación **cálculo de ETA** se exponía en la UT4 como `GET /api/ambulancias/{id}/eta` (JSON). Ahora la expone `svc-ruteo` por SOAP con el contrato [`contracts/ruteo.wsdl`](contracts/ruteo.wsdl), y la consume `svc-despacho` con un cliente **zeep** generado desde ese WSDL ([`clientes.py`](services/despacho/app/clientes.py)). Como mejora, la operación pasó a ser **por lote** (todas las candidatas en un mensaje). Los demás servicios siguen en REST.

### Patrones (y la falacia que abordan)

| Patrón | Dónde | Falacia |
|---|---|---|
| Timeout con presupuesto total (2 s) | [`resiliencia.py`](services/despacho/app/resiliencia.py) `Plazo` | La red es confiable / la latencia es cero |
| Retry con backoff + jitter (solo idempotentes) | `reintentar` | La red es confiable |
| **Circuit Breaker** + **Fallback** (ETA por Haversine, `eta_estimada=true`) | `CircuitBreaker`, `_obtener_etas` | La red es confiable |
| Bulkhead (máx. 10 llamadas concurrentes a ruteo) | `Bulkhead` | La red es confiable |
| Reserva idempotente (`Idempotency-Key`) | [`flota/main.py`](services/flota/app/main.py) | La red es confiable |
| Cache-Aside (Redis) | `svc-flota` | La latencia es cero |
| Publisher-Subscriber, Queue-Based Load Leveling, Async Request-Reply, DLQ | [`reportes/main.py`](services/reportes/app/main.py) | La red es confiable / la latencia es cero |
| Gateway Routing, Health Endpoint Monitoring, External Configuration Store | `gateway/`, `/health`, `config/*.env` | La topología no cambia |

## Cómo correrlo

Requisitos: Docker (con Compose v2).

```bash
docker compose up -d --build --wait          # microservicios -> http://localhost:8080
curl -X POST localhost:8080/api/despachos \
     -H 'X-API-Key: clave-demo-ut5' -H 'Content-Type: application/json' \
     -d '{"lat": -34.90, "lon": -56.16}'
bash scripts/demo-soap.sh                     # WSDL + petición/respuesta SOAP + consumo con zeep
```

Consola de RabbitMQ: http://localhost:15672 (guest / guest).

Monolito de comparación (baseline UT4): `docker compose -f docker-compose.ut4.yml up -d --build --wait` → http://localhost:18090.

### Ver los patrones funcionando

```bash
docker compose stop ruteo-mock                # el circuito se abre y los despachos salen con eta_estimada=true
docker compose logs svc-despacho-1 | grep circuito
docker compose start ruteo-mock               # a los 30 s el circuito pasa a SEMIABIERTO y se cierra
curl -X POST localhost:8080/api/reportes -H 'X-API-Key: clave-demo-ut5' \
     -H 'Content-Type: application/json' -d '{"tipo":"falla"}'   # tira svc-reportes; el despacho sigue
```

## Pruebas

```bash
python -m pytest tests/unit                   # 18 tests: CB, Retry, Plazo, Bulkhead, Fallback, SOAP vs WSDL
bash scripts/todas.sh                         # P0-P3 sobre las dos arquitecturas (k6, ~45 min)
python scripts/resumir.py                     # results/resumen.md + results/disponibilidad.png
```

| # | Escenario | Falla inyectada |
|---|---|---|
| P0 | Línea base | ninguna |
| P1 | Cae el proveedor de ruteo | `stop ruteo-mock` en el s 15, `start` en el s 45 |
| P2 | Reporte defectuoso | en el s 15 se pide un reporte que mata el proceso que lo genera |
| P3 | Cae una instancia | `docker kill` de `svc-despacho-2` (o del monolito) en el s 15 |

Carga: 20 despachos/s durante 60 s, 3 corridas por escenario, mediana. Mismos límites de CPU y memoria (1 CPU, 384 MB) por contenedor en las dos arquitecturas.

## Limitaciones conocidas

- **Sin Transactional Outbox**: si RabbitMQ está caído en el momento de publicar, el evento se pierde (queda en el log). La proyección de reportes puede quedar desactualizada. Es la mejora documentada para producción.
- Una sola instancia de PostgreSQL (con separación lógica por esquema y usuario): es un punto de falla compartido.
- El baseline UT4 es una reconstrucción mínima del monolito descrito en el informe, no el código original.
