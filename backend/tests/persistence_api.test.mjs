import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(testDir, "..");
const rootDir = resolve(backendDir, "..");
const probe = resolve(testDir, "logic_probe.py");
const windowsPython = resolve(rootDir, ".venv/Scripts/python.exe");
const unixPython = resolve(rootDir, ".venv/bin/python");
const python = process.env.PYTHON
  || (existsSync(windowsPython) ? windowsPython : null)
  || (existsSync(unixPython) ? unixPython : "python");

function temporaryDatabase() {
  const directory = mkdtempSync(resolve(tmpdir(), "aero-spec008-"));
  return { directory, database: resolve(directory, "test.db") };
}

function runProbe(request, database) {
  const env = {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONIOENCODING: "utf-8",
  };
  for (const key of ["AEMET_API_KEY", "REE_API_KEY", "ESIOS_TOKEN", "RENDER_API_KEY"]) {
    delete env[key];
  }
  if (database) env.DB_PATH = database;

  const payload = { ...request };
  if (database) payload.db_path = database;
  const result = spawnSync(python, [probe], {
    cwd: backendDir,
    env,
    input: JSON.stringify(payload),
    encoding: "utf8",
    maxBuffer: 2 * 1024 * 1024,
  });
  assert.equal(result.error, undefined, `No se pudo ejecutar el adaptador Python: ${result.error?.message}`);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("la inicialización usa las tablas canónicas y elimina las tablas heredadas", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({ action: "schema" }, database);
  for (const name of ["generacion", "aemet_diario", "prediccion_diaria", "prediccion_propia"]) {
    assert.ok(result.tablas.includes(name), `falta la tabla ${name}`);
  }
  for (const name of ["predictions", "aemet_daily", "prediccion_aemet"]) {
    assert.ok(!result.tablas.includes(name), `se creó la tabla heredada ${name}`);
  }
  assert.deepEqual(result.columnas.prediccion_propia, [
    "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
    "modelo", "n_variables", "vector_entrada", "origenes", "real_mwh", "error_mwh",
  ]);
});

test("un modelo con orden incompatible deja readiness en 503", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const modelPath = resolve(backendDir, "modelos/lr_eolica.joblib");
  const result = runProbe({
    action: "invalid_model_health",
    model_path: modelPath,
  }, database);
  assert.equal(result.status, 503);
  assert.equal(result.body.status, "error");
  assert.match(result.body.detail, /Modelo LR-19/);
});

test("la predicción propia es idempotente y preserva el real al refrescar", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const target = "2026-01-11";
  const vector = { velmedia: 3, racha: 9, eolica_prev: 250000 };
  const origins = { velmedia: "prevision", racha: "prevision", eolica_prev: "prevision" };
  const result = runProbe({
    action: "own_prediction_roundtrip",
    real_mwh: 120,
    primera: {
      fecha_objetivo: target,
      fecha_emision: "2026-01-10",
      emitida_en: "2026-01-10T03:00:00+01:00",
      prediccion_mwh: 100,
      modelo: "Linear Regression",
      n_variables: 19,
      vector_entrada: vector,
      origenes: origins,
    },
    misma_emision: {
      fecha_objetivo: target,
      fecha_emision: "2026-01-10",
      emitida_en: "2026-01-10T09:00:00+01:00",
      prediccion_mwh: 105,
      modelo: "Linear Regression",
      n_variables: 19,
      vector_entrada: vector,
      origenes: origins,
    },
    siguiente_emision: {
      fecha_objetivo: target,
      fecha_emision: "2026-01-11",
      emitida_en: "2026-01-11T03:00:00+01:00",
      prediccion_mwh: 110,
      modelo: "Linear Regression",
      n_variables: 19,
      vector_entrada: vector,
      origenes: origins,
    },
  }, database);

  assert.equal(result.length, 2);
  assert.equal(result[0].fecha_emision, "2026-01-10");
  assert.equal(result[0].prediccion_mwh, 105);
  assert.equal(result[0].real_mwh, 120);
  assert.equal(result[0].error_mwh, 15);
  assert.equal(result[1].fecha_emision, "2026-01-11");
  assert.equal(result[1].real_mwh, null);
  assert.deepEqual(result[0].vector_entrada, vector);
  assert.deepEqual(result[0].origenes, origins);
});

