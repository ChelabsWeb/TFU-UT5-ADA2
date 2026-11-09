import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import datos from "./datos.json";
import { Caja, Etiqueta, Fondo, Flecha, Leyenda, Paquete, Titulo, entrada, type Estado, type Punto } from "./piezas";
import { C, s } from "./tema";

// ------------------------------------------------------------------ diagrama
const W = 230;
const N = {
  cliente: { x: 150, y: 470 },
  gateway: { x: 420, y: 470 },
  d1: { x: 730, y: 360 },
  d2: { x: 730, y: 580 },
  flota: { x: 1080, y: 230 },
  ruteo: { x: 1080, y: 470 },
  proveedor: { x: 1420, y: 470 },
  rabbit: { x: 1080, y: 720 },
  reportes: { x: 1420, y: 720 },
  dlq: { x: 1720, y: 720 },
} as const;
type Nodo = keyof typeof N;
const der = (n: Nodo): Punto => ({ x: N[n].x + W / 2, y: N[n].y });
const izq = (n: Nodo): Punto => ({ x: N[n].x - W / 2, y: N[n].y });

const ARISTAS: [Punto, Punto, number][] = [
  [der("cliente"), izq("gateway"), 0],
  [der("gateway"), izq("d1"), 1],
  [der("gateway"), izq("d2"), 1],
  [der("d1"), izq("flota"), 2],
  [der("d2"), izq("flota"), 2],
  [der("d1"), izq("ruteo"), 3],
  [der("d2"), izq("ruteo"), 3],
  [der("ruteo"), izq("proveedor"), 3],
  [der("d1"), izq("rabbit"), 4],
  [der("d2"), izq("rabbit"), 4],
  [der("rabbit"), izq("reportes"), 4],
];

type Props = {
  paso?: number; // 0..4: cuántos grupos se ven (para la escena que lo arma)
  inicioPasos?: number[]; // frame en que aparece cada grupo
  estados?: Partial<Record<Nodo, Estado>>;
  subs?: Partial<Record<Nodo, string>>;
  conDlq?: boolean;
};

const Diagrama: React.FC<Props> = ({ inicioPasos = [-99, -99, -99, -99, -99], estados = {}, subs = {}, conDlq }) => {
  const caja = (n: Nodo, titulo: string, sub: string, grupo: number) => (
    <Caja
      x={N[n].x}
      y={N[n].y}
      titulo={titulo}
      sub={subs[n] ?? sub}
      estado={estados[n] ?? "normal"}
      aparece={inicioPasos[grupo]}
    />
  );
  return (
    <>
      {ARISTAS.map(([a, b, g], i) => (
        <Flecha key={i} a={a} b={b} aparece={inicioPasos[g] + 6} />
      ))}
      {conDlq && <Flecha a={der("reportes")} b={izq("dlq")} aparece={-99} color={C.rojo} punteada />}
      {caja("cliente", "operador", "", 0)}
      {caja("gateway", "gateway", "API key · límites", 0)}
      {caja("d1", "despacho 1", "servicio crítico", 1)}
      {caja("d2", "despacho 2", "réplica", 1)}
      {caja("flota", "flota", "estado + Redis", 2)}
      {caja("ruteo", "ruteo", "SOAP · WSDL", 3)}
      {caja("proveedor", "proveedor", "externo", 3)}
      {caja("rabbit", "RabbitMQ", "eventos y colas", 4)}
      {caja("reportes", "reportes", "proyección", 4)}
      {conDlq && (
        <Caja x={N.dlq.x} y={N.dlq.y} w={180} titulo="DLQ" sub="cola de errores" estado={estados.dlq ?? "normal"} />
      )}
    </>
  );
};

// ------------------------------------------------------------------ escenas
export const Portada: React.FC = () => {
  const f = useCurrentFrame();
  const a = entrada(f, 4);
  const b = entrada(f, 16);
  return (
    <Fondo>
      <div style={{ position: "absolute", left: 160, top: 360, opacity: a, transform: `translateY(${(1 - a) * 16}px)` }}>
        <div style={{ fontSize: 88, fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.05 }}>
          Flota de ambulancias:
          <br />
          de monolito a microservicios
        </div>
      </div>
      <div style={{ position: "absolute", left: 160, top: 620, fontSize: 34, color: C.gris, opacity: b }}>
        Análisis y Diseño de Aplicaciones II · TFU UT5 · Grupo 4
      </div>
    </Fondo>
  );
};

