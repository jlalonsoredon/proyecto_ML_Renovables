// Pruebas de la lógica de la previsión publicada (spec 010, plan §5).
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

import {
  FORECAST_STATE,
  generationLabel,
  snapshotStatus,
  staleMessage,
  todayInMadrid,
  tomorrowInMadrid,
  validateSnapshot,
} from "../src/utils/forecast.mjs";
import { cardView, toneClass } from "../src/utils/live-prediction.mjs";

const TODAY = "2026-11-16";
const TOMORROW = "2026-11-17";

function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

const FEATURES = [
  "velmedia", "racha", "mes", "dia_semana", "dia_año",
  "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
  "vel_ma3", "vel_ma7", "vel_ma14",
  "racha_ma3", "racha_ma7", "racha_ma14",
  "eolica_ma7", "sol_lag1", "tmed_lag1", "eolica_prev",
];

/** Snapshot válido emitido el 16/11 para el 17/11, con datos de muestra. */
function buildSnapshot() {
  const historico = Array.from({ length: 45 }, (_, index) => ({
    fecha: addDays("2026-11-14", index - 44),
    eolica: 100000 + index * 1000,
  }));
  const serie = (value) => Array.from({ length: 30 }, () => value);
  const vector = Object.fromEntries(FEATURES.map((name, index) => [name, index + 1]));
  const origenes = Object.fromEntries(FEATURES.map((name) => [name, "observacion"]));
  return {
    schema_version: 1,
    version: "2026-11-16T050213Z",
    fecha_generacion: "2026-11-16T05:02:13+01:00",
    fecha_objetivo: TOMORROW,
    fecha_emision: TODAY,
    fecha_observacion: "2026-11-14",
    prediccion: {
      fecha: TOMORROW,
      prediccionMWh: 278461,
      modelo: "Linear Regression",
      features: { velmedia: 3.17, racha: 6.4 },
      n_variables: 19,
      vector_entrada: vector,
      origenes,
      fecha_emision: TODAY,
      emitida_en: "2026-11-16T05:01:44+01:00",
    },
    historico,
    grafico: {
      fechas_hist: serie("2026-10-16"),
      real_gwh: serie(1.23),
      pred_gwh: serie(1.24),
      vel_norm: serie(0.31),
      racha_norm: serie(-0.42),
      vel_ms: serie(3.1),
      racha_ms: serie(6.4),
      manana: { fecha: TOMORROW, pred_gwh: 278.46, prediccion_mwh: 278461.37 },
      predicciones_propias: [],
      avisos: [],
    },
    avisos: [],
  };
}

const clone = (value) => structuredClone(value);
const countProblems = (problems, prefix) => problems.filter((problem) => problem.startsWith(prefix)).length;

test("tomorrowInMadrid cruza mes, año y 29 de febrero", () => {
  assert.equal(tomorrowInMadrid("2026-11-30"), "2026-12-01");
  assert.equal(tomorrowInMadrid("2026-12-31"), "2027-01-01");
  assert.equal(tomorrowInMadrid("2028-02-28"), "2028-02-29");
  assert.equal(tomorrowInMadrid("2028-02-29"), "2028-03-01");
  assert.equal(tomorrowInMadrid("2027-02-28"), "2027-03-01");
});

test("un snapshot válido evaluado con su fecha no tiene problemas", () => {
  assert.deepEqual(validateSnapshot(buildSnapshot(), TODAY), []);
});

test("falta prediccion o grafico: un problema por clave", () => {
  const sinPrediccion = buildSnapshot();
  delete sinPrediccion.prediccion;
  const problemasA = validateSnapshot(sinPrediccion, TODAY);
  assert.equal(countProblems(problemasA, "V1: falta prediccion"), 1);
  assert.equal(countProblems(problemasA, "V1: falta grafico"), 0);

  const sinGrafico = buildSnapshot();
  delete sinGrafico.grafico;
  const problemasB = validateSnapshot(sinGrafico, TODAY);
  assert.equal(countProblems(problemasB, "V1: falta grafico"), 1);
  assert.equal(countProblems(problemasB, "V1: falta prediccion"), 0);
  assert.equal(snapshotStatus(sinGrafico, TODAY).estado, FORECAST_STATE.UNAVAILABLE);
});

