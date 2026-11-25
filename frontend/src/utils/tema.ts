// Tema claro/oscuro (spec 012, D-12-3). Oscuro por defecto; se guarda en localStorage con la clave «aero-tema».
import type { Chart } from "chart.js";

export const CLAVE_TEMA = "aero-tema";
export type Tema = "oscuro" | "claro";

export function temaActual(): Tema {
  return document.documentElement.classList.contains("dark") ? "oscuro" : "claro";
}

export function aplicarTema(tema: Tema) {
  document.documentElement.classList.toggle("dark", tema === "oscuro");
  try {
    localStorage.setItem(CLAVE_TEMA, tema);
  } catch {
    /* sin almacenamiento: el tema no se recuerda */
  }
  window.dispatchEvent(new CustomEvent("aero-tema", { detail: tema }));
}

/** Valor de un token CSS (muted, grid, ink...) con el tema actual. */
export function token(nombre: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${nombre}`).trim();
}

/** Repinta texto y rejilla de una gráfica con los tokens del tema actual. */
export function recolorear(chart: Chart) {
  const texto = token("muted");
  const rejilla = token("grid");
  const opciones: any = chart.options;
  for (const escala of Object.values<any>(opciones.scales ?? {})) {
    escala.ticks = { ...(escala.ticks ?? {}), color: texto };
    if (escala.title) escala.title.color = texto;
    if (escala.grid?.drawOnChartArea !== false) escala.grid = { ...(escala.grid ?? {}), color: rejilla };
  }
  // Series con color de token: `tokenColor` (línea) y `tokenBg` (relleno).
  for (const d of chart.data.datasets as any[]) {
    if (d.tokenColor) d.borderColor = token(d.tokenColor);
    if (d.tokenBg) d.backgroundColor = token(d.tokenBg);
  }
  const leyenda = opciones.plugins?.legend?.labels;
  if (leyenda) leyenda.color = texto;
  chart.update("none");
}

/** Hace que la gráfica siga el tema: se colorea ya y se repinta al cambiarlo. */
export function seguirTema(chart: Chart) {
  window.addEventListener("aero-tema", () => recolorear(chart));
  recolorear(chart);
}
