// Versión para las gráficas con Chart.js por CDN: texto y rejilla siguen los tokens del tema (spec 012).
(function () {
  if (!window.Chart) return;
  function token(n) { return getComputedStyle(document.documentElement).getPropertyValue("--" + n).trim(); }
  function recolorear(chart) {
    var texto = token("muted"), rejilla = token("grid"), o = chart.options;
    Object.keys(o.scales || {}).forEach(function (k) {
      var e = o.scales[k];
      e.ticks = Object.assign({}, e.ticks, { color: texto });
      if (e.title) e.title.color = texto;
      if (!e.grid || e.grid.drawOnChartArea !== false) e.grid = Object.assign({}, e.grid, { color: rejilla });
    });
    var l = o.plugins && o.plugins.legend && o.plugins.legend.labels;
    if (l) l.color = texto;
    chart.update("none");
  }
  Chart.register({
    id: "aeroTema",
    afterInit: function (chart) {
      recolorear(chart);
      window.addEventListener("aero-tema", function () { if (chart.canvas && chart.canvas.isConnected) recolorear(chart); });
    },
  });
})();