test("las previsiones AEMET/REE se archivan en una tabla común sin duplicar", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "forecast_roundtrip",
    capturas: [
      ["aemet", [{
        elaborado: "2026-01-10T08:00:00",
        objetivo: "2026-01-11",
        ubicacion: "Gecama (Cuenca)",
        uso: "eolica",
        viento_ms: 3,
        racha_ms: 9,
      }]],
      ["ree", [{
        elaborado: "2026-01-10T08:00:00",
        objetivo: "2026-01-11",
        ubicacion: "peninsula",
        uso: "eolica",
        eolica_mwh: 250000,
      }]],
      ["ree", [{
        elaborado: "2026-01-10T08:00:00",
        objetivo: "2026-01-11",
        ubicacion: "peninsula",
        uso: "eolica",
        eolica_mwh: 250000,
      }]],
    ],
  }, database);
  assert.equal(result.aemet, 1);
  assert.equal(result.ree, 1);
});

test("forecast API usa la revisión AEMET elegible y no una posterior al objetivo", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "forecast_payload",
    hoy: "2026-01-10",
    capturas: [
      ["aemet", [{
        elaborado: "2026-01-10T08:00:00+01:00",
        capturado_en: "2026-01-10T08:05:00+01:00",
        objetivo: "2026-01-11",
        ubicacion: "Gecama (Cuenca)",
        uso: "eolica",
        viento_ms: 4,
        racha_ms: 8,
      }]],
      ["aemet", [{
        elaborado: "2026-01-11T08:00:00+01:00",
        capturado_en: "2026-01-11T08:05:00+01:00",
        objetivo: "2026-01-11",
        ubicacion: "Gecama (Cuenca)",
        uso: "eolica",
        viento_ms: 99,
        racha_ms: 199,
      }]],
      ["ree", [{
        elaborado: "2026-01-10T08:00:00+01:00",
        capturado_en: "2026-01-10T08:05:00+01:00",
        objetivo: "2026-01-11",
        ubicacion: "peninsula",
        uso: "eolica",
        eolica_mwh: 250000,
      }]],
      ["ree", [{
        elaborado: "2026-01-11T08:00:00+01:00",
        capturado_en: "2026-01-11T08:05:00+01:00",
        objetivo: "2026-01-11",
        ubicacion: "peninsula",
        uso: "eolica",
        eolica_mwh: 720000,
      }]],
    ],
  }, database);
  assert.equal(result.fecha, "2026-01-11");
  assert.equal(result.velmedia, 4);
  assert.equal(result.racha, 8);
  assert.equal(result.estaciones["Gecama (Cuenca)"].velmedia, 4);
  assert.equal(result.estaciones["Gecama (Cuenca)"].racha, 8);
  assert.equal(result.ree.eolica_mwh, 250000);
  assert.equal(result.ree.elaborado, "2026-01-10T08:00:00+01:00");
  assert.equal(result.ree.origen, "prevision");
  assert.equal("dias_media" in result.ree, false);
});

test("forecast API devuelve fuentes ausentes como null con avisos", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "forecast_payload",
    hoy: "2026-01-10",
    capturas: [],
  }, database);
  assert.equal(result.fecha, "2026-01-11");
  assert.equal(result.velmedia, null);
  assert.equal(result.racha, null);
  assert.equal(result.ree, null);
  assert.equal(result.avisos.length, 2);
  assert.ok(result.avisos.some((aviso) => aviso.includes("AEMET")));
  assert.ok(result.avisos.some((aviso) => aviso.includes("REE")));
});

test("solo se actualizan filas REE cuando se autoriza refrescar un día incompleto", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "generation_update_roundtrip",
    hoy: "2026-01-11",
    replace_date: "2026-01-10",
    initial: [{
      datetime: "2026-01-09T23:00:00Z",
      tecnologia: "Eólica",
      tipo: "Renovable",
      valor_MWh: 40000,
      porcentaje: 10,
    }],
    update: [{
      datetime: "2026-01-09T23:00:00Z",
      tecnologia: "Eólica",
      tipo: "Renovable",
      valor_MWh: 100000,
      porcentaje: 20,
    }],
  }, database);
  assert.equal(result.without_authorized_replace["2026-01-10"], 40000);
  assert.equal(result.with_authorized_replace["2026-01-10"], 100000);
});

