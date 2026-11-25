// Plugin global de Chart.js: toda gráfica toma texto y rejilla de los tokens del tema y se repinta al cambiarlo.
import { Chart } from "chart.js";
import { recolorear } from "./tema";

Chart.register({
  id: "aeroTema",
  afterInit(chart) {
    recolorear(chart);
    window.addEventListener("aero-tema", () => {
      if (chart.canvas?.isConnected) recolorear(chart);
    });
  },
});
