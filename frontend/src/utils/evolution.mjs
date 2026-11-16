// Lógica pura de la spec 009: sin DOM, sin red y sin reloj.
// Las decisiones sobre fechas reciben "today" (YYYY-MM-DD, hora peninsular).

/** Vocabulario de estados visible en la interfaz (D-9-15). */
export const STATUS = Object.freeze({
  CURRENT: "vigente",
  HISTORICAL: "histórico",
  UNAVAILABLE: "no disponible",
  STALE: "caducado",
});

// Regla de día completo heredada de la spec 008 (D-9-13).
const CONTEXT_DAYS = 7;
const MIN_CONTEXT_VALUES = 5;
const MIN_RATIO = 0.6;

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Configuración de formato por métrica: decimales máximos y unidad. */
const METRIC_FORMAT = {
  rmse: { digits: 1, unit: " MWh" },
  mae: { digits: 1, unit: " MWh" },
  r2: { digits: 4, unit: "" },
  mape: { digits: 2, unit: " %" },
  mwh: { digits: 0, unit: " MWh" },
};

const isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);

/** @param {number[]} values */
function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Indica si el día en la posición "index" está completo: necesita al menos
 * cinco valores entre los siete días anteriores y alcanzar el 60 % de su
 * mediana. Con menos contexto no se da por completo (CE-9).
 * @param {(number|null)[]} values Generación eólica diaria, en orden.
 * @param {number} index
 */
export function isCompleteDay(values, index) {
  const value = values[index];
  if (!isFiniteNumber(value)) return false;
  const context = values
    .slice(Math.max(0, index - CONTEXT_DAYS), index)
    .filter(isFiniteNumber);
  if (context.length < MIN_CONTEXT_VALUES) return false;
  const reference = median(context);
  if (reference <= 0) return value > 0;
  return value >= MIN_RATIO * reference;
}

/**
 * Descarta los días finales incompletos y devuelve los "size" últimos (D-9-14).
 * @param {{fecha: string, eolica: number|null}[]} series Ordenada por fecha.
 * @param {number} size
 */
export function selectCompleteWindow(series, size) {
  const values = series.map((day) => day.eolica);
  let end = series.length;
  while (end > 0 && !isCompleteDay(values, end - 1)) end -= 1;
  return {
    days: series.slice(Math.max(0, end - size), end),
    discarded: series.length - end,
  };
}

/**
 * Dos filas son comparables si comparten variables, ventana y días, y la
 * ventana es conocida (D-9-8).
 */
export function areComparable(rowA, rowB) {
  const a = rowA?.protocolo;
  const b = rowB?.protocolo;
  if (!a || !b) return false;
  if (!a.desde || !a.hasta || !a.dias) return false;
  return (
    a.variables === b.variables &&
    a.desde === b.desde &&
    a.hasta === b.hasta &&
    a.dias === b.dias
  );
}

/** Rechaza valores no finitos, errores negativos y R² mayor que 1 (CE-12). */
export function isPlausibleMetric(value, metric) {
  if (!isFiniteNumber(value)) return false;
  if (metric === "r2") return value <= 1;
  return value >= 0;
}

/** Diferencia B − A solo entre filas comparables con valores plausibles. */
export function metricDelta(rowA, rowB, metric) {
  if (!areComparable(rowA, rowB)) return null;
  const a = rowA[metric];
  const b = rowB[metric];
  if (!isPlausibleMetric(a, metric) || !isPlausibleMetric(b, metric)) return null;
  return b - a;
}

/** Número en formato español con separador de miles siempre. */
export function formatNumber(value, maxDigits) {
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: maxDigits,
    useGrouping: "always",
  }).format(value);
}

/** Métrica formateada con su unidad, o «no disponible». */
export function formatMetric(value, metric) {
  const config = METRIC_FORMAT[metric];
  if (!config) return STATUS.UNAVAILABLE;
  const plausible = metric === "mwh" ? isFiniteNumber(value) && value >= 0 : isPlausibleMetric(value, metric);
  if (!plausible) return STATUS.UNAVAILABLE;
  return formatNumber(value, config.digits) + config.unit;
}

/** Fecha larga en español, sin conversión de zona horaria. */
export function formatDateEs(isoDate) {
  const match = typeof isoDate === "string" ? ISO_DATE.exec(isoDate) : null;
  if (!match) return STATUS.UNAVAILABLE;
  const [, year, month, day] = match;
  const monthName = MONTHS[Number(month) - 1];
  if (!monthName || Number(day) < 1 || Number(day) > 31) return STATUS.UNAVAILABLE;
  return `${Number(day)} de ${monthName} de ${year}`;
}

/** Estado declarado por una fila de métricas. */
export function rowStatus(row) {
  const declared = row?.estado;
  return Object.values(STATUS).includes(declared) ? declared : STATUS.UNAVAILABLE;
}
