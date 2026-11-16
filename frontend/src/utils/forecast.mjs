// Lógica pura de la spec 010: sin DOM, sin red y sin reloj oculto.
// Solo todayInMadrid lee el reloj, y recibe el instante como parámetro.
// El workflow de GitHub Actions importa este módulo con `node` a secas, así que
// no puede depender de Astro, de Vite ni de ningún paquete.

export const SCHEMA_VERSION = 1;
export const EXPECTED_VARIABLES = 19;
export const MIN_HISTORY_POINTS = 30;
export const MAX_OBSERVATION_AGE_DAYS = 2;
export const MAX_MWH_DIFFERENCE = 1;

/** Estados de la previsión publicada (D-10-6). */
export const FORECAST_STATE = Object.freeze({
  OK: "ok",
  PENDING: "pendiente",
  STALE: "caducado",
  UNAVAILABLE: "no_disponible",
});

// Debe mantenerse alineada con MARCAS_DATOS_NO_REALES de forecast_cache.py (V10).
const NON_REAL_DATA_MARKS = [
  "no se pudieron leer",
  "sin datos históricos",
  "no hay una predicción propia",
  "simulad",
  "mock",
];

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const VERSION = /^\d{4}-\d{2}-\d{2}T\d{6}Z$/;
const HAS_OFFSET = /(Z|[+-]\d{2}:\d{2})$/;
const CHART_SERIES = ["fechas_hist", "real_gwh", "pred_gwh", "vel_norm", "racha_norm", "vel_ms", "racha_ms"];

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);

/** Verdadero solo para fechas YYYY-MM-DD que existen en el calendario. */
function isIsoDate(value) {
  const match = typeof value === "string" ? ISO_DATE.exec(value) : null;
  if (!match) return false;
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day
  );
}

/** Suma días a una fecha YYYY-MM-DD con Date.UTC, sin cruzar husos. */
function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