test("fecha_objetivo de ayer: caducado con el texto correcto", () => {
  const status = snapshotStatus(buildSnapshot(), "2026-11-18");
  assert.equal(status.estado, FORECAST_STATE.STALE);
  assert.equal(status.tono, "aviso");
  assert.equal(
    status.mensaje,
    "La previsión publicada es del 16/11 para el 17/11. No hay datos más recientes.",
  );
});

test("fecha_objetivo de hoy: pendiente con el texto informativo", () => {
  const status = snapshotStatus(buildSnapshot(), TOMORROW);
  assert.equal(status.estado, FORECAST_STATE.PENDING);
  assert.equal(status.tono, "info");
  assert.equal(
    status.mensaje,
    "La previsión de mañana todavía no se ha publicado. La última disponible es para hoy, 17/11.",
  );
});

test("n_variables 16 es no_disponible", () => {
  const snapshot = buildSnapshot();
  snapshot.prediccion.n_variables = 16;
  assert.equal(snapshotStatus(snapshot, TODAY).estado, FORECAST_STATE.UNAVAILABLE);
  assert.equal(countProblems(validateSnapshot(snapshot, TODAY), "V4"), 1);
});

test("NaN en prediccionMWh es no_disponible", () => {
  const snapshot = buildSnapshot();
  snapshot.prediccion.prediccionMWh = Number.NaN;
  assert.equal(snapshotStatus(snapshot, TODAY).estado, FORECAST_STATE.UNAVAILABLE);
  assert.equal(countProblems(validateSnapshot(snapshot, TODAY), "V5"), 1);
});

test("longitudes desalineadas en grafico se señalan; una lista que no es lista, también", () => {
  const desalineado = buildSnapshot();
  desalineado.grafico.vel_ms.pop();
  const problemasA = validateSnapshot(desalineado, TODAY);
  assert.equal(countProblems(problemasA, "V8"), 1);
  assert.equal(snapshotStatus(desalineado, TODAY).estado, FORECAST_STATE.UNAVAILABLE);

  const noLista = buildSnapshot();
  noLista.grafico.racha_norm = "no es una lista";
  assert.equal(countProblems(validateSnapshot(noLista, TODAY), "V8: grafico.racha_norm no es una lista"), 1);
});

test("generationLabel en dos husos distintos da el mismo texto", () => {
  const conOffset = buildSnapshot();
  conOffset.fecha_generacion = "2026-11-16T03:12:44+01:00";
  const enUtc = buildSnapshot();
  enUtc.fecha_generacion = "2026-11-16T02:12:44Z";
  assert.equal(generationLabel(conOffset), "Datos del 16/11/2026 a las 03:12");
  assert.equal(generationLabel(enUtc), generationLabel(conOffset));
});

test("el snapshot real del repositorio pasa validateSnapshot y snapshotStatus", (t) => {
  const ruta = new URL("../src/data/forecast-snapshot.json", import.meta.url);
  if (!existsSync(ruta)) {
    t.skip("forecast-snapshot.json aún no existe: se siembra en T-10-09");
    return;
  }
  const snapshot = JSON.parse(readFileSync(ruta, "utf8"));
  const emitido = snapshot.fecha_emision;
  assert.deepEqual(validateSnapshot(snapshot, emitido), []);
  assert.equal(snapshotStatus(snapshot, emitido).estado, FORECAST_STATE.OK);
});

