import { loadFont } from "@remotion/google-fonts/Inter";

export const { fontFamily } = loadFont("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });

export const C = {
  fondo: "#F6F7F9",
  tinta: "#14171C",
  gris: "#5C6370",
  grisClaro: "#A3A9B3",
  linea: "#D5D9E0",
  caja: "#FFFFFF",
  azul: "#1F6FB2",
  azulSuave: "#E3EEF8",
  rojo: "#C0392B",
  rojoSuave: "#FBE7E4",
  verde: "#1E8E5A",
  verdeSuave: "#E1F4EA",
  ambar: "#B7791F",
  ambarSuave: "#FBF0DC",
};

export const FPS = 30;
export const s = (seg: number) => Math.round(seg * FPS);
