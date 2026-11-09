import React from "react";
import { Composition } from "remotion";
import { DURACION, Explicacion } from "./Explicacion";
import { DURACION_NARRADO, Narrado } from "./Narrado";
import { FPS } from "./tema";

export const Raiz: React.FC = () => (
  <>
    <Composition id="Narrado" component={Narrado} durationInFrames={DURACION_NARRADO} fps={FPS} width={1920} height={1080} />
    <Composition id="Explicacion" component={Explicacion} durationInFrames={DURACION} fps={FPS} width={1920} height={1080} />
  </>
);