test("la generación REE se agrupa por día de Europe/Madrid en invierno y verano", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "generation_madrid_dates",
    rows: [
      {
        datetime: "2026-01-10T23:00:00Z",
        tecnologia: "Eólica",
        tipo: "Renovable",
        valor_MWh: 100,
        porcentaje: 10,
      },
      {
        datetime: "2026-07-10T22:00:00Z",
        tecnologia: "Eólica",
        tipo: "Renovable",
        valor_MWh: 200,
        porcentaje: 20,
      },
    ],
  }, database);
  assert.equal(result["2026-01-11"], 100);
  assert.equal(result["2026-07-11"], 200);
});

test("la reconciliación no asigna como real un día REE incompleto", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "reconcile_incomplete_generation",
    hoy: "2026-01-08",
    generacion: Array.from({ length: 8 }, (_, index) => ({
      datetime: `2026-01-${String(index + 1).padStart(2, "0")}T12:00:00Z`,
      tecnologia: "Eólica",
      tipo: "Renovable",
      valor_MWh: index === 7 ? 30000 : 100000,
      porcentaje: 20,
    })),
    predicciones: [
      {
        fecha_objetivo: "2026-01-07",
        fecha_emision: "2026-01-06",
        emitida_en: "2026-01-06T03:00:00+01:00",
        prediccion_mwh: 90000,
      },
      {
        fecha_objetivo: "2026-01-08",
        fecha_emision: "2026-01-07",
        emitida_en: "2026-01-07T03:00:00+01:00",
        prediccion_mwh: 80000,
      },
      {
        fecha_objetivo: "2026-01-09",
        fecha_emision: "2026-01-08",
        emitida_en: "2026-01-08T03:00:00+01:00",
        prediccion_mwh: 70000,
      },
    ],
  }, database);
  assert.equal(result.actualizadas, 1);
  assert.equal(result.emisiones["2026-01-07"].real_mwh, 100000);
  assert.equal(result.emisiones["2026-01-07"].error_mwh, 10000);
  assert.equal(result.emisiones["2026-01-08"].real_mwh, null);
  assert.equal(result.emisiones["2026-01-09"].real_mwh, null);
});

test("el migrador exige apply, instala la instantánea y conserva backup", (t) => {
  const { directory, database } = temporaryDatabase();
  const backupDir = resolve(directory, "backups");
  const targetModel = resolve(directory, "lr_eolica.joblib");
  const targetReport = resolve(directory, "familia_como_modelo.json");
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  runProbe({ action: "create_legacy_db" }, database);
  writeFileSync(targetModel, "modelo-antiguo");
  writeFileSync(targetReport, "acta-antigua");

  const sourceDb = resolve(rootDir, "src/data/ree_generacion.db");
  const sourceModel = resolve(rootDir, "src/data/modelos/lr_eolica.joblib");
  const sourceReport = resolve(rootDir, "src/data/modelos/familia_como_modelo.json");
  const migrator = resolve(backendDir, "migrate_render_snapshot.py");
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: "1" };
  for (const key of ["AEMET_API_KEY", "REE_API_KEY", "ESIOS_TOKEN", "RENDER_API_KEY"]) {
    delete env[key];
  }
  const result = spawnSync(python, [
    migrator,
    "--source-db", sourceDb,
    "--target-db", database,
    "--source-model", sourceModel,
    "--target-model", targetModel,
    "--source-report", sourceReport,
    "--target-report", targetReport,
    "--backup-dir", backupDir,
    "--apply",
  ], { cwd: backendDir, env, encoding: "utf8", maxBuffer: 4 * 1024 * 1024 });

  assert.equal(result.error, undefined, `No se pudo ejecutar migrador: ${result.error?.message}`);
  assert.equal(result.status, 0, result.stderr);
  const installed = runProbe({ action: "inspect_db" }, database);
  const source = runProbe({ action: "inspect_db" }, sourceDb);
  for (const table of ["generacion", "aemet_diario", "prediccion_diaria", "prediccion_propia"]) {
    assert.equal(installed.conteos[table], source.conteos[table], `conteo distinto: ${table}`);
  }
  assert.equal(installed.tablas.includes("legacy_sentinel"), false);
  assert.equal(installed.tablas.includes("predictions"), false);

  const backups = readdirSync(backupDir);
  assert.ok(backups.some((name) => name.endsWith(".db")));
  assert.ok(backups.some((name) => name.endsWith(".joblib")));
  assert.equal(readFileSync(targetModel).equals(readFileSync(sourceModel)), true);
  assert.equal(readFileSync(targetReport).equals(readFileSync(sourceReport)), true);
  assert.equal(
    readdirSync(directory).some((name) => /\\.tmp-(wal|shm)$/.test(name)),
    false,
    "no deben quedar sidecars temporales del reemplazo",
  );
});

