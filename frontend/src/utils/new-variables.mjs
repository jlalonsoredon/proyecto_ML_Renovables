// Cálculos de la sección «Las nuevas variables» (spec 013). Funciones puras: sin DOM ni red.

/** Media aritmética de una lista de números. */
function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** Coeficiente de correlación de Pearson entre dos series de la misma longitud. */
export function pearson(xs, ys) {
  if (xs.length !== ys.length || xs.length < 2) throw new Error("Las series deben tener la misma longitud (≥ 2)");
  const mx = mean(xs);
  const my = mean(ys);
  let sxy = 0;
  let sxx = 0;
  let syy = 0;
  for (let i = 0; i < xs.length; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxy += dx * dy;
    sxx += dx * dx;
    syy += dy * dy;
  }
  return sxy / Math.sqrt(sxx * syy);
}

/** Recta de mínimos cuadrados y = a + b·x. */
export function linearFit(xs, ys) {
  const mx = mean(xs);
  const my = mean(ys);
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < xs.length; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) ** 2;
  }
  const slope = sxy / sxx;
  return { intercept: my - slope * mx, slope };
}

/**
 * Resumen por tramos del eje horizontal: cuántos días caen en cada tramo y la media del vertical.
 * Los tramos son [a, b), salvo el último, que incluye su límite superior. Los tramos vacíos se omiten.
 */
export function binSummary(xs, ys, edges) {
  const rows = [];
  for (let k = 0; k < edges.length - 1; k++) {
    const from = edges[k];
    const to = edges[k + 1];
    const last = k === edges.length - 2;
    const selected = [];
    for (let i = 0; i < xs.length; i++) {
      if ((xs[i] >= from && xs[i] < to) || (last && xs[i] === to)) selected.push(ys[i]);
    }
    if (selected.length > 0) rows.push({ from, to, days: selected.length, mean: mean(selected) });
  }
  return rows;
}
