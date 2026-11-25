// Pruebas de la lógica pura y de los datos congelados de la spec 009.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  STATUS,
  isCompleteDay,
  selectCompleteWindow,
  areComparable,
  metricDelta,
  isPlausibleMetric,
  formatMetric,
  rowStatus,
  formatDateEs,
} from "../src/utils/evolution.mjs";

const readJson = (name) =>
  JSON.parse(readFileSync(new URL(`../src/data/${name}`, import.meta.url), "utf8"));

// Serie diaria a partir de valores de eólica, empezando el 2026-10-01.
function dailySeries(values) {
  return values.map((eolica, i) => {
    const day = new Date(Date.UTC(2026, 9, 1 + i));
    return { fecha: day.toISOString().slice(0, 10), eolica };
  });
}

// ── Día completo ────────────────────────────────────────────────────────────

test("un día normal es completo", () => {
  const values = [200, 210, 190, 205, 195, 200, 210, 180];
  assert.equal(isCompleteDay(values, 7), true);
});

test("un día por debajo del 60 % de la mediana no es completo", () => {
  const values = [200, 210, 190, 205, 195, 200, 210, 100];
  assert.equal(isCompleteDay(values, 7), false);
});

test("un día a cero no es completo", () => {
  const values = [200, 210, 190, 205, 195, 200, 210, 0];
  assert.equal(isCompleteDay(values, 7), false);
});

test("con menos de cinco valores de entorno el día no es completo", () => {
  const values = [200, 210, 190, 205, 180];
  assert.equal(isCompleteDay(values, 4), false);
});

test("un valor ausente no es completo", () => {
  const values = [200, 210, 190, 205, 195, 200, 210, null];
  assert.equal(isCompleteDay(values, 7), false);
});

// ── Ventana de 30 días ──────────────────────────────────────────────────────

test("45 días con el último incompleto devuelven 30 completos", () => {
  const values = Array.from({ length: 45 }, () => 200);
  values[44] = 0;
  const result = selectCompleteWindow(dailySeries(values), 30);
  assert.equal(result.days.length, 30);
  assert.equal(result.discarded, 1);
  assert.equal(result.days.at(-1).fecha, "2026-11-13");
});

test("varios días finales incompletos se descartan seguidos", () => {
  const values = Array.from({ length: 45 }, () => 200);
  values[43] = 50;
  values[44] = 0;
  const result = selectCompleteWindow(dailySeries(values), 30);
  assert.equal(result.days.length, 30);
  assert.equal(result.discarded, 2);
});

test("con menos días completos que el tamaño se devuelven los que haya", () => {
  const values = Array.from({ length: 20 }, () => 200);
  const result = selectCompleteWindow(dailySeries(values), 30);
  assert.equal(result.days.length, 20);
});

test("una serie vacía devuelve una ventana vacía", () => {
  const result = selectCompleteWindow([], 30);
  assert.deepEqual(result.days, []);
});

// ── Comparabilidad ──────────────────────────────────────────────────────────

const lr19 = {
  modelo: "Linear Regression",
  protocolo: { variables: 19, desde: "2025-11-22", hasta: "2026-11-10", dias: 354 },
  rmse: 23108.4,
};
const lgbm19 = {
  modelo: "LightGBM",
  protocolo: { variables: 19, desde: "2025-11-22", hasta: "2026-11-10", dias: 354 },
  rmse: 20246.4,
};
const baseline = {
  modelo: "Linear Regression",
  protocolo: { variables: 16, desde: null, hasta: null, dias: null },
  rmse: 60433,
};

test("la línea base y la referencia no son comparables", () => {
  assert.equal(areComparable(baseline, lr19), false);
  assert.equal(metricDelta(baseline, lr19, "rmse"), null);
});

test("dos modelos con el mismo protocolo son comparables", () => {
  assert.equal(areComparable(lr19, lgbm19), true);
  assert.ok(Math.abs(metricDelta(lr19, lgbm19, "rmse") - -2862) < 0.001);
});