test("el migrador restaura BD y artefactos ante un error tras activar la BD", (t) => {
  const { directory, database } = temporaryDatabase();
  const backupDir = resolve(directory, "rollback-backup");
  const targetModel = resolve(directory, "lr_eolica.joblib");
  const targetReport = resolve(directory, "familia_como_modelo.json");
  const previousModel = Buffer.from("modelo-anterior");
  const previousReport = Buffer.from("acta-anterior");
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  runProbe({ action: "create_legacy_db" }, database);
  writeFileSync(targetModel, previousModel);
  writeFileSync(targetReport, previousReport);
  const result = runProbe({
    action: "migration_rollback",
    source_db: resolve(rootDir, "src/data/ree_generacion.db"),
    source_model: resolve(rootDir, "src/data/modelos/lr_eolica.joblib"),
    source_report: resolve(rootDir, "src/data/modelos/familia_como_modelo.json"),
    target_model: targetModel,
    target_report: targetReport,
    backup_dir: backupDir,
  }, database);

  assert.equal(result.error_injected, true);
  assert.equal(result.database_restored, true);
  assert.equal(result.model_restored, true);
  assert.equal(result.report_restored, true);
  assert.equal(result.backup_exists, true);
});

test("la API responde 503 estructurado sin generar un fallback", () => {
  const result = runProbe({
    action: "api_unavailable",
    fecha: "2026-01-11",
    faltan: ["eolica_prev"],
    avisos: ["No hay previsión REE elegible"],
  });
  assert.equal(result.status, 503);
  assert.equal(result.body.fecha, "2026-01-11");
  assert.deepEqual(result.body.faltan, ["eolica_prev"]);
  assert.deepEqual(result.body.avisos, ["No hay previsión REE elegible"]);
  assert.equal("prediccionMWh" in result.body, false);
});

test("el flujo diario respeta el orden de fuentes, reales y emisión", () => {
  const result = runProbe({
    action: "scheduler_order",
    hoy: "2026-01-10",
  });
  assert.deepEqual(result, [
    "capture_aemet_forecast",
    "capture_ree_forecast",
    "download_ree_data",
    "download_aemet_data",
    "reconcile_own_predictions",
    "run_prediction",
  ]);
});

test("un fallo programado se registra y no detiene los pasos siguientes", () => {
  const result = runProbe({ action: "scheduler_failure", hoy: "2026-01-10" });
  assert.deepEqual(result.llamadas, [
    "capture_aemet_forecast",
    "capture_ree_forecast",
    "download_ree_data",
    "download_aemet_data",
    "reconcile_own_predictions",
    "run_prediction",
  ]);
  assert.equal(result.resultados.capture_aemet_forecast, null);
  assert.equal(result.error_logged, true);
});

test("la app programa captura 03:00 y reintento 09:00 en Europe/Madrid", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({ action: "scheduler_schedule" }, database);
  assert.deepEqual(result.jobs, [
    { function: "run_daily_snapshot", hour: 3, minute: 0, timezone: "Europe/Madrid" },
    { function: "retry_forecast_capture", hour: 9, minute: 0, timezone: "Europe/Madrid" },
  ]);
  assert.equal(result.started, true);
  assert.equal(result.shutdown, true);
  assert.equal(result.backfill_started, true);
});

test("un refresh 503 no requiere ni fabrica predicción", () => {
  const result = runProbe({
    action: "api_refresh_unavailable",
    fecha: "2026-01-11",
    faltan: ["eolica_prev"],
    avisos: ["No hay previsión REE elegible"],
  });
  assert.equal(result.status, 503);
  assert.equal(result.body.fecha, "2026-01-11");
  assert.deepEqual(result.body.faltan, ["eolica_prev"]);
  assert.equal("prediccionMWh" in result.body, false);
});

test("un refresh fallido deja intacta la emisión previa del objetivo", (t) => {
  const { directory, database } = temporaryDatabase();
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = runProbe({
    action: "api_refresh_preserves",
    hoy: "2026-01-10",
  }, database);
  assert.equal(result.status, 503);
  assert.equal(result.body.fecha, "2026-01-11");
  assert.equal(result.count, 1);
  assert.equal(result.prediccion_mwh, 100);
});

