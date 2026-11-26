// Pruebas de los cálculos del análisis exploratorio de Proceso (spec 016).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { standardize, histogram, weekEnding, weeklyMeans } from "../src/utils/eda-series.mjs";
import { pearson } from "../src/utils/new-variables.mjs";

const data = JSON.parse(readFileSync(new URL("../src/data/nuevas-variables.json", import.meta.url), "utf8"));
const lgbm = JSON.parse(readFileSync(new URL("../src/data/importancia-lgbm.json", import.meta.url), "utf8"));

const close = (a, b, tol = 1e-9) => Math.abs(a - b) < tol;

test("standardize: media 0 y desviación 1", () => {
  const z = standardize([2, 4, 4, 4, 5, 5, 7, 9]);
  assert.ok(close(z.reduce((s, v) => s + v, 0) / z.length, 0));
  assert.ok(close(Math.sqrt(z.reduce((s, v) => s + v * v, 0) / z.length), 1));
  assert.deepEqual(z.slice(0, 2), [-1.5, -0.5]);
});

test("histogram: tramos iguales, el máximo entra y lo de fuera se cuenta aparte", () => {
  // Tramos de 0,5: [-1, -0,5), [-0,5, 0), [0, 0,5), [0,5, 1]
  const h = histogram([-2, -0.5, 0, 0.4, 1, 3], -1, 1, 4);
  assert.deepEqual(h.counts, [0, 1, 2, 1]);
  assert.deepEqual(h.centers, [-0.75, -0.25, 0.25, 0.75]);
  assert.equal(h.outside, 2);
});

test("weekEnding: semanas de lunes a domingo, etiquetadas por su domingo", () => {
  assert.equal(weekEnding("2026-11-23"), "2026-11-29"); // lunes
  assert.equal(weekEnding("2026-11-29"), "2026-11-29"); // domingo
  assert.equal(weekEnding("2026-12-31"), "2027-01-03"); // cruza de año
});

test("weeklyMeans: media por semana y en orden", () => {
  const r = weeklyMeans(["2026-11-24", "2026-11-23", "2026-11-30"], { a: [2, 4, 10] });
  assert.deepEqual(r.weeks, ["2026-11-29", "2026-12-06"]);
  assert.deepEqual(r.means.a, [3, 10]);
});

test("CA-3: viento y racha del JSON con su correlación del notebook", () => {
  for (const clave of ["velmedia", "racha"]) {
    assert.equal(data[clave].length, data.fecha.length, clave);
    const r = pearson(data[clave], data.eolica_gwh);
    assert.ok(Math.abs(r - data.correlacion[clave]) < 0.002, `${clave}: ${r} frente a ${data.correlacion[clave]}`);
  }
  // La escala común no cambia la correlación.
  const r = pearson(standardize(data.velmedia), standardize(data.eolica_gwh));
  assert.ok(Math.abs(r - data.correlacion.velmedia) < 0.002);
});

test("CA-3: importancia de LightGBM con las 19 variables del modelo", () => {
  const valores = Object.values(lgbm.valores);
  assert.equal(valores.length, 19);
  assert.ok(valores.every((v) => Number.isInteger(v) && v > 0));
  const maxima = Object.entries(lgbm.valores).sort((a, b) => b[1] - a[1])[0][0];
  assert.equal(maxima, "eolica_prev");
});
