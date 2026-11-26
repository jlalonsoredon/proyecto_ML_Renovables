// Cálculos del análisis exploratorio de Proceso (spec 016). Funciones puras: sin DOM ni red.

/** Escala común (como StandardScaler): media 0 y desviación típica poblacional 1. */
export function standardize(values) {
  const n = values.length;
  const mean = values.reduce((sum, v) => sum + v, 0) / n;
  const std = Math.sqrt(values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / n);
  return values.map((v) => (v - mean) / std);
}

/**
 * Histograma de `bins` tramos iguales entre `min` y `max`. Devuelve los centros,
 * los recuentos y cuántos valores quedaron fuera del rango (no se reparten en los extremos).
 */
export function histogram(values, min, max, bins) {
  const width = (max - min) / bins;
  const counts = new Array(bins).fill(0);
  let outside = 0;
  for (const v of values) {
    if (v < min || v > max) {
      outside++;
      continue;
    }
    counts[Math.min(bins - 1, Math.floor((v - min) / width))]++;
  }
  const centers = counts.map((_, i) => min + width * (i + 0.5));
  return { centers, counts, outside };
}

/** Domingo (YYYY-MM-DD) que cierra la semana de lunes a domingo de una fecha. */
export function weekEnding(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const toSunday = (7 - date.getUTCDay()) % 7;
  date.setUTCDate(date.getUTCDate() + toSunday);
  return date.toISOString().slice(0, 10);
}

/**
 * Medias semanales (semanas de lunes a domingo, etiquetadas por su domingo) de varias series
 * diarias que comparten las mismas fechas, en orden cronológico.
 */
export function weeklyMeans(dates, seriesByKey) {
  const keys = Object.keys(seriesByKey);
  const groups = new Map();
  dates.forEach((date, i) => {
    const week = weekEnding(date);
    if (!groups.has(week)) groups.set(week, { n: 0, sums: Object.fromEntries(keys.map((k) => [k, 0])) });
    const group = groups.get(week);
    group.n++;
    for (const k of keys) group.sums[k] += seriesByKey[k][i];
  });
  const weeks = [...groups.keys()].sort();
  const means = Object.fromEntries(keys.map((k) => [k, weeks.map((w) => groups.get(w).sums[k] / groups.get(w).n)]));
  return { weeks, means };
}
