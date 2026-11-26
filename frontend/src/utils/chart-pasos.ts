// Lectura de valores y botones anterior/siguiente para gráficas de Chart.js (spec 016).
// Permite recorrer la gráfica con el teclado o con el dedo y deja escrito el valor activo.
import type { ActiveElement, Chart, ChartEvent } from "chart.js";

interface Opciones {
  total: () => number;
  datasets: () => number[];
  texto: (indice: number) => string;
  vacio: string;
}

export function conectarPasos(chart: Chart<any, any, any>, raiz: HTMLElement, opciones: Opciones) {
  const lectura = raiz.querySelector<HTMLElement>("[data-lectura]");
  let actual: number | null = null;

  const escribir = (indice: number | null) => {
    actual = indice;
    if (lectura) lectura.textContent = indice == null ? opciones.vacio : opciones.texto(indice);
  };

  const activar = (indice: number) => {
    const elementos = opciones.datasets().map((datasetIndex) => ({ datasetIndex, index: indice }));
    if (elementos.length === 0) return;
    const punto = chart.getDatasetMeta(elementos[0].datasetIndex).data[indice];
    chart.setActiveElements(elementos);
    chart.tooltip?.setActiveElements(elementos, { x: punto?.x ?? 0, y: punto?.y ?? 0 });
    chart.update("none");
    escribir(indice);
  };

  raiz.querySelector("[data-prev]")?.addEventListener("click", () => {
    activar(actual == null ? opciones.total() - 1 : Math.max(0, actual - 1));
  });
  raiz.querySelector("[data-next]")?.addEventListener("click", () => {
    activar(actual == null ? 0 : Math.min(opciones.total() - 1, actual + 1));
  });
  chart.options.onHover = (_evento: ChartEvent, activos: ActiveElement[]) => {
    if (activos.length > 0) escribir(activos[0].index);
  };
  escribir(null);
  return { reiniciar: () => escribir(null) };
}