export const Antes: React.FC<{ leyenda?: boolean }> = ({ leyenda = true }) => {
  const f = useCurrentFrame();
  const cae = s(4.2);
  const caido = f >= cae;
  const estado: Estado = caido ? "caido" : "normal";
  const mods: [string, number][] = [
    ["despacho", 700],
    ["flota", 920],
    ["ETA (REST)", 1140],
    ["reportes", 1360],
  ];
  return (
    <Fondo>
      <Titulo texto="Antes: un monolito en capas" />
      <div
        style={{
          position: "absolute",
          left: 540,
          top: 290,
          width: 980,
          height: 380,
          borderRadius: 24,
          border: `3px solid ${caido ? C.rojo : C.linea}`,
          background: caido ? C.rojoSuave : C.caja,
          opacity: entrada(f, 4),
        }}
      >
        <div style={{ position: "absolute", left: 32, top: 24, fontSize: 28, fontWeight: 600, color: caido ? C.rojo : C.tinta }}>
          {caido ? "monolito UT4 · sin servicio" : "monolito UT4 · un proceso, una base SQLite"}
        </div>
      </div>
      {mods.map(([t, x], i) => (
        <Caja key={t} x={x} y={520} w={190} titulo={t} estado={estado} aparece={10 + i * 6} />
      ))}
      <Caja x={190} y={500} w={200} titulo="operador" aparece={6} />
      <Flecha a={{ x: 290, y: 500 }} b={{ x: 540, y: 500 }} aparece={14} color={caido ? C.rojo : C.grisClaro} />
      <Paquete a={{ x: 1360, y: 860 }} b={{ x: 1360, y: 565 }} desde={s(2.8)} dur={s(1.3)} color={C.rojo} etiqueta="reporte defectuoso" />
      {caido && <Etiqueta x={400} y={430} texto="despachos rechazados" color={C.rojo} fondo={C.rojoSuave} aparece={cae + 6} />}
      {leyenda && (
      <Leyenda
        lineas={[
          [s(0.3), s(2.8), "Antes, todo vivía en un solo proceso."],
          [s(2.8), s(5.6), "Un reporte defectuoso tira ese proceso…"],
          [s(5.6), s(9.6), "…y con él se cae el despacho de ambulancias."],
        ]}
      />
      )}
    </Fondo>
  );
};

export const Ahora: React.FC<{ leyenda?: boolean }> = ({ leyenda = true }) => (
  <Fondo>
    <Titulo texto="Ahora: microservicios" />
    <Diagrama inicioPasos={[s(0.4), s(2.2), s(4.4), s(5.4), s(8)]} />
    {leyenda && (
      <Leyenda
      lineas={[
        [s(0.4), s(4.2), "Un servicio por capacidad de negocio, cada uno dueño de sus datos."],
        [s(4.2), s(7.8), "El despacho, que es crítico, corre en dos réplicas."],
        [s(7.8), s(11.6), "Lo que no es urgente viaja por eventos, en RabbitMQ."],
      ]}
    />
      )}
  </Fondo>
);

const XmlSoap: React.FC<{ desde: number; hasta: number }> = ({ desde, hasta }) => {
  const f = useCurrentFrame();
  if (f < desde || f > hasta) return null;
  const op = Math.min(entrada(f, desde, 10), interpolate(f, [hasta - 10, hasta], [1, 0], { extrapolateLeft: "clamp" }));
  const l = (t: string, ind = 0, color: string = C.gris) => (
    <div style={{ paddingLeft: ind * 22, color }}>{t}</div>
  );
  return (
    <div
      style={{
        position: "absolute",
        left: 1300,
        top: 90,
        width: 520,
        padding: "18px 24px",
        borderRadius: 14,
        background: C.caja,
        border: `2px solid ${C.azul}`,
        fontSize: 20,
        lineHeight: 1.45,
        opacity: op,
      }}
    >
      {l("<soap:Envelope>", 0)}
      {l("<CalcularETAsRequest>", 1, C.azul)}
      {l("<destino> -34.90, -56.16 </destino>", 2, C.tinta)}
      {l("<ambulancia> AMB-012 … </ambulancia>", 2, C.tinta)}
      {l("<ambulancia> AMB-047 … </ambulancia>", 2, C.tinta)}
      {l("</CalcularETAsRequest>", 1, C.azul)}
      {l("</soap:Envelope>", 0)}
    </div>
  );
};

