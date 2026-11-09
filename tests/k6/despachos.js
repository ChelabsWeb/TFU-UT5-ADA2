// Carga constante de despachos contra el gateway (o el monolito).
//   BASE      URL base (http://host.docker.internal:8080 o :18090)
//   RPS       despachos por segundo (20)
//   DURACION  duración (60s)
//   SALIDA    archivo JSON con el resumen
import http from 'k6/http';
import { Counter, Rate } from 'k6/metrics';

const exito = new Rate('despacho_exitoso');
const etaEstimada = new Counter('eta_estimada');
const etaExacta = new Counter('eta_exacta');

export const options = {
  scenarios: {
    despachos: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RPS || 20),
      timeUnit: '1s',
      duration: __ENV.DURACION || '60s',
      preAllocatedVUs: 60,
      maxVUs: 300,
    },
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
};

const params = {
  headers: { 'Content-Type': 'application/json', 'X-API-Key': 'clave-demo-ut5' },
  timeout: '10s',
};

export default function () {
  const cuerpo = JSON.stringify({
    lat: -34.88 + (Math.random() - 0.5) * 0.1,
    lon: -56.16 + (Math.random() - 0.5) * 0.16,
    prioridad: 'ALTA',
  });
  const r = http.post(`${__ENV.BASE}/api/despachos`, cuerpo, params);
  const ok = r.status === 201;
  exito.add(ok);
  if (ok) {
    if (r.json('eta_estimada')) etaEstimada.add(1);
    else etaExacta.add(1);
  }
}

export function handleSummary(data) {
  return { [__ENV.SALIDA || '/resultados/resumen.json']: JSON.stringify(data, null, 2) };
}
