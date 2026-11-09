/**
 * Video narrado: la voz (una toma, src/voz.json) marca el tiempo de todo.
 * La terminal reproduce la demo grabada contra el sistema real (src/demo.json, scripts/grabar-demo.py)
 * y los paneles muestran código copiado tal cual del repo (src/codigo.json, scripts/fragmentos.py).
 */
import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import codigo from "./codigo.json";
import demo from "./demo.json";
import { Ahora, Antes, Cierre, Portada, Resultados } from "./Explicacion";
import { Fondo, Titulo, entrada } from "./piezas";
import { C, FPS, fontFamily, mono } from "./tema";
import voz from "./voz.json";

// ------------------------------------------------------------------ tiempos de la voz
type Frase = { escena: string; texto: string; a: number; b: number };
const FRASES = voz.frases as Frase[];
const PALABRAS = voz.palabras as [string, number, number][];
const fr = (seg: number) => Math.round(seg * FPS);

const norm = (t: string) =>
  t
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]/g, "");

const ORDEN = [
  "portada",
  "antes",
  "ahora",
  "arriba",
  "despacho",
  "codigo-soap",
  "soap",
  "codigo-cb",
  "cae",
  "vuelve",
  "codigo-dlq",
  "reporte",
  "replica",
  "resultados",
  "cierre",
] as const;
type Escena = (typeof ORDEN)[number];

const frasesDe = (e: Escena) => FRASES.filter((f) => f.escena === e);
const INICIO: Record<Escena, number> = Object.fromEntries(
  ORDEN.map((e, i) => [e, i === 0 ? 0 : fr(frasesDe(e)[0].a - 0.35)]),
) as Record<Escena, number>;
export const DURACION_NARRADO = fr(voz.fin + 2.2);
const FIN: Record<Escena, number> = Object.fromEntries(
  ORDEN.map((e, i) => [e, i + 1 < ORDEN.length ? INICIO[ORDEN[i + 1]] : DURACION_NARRADO]),
) as Record<Escena, number>;

/** Frame (relativo a la escena) en que la voz dice `palabra` dentro de la frase `n` de la escena. */
const cuando = (e: Escena, n: number, palabra?: string, adelanto = 0.15): number => {
  const f = frasesDe(e)[n];
  let t = f.a;
  if (palabra) {
    const w = PALABRAS.find(([txt, a]) => a >= f.a - 0.01 && a <= f.b && norm(txt) === norm(palabra));
    if (!w) throw new Error(`no encuentro «${palabra}» en ${e}/${n}`);
    t = w[1];
  }
  return fr(t - adelanto) - INICIO[e];
};

// ------------------------------------------------------------------ subtítulos (renglones cortos, cortados en pausas)
type Renglon = { a: number; b: number; texto: string };
const MAX = 46;

const partir = (texto: string): string[] => {
  // primero por puntuación; si un trozo sigue largo, por palabras
  const trozos = texto.match(/[^,:.;]+[,:.;]?/g)?.map((t) => t.trim()).filter(Boolean) ?? [texto];
  const juntos: string[] = [];
  for (const t of trozos) {
    const ultimo = juntos[juntos.length - 1];
    if (ultimo && ultimo.length + t.length + 1 <= MAX && !/[.:]$/.test(ultimo)) juntos[juntos.length - 1] = `${ultimo} ${t}`;
    else juntos.push(t);
  }
  const salida: string[] = [];
  for (const t of juntos) {
    if (t.length <= MAX) {
      salida.push(t);
      continue;
    }
    const ps = t.split(" ");
    const n = Math.ceil(t.length / MAX);
    const porRenglon = Math.ceil(ps.length / n);
    for (let i = 0; i < ps.length; i += porRenglon) salida.push(ps.slice(i, i + porRenglon).join(" "));
  }
  return salida;
};

const RENGLONES: Renglon[] = FRASES.flatMap((f, i) => {
  const palabras = PALABRAS.filter(([, a, b]) => a >= f.a - 0.01 && b <= f.b + 0.01);
  const trozos = partir(f.texto);
  const total = f.texto.length;
  const siguiente = FRASES[i + 1]?.a ?? f.b + 1;
  let pos = 0;
  const inicios = trozos.map((t) => {
    const idx = Math.min(palabras.length - 1, Math.round((pos / total) * palabras.length));
    pos += t.length + 1;
    return idx === 0 ? f.a : palabras[idx][1];
  });
  return trozos.map((t, k) => ({
    a: fr(inicios[k] - 0.1),
    b: k + 1 < trozos.length ? fr(inicios[k + 1] - 0.1) : fr(Math.min(f.b + 0.5, siguiente - 0.15)),
    texto: t,
  }));
});