const Flujo: React.FC = () => {
  const P = (a: Punto, b: Punto, d: number, du: number, et?: string, color?: string) => (
    <Paquete a={a} b={b} desde={s(d)} dur={s(du)} etiqueta={et} color={color} />
  );
  return (
    <Fondo>
      <Titulo texto="Registrar un despacho" />
      <Diagrama />
      {P(der("cliente"), izq("gateway"), 0.3, 0.6)}
      {P(der("gateway"), izq("d1"), 0.9, 0.6)}
      {P(der("d1"), izq("flota"), 1.8, 0.8, "¿disponibles?")}
      {P(izq("flota"), der("d1"), 2.7, 0.8)}
      {P(der("d1"), izq("ruteo"), 3.8, 0.8, "SOAP · CalcularETAs")}
      {P(der("ruteo"), izq("proveedor"), 4.7, 0.6)}
      {P(izq("proveedor"), der("ruteo"), 5.4, 0.6)}
      {P(izq("ruteo"), der("d1"), 6.1, 0.8)}
      {P(der("d1"), izq("flota"), 7.3, 0.8, "reservar", C.verde)}
      {P(der("d1"), izq("rabbit"), 8.6, 0.9, "DespachoRegistrado")}
      {P(der("rabbit"), izq("reportes"), 9.6, 0.8)}
      {P(izq("d1"), der("gateway"), 10.2, 0.6, undefined, C.verde)}
      {P(izq("gateway"), der("cliente"), 10.8, 0.6, "201 · ETA 6 min", C.verde)}
      <XmlSoap desde={s(3.8)} hasta={s(7.2)} />
      <Leyenda
        lineas={[
          [s(0.2), s(3.6), "Despacho pide a flota las ambulancias disponibles."],
          [s(3.6), s(7.2), "Las ETAs llegan en una sola llamada SOAP, con contrato WSDL."],
          [s(7.2), s(10.2), "Reserva la más rápida y avisa con un evento."],
          [s(10.2), s(13.6), "Los reportes se actualizan solos, sin frenar el despacho."],
        ]}
      />
    </Fondo>
  );
};