test("una ventana desconocida nunca es comparable, ni consigo misma", () => {
  assert.equal(areComparable(baseline, baseline), false);
});

test("no hay diferencia si una métrica es implausible", () => {
  const broken = { ...lgbm19, rmse: -5 };
  assert.equal(metricDelta(lr19, broken, "rmse"), null);
});

// ── Formato ─────────────────────────────────────────────────────────────────

test("las métricas se formatean en español", () => {
  assert.equal(formatMetric(23108.355669990728, "rmse"), "23.108,4 MWh");
  assert.equal(formatMetric(60433, "rmse"), "60.433 MWh");
  assert.equal(formatMetric(0.9307591979859493, "r2"), "0,9308");
  assert.equal(formatMetric(0.579, "r2"), "0,579");
  assert.equal(formatMetric(41.73, "mape"), "41,73 %");
  assert.equal(formatMetric(5000, "mae"), "5.000 MWh");
});

test("una métrica ausente o implausible es «no disponible»", () => {
  assert.equal(formatMetric(null, "mape"), STATUS.UNAVAILABLE);
  assert.equal(formatMetric(undefined, "rmse"), STATUS.UNAVAILABLE);
  assert.equal(formatMetric(Number.NaN, "rmse"), STATUS.UNAVAILABLE);
  assert.equal(formatMetric(1.2, "r2"), STATUS.UNAVAILABLE);
  assert.equal(formatMetric(-10, "rmse"), STATUS.UNAVAILABLE);
});

test("la plausibilidad rechaza valores imposibles", () => {
  assert.equal(isPlausibleMetric(0.93, "r2"), true);
  assert.equal(isPlausibleMetric(-0.2, "r2"), true);
  assert.equal(isPlausibleMetric(1.01, "r2"), false);
  assert.equal(isPlausibleMetric(-1, "mae"), false);
  assert.equal(isPlausibleMetric(Infinity, "rmse"), false);
});

test("las fechas se formatean sin conversión de zona", () => {
  assert.equal(formatDateEs("2026-11-16"), "16 de noviembre de 2026");
  assert.equal(formatDateEs("2027-01-01"), "1 de enero de 2027");
  assert.equal(formatDateEs("no-es-fecha"), STATUS.UNAVAILABLE);
  assert.equal(formatDateEs(null), STATUS.UNAVAILABLE);
});

// ── Estados ─────────────────────────────────────────────────────────────────

test("el estado de una fila sale de lo que declara", () => {
  assert.equal(rowStatus({ estado: "vigente" }), STATUS.CURRENT);
  assert.equal(rowStatus({ estado: "histórico" }), STATUS.HISTORICAL);
  assert.equal(rowStatus({ estado: "inventado" }), STATUS.UNAVAILABLE);
  assert.equal(rowStatus({}), STATUS.UNAVAILABLE);
});

// ── Integridad de los datos congelados ──────────────────────────────────────

const CATEGORIES = new Set(["datos", "modelo", "produccion", "interfaz"]);

test("el recorrido tiene las diez specs en orden y completas", () => {
  const { hitos, glosario } = readJson("spec-timeline.json");
  assert.deepEqual(
    hitos.map((h) => h.numero),
    ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"],
  );
  for (const hito of hitos) {
    for (const field of ["titulo", "resumen", "partida", "cambio", "resultado", "detalle"]) {
      assert.ok(typeof hito[field] === "string" && hito[field].trim(), `${hito.numero}.${field}`);
    }
    assert.ok(hito.categorias.length > 0, `${hito.numero} sin categorías`);
    for (const c of hito.categorias) assert.ok(CATEGORIES.has(c), `${hito.numero}: ${c}`);
  }
  const terms = glosario.map((g) => g.termino);
  for (const term of ["R²", "RMSE", "MAE", "MAPE", "Retardo", "Media móvil", "Walk-forward", "Variable"]) {
    assert.ok(terms.includes(term), `falta ${term} en el glosario`);
  }
});