const Subtitulos: React.FC = () => {
  const f = useCurrentFrame();
  const r = RENGLONES.find(({ a, b }) => f >= a && f < b);
  if (!r) return null;
  const op = Math.min(entrada(f, r.a, 5), interpolate(f, [r.b - 5, r.b], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 46,
        textAlign: "center",
        fontFamily,
        fontSize: 40,
        fontWeight: 500,
        letterSpacing: "-0.01em",
        color: C.tinta,
        opacity: op,
        textShadow: `0 0 12px ${C.fondo}, 0 0 4px ${C.fondo}`,
      }}
    >
      {r.texto}
    </div>
  );
};

// ------------------------------------------------------------------ resaltado de sintaxis (mínimo)
const T = {
  texto: "#D6DAE1",
  tenue: "#7D8590",
  verde: "#7EC699",
  ambar: "#E5B567",
  rojo: "#F08A7E",
  azul: "#8AB4F8",
};

type Pieza = [string, string];
const colorear = (linea: string, reglas: [RegExp, string][], base: string): Pieza[] => {
  const piezas: Pieza[] = [];
  let resto = linea;
  while (resto.length) {
    let mejor: { i: number; largo: number; color: string } | null = null;
    for (const [re, color] of reglas) {
      const m = re.exec(resto);
      if (m && m[0].length && (mejor === null || m.index < mejor.i)) mejor = { i: m.index, largo: m[0].length, color };
    }
    if (!mejor) {
      piezas.push([resto, base]);
      break;
    }
    if (mejor.i > 0) piezas.push([resto.slice(0, mejor.i), base]);
    piezas.push([resto.slice(mejor.i, mejor.i + mejor.largo), mejor.color]);
    resto = resto.slice(mejor.i + mejor.largo);
  }
  return piezas;
};