const CaeProveedor: React.FC = () => {
  const f = useCurrentFrame();
  const t = f / 30;
  const proveedorCaido = t >= 0.8 && t < 9.5;
  const cb = t < 4 ? "cerrado" : t < 10.2 ? "abierto" : t < 11.6 ? "semiabierto" : "cerrado";
  const cbColor = { cerrado: [C.verde, C.verdeSuave], abierto: [C.rojo, C.rojoSuave], semiabierto: [C.ambar, C.ambarSuave] }[cb];
  const despachos = [];
  for (let d = 4.6; d < 9.4; d += 1.2) {
    despachos.push(
      <Paquete key={d} a={izq("d1")} b={der("cliente")} desde={s(d)} dur={s(1)} color={C.ambar} etiqueta={d < 5 ? "201 · ETA estimada" : undefined} />,
    );
  }
  return (
    <Fondo>
      <Titulo texto="Si se cae el proveedor de ruteo" />
      <Diagrama
        estados={{
          proveedor: proveedorCaido ? "caido" : "normal",
          d1: t >= 4 && t < 11.6 ? "alerta" : "normal",
        }}
        subs={{ proveedor: proveedorCaido ? "no responde" : "externo", d1: t >= 4 && t < 11.6 ? "usa el fallback" : "servicio crítico" }}
      />
      <Paquete a={der("d1")} b={izq("ruteo")} desde={s(1.4)} dur={s(0.7)} />
      <Paquete a={der("ruteo")} b={{ x: N.proveedor.x - 160, y: N.proveedor.y }} desde={s(2.1)} dur={s(0.5)} color={C.rojo} etiqueta="sin respuesta" />
      <Paquete a={der("d1")} b={izq("ruteo")} desde={s(2.8)} dur={s(0.7)} />
      <Paquete a={der("ruteo")} b={{ x: N.proveedor.x - 160, y: N.proveedor.y }} desde={s(3.4)} dur={s(0.5)} color={C.rojo} />
      {despachos}
      <Paquete a={der("d1")} b={izq("ruteo")} desde={s(10.4)} dur={s(0.5)} etiqueta="llamada de prueba" />
      <Paquete a={der("ruteo")} b={izq("proveedor")} desde={s(10.9)} dur={s(0.4)} />
      <Paquete a={izq("proveedor")} b={der("ruteo")} desde={s(11.3)} dur={s(0.3)} color={C.verde} />
      <div
        style={{
          position: "absolute",
          left: N.ruteo.x,
          top: N.ruteo.y - 82,
          transform: "translate(-50%, -50%)",
          padding: "8px 16px",
          borderRadius: 999,
          background: cbColor[1],
          color: cbColor[0],
          fontSize: 22,
          fontWeight: 600,
          whiteSpace: "nowrap",
        }}
      >
        circuito {cb}
      </div>
      <Leyenda
        lineas={[
          [s(0.3), s(3.9), "Se cae el proveedor externo de ruteo."],
          [s(3.9), s(6.6), "El circuit breaker se abre: deja de esperarlo."],
          [s(6.6), s(9.6), "El despacho sale igual, con una ETA estimada por distancia."],
          [s(9.6), s(14.6), "Cuando vuelve, una llamada de prueba cierra el circuito."],
        ]}
      />
    </Fondo>
  );
};

const ReporteDefectuoso: React.FC = () => {
  const f = useCurrentFrame();
  const t = f / 30;
  const reportes: Estado = (t >= 2 && t < 4.4) || (t >= 6 && t < 8) ? "caido" : t >= 4.4 && t < 6 ? "alerta" : "normal";
  const sub = reportes === "caido" ? "proceso caído" : reportes === "alerta" ? "reiniciando" : "proyección";
  const ok = [];
  for (let d = 0.4; d < 10.5; d += 1.0) {
    ok.push(<Paquete key={`a${d}`} a={der("cliente")} b={izq("gateway")} desde={s(d)} dur={s(0.45)} color={C.verde} />);
    ok.push(<Paquete key={`b${d}`} a={der("gateway")} b={izq(d % 2 < 1 ? "d1" : "d2")} desde={s(d + 0.45)} dur={s(0.45)} color={C.verde} />);
  }
  return (
    <Fondo>
      <Titulo texto="Si un reporte tira el servicio de reportes" />
      <Diagrama conDlq estados={{ reportes, dlq: t >= 8.6 ? "alerta" : "normal" }} subs={{ reportes: sub }} />
      {ok}
      <Paquete a={der("rabbit")} b={izq("reportes")} desde={s(1.2)} dur={s(0.8)} color={C.rojo} etiqueta="reporte defectuoso" />
      <Paquete a={der("rabbit")} b={izq("reportes")} desde={s(5.2)} dur={s(0.8)} color={C.rojo} etiqueta="otro intento" />
      <Paquete a={der("reportes")} b={izq("dlq")} desde={s(8)} dur={s(0.6)} color={C.rojo} />
      <Etiqueta x={N.d1.x} y={N.d1.y - 80} texto="sigue despachando" color={C.verde} fondo={C.verdeSuave} aparece={s(2.4)} />
      <Leyenda
        lineas={[
          [s(0.3), s(3.4), "Un reporte defectuoso tira el servicio de reportes."],
          [s(3.4), s(6.6), "El despacho ni se entera: sigue atendiendo."],
          [s(6.6), s(10.6), "Tras tres intentos, el mensaje queda apartado en la DLQ."],
        ]}
      />
    </Fondo>
  );
};

type Fila = { exito: number; p95: number | null; sinServicio: number | null };
const D = datos as unknown as { escenarios: Record<string, { nombre: string; micro: Fila; ut4: Fila }>; p95base: { micro: number; ut4: number } };