test("las métricas tienen nueve filas con estado y protocolo", () => {
  const { lineaBase, referencia, filas } = readJson("model-metrics.json");
  assert.equal(filas.length, 9);
  assert.equal(filas.filter((f) => rowStatus(f) === STATUS.HISTORICAL).length, 8);
  assert.equal(filas.filter((f) => rowStatus(f) === STATUS.CURRENT).length, 1);
  for (const fila of filas) {
    assert.ok(Number.isInteger(fila.protocolo.variables), fila.modelo);
    for (const metric of ["rmse", "mae", "r2", "mape"]) {
      const value = fila[metric];
      assert.ok(value === null || isPlausibleMetric(value, metric), `${fila.modelo}.${metric}`);
      assert.notEqual(value, 0, `${fila.modelo}.${metric} no puede ser cero`);
    }
  }
  assert.equal(lineaBase.rmse, 60433);
  assert.equal(lineaBase.r2, 0.579);
  assert.equal(areComparable(lineaBase, referencia), false);
  const rejected = filas.find((f) => f.decision === "rechazado");
  assert.ok(rejected && rejected.motivo, "falta la candidata rechazada con su motivo");
});

test("la importancia de variables tiene las 19 del modelo vigente", () => {
  const { importancia } = readJson("reference-series.json");
  assert.equal(importancia.valores.length, 19);
  const total = importancia.valores.reduce((sum, v) => sum + v.importance, 0);
  assert.ok(Math.abs(total - 1) <= 0.001, `suma ${total}`);
  for (const v of importancia.valores) assert.ok(v.descripcion, `${v.feature} sin descripción`);
});

test("las predicciones por modelo tienen 16 y 19 variables alineadas con la serie real", () => {
  const data = readJson("model-predictions.json");
  const { semanas, real, modelos, protocolo16, protocolo19 } = data;
  assert.equal(modelos.length, 8);
  assert.equal(protocolo16.variables, 16);
  assert.equal(protocolo19.variables, 19);
  // Spec 011: las dos variantes comparten ventana y entrenamiento; solo cambia el número de variables.
  for (const clave of ["desde", "hasta", "dias", "semanas", "entrenamiento_hasta", "dias_entrenamiento"]) {
    assert.equal(protocolo16[clave], protocolo19[clave], clave);
  }
  assert.equal(semanas.length, protocolo19.semanas);
  assert.equal(semanas[0], "2025-06-29");
  assert.equal(semanas.at(-1), "2026-11-08");
  assert.equal(real.length, semanas.length);
  for (const m of modelos) {
    // Cada línea cubre todo el eje, de la primera a la última semana.
    for (const clave of ["pred16", "pred19"]) {
      assert.equal(m[clave].length, semanas.length, `${m.modelo}.${clave}`);
      assert.ok(m[clave].every((v) => Number.isFinite(v)), `${m.modelo}.${clave} tiene huecos`);
    }
    for (const clave of ["metricas16", "metricas19"]) {
      for (const metric of ["rmse", "mae", "r2", "mape"]) {
        assert.ok(isPlausibleMetric(m[clave][metric], metric), `${m.modelo}.${clave}.${metric}`);
      }
    }
  }
  assert.ok(modelos.some((m) => m.modelo === "Linear Regression"), "falta el modelo vigente");
  // La evaluación del notebook usa otra ventana que la del modelo en producción:
  // sus cifras no se pueden restar a las de la referencia.
  const { referencia } = readJson("model-metrics.json");
  assert.equal(areComparable({ protocolo: protocolo19 }, referencia), false);
});

test("la serie semanal renovable no tiene huecos ni valores negativos", () => {
  const { serieRenovable } = readJson("reference-series.json");
  const { semanas, tecnologias } = serieRenovable;
  assert.ok(semanas.length > 200);
  for (const t of tecnologias) {
    assert.equal(t.valores.length, semanas.length, t.nombre);
    for (const v of t.valores) assert.ok(Number.isFinite(v) && v >= 0, t.nombre);
  }
});
