// Pruebas de la sección «Las nuevas variables» (spec 013).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pearson, linearFit, binSummary } from "../src/utils/new-variables.mjs";

const data = JSON.parse(readFileSync(new URL("../src/data/nuevas-variables.json", import.meta.url), "utf8"));

test("pearson: correlación perfecta, inversa y nula", () => {
  assert.equal(pearson([1, 2, 3], [2, 4, 6]), 1);
  assert.equal(pearson([1, 2, 3], [6, 4, 2]), -1);
  assert.equal(pearson([1, 2, 3, 4], [1, 3, 3, 1]), 0);
  assert.throws(() => pearson([1, 2], [1]));
});

test("linearFit: recupera la recta exacta", () => {
  const { intercept, slope } = linearFit([0, 1, 2, 3], [1, 3, 5, 7]);
  assert.equal(slope, 2);
  assert.equal(intercept, 1);
});

test("binSummary: tramos [a, b), el último cerrado, sin tramos vacíos", () => {
  const rows = binSummary([0, 1, 2, 5, 10], [10, 20, 30, 40, 50], [0, 2, 4, 10]);
  assert.deepEqual(rows, [
    { from: 0, to: 2, days: 2, mean: 15 },
    { from: 2, to: 4, days: 1, mean: 30 },
    { from: 4, to: 10, days: 2, mean: 45 },
  ]);
});

test("CA-1: 1.770 días y todas las series con la misma longitud", () => {
  assert.equal(data.periodo.dias, 1770);
  for (const serie of ["sol_lag1", "tmed_lag1", "eolica_prev_gwh", "eolica_gwh"]) {
    assert.equal(data[serie].length, data.fecha.length, serie);
    assert.ok(data[serie].every((v) => typeof v === "number" && Number.isFinite(v)), serie);
  }
  assert.equal(data.fecha[0], data.periodo.desde);
  assert.equal(data.fecha.at(-1), data.periodo.hasta);
});

test("CA-2: las correlaciones del JSON coinciden con las recalculadas", () => {
  const pares = { sol_lag1: data.sol_lag1, tmed_lag1: data.tmed_lag1, eolica_prev: data.eolica_prev_gwh };
  for (const [clave, xs] of Object.entries(pares)) {
    const r = pearson(xs, data.eolica_gwh);
    assert.ok(Math.abs(r - data.correlacion[clave]) < 0.002, `${clave}: ${r} frente a ${data.correlacion[clave]}`);
  }
  assert.ok(data.correlacion.sol_lag1 < 0 && data.correlacion.tmed_lag1 < 0, "la relación con el sol y la temperatura es inversa");
});