/** Fecha de hoy en Europe/Madrid para el instante dado, YYYY-MM-DD. */
export function todayInMadrid(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** Día siguiente a una fecha YYYY-MM-DD. */
export function tomorrowInMadrid(today) {
  return addDays(today, 1);
}

const shortDate = (isoDate) => `${isoDate.slice(8, 10)}/${isoDate.slice(5, 7)}`;
const fullDate = (isoDate) => `${shortDate(isoDate)}/${isoDate.slice(0, 4)}`;

/** «Datos del 16/11/2026 a las 05:02», siempre en hora de Madrid. */
export function generationLabel(snapshot) {
  const text = snapshot?.fecha_generacion;
  const instant = typeof text === "string" && HAS_OFFSET.test(text) ? Date.parse(text) : NaN;
  if (Number.isNaN(instant)) return "Fecha de generación no disponible";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("es-ES", {
      timeZone: "Europe/Madrid",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(instant))
      .map((part) => [part.type, part.value]),
  );
  return `Datos del ${parts.day}/${parts.month}/${parts.year} a las ${parts.hour}:${parts.minute}`;
}

/** Recorre el objeto y devuelve las rutas con números no finitos. */
function nonFinitePaths(value, path = "snapshot") {
  if (typeof value === "number") return Number.isFinite(value) ? [] : [path];
  if (Array.isArray(value)) return value.flatMap((item, index) => nonFinitePaths(item, `${path}[${index}]`));
  if (isObject(value)) return Object.entries(value).flatMap(([key, item]) => nonFinitePaths(item, `${path}.${key}`));
  return [];
}

/**
 * Comprobaciones que no dependen de la fecha de hoy: V1, V4, V5, V8–V12 y el
 * orden de V7. Si fallan, el snapshot es ilegible o está incompleto.
 */
function structuralProblems(snapshot) {
  if (!isObject(snapshot)) return ["V1: el snapshot no es un objeto"];

  const problems = [];
  const { prediccion, historico, grafico } = snapshot;

  // V1
  if (snapshot.schema_version !== SCHEMA_VERSION) problems.push(`V1: schema_version no es ${SCHEMA_VERSION}`);
  if (!VERSION.test(String(snapshot.version ?? ""))) problems.push("V1: version no tiene formato YYYY-MM-DDTHHMMSSZ");
  for (const key of ["fecha_objetivo", "fecha_emision", "fecha_observacion"]) {
    if (!isIsoDate(snapshot[key])) problems.push(`V1: ${key} no es una fecha válida`);
  }
  if (typeof snapshot.fecha_generacion !== "string" || Number.isNaN(Date.parse(snapshot.fecha_generacion))) {
    problems.push("V1: fecha_generacion no es un instante válido");
  }
  if (!isObject(prediccion)) problems.push("V1: falta prediccion");
  if (!Array.isArray(historico)) problems.push("V1: falta historico");
  if (!isObject(grafico)) problems.push("V1: falta grafico");
  if (!Array.isArray(snapshot.avisos)) problems.push("V1: avisos no es una lista");
  if (!isObject(prediccion) || !Array.isArray(historico) || !isObject(grafico)) return problems;

  // V4
  if (typeof prediccion.modelo !== "string" || !prediccion.modelo.trim()) problems.push("V4: modelo vacío");
  if (prediccion.n_variables !== EXPECTED_VARIABLES) problems.push(`V4: n_variables no es ${EXPECTED_VARIABLES}`);

  // V5
  const value = prediccion.prediccionMWh;
  if (!isFiniteNumber(value) || value <= 0) problems.push("V5: prediccionMWh no es un número finito mayor que cero");

  // V7 (orden) y V12
  const dates = historico.map((row) => (isObject(row) ? row.fecha : undefined));
  if (historico.length === 0) {
    problems.push("V7: historico vacío");
  } else if (!dates.every(isIsoDate)) {
    problems.push("V7: historico contiene fechas ilegibles");
  } else {
    if (dates.some((date, index) => index > 0 && date <= dates[index - 1])) {
      problems.push("V7: historico no está ordenado ni es estrictamente creciente");
    }
    if (snapshot.fecha_observacion !== dates.at(-1)) {
      problems.push("V7: fecha_observacion no es la última fecha del historico");
    }
  }
  if (historico.length < MIN_HISTORY_POINTS) {
    problems.push(`V12: historico tiene ${historico.length} puntos; se exigen al menos ${MIN_HISTORY_POINTS}`);
  }

  // V8
  const lengths = {};
  for (const key of CHART_SERIES) {
    if (Array.isArray(grafico[key])) lengths[key] = grafico[key].length;
    else problems.push(`V8: grafico.${key} no es una lista`);
  }
  if (new Set(Object.values(lengths)).size > 1) problems.push("V8: longitudes desalineadas en grafico");

  // V9
  const tomorrowChart = grafico.manana;
  if (!isObject(tomorrowChart)) {
    problems.push("V9: falta grafico.manana");
  } else {
    if (tomorrowChart.fecha !== snapshot.fecha_objetivo) problems.push("V9: grafico.manana.fecha no coincide con fecha_objetivo");
    const chartValue = tomorrowChart.prediccion_mwh;
    if (!isFiniteNumber(chartValue) || !isFiniteNumber(value) || Math.abs(chartValue - value) >= MAX_MWH_DIFFERENCE) {
      problems.push("V9: grafico.manana.prediccion_mwh difiere de prediccionMWh en 1 MWh o más");
    }
  }

  // V10
  if (!Array.isArray(grafico.avisos)) {
    problems.push("V10: grafico.avisos no es una lista");
  } else {
    for (const warning of grafico.avisos) {
      const text = String(warning).toLowerCase();
      if (NON_REAL_DATA_MARKS.some((mark) => text.includes(mark))) {
        problems.push(`V10: aviso de datos no reales en la gráfica: ${warning}`);
      }
    }
  }

  // V11
  for (const path of nonFinitePaths(snapshot)) problems.push(`V11: valor no finito en ${path}`);
  const badRow = historico.findIndex((row) => !isObject(row) || !isFiniteNumber(row.eolica));
  if (badRow !== -1) problems.push(`V11: historico[${badRow}].eolica no es un número`);

  return problems;
}

/**
 * Valida el snapshot completo frente a la fecha de hoy: V1–V5 y V7–V12.
 * V6 (las 19 variables y sus orígenes) solo se comprueba en el backend.
 * @param {object} snapshot
 * @param {string} today Fecha de Madrid, YYYY-MM-DD.
 * @returns {string[]} Problemas encontrados; vacío si es válido.
 */
export function validateSnapshot(snapshot, today) {
  const problems = structuralProblems(snapshot);
  if (!isObject(snapshot) || !isIsoDate(today)) {
    return isIsoDate(today) ? problems : [...problems, "today no es una fecha válida"];
  }
  const tomorrow = tomorrowInMadrid(today);

  // V2
  if (!(snapshot.prediccion?.fecha === snapshot.fecha_objetivo && snapshot.fecha_objetivo === tomorrow)) {
    problems.push(
      `V2: fecha de la predicción (${snapshot.prediccion?.fecha}), fecha_objetivo (${snapshot.fecha_objetivo}) y mañana (${tomorrow}) no coinciden`,
    );
  }

  // V3
  const issued = snapshot.prediccion?.fecha_emision;
  if (!(issued === today && snapshot.fecha_emision === issued)) {
    problems.push("V3: fecha_emision no es hoy o no coincide con la de la predicción");
  }

  // V7 (frescura)
  const oldest = addDays(today, -MAX_OBSERVATION_AGE_DAYS);
  if (!isIsoDate(snapshot.fecha_observacion) || snapshot.fecha_observacion < oldest) {
    problems.push(`V7: fecha_observacion tiene más de ${MAX_OBSERVATION_AGE_DAYS} días de antigüedad`);
  }

  return problems;
}

const UNAVAILABLE_MESSAGE =
  "No hay una previsión publicada válida. El resto de la página sigue siendo válido.";

/** Estado, tono y texto de la previsión según la fecha objetivo. */
function classify(snapshot, today) {
  const problems = structuralProblems(snapshot);
  if (problems.length > 0) {
    return { estado: FORECAST_STATE.UNAVAILABLE, motivo: problems[0], tono: "error", mensaje: UNAVAILABLE_MESSAGE };
  }

  const target = snapshot.fecha_objetivo;
  const tomorrow = tomorrowInMadrid(today);
  if (target === tomorrow) {
    return {
      estado: FORECAST_STATE.OK,
      motivo: null,
      tono: "ok",
      mensaje: `Previsión para el ${fullDate(target)}. ${generationLabel(snapshot)}.`,
    };
  }
  if (target === today) {
    return {
      estado: FORECAST_STATE.PENDING,
      motivo: "la previsión de mañana todavía no se ha publicado",
      tono: "info",
      mensaje: `La previsión de mañana todavía no se ha publicado. La última disponible es para hoy, ${shortDate(target)}.`,
    };
  }
  if (target < today) {
    return {
      estado: FORECAST_STATE.STALE,
      motivo: "la fecha objetivo ya pasó",
      tono: "aviso",
      mensaje: `La previsión publicada es del ${shortDate(snapshot.fecha_emision)} para el ${shortDate(target)}. No hay datos más recientes.`,
    };
  }
  return {
    estado: FORECAST_STATE.UNAVAILABLE,
    motivo: "la fecha objetivo es posterior a mañana",
    tono: "error",
    mensaje: UNAVAILABLE_MESSAGE,
  };
}

/**
 * Clasifica la previsión publicada: ok, pendiente, caducado o no_disponible.
 * @param {object} snapshot
 * @param {string} today Fecha de Madrid, YYYY-MM-DD.
 * @returns {{estado: string, motivo: string|null, tono: string, mensaje: string, objetivo: string|null}}
 */
export function snapshotStatus(snapshot, today) {
  const result = classify(snapshot, today);
  const objective = result.estado === FORECAST_STATE.UNAVAILABLE ? null : snapshot.fecha_objetivo;
  return { ...result, objetivo: objective };
}

/**
 * Texto del aviso cuando el objetivo no es mañana. Con la previsión de mañana
 * ya publicada no hay nada que avisar y devuelve null.
 */
export function staleMessage(snapshot, today) {
  const result = classify(snapshot, today);
  return result.estado === FORECAST_STATE.OK ? null : result.mensaje;
}

// Espejo de AVISOS_ESPERADOS en backend/app/services/forecast_cache.py.
const AVISOS_ESPERADOS = Object.freeze([
  "Paso capture_ree_forecast: fallo",
  "Paso download_aemet_data: parcial",
]);

/** Avisos que impiden tomar el snapshot por limpio; los esperables a esa hora no cuentan. */
export function avisosBloqueantes(snapshot) {
  const avisos = Array.isArray(snapshot?.avisos) ? snapshot.avisos : [];
  return avisos.filter((aviso) => !AVISOS_ESPERADOS.includes(aviso));
}