// terminal: lo que importa leer
const REGLAS_TERMINAL: [RegExp, string][] = [
  [/^#.*$/, T.tenue],
  [/\bSEMIABIERTO\b/, T.ambar],
  [/\bABIERTO\b/, T.rojo],
  [/\bCERRADO\b/, T.verde],
  [/\bFALLIDO\b/, T.rojo],
  [/\(healthy\)/, T.verde],
  [/eta_estimada=true|"eta_estimada": true/, T.ambar],
  [/eta_estimada=false|"eta_estimada": false/, T.verde],
  [/\bStopped\b/, T.rojo],
  [/\bStarted\b/, T.verde],
  [/\b201\b/, T.verde],
  [/<\/?[\w:]+>/, T.azul],
];

// código claro (fondo blanco)
const K = { kw: "#7A3E9D", str: "#2E7D4F", com: "#8A919C", num: "#B35C00", tag: "#1F6FB2", base: C.tinta };
const REGLAS_PY: [RegExp, string][] = [
  [/#.*$/, K.com],
  [/"[^"]*"|'[^']*'/, K.str],
  [/\b(def|if|elif|else|return|try|except|with|for|in|and|or|not|is|None|True|False|lambda|as|raise|self)\b/, K.kw],
  [/\b\d+(\.\d+)?\b/, K.num],
];
const REGLAS_XML: [RegExp, string][] = [
  [/"[^"]*"/, K.str],
  [/<\/?[\w:]+|\/?>/, K.tag],
];

// ------------------------------------------------------------------ terminal con la demo grabada
type Paso = { escena: string; cmd: string; out: string; nota: string | null; t: string };
const PASOS = demo as Paso[];

type Programa = { paso: Paso; desde: number; velocidad?: number; nota?: string };

const LH = 32;
const Terminal: React.FC<{ programa: Programa[]; alto?: number }> = ({ programa, alto = 740 }) => {
  const f = useCurrentFrame();
  const lineas: { piezas: Pieza[]; prompt?: boolean; cursor?: boolean }[] = [];
  for (const { paso, desde, velocidad = 40, nota } of programa) {
    if (f < desde) break;
    const n = nota ?? paso.nota;
    if (n) lineas.push({ piezas: [[`# ${n}`, T.tenue]] });
    const tipeo = Math.min(paso.cmd.length, Math.floor((f - desde) * 2.2));
    const escribiendo = tipeo < paso.cmd.length;
    const corte = paso.cmd.indexOf("   #");
    const tipeado = paso.cmd.slice(0, tipeo);
    lineas.push({
      piezas:
        corte > 0 && tipeo > corte
          ? [
              [tipeado.slice(0, corte), T.texto],
              [tipeado.slice(corte), T.tenue],
            ]
          : [[tipeado, T.texto]],
      prompt: true,
      cursor: escribiendo,
    });
    if (escribiendo) break;
    const desdeSalida = desde + Math.ceil(paso.cmd.length / 2.2) + 6;
    const mostrar = Math.max(0, Math.floor((f - desdeSalida) * velocidad));
    let quedan = mostrar;
    for (const l of paso.out.split("\n")) {
      if (quedan <= 0) break;
      const visible = l.slice(0, quedan);
      quedan -= l.length + 1;
      lineas.push({ piezas: colorear(visible, REGLAS_TERMINAL, T.texto) });
    }
    if (mostrar > 0) lineas.push({ piezas: [] });
  }
  const caben = Math.floor((alto - 70) / LH);
  const corrimiento = Math.max(0, lineas.length - caben) * LH;
  const op = entrada(f, 0, 10);
  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        top: 168,
        width: 1680,
        height: alto,
        borderRadius: 16,
        background: "#16191E",
        boxShadow: "0 2px 4px rgba(20,23,28,.08), 0 18px 48px rgba(20,23,28,.18)",
        overflow: "hidden",
        opacity: op,
        transform: `translateY(${(1 - op) * 14}px)`,
      }}
    >
      <div style={{ height: 46, display: "flex", alignItems: "center", padding: "0 22px", color: T.tenue, fontSize: 19, borderBottom: "1px solid #262A31" }}>
        terminal · ~/TFU-UT5-ADA2
      </div>
      <div style={{ position: "absolute", left: 28, right: 28, top: 62, bottom: 12, overflow: "hidden" }}>
        <div style={{ transform: `translateY(${-corrimiento}px)`, fontFamily: mono, fontSize: 22, lineHeight: `${LH}px`, whiteSpace: "pre" }}>
          {lineas.map((l, i) => (
            <div key={i} style={{ height: LH }}>
              {l.prompt && <span style={{ color: T.verde }}>$ </span>}
              {l.piezas.map(([t, c], j) => (
                <span key={j} style={{ color: c }}>
                  {t}
                </span>
              ))}
              {l.cursor && <span style={{ background: T.texto, color: T.texto }}> </span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const Sello: React.FC<{ texto: string }> = ({ texto }) => {
  const f = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 122, top: 132, fontSize: 24, color: C.gris, opacity: entrada(f, 8) }}>{texto}</div>
  );
};

const pasos = (e: string) => PASOS.filter((p) => p.escena === e);
const DIA = "9/11/2026";

const EscenaDemo: React.FC<{ titulo: string; programa: Programa[] }> = ({ titulo, programa }) => (
  <Fondo>
    <Titulo texto={titulo} arriba={52} />
    <Sello texto={`salida real del sistema corriendo · ${DIA}`} />
    <Terminal programa={programa} />
  </Fondo>
);

// ------------------------------------------------------------------ panel de código
type Frag = { archivo: string; desde: number; lineas: string[] };
const FRAG = codigo as Record<string, Frag>;

type Resalte = { desde: number; hasta: number; frame: number };

const Panel: React.FC<{
  id: string;
  x: number;
  y: number;
  w: number;
  aparece: number;
  sale?: number;
  resaltes?: Resalte[];
  tam?: number;
}> = ({ id, x, y, w, aparece, sale, resaltes = [], tam = 19 }) => {
  const f = useCurrentFrame();
  const fr0 = FRAG[id];
  const lh = Math.round(tam * 1.42);
  const xml = fr0.archivo.endsWith(".wsdl");
  // sangría común fuera
  const sangria = Math.min(...fr0.lineas.filter((l) => l.trim()).map((l) => l.length - l.trimStart().length));
  const activo = [...resaltes].reverse().find((r) => f >= r.frame);
  const kActivo = activo ? entrada(f, activo.frame, 10) : 0;
  let op = entrada(f, aparece, 14);
  if (sale !== undefined) op = Math.min(op, interpolate(f, [sale, sale + 10], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  if (op <= 0) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: w,
        borderRadius: 14,
        background: C.caja,
        border: `1px solid ${C.linea}`,
        boxShadow: "0 1px 2px rgba(20,23,28,.05), 0 10px 30px rgba(20,23,28,.07)",
        opacity: op,
        transform: `translateY(${(1 - op) * 14}px)`,
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "12px 22px", fontSize: 20, color: C.gris, borderBottom: `1px solid ${C.linea}` }}>{fr0.archivo}</div>
      <div style={{ padding: "12px 0", fontFamily: mono, fontSize: tam, lineHeight: `${lh}px`, whiteSpace: "pre" }}>
        {fr0.lineas.map((l, i) => {
          const n = fr0.desde + i;
          const dentro = activo && n >= activo.desde && n <= activo.hasta;
          const opLinea = activo ? (dentro ? 1 : 1 - 0.55 * kActivo) : 1;
          return (
            <div
              key={i}
              style={{
                display: "flex",
                height: lh,
                background: dentro ? `rgba(31,111,178,${0.1 * kActivo})` : "transparent",
                boxShadow: dentro ? `inset 4px 0 0 rgba(31,111,178,${kActivo})` : "none",
              }}
            >
              <span style={{ width: 66, textAlign: "right", paddingRight: 18, color: C.grisClaro, flexShrink: 0 }}>{n}</span>
              <span style={{ opacity: opLinea }}>
                {colorear(l.slice(sangria), xml ? REGLAS_XML : REGLAS_PY, K.base).map(([t, c], j) => (
                  <span key={j} style={{ color: c }}>
                    {t}
                  </span>
                ))}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ escenas
const P = (e: string, i: number) => pasos(e)[i];

const ESCENAS: Record<Escena, React.FC> = {
  portada: Portada,
  antes: () => <Antes leyenda={false} />,
  ahora: () => <Ahora leyenda={false} />,
  arriba: () => (
    <EscenaDemo titulo="El sistema, corriendo" programa={[{ paso: P("arriba", 0), desde: 10, velocidad: 6 }]} />
  ),
  despacho: () => (
    <EscenaDemo titulo="Pedir una ambulancia" programa={[{ paso: P("despacho", 0), desde: 8 }]} />
  ),
  "codigo-soap": () => (
    <Fondo>
      <Titulo texto="De REST a SOAP" arriba={52} />
      <Panel
        id="wsdl"
        x={120}
        y={150}
        w={1680}
        tam={18}
        aparece={cuando("codigo-soap", 1, "contrato")}
        resaltes={[{ desde: 41, hasta: 48, frame: cuando("codigo-soap", 1, "archivo") }]}
      />
      <Panel
        id="zeep"
        x={120}
        y={660}
        w={1680}
        tam={18}
        aparece={cuando("codigo-soap", 1, "consume")}
        resaltes={[{ desde: 79, hasta: 82, frame: cuando("codigo-soap", 1, "generado") }]}
      />
    </Fondo>
  ),
  soap: () => (
    <EscenaDemo titulo="La respuesta SOAP" programa={[{ paso: P("soap", 0), desde: 8, velocidad: 30 }]} />
  ),
  "codigo-cb": () => (
    <Fondo>
      <Titulo texto="Circuit breaker y fallback" arriba={52} />
      <Panel
        id="cb"
        x={120}
        y={150}
        w={1680}
        aparece={cuando("codigo-cb", 1, "circuit")}
        sale={cuando("codigo-cb", 2, "mientras")}
        resaltes={[{ desde: 154, hasta: 160, frame: cuando("codigo-cb", 1, "mitad") }]}
      />
      <Panel
        id="fallback"
        x={120}
        y={150}
        w={1680}
        aparece={cuando("codigo-cb", 2, "mientras") + 6}
        resaltes={[
          { desde: 122, hasta: 123, frame: cuando("codigo-cb", 2, "abierto") },
          { desde: 130, hasta: 131, frame: cuando("codigo-cb", 2, "estima") },
        ]}
      />
      <DependeDe />
    </Fondo>
  ),
  cae: () => (
    <EscenaDemo
      titulo="Se cae el proveedor"
      programa={[
        { paso: P("cae", 0), desde: 6, velocidad: 4 },
        { paso: P("cae", 1), desde: cuando("cae", 1), velocidad: 16 },
        { paso: P("cae", 2), desde: cuando("cae", 1, "logs", 1.6), velocidad: 6 },
      ]}
    />
  ),
  vuelve: () => (
    <EscenaDemo
      titulo="Vuelve el proveedor"
      programa={[
        { paso: P("vuelve", 0), desde: 6, velocidad: 4 },
        { paso: P("vuelve", 1), desde: cuando("vuelve", 0, "treinta", 0.6) },
        { paso: P("vuelve", 2), desde: cuando("vuelve", 0, "cierra", 0.9), velocidad: 6 },
      ]}
    />
  ),
  "codigo-dlq": () => (
    <Fondo>
      <Titulo texto="Reportes por una cola, con DLQ" arriba={52} />
      <Panel
        id="cola"
        x={120}
        y={150}
        w={1680}
        tam={18}
        aparece={cuando("codigo-dlq", 0, "cola", 0.6)}
        resaltes={[
          { desde: 69, hasta: 69, frame: cuando("codigo-dlq", 1, "reintenta") },
          { desde: 60, hasta: 63, frame: cuando("codigo-dlq", 1, "muertos", 0.8) },
        ]}
      />
      <Panel
        id="falla"
        x={120}
        y={580}
        w={1680}
        tam={18}
        aparece={cuando("codigo-dlq", 1, "mensaje")}
        resaltes={[{ desde: 123, hasta: 123, frame: cuando("codigo-dlq", 1, "abajo") }]}
      />
    </Fondo>
  ),
  reporte: () => (
    <EscenaDemo
      titulo="Un reporte defectuoso"
      programa={[
        { paso: P("reporte", 0), desde: 6, velocidad: 6 },
        { paso: P("reporte", 1), desde: cuando("reporte", 1, "despacho", 0.9) },
        { paso: P("reporte", 2), desde: cuando("reporte", 1, "reintentos", 0.6), nota: "unos segundos después", velocidad: 8 },
        { paso: P("reporte", 3), desde: cuando("reporte", 1, "fallido", 0.1) },
      ]}
    />
  ),
  replica: () => (
    <EscenaDemo
      titulo="Se cae una réplica de despacho"
      programa={[
        { paso: P("replica", 0), desde: 8 },
        { paso: P("replica", 1), desde: cuando("replica", 1, "gateway", 0.8), velocidad: 1.2 },
      ]}
    />
  ),
  resultados: () => <Resultados leyenda={false} />,
  cierre: Cierre,
};

/** Rótulo de la frase 0 de codigo-cb, antes de que aparezca el código. */
function DependeDe() {
  const f = useCurrentFrame();
  const hasta = cuando("codigo-cb", 1, "circuit");
  if (f >= hasta + 10) return null;
  const op = Math.min(entrada(f, 4, 14), interpolate(f, [hasta - 4, hasta + 6], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const caja = (x: number, t: string, sub: string, rojo = false) => (
    <div
      style={{
        position: "absolute",
        left: x,
        top: 430,
        width: 360,
        height: 130,
        borderRadius: 16,
        background: rojo ? C.rojoSuave : C.caja,
        border: `2px solid ${rojo ? C.rojo : C.linea}`,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div style={{ fontSize: 34, fontWeight: 600 }}>{t}</div>
      <div style={{ fontSize: 22, color: rojo ? C.rojo : C.gris, marginTop: 6 }}>{sub}</div>
    </div>
  );
  return (
    <div style={{ position: "absolute", inset: 0, opacity: op }}>
      {caja(300, "despacho", "necesita la ETA")}
      {caja(780, "ruteo", "SOAP")}
      {caja(1260, "proveedor", "externo · puede fallar", true)}
      <svg style={{ position: "absolute", inset: 0 }} width={1920} height={1080}>
        <line x1={660} y1={495} x2={780} y2={495} stroke={C.grisClaro} strokeWidth={3} />
        <line x1={1140} y1={495} x2={1260} y2={495} stroke={C.rojo} strokeWidth={3} strokeDasharray="8 8" />
      </svg>
    </div>
  );
}

export const Narrado: React.FC = () => (
  <AbsoluteFill style={{ background: C.fondo }}>
    <Audio src={staticFile("voz/toma.mp3")} />
    {ORDEN.map((e) => {
      const Comp = ESCENAS[e];
      return (
        <Sequence key={e} from={INICIO[e]} durationInFrames={FIN[e] - INICIO[e]} name={e}>
          <Comp />
        </Sequence>
      );
    })}
    <Subtitulos />
  </AbsoluteFill>
);
