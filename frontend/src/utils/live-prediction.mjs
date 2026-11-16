// Tarjeta de la previsión publicada. Sin red: los valores salen del snapshot en
// build y el navegador solo recalcula el estado con la fecha de hoy.
import { FORECAST_STATE, snapshotStatus, todayInMadrid } from "./forecast.mjs";
import { STATUS, formatMetric, formatDateEs, formatNumber } from "./evolution.mjs";

const REFERENCE_VARIABLES = 19;

const TONE_CLASSES = {
  ok: "text-green-700 dark:text-green-300",
  info: "text-blue-700 dark:text-blue-300",
  aviso: "text-amber-700 dark:text-amber-300",
  error: "text-red-700 dark:text-red-300",
};

/** Clases de color para el tono de un estado; vacío si el tono no se conoce. */
export function toneClass(tone) {
  return TONE_CLASSES[tone] ?? "";
}

function formatWind(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? `${formatNumber(value, 2)} m/s`
    : STATUS.UNAVAILABLE;
}

/**
 * Textos de la tarjeta para un snapshot y una fecha. Si el snapshot no es
 * válido, todos los campos valen «no disponible»; nunca se rellena con otro dato.
 */
export function cardView(snapshot, today = todayInMadrid()) {
  const status = snapshotStatus(snapshot, today);
  const fields = {};
  const names = ["valor", "fecha", "emision", "familia", "variables", "velmedia", "racha", "version"];

  if (status.estado === FORECAST_STATE.UNAVAILABLE) {
    for (const name of names) fields[name] = STATUS.UNAVAILABLE;
    return { estado: status.estado, tono: status.tono, mensaje: status.mensaje, campos: fields };
  }

  const prediction = snapshot.prediccion;
  const variables = prediction.n_variables;
  fields.valor = formatMetric(prediction.prediccionMWh, "mwh").replace(" MWh", "");
  fields.fecha = formatDateEs(snapshot.fecha_objetivo);
  fields.emision = formatDateEs(snapshot.fecha_emision);
  fields.familia = prediction.modelo || STATUS.UNAVAILABLE;
  fields.variables = String(variables);
  fields.velmedia = formatWind(prediction.features?.velmedia);
  fields.racha = formatWind(prediction.features?.racha);
  fields.version = variables === REFERENCE_VARIABLES
    ? `La previsión usa el modelo de referencia (${REFERENCE_VARIABLES} variables).`
    : `La previsión usa una versión distinta del modelo de referencia de ${REFERENCE_VARIABLES} variables. Las métricas de esta web corresponden a la referencia.`;
  return { estado: status.estado, tono: status.tono, mensaje: status.mensaje, campos: fields };
}

function setState(root, view) {
  root.dataset.state = view.estado;
  root.querySelectorAll('[data-field="estado"]').forEach((el) => {
    el.textContent = view.mensaje;
    // data-tone="none": fondos de color propio donde el tono de estado no contrasta.
    const tone = el.dataset.tone === "none" ? "" : toneClass(view.tono);
    el.className = `${el.dataset.baseClass ?? ""} ${tone}`.trim();
  });
}

/** Recalcula el estado de todos los bloques [data-live-prediction] con la fecha de hoy. */
export function initLivePrediction(snapshot) {
  const roots = [...document.querySelectorAll("[data-live-prediction]")];
  if (roots.length === 0) return;
  const view = cardView(snapshot, todayInMadrid());
  roots.forEach((root) => setState(root, view));
}
