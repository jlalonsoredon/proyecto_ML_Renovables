import test from "node:test";
import assert from "node:assert/strict";

import {
  parseSol,
  summarizeInsolation,
  decideAvailability,
  splitDateRange,
} from "../insolation_probe.mjs";

// ─────────────────────────────────────────────
// Lectura del campo "sol" de AEMET
// ─────────────────────────────────────────────

test("parseSol interpreta la coma decimal y respeta el cero", () => {
  assert.equal(parseSol("13,6"), 13.6);
  assert.equal(parseSol("13.6"), 13.6);
  assert.equal(parseSol("0,0"), 0);
  assert.equal(parseSol(7), 7);
});

test("parseSol trata como ausente lo que no es un número", () => {
  const ausentes = [null, undefined, "", "   ", "Ip", "Acum", "abc"];
  for (const valor of ausentes) {
    assert.equal(parseSol(valor), null, `valor=${JSON.stringify(valor)}`);
  }
});

test("un día con 0 horas de sol es un dato válido, no un hueco", () => {
  const resumen = summarizeInsolation([{ fecha: "2026-06-01", sol: "0,0" }]);
  assert.equal(resumen.days, 1);
  assert.equal(resumen.daysWithSol, 1);
  assert.equal(resumen.missing, 0);
});

// ─────────────────────────────────────────────
// Resumen de la serie
// ─────────────────────────────────────────────

test("summarizeInsolation informa cobertura, huecos y rango de fechas", () => {
  const filas = [
    { fecha: "2026-06-01", sol: "13,6" },
    { fecha: "2026-06-02", sol: "" },
    { fecha: "2026-06-03", sol: "13,2" },
    { fecha: "2026-06-04", sol: null },
    { fecha: "2026-06-05", sol: "13,7" },
  ];
  const resumen = summarizeInsolation(filas);

  assert.equal(resumen.days, 5);
  assert.equal(resumen.daysWithSol, 3);
  assert.equal(resumen.missing, 2);
  assert.equal(resumen.coveragePct, 60);
  assert.equal(resumen.firstDate, "2026-06-01");
  assert.equal(resumen.lastDate, "2026-06-05");
  assert.equal(resumen.maxHours, 13.7);
  assert.equal(resumen.minHours, 13.2);
});

test("los valores imposibles no cuentan como día con dato", () => {
  const resumen = summarizeInsolation([
    { fecha: "2026-06-01", sol: "25,5" },
    { fecha: "2026-06-02", sol: "-1" },
    { fecha: "2026-06-03", sol: "8" },
  ]);

  assert.equal(resumen.days, 3);
  assert.equal(resumen.daysWithSol, 1);
  assert.equal(resumen.invalidValues, 2);
  assert.equal(resumen.missing, 0);
});

test("las fechas repetidas no inflan el número de días ni la cobertura", () => {
  const resumen = summarizeInsolation([
    { fecha: "2026-06-01", sol: "10" },
    { fecha: "2026-06-01", sol: "12" },
  ]);

  assert.equal(resumen.days, 1);
  assert.equal(resumen.daysWithSol, 1);
  assert.equal(resumen.coveragePct, 100);
});

// ─────────────────────────────────────────────
// Veredicto
// ─────────────────────────────────────────────

test("una estación sin insolación no es apta y el motivo la identifica", () => {
  const resumen = summarizeInsolation([{ fecha: "2026-06-01", sol: "" }]);
  const veredicto = decideAvailability(resumen, { indicativo: "9434" });

  assert.equal(veredicto.ok, false);
  assert.match(veredicto.reason, /9434/);
  assert.match(veredicto.reason, /insolaci/i);
});

test("una estación con insolación es apta y el motivo resume la cobertura", () => {
  const resumen = summarizeInsolation([
    { fecha: "2026-06-01", sol: "14,2" },
    { fecha: "2026-06-02", sol: "13,4" },
  ]);
  const veredicto = decideAvailability(resumen, { indicativo: "4452" });

  assert.equal(veredicto.ok, true);
  assert.match(veredicto.reason, /4452/);
  assert.match(veredicto.reason, /100 %/);
});

test("AEMET sin días devuelve un motivo explícito, no un cero silencioso", () => {
  const veredicto = decideAvailability(summarizeInsolation([]), {
    indicativo: "4452",
  });

  assert.equal(veredicto.ok, false);
  assert.equal(veredicto.days, 0);
  assert.match(veredicto.reason, /4452/);
});

test("dos ejecuciones con la misma entrada dan el mismo resultado", () => {
  const filas = [
    { fecha: "2026-06-01", sol: "9,5" },
    { fecha: "2026-06-02", sol: null },
  ];

  assert.deepEqual(summarizeInsolation(filas), summarizeInsolation(filas));
});

// ─────────────────────────────────────────────
// Troceo de la ventana
// AEMET no admite más de 6 meses por petición
// ─────────────────────────────────────────────

test("splitDateRange deja una sola ventana si el rango cabe", () => {
  assert.deepEqual(splitDateRange("2022-01-01", "2022-01-10", 150), [
    ["2022-01-01", "2022-01-10"],
  ]);
});

test("splitDateRange trocea, encadena y no solapa", () => {
  const ventanas = splitDateRange("2022-01-01", "2022-12-31", 150);

  assert.ok(ventanas.length > 1, "debería trocear un año en varias ventanas");
  assert.equal(ventanas[0][0], "2022-01-01");
  assert.equal(ventanas.at(-1)[1], "2022-12-31");

  for (let i = 0; i < ventanas.length; i += 1) {
    const [desde, hasta] = ventanas[i];
    assert.ok(desde <= hasta, `ventana invertida: ${desde} → ${hasta}`);
    const dias = (Date.parse(`${hasta}T00:00:00Z`) - Date.parse(`${desde}T00:00:00Z`)) / 86400000 + 1;
    assert.ok(dias <= 150, `ventana de ${dias} días: ${desde} → ${hasta}`);

    if (i > 0) {
      const anteriorFin = ventanas[i - 1][1];
      const siguiente = new Date(`${anteriorFin}T00:00:00Z`);
      siguiente.setUTCDate(siguiente.getUTCDate() + 1);
      assert.equal(desde, siguiente.toISOString().slice(0, 10), "las ventanas deben ser consecutivas");
    }
  }
});

test("splitDateRange rechaza un rango invertido", () => {
  assert.throws(() => splitDateRange("2022-06-01", "2022-01-01", 150), /rango/i);
});

// ─────────────────────────────────────────────
// Hueco interno
// ─────────────────────────────────────────────

test("summarizeInsolation mide el hueco interno más largo", () => {
  const resumen = summarizeInsolation([
    { fecha: "2026-06-01", sol: "10" },
    { fecha: "2026-06-05", sol: "9" },
  ]);

  assert.equal(resumen.maxGapDays, 3);
});

test("sin días intermedios ausentes el hueco es cero", () => {
  const resumen = summarizeInsolation([
    { fecha: "2026-06-01", sol: "10" },
    { fecha: "2026-06-02", sol: "" },
    { fecha: "2026-06-03", sol: "9" },
  ]);

  assert.equal(resumen.maxGapDays, 0);
});
