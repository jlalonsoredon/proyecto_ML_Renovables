// Pruebas de la spec 019: predicción provisional sin la previsión de REE y guarda del workflow.
import { test } from "node:test";
import assert from "node:assert/strict";
import { isProvisional, shouldSkipRefresh } from "../src/utils/forecast.mjs";
import { cardView } from "../src/utils/live-prediction.mjs";
import { readFileSync } from "node:fs";

const real = JSON.parse(readFileSync(new URL("../src/data/forecast-snapshot.json", import.meta.url), "utf8"));
const conOrigen = (origen, cambios = {}) => ({
  ...structuredClone(real),
  ...cambios,
  prediccion: { ...structuredClone(real.prediccion), origenes: { ...real.prediccion.origenes, eolica_prev: origen } },
});

test("CA-1: provisional con eolica_prev estimada o ausente, no con la previsión real", () => {
  assert.equal(isProvisional(conOrigen("estimada")), true);
  assert.equal(isProvisional(conOrigen(undefined)), true);
  assert.equal(isProvisional({}), true);
  assert.equal(isProvisional(conOrigen("prevision")), false);
});

test("CA-2: la guarda no omite un snapshot provisional del día de mañana", () => {
  const hoy = real.fecha_emision;
  const base = { fecha_objetivo: real.fecha_objetivo, avisos: ["Paso capture_ree_forecast: fallo"] };
  assert.equal(shouldSkipRefresh(conOrigen("estimada", base), hoy).omitir, false);
  assert.match(shouldSkipRefresh(conOrigen("estimada", base), hoy).motivo, /provisional: sí/);
  assert.equal(shouldSkipRefresh(conOrigen("prevision", { ...base, avisos: [] }), hoy).omitir, true);
  // El aviso esperado de REE no bloquea por sí solo si la previsión ya es la real.
  assert.equal(shouldSkipRefresh(conOrigen("prevision", base), hoy).omitir, true);
  // Un aviso no esperado sigue obligando a repetir.
  assert.equal(shouldSkipRefresh(conOrigen("prevision", { ...base, avisos: ["otro aviso"] }), hoy).omitir, false);
  // Si el snapshot no es el de mañana, se ejecuta.
  assert.equal(shouldSkipRefresh(conOrigen("prevision", { fecha_objetivo: "2000-01-01", avisos: [] }), hoy).omitir, false);
});

test("CA-4: cardView marca la tarjeta como provisional solo cuando corresponde", () => {
  const hoy = real.fecha_emision;
  assert.equal(cardView(conOrigen("estimada"), hoy).provisional, true);
  assert.equal(cardView(conOrigen("prevision"), hoy).provisional, false);
});