test("un build de hace dos días, evaluado con la fecha de hoy, da caducado", () => {
  const status = snapshotStatus(buildSnapshot(), "2026-11-19");
  assert.equal(status.estado, FORECAST_STATE.STALE);
  assert.match(staleMessage(buildSnapshot(), "2026-11-19"), /La previsión publicada es del 16\/11/);
});

test("el estado no depende de nada más que de su entrada", () => {
  const snapshot = buildSnapshot();
  const primera = snapshotStatus(snapshot, TOMORROW);
  const segunda = snapshotStatus(clone(snapshot), TOMORROW);
  assert.deepEqual(primera, segunda);
  assert.deepEqual(validateSnapshot(snapshot, TODAY), validateSnapshot(clone(snapshot), TODAY));
});

test("validateSnapshot rechaza avisos con marcas de datos simulados", () => {
  const simulado = buildSnapshot();
  simulado.grafico.avisos = ["Datos simulados de demostración"];
  assert.equal(countProblems(validateSnapshot(simulado, TODAY), "V10"), 1);

  const sinLeer = buildSnapshot();
  sinLeer.grafico.avisos = ["No se pudieron leer datos de viento históricos"];
  assert.equal(countProblems(validateSnapshot(sinLeer, TODAY), "V10"), 1);

  assert.equal(countProblems(validateSnapshot(buildSnapshot(), TODAY), "V10"), 0);
});

test("generationLabel usa fecha_generacion: un snapshot de las 03:12 no muestra las 05:00", () => {
  const snapshot = buildSnapshot();
  snapshot.fecha_generacion = "2026-11-16T03:12:44+01:00";
  assert.equal(generationLabel(snapshot), "Datos del 16/11/2026 a las 03:12");
  assert.ok(!snapshotStatus(snapshot, TODAY).mensaje.includes("05:00"));
});

test("todayInMadrid con un instante UTC fijo devuelve la fecha de Madrid en verano e invierno", () => {
  assert.equal(todayInMadrid(new Date("2026-07-15T22:30:00Z")), "2026-07-16");
  assert.equal(todayInMadrid(new Date("2026-07-15T21:59:00Z")), "2026-07-15");
  assert.equal(todayInMadrid(new Date("2026-12-15T22:30:00Z")), "2026-12-15");
  assert.equal(todayInMadrid(new Date("2026-12-15T23:00:00Z")), "2026-12-16");
});

test("cardView con un snapshot válido muestra sus valores y el estado ok", () => {
  const view = cardView(buildSnapshot(), TODAY);
  assert.equal(view.estado, FORECAST_STATE.OK);
  assert.equal(view.campos.valor, "278.461");
  assert.equal(view.campos.fecha, "17 de noviembre de 2026");
  assert.equal(view.campos.familia, "Linear Regression");
  assert.equal(view.campos.variables, "19");
  assert.equal(view.mensaje, "Previsión para el 17/11/2026. Datos del 16/11/2026 a las 05:02.");
});

test("cardView con el mismo snapshot cambia de estado solo con la fecha", () => {
  const snapshot = buildSnapshot();
  assert.equal(cardView(snapshot, TODAY).estado, FORECAST_STATE.OK);
  assert.equal(cardView(snapshot, TOMORROW).estado, FORECAST_STATE.PENDING);
  assert.equal(cardView(snapshot, "2026-11-19").estado, FORECAST_STATE.STALE);
});

test("cardView con un snapshot inválido no rellena ningún campo", () => {
  const snapshot = buildSnapshot();
  snapshot.prediccion.n_variables = 16;
  const view = cardView(snapshot, TODAY);
  assert.equal(view.estado, FORECAST_STATE.UNAVAILABLE);
  assert.ok(Object.values(view.campos).every((text) => text === "no disponible"));
  assert.equal(cardView(null, TODAY).estado, FORECAST_STATE.UNAVAILABLE);
});

test("toneClass devuelve vacío para un tono desconocido", () => {
  assert.equal(toneClass("inventado"), "");
  assert.notEqual(toneClass("aviso"), "");
});
