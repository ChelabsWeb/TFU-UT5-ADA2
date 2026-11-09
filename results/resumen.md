| Escenario | Arquitectura | Éxito | p50 | p95 | ETA estimadas | Seg. sin servicio | Recuperación | Reportes |
|---|---|---|---|---|---|---|---|---|
| P0 Línea base sin fallas | Monolito UT4 | 100.0 % | 68 ms | 95 ms | 0 | 0 s | – |  |
| P0 Línea base sin fallas | Microservicios | 100.0 % | 91 ms | 122 ms | 0 | 0 s | – |  |
| P1 Cae el proveedor de ruteo | Monolito UT4 | 52.6 % | 76 ms | 1514 ms | 0 | 25 s | 0.9 s |  |
| P1 Cae el proveedor de ruteo | Microservicios | 100.0 % | 59 ms | 122 ms | 625 | 0 s | 0.9 s |  |
| P2 Reporte defectuoso tira reportes | Monolito UT4 | 97.8 % | 70 ms | 96 ms | 0 | 1 s | – | normal: PENDIENTE; defectuoso: PENDIENTE |
| P2 Reporte defectuoso tira reportes | Microservicios | 100.0 % | 93 ms | 123 ms | 0 | 0 s | – | normal: LISTO; defectuoso: FALLIDO; DLQ: 0 |
| P3 Cae una instancia de despacho | Monolito UT4 | 47.8 % | 71 ms | 106 ms | 0 | 32 s | 0.9 s |  |
| P3 Cae una instancia de despacho | Microservicios | 99.8 % | 100 ms | 224 ms | 0 | 0 s | – |  |