test("el payload del gráfico alinea la última emisión y conserva trazabilidad", () => {
  const names = [
    "velmedia", "racha", "mes", "dia_semana", "dia_año",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14", "eolica_ma7",
    "sol_lag1", "tmed_lag1", "eolica_prev",
  ];
  const tomorrowVector = Object.fromEntries(names.map((name) => [name, name === "velmedia" ? 3 : 1]));
  const tomorrowOrigins = Object.fromEntries(names.map((name) => [name, "observacion"]));
  tomorrowOrigins.velmedia = "prevision";
  const predictions = [
    { fecha_objetivo: "2026-01-01", fecha_emision: "2025-12-31", emitida_en: "2025-12-31T03:00:00+01:00", prediccion_mwh: 9000, modelo: "Linear Regression", n_variables: 19, vector_entrada: {}, origenes: {}, real_mwh: 10000, error_mwh: 1000 },
    { fecha_objetivo: "2026-01-01", fecha_emision: "2025-12-31", emitida_en: "2025-12-31T09:00:00+01:00", prediccion_mwh: 9500, modelo: "Linear Regression", n_variables: 19, vector_entrada: {}, origenes: {}, real_mwh: 10000, error_mwh: 500 },
    { fecha_objetivo: "2026-01-02", fecha_emision: "2026-01-01", emitida_en: "2026-01-01T03:00:00+01:00", prediccion_mwh: 10000, modelo: "Linear Regression", n_variables: 19, vector_entrada: {}, origenes: {}, real_mwh: null, error_mwh: null },
    { fecha_objetivo: "2026-01-03", fecha_emision: "2026-01-02", emitida_en: "2026-01-02T03:00:00+01:00", prediccion_mwh: 12000, modelo: "Linear Regression", n_variables: 19, vector_entrada: tomorrowVector, origenes: tomorrowOrigins, real_mwh: null, error_mwh: null },
  ];
  const result = runProbe({
    action: "chart_payload",
    hoy: "2026-01-02",
    historico: [
      { fecha: "2026-01-01", eolica: 10000 },
      { fecha: "2026-01-02", eolica: 11000 },
    ],
    viento: {
      "2026-01-01": { velmedia: 2, racha: 4 },
      "2026-01-02": { velmedia: 4, racha: 6 },
    },
    predicciones_propias: predictions,
  });
  assert.deepEqual(result.fechas_hist, ["2026-01-01", "2026-01-02"]);
  assert.deepEqual(result.real_gwh, [10, 11]);
  assert.deepEqual(result.pred_gwh, [9.5, 10]);
  assert.equal(result.predicciones_propias.length, 4);
  assert.equal(result.manana.fecha, "2026-01-03");
  assert.equal(result.manana.pred_gwh, 12);
  assert.equal(result.manana.vector_entrada.velmedia, 3);
});

test("el gráfico representa la predicción ausente como null y no usa fallback", () => {
  const result = runProbe({
    action: "chart_payload",
    hoy: "2026-01-02",
    historico: [{ fecha: "2026-01-02", eolica: 11000 }],
    viento: {},
    predicciones_propias: [],
  });
  assert.deepEqual(result.fechas_hist, ["2026-01-02"]);
  assert.deepEqual(result.pred_gwh, [null]);
  assert.equal(result.manana.pred_gwh, null);
  assert.equal(result.manana.prediccion_mwh, null);
  assert.equal(result.manana.estado, "no_disponible");
  assert.equal(result.manana.es_fallback, false);
  assert.ok(result.avisos.some((aviso) => aviso.includes("no se ha aplicado fallback")));
});

test("el endpoint de comparación conserva histórico y añade el acta LR-19", () => {
  const rootDir = resolve(backendDir, "..");
  const report = resolve(rootDir, "src/data/modelos/familia_como_modelo.json");
  const result = runProbe({ action: "model_comparison", metrics_path: report });
  assert.equal(Array.isArray(result), true);
  assert.equal(result.length, 9);
  assert.equal(result[0].historico, true);
  assert.equal(result[0].n_variables, 16);
  const lr = result.find((row) => row.modelo === "Linear Regression (19 variables)");
  const lightgbm = result.find((row) => row.modelo === "LightGBM (19 variables)");
  assert.equal(lr.rol, "produccion");
  assert.equal(lr.n_variables, 19);
  assert.equal(lightgbm.decision, "rechazado");
  assert.equal(lightgbm.mape, null);
  assert.equal(lightgbm.accuracy, null);
  assert.equal(lightgbm.folds.length, 4);
});
