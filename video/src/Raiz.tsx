import React from "react";
import { Composition } from "remotion";
import { DURACION, Explicacion } from "./Explicacion";
import { FPS } from "./tema";

export const Raiz: React.FC = () => (
  <Composition id="Explicacion" component={Explicacion} durationInFrames={DURACION} fps={FPS} width={1920} height={1080} />
);
