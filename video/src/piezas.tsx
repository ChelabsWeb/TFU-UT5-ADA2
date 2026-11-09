import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, fontFamily } from "./tema";

export const entrada = (frame: number, desde: number, dur = 18) =>
  interpolate(frame, [desde, desde + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

export const Fondo: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", inset: 0, background: C.fondo, fontFamily, color: C.tinta }}>{children}</div>
);

/** Subtítulo: renglones cortos, sin caja, que entran y salen. */
export const Leyenda: React.FC<{ lineas: [number, number, string][] }> = ({ lineas }) => {
  const f = useCurrentFrame();
  const activa = lineas.find(([a, b]) => f >= a && f < b);
  if (!activa) return null;
  const [a, b, texto] = activa;
  const op = Math.min(entrada(f, a, 8), interpolate(f, [b - 8, b], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 70,
        textAlign: "center",
        fontSize: 40,
        fontWeight: 500,
        letterSpacing: "-0.01em",
        color: C.tinta,
        opacity: op,
        transform: `translateY(${(1 - op) * 10}px)`,
      }}
    >
      {texto}
    </div>
  );
};

export const Titulo: React.FC<{ texto: string; desde?: number; arriba?: number }> = ({ texto, desde = 0, arriba = 70 }) => {
  const f = useCurrentFrame();
  const op = entrada(f, desde);
  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        top: arriba,
        fontSize: 52,
        fontWeight: 600,
        letterSpacing: "-0.02em",
        opacity: op,
        transform: `translateY(${(1 - op) * 14}px)`,
      }}
    >
      {texto}
    </div>
  );
};

export type Estado = "normal" | "caido" | "activo" | "alerta";

export const Caja: React.FC<{
  x: number;
  y: number;
  w?: number;
  h?: number;
  titulo: string;
  sub?: string;
  estado?: Estado;
  aparece?: number;
}> = ({ x, y, w = 230, h = 92, titulo, sub, estado = "normal", aparece = 0 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const k = spring({ frame: f - aparece, fps, config: { damping: 200 } });
  const colores = {
    normal: { bg: C.caja, borde: C.linea, txt: C.tinta },
    activo: { bg: C.azulSuave, borde: C.azul, txt: C.tinta },
    alerta: { bg: C.ambarSuave, borde: C.ambar, txt: C.tinta },
    caido: { bg: C.rojoSuave, borde: C.rojo, txt: C.grisClaro },
  }[estado];
  return (
    <div
      style={{
        position: "absolute",
        left: x - w / 2,
        top: y - h / 2,
        width: w,
        height: h,
        borderRadius: 14,
        background: colores.bg,
        border: `2px solid ${colores.borde}`,
        boxShadow: "0 1px 2px rgba(20,23,28,.06), 0 8px 24px rgba(20,23,28,.06)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        opacity: k,
        transform: `scale(${0.92 + 0.08 * k})`,
      }}
    >
      <div style={{ fontSize: 26, fontWeight: 600, color: colores.txt, letterSpacing: "-0.01em" }}>{titulo}</div>
      {sub && <div style={{ fontSize: 18, color: estado === "caido" ? C.rojo : C.gris, marginTop: 4 }}>{sub}</div>}
    </div>
  );
};

export type Punto = { x: number; y: number };

export const Flecha: React.FC<{ a: Punto; b: Punto; aparece?: number; color?: string; punteada?: boolean }> = ({
  a,
  b,
  aparece = 0,
  color = C.grisClaro,
  punteada,
}) => {
  const f = useCurrentFrame();
  const p = entrada(f, aparece, 20);
  const x2 = a.x + (b.x - a.x) * p;
  const y2 = a.y + (b.y - a.y) * p;
  return (
    <svg style={{ position: "absolute", inset: 0, overflow: "visible" }} width={1920} height={1080}>
      <line
        x1={a.x}
        y1={a.y}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={3}
        strokeDasharray={punteada ? "8 8" : undefined}
        strokeLinecap="round"
      />
    </svg>
  );
};

/** Un mensaje que viaja de a a b entre los frames [desde, desde+dur]. */
export const Paquete: React.FC<{ a: Punto; b: Punto; desde: number; dur?: number; color?: string; etiqueta?: string }> = ({
  a,
  b,
  desde,
  dur = 20,
  color = C.azul,
  etiqueta,
}) => {
  const f = useCurrentFrame();
  if (f < desde || f > desde + dur + 4) return null;
  const t = interpolate(f, [desde, desde + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const x = a.x + (b.x - a.x) * t;
  const y = a.y + (b.y - a.y) * t;
  const op = interpolate(f, [desde + dur, desde + dur + 4], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: x, top: y, opacity: op }}>
      <div
        style={{
          position: "absolute",
          left: -11,
          top: -11,
          width: 22,
          height: 22,
          borderRadius: 11,
          background: color,
          boxShadow: `0 0 0 6px ${color}33`,
        }}
      />
      {etiqueta && (
        <div
          style={{
            position: "absolute",
            left: 18,
            top: -40,
            whiteSpace: "nowrap",
            fontSize: 20,
            fontWeight: 600,
            color,
          }}
        >
          {etiqueta}
        </div>
      )}
    </div>
  );
};

export const Etiqueta: React.FC<{ x: number; y: number; texto: string; color?: string; fondo?: string; aparece?: number }> = ({
  x,
  y,
  texto,
  color = C.azul,
  fondo = C.azulSuave,
  aparece = 0,
}) => {
  const f = useCurrentFrame();
  const op = entrada(f, aparece, 10);
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `translate(-50%, -50%) scale(${0.9 + 0.1 * op})`,
        opacity: op,
        padding: "8px 16px",
        borderRadius: 999,
        background: fondo,
        color,
        fontSize: 22,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {texto}
    </div>
  );
};