export const Resultados: React.FC<{ leyenda?: boolean }> = ({ leyenda = true }) => {
  const f = useCurrentFrame();
  const escs = ["P1", "P2", "P3"];
  const alto = 330;
  return (
    <Fondo>
      <Titulo texto="Lo medimos" />
      <div style={{ position: "absolute", left: 120, top: 150, fontSize: 28, color: C.gris, opacity: entrada(f, 6) }}>
        despachos exitosos durante la falla · 20 por segundo, 60 s, mediana de 3 corridas
      </div>
      {escs.map((e, i) => {
        const x0 = 200 + i * 540;
        const fila = D.escenarios[e];
        return (
          <div key={e}>
            {(["ut4", "micro"] as const).map((arq, j) => {
              const v = fila[arq].exito;
              const k = entrada(f, s(0.8) + i * 8 + j * 4, 24);
              const h = alto * v * k;
              const color = arq === "micro" ? C.azul : C.grisClaro;
              return (
                <div key={arq}>
                  <div
                    style={{
                      position: "absolute",
                      left: x0 + j * 170,
                      top: 300 + alto - h,
                      width: 130,
                      height: h,
                      borderRadius: "10px 10px 0 0",
                      background: color,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      left: x0 + j * 170 - 45,
                      width: 220,
                      whiteSpace: "nowrap",
                      top: 300 + alto - h - 52,
                      textAlign: "center",
                      fontSize: 34,
                      fontWeight: 700,
                      fontVariantNumeric: "tabular-nums",
                      color: arq === "micro" ? C.azul : C.gris,
                      opacity: k,
                    }}
                  >
                    {(v * 100 * k).toFixed(1).replace(".", ",")} %
                  </div>
                  <div
                    style={{ position: "absolute", left: x0 + j * 170, width: 130, top: 300 + alto + 14, textAlign: "center", fontSize: 22, color: C.gris }}
                  >
                    {arq === "micro" ? "microservicios" : "monolito"}
                  </div>
                </div>
              );
            })}
            <div style={{ position: "absolute", left: x0, width: 300, top: 300 + alto + 56, fontSize: 26, fontWeight: 600 }}>
              {fila.nombre}
            </div>
          </div>
        );
      })}
      {leyenda && (
      <Leyenda
        lineas={[
          [s(0.4), s(5.4), "Con la falla inyectada, el despacho sigue funcionando."],
          [
            s(5.4),
            s(10.6),
            `El costo: más saltos de red. p95 sin fallas ${Math.round(D.p95base.micro)} ms contra ${Math.round(D.p95base.ut4)} ms.`,
          ],
        ]}
      />
      )}
    </Fondo>
  );
};

export const Cierre: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Fondo>
      <div style={{ position: "absolute", left: 160, top: 380, opacity: entrada(f, 4) }}>
        <div style={{ fontSize: 76, fontWeight: 700, letterSpacing: "-0.03em" }}>Ganamos disponibilidad</div>
        <div style={{ fontSize: 44, color: C.gris, marginTop: 16, opacity: entrada(f, 16) }}>
          a cambio de latencia y de más piezas que operar.
        </div>
      </div>
      <div style={{ position: "absolute", left: 160, bottom: 110, fontSize: 28, color: C.gris, opacity: entrada(f, 30) }}>
        Grupo 4 · Cárdenas, Arzuaga, Ruiz, Merino, Méndez
      </div>
    </Fondo>
  );
};

export const ESCENAS: [React.FC, number][] = [
  [Portada, s(4)],
  [Antes, s(10)],
  [Ahora, s(12)],
  [Flujo, s(14)],
  [CaeProveedor, s(15)],
  [ReporteDefectuoso, s(11)],
  [Resultados, s(11)],
  [Cierre, s(5)],
];
export const DURACION = ESCENAS.reduce((a, [, d]) => a + d, 0);

export const Explicacion: React.FC = () => {
  let desde = 0;
  return (
    <AbsoluteFill style={{ background: C.fondo }}>
      {ESCENAS.map(([Escena, dur], i) => {
        const el = (
          <Sequence key={i} from={desde} durationInFrames={dur}>
            <Escena />
          </Sequence>
        );
        desde += dur;
        return el;
      })}
    </AbsoluteFill>
  );
};
