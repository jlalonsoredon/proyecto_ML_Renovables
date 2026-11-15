// Frontera con el navegador: lee reloj, red y DOM. Las decisiones se delegan
// en evolution.mjs para poder probarlas sin navegador.
import { STATUS, predictionStatus, formatMetric, formatDateEs, formatNumber } from "./evolution.mjs";

export const API_BASE_URL = import.meta.env.PUBLIC_API_URL || "http://localhost:8000";

/** Tiempo máximo de espera: tolera el arranque en frío del servicio (P-9-6). */
export const TIMEOUT_MS = 60_000;

/** Versión del modelo de referencia (D-9-6). */
const REFERENCE_VARIABLES = 19;

/** Fecha de hoy en hora peninsular, YYYY-MM-DD. */
export function todayInMadrid(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** Petición JSON con tiempo de espera. Lanza un error si falla o expira. */
export async function fetchJson(path, timeoutMs = TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { signal: controller.signal });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

const STATE_MESSAGES = {
  loading: "Cargando la predicción… El servicio puede tardar hasta un minuto en arrancar.",
  ok: "Predicción disponible.",
  caducado: `Dato ${STATUS.STALE}: la fecha objetivo ya ha pasado.`,
  no_disponible: `Predicción ${STATUS.UNAVAILABLE}: el servicio no ha devuelto una predicción válida.`,
  error: "No se ha podido contactar con el servicio. El resto de la página sigue siendo válido.",
};

const STATE_CLASSES = {
  ok: "text-green-700 dark:text-green-300",
  caducado: "text-amber-700 dark:text-amber-300",
  no_disponible: "text-amber-700 dark:text-amber-300",
  error: "text-red-700 dark:text-red-300",
  loading: "",
};

function setField(root, name, text) {
  root.querySelectorAll(`[data-field="${name}"]`).forEach((el) => {
    el.textContent = text;
  });
}

function setState(root, state) {
  root.dataset.state = state;
  root.setAttribute("aria-busy", state === "loading" ? "true" : "false");
  root.querySelectorAll('[data-field="estado"]').forEach((el) => {
    el.textContent = STATE_MESSAGES[state];
    // data-tone="none": fondos de color propio donde el tono de estado no contrasta.
    const tone = el.dataset.tone === "none" ? "" : STATE_CLASSES[state] ?? "";
    el.className = `${el.dataset.baseClass ?? ""} ${tone}`.trim();
  });
}

function formatWind(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? `${formatNumber(value, 2)} m/s`
    : STATUS.UNAVAILABLE;
}

function render(root, response, today) {
  const status = predictionStatus(response, today);
  setState(root, status.state);
  if (status.state === "no_disponible") {
    ["valor", "fecha", "familia", "variables", "emision", "velmedia", "racha", "version"].forEach(
      (name) => setField(root, name, STATUS.UNAVAILABLE),
    );
    return;
  }
  setField(root, "valor", formatMetric(status.valueMWh, "mwh").replace(" MWh", ""));
  setField(root, "fecha", formatDateEs(status.target));
  setField(root, "familia", status.family ?? STATUS.UNAVAILABLE);
  setField(root, "variables", status.nVariables === null ? STATUS.UNAVAILABLE : String(status.nVariables));
  setField(root, "emision", status.issuedOn ? formatDateEs(status.issuedOn) : STATUS.UNAVAILABLE);
  setField(root, "velmedia", formatWind(response?.features?.velmedia));
  setField(root, "racha", formatWind(response?.features?.racha));

  const version = status.nVariables === REFERENCE_VARIABLES
    ? `El servicio responde con el modelo de referencia (${REFERENCE_VARIABLES} variables).`
    : `El servicio responde con una versión distinta del modelo de referencia de ${REFERENCE_VARIABLES} variables. Las métricas de esta web corresponden a la referencia.`;
  setField(root, "version", version);
}

/** Rellena todos los bloques [data-live-prediction] con una sola petición. */
export async function initLivePrediction() {
  const roots = [...document.querySelectorAll("[data-live-prediction]")];
  if (roots.length === 0) return;
  roots.forEach((root) => setState(root, "loading"));

  const today = todayInMadrid();
  try {
    const response = await fetchJson("/api/prediction");
    roots.forEach((root) => render(root, response, today));
  } catch (error) {
    // 503: el servicio responde, pero no tiene una predicción válida.
    if (error?.status === 503) {
      roots.forEach((root) => render(root, null, today));
    } else {
      roots.forEach((root) => setState(root, "error"));
    }
  }
}
