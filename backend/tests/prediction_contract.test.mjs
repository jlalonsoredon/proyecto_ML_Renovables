import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(testDir, "..");
const rootDir = resolve(backendDir, "..");
const probeScript = resolve(testDir, "logic_probe.py");
const windowsPython = resolve(rootDir, ".venv/Scripts/python.exe");
const unixPython = resolve(rootDir, ".venv/bin/python");
const python = process.env.PYTHON
  || (existsSync(windowsPython) ? windowsPython : null)
  || (existsSync(unixPython) ? unixPython : "python");

const FEATURE_COLS = [
  "velmedia", "racha", "mes", "dia_semana", "dia_año",
  "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
  "vel_ma3", "vel_ma7", "vel_ma14",
  "racha_ma3", "racha_ma7", "racha_ma14", "eolica_ma7",
  "sol_lag1", "tmed_lag1", "eolica_prev",
];

function probe(request) {
  const env = {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONIOENCODING: "utf-8",
  };
  for (const key of ["AEMET_API_KEY", "REE_API_KEY", "ESIOS_TOKEN", "RENDER_API_KEY"]) {
    delete env[key];
  }
  const result = spawnSync(python, [probeScript], {
    cwd: backendDir,
    env,
    input: JSON.stringify(request),
    encoding: "utf8",
    maxBuffer: 4 * 1024 * 1024,
  });
  assert.equal(result.error, undefined, `No se pudo ejecutar el adaptador Python: ${result.error?.message}`);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("el artefacto backend coincide con LR-19 y su orden declarado", () => {
  const source = resolve(rootDir, "src/data/modelos/lr_eolica.joblib");
  const production = resolve(backendDir, "modelos/lr_eolica.joblib");
  const sourceHash = createHash("sha256").update(readFileSync(source)).digest("hex");
  const backendHash = createHash("sha256").update(readFileSync(production)).digest("hex");

  assert.equal(sourceHash, "e915381e2c24fcfbc2a81ab6eca2fdede7c7729f1abe2f79e58491cf9647c702");
  assert.equal(backendHash, sourceHash);

  const model = probe({
    action: "model_contract",
    model_path: production,
    expected_features: FEATURE_COLS,
    reference_db: resolve(rootDir, "src/data/ree_generacion.db"),
  });
  assert.equal(model.loaded, true);
  assert.equal(model.familia, "Linear Regression");
  assert.equal(model.usa_scaler, true);
  assert.equal(model.n_features_in, 19);
  assert.deepEqual(model.features, FEATURE_COLS);
  assert.ok(model.inference.abs_diff < 1e-6);
});

test("la ventana mixta conserva fuentes y no acorta una ventana incompleta", () => {
  const mixed = probe({
    action: "resolve_window",
    hoy: "2026-01-10",
    objetivo: "2026-01-11",
    dias: 3,
    observaciones: {
      "2026-01-09": 2,
      "2026-01-10": 4,
    },
    previsiones: { "2026-01-11": 6 },
  });
  assert.equal(mixed.valor, 4);
  assert.equal(mixed.origen, "mixta");
  assert.equal(mixed.dias_observados, 2);
  assert.equal(mixed.dias_previstos, 1);

  const incomplete = probe({
    action: "resolve_window",
    hoy: "2026-01-10",
    objetivo: "2026-01-11",
    dias: 3,
    observaciones: { "2026-01-10": 4 },
    previsiones: { "2026-01-11": 6 },
  });
  assert.equal(incomplete.valor, null);
  assert.deepEqual(incomplete.faltantes, ["2026-01-09"]);
});

test("la última publicación REE anómala se descarta como ancla", () => {
  const result = probe({
    action: "freshness",
    hoy: "2026-01-08",
    generacion: {
      "2026-01-01": 100000,
      "2026-01-02": 100000,
      "2026-01-03": 100000,
      "2026-01-04": 100000,
      "2026-01-05": 100000,
      "2026-01-06": 100000,
      "2026-01-07": 100000,
      "2026-01-08": 50000,
    },
  });
  assert.equal(result.ancla, "2026-01-07");
  assert.deepEqual(result.descartados, ["2026-01-08"]);
});

test("el cliente REE identifica huecos internos aunque exista una fecha máxima", () => {
  const result = probe({
    action: "missing_generation_dates",
    hoy: "2026-01-10",
    dias: 4,
    presentes: ["2026-01-06", "2026-01-08", "2026-01-09"],
  });
  assert.deepEqual(result, ["2026-01-07"]);
});

test("eolica_prev no usa una elaboración del día objetivo y rellena solo con previsiones reales", () => {
  const result = probe({
    action: "ree_target",
    hoy: "2026-01-10",
    objetivo: "2026-01-11",
    previsiones_ree: [
      { objetivo: "2026-01-11", ubicacion: "peninsula", elaborado: "2026-01-11", eolica_mwh: 600000 },
      { objetivo: "2026-01-04", ubicacion: "peninsula", elaborado: "2026-01-03", eolica_mwh: 100000 },
      { objetivo: "2026-01-05", ubicacion: "peninsula", elaborado: "2026-01-04", eolica_mwh: 0 },
      { objetivo: "2026-01-06", ubicacion: "peninsula", elaborado: "2026-01-05", eolica_mwh: 200000 },
      { objetivo: "2026-01-07", ubicacion: "peninsula", elaborado: "2026-01-06", eolica_mwh: 200000 },
      { objetivo: "2026-01-08", ubicacion: "peninsula", elaborado: "2026-01-07", eolica_mwh: 200000 },
      { objetivo: "2026-01-09", ubicacion: "peninsula", elaborado: "2026-01-08", eolica_mwh: 200000 },
      { objetivo: "2026-01-10", ubicacion: "peninsula", elaborado: "2026-01-09", eolica_mwh: 200000 },
      { objetivo: "2026-01-10", ubicacion: "peninsula", elaborado: "2026-01-10", eolica_mwh: 720000 },
    ],
  });
  assert.equal(result.valor, 157142.85714285713);
  assert.equal(result.origen, "estimada");
  assert.equal(result.dias_media, 7);
});

test("el mapa completo devuelve exactamente 19 variables y sus orígenes", () => {
  const obsMeteo = {};
  const obsGen = {};
  for (let day = 2; day <= 14; day += 1) {
    const date = `2026-01-${String(day).padStart(2, "0")}`;
    obsMeteo[date] = { velmedia: 2, racha: 5 };
  }
  for (let day = 1; day <= 14; day += 1) {
    obsGen[`2026-01-${String(day).padStart(2, "0")}`] = 100000;
  }

  const ubicaciones = [
    "Gecama (Cuenca)", "Maranchón (Guadalaj.)", "Borja (Zaragoza)",
    "Tarifa (Cádiz)", "Briviesca (Burgos)", "La Muela (Zaragoza)",
    "El Andévalo (Huelva)",
  ];
  const aemetRows = ubicaciones.map((ubicacion) => ({
    fuente: "aemet",
    elaborado: "2026-01-14T08:00:00",
    objetivo: "2026-01-15",
    ubicacion,
    uso: "eolica",
    viento_ms: 3,
    racha_ms: 9,
  }));
  const reeRows = [{
    fuente: "ree",
    elaborado: "2026-01-14T08:00:00",
    objetivo: "2026-01-15",
    ubicacion: "peninsula",
    eolica_mwh: 250000,
    capturado_en: "2026-01-14T08:05:00",
  }];

  const result = probe({
    action: "build_map",
    hoy: "2026-01-14",
    obs_meteo: obsMeteo,
    obs_solar: { "2026-01-14": { sol: 6, tmed: 18 } },
    obs_gen: obsGen,
    aemet_rows: aemetRows,
    ree_rows: reeRows,
  });

  assert.deepEqual(result.features, FEATURE_COLS);
  assert.equal(result.faltan.length, 0);
  assert.equal(Object.keys(result.vector_entrada).length, 19);
  assert.deepEqual(Object.keys(result.vector_entrada), FEATURE_COLS);
  assert.equal(result.mapa.eolica_prev.valor, 250000);
  assert.equal(result.mapa.eolica_prev.origen, "prevision");
  assert.equal(result.mapa.sol_lag1.valor, 6);
  assert.equal(result.mapa.sol_lag1.origen, "observacion");
});

test("la fila nacional no se promedia con las ubicaciones y solo cubre su día", () => {
  const base = [
    { objetivo: "2026-11-21", ubicacion: "A", uso: "eolica", elaborado: "2026-11-20T21:00:00+01:00", viento_ms: 2, racha_ms: 5 },
    { objetivo: "2026-11-21", ubicacion: "B", uso: "eolica", elaborado: "2026-11-20T21:00:00+01:00", viento_ms: 4, racha_ms: 7 },
  ];
  const nacional = {
    objetivo: "2026-11-22", ubicacion: "nacional", uso: "eolica",
    elaborado: "2026-11-22T06:27:53+00:00", viento_ms: 3.27, racha_ms: 9.96,
  };

  const soloNacional = probe({
    action: "national_series",
    rows: [...base, nacional],
    uso: "eolica",
    hoy: "2026-11-22",
  });
  assert.equal(soloNacional["2026-11-21"].viento_ms, 3);
  assert.equal(soloNacional["2026-11-22"].viento_ms, 3.27);
  assert.equal(soloNacional["2026-11-22"].racha_ms, 9.96);

  const conUbicacion = probe({
    action: "national_series",
    rows: [
      ...base,
      nacional,
      { objetivo: "2026-11-22", ubicacion: "A", uso: "eolica", elaborado: "2026-11-22T06:00:00+01:00", viento_ms: 6, racha_ms: 12 },
    ],
    uso: "eolica",
    hoy: "2026-11-22",
  });
  assert.equal(conUbicacion["2026-11-22"].viento_ms, 6);
  assert.equal(conUbicacion["2026-11-22"].racha_ms, 12);
});

test("el archivo durable restaura AEMET y REE sin duplicar", (t) => {
  const dir = mkdtempSync(resolve(tmpdir(), "aero-archivo-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const dbPath = resolve(dir, "test.db");
  const snapshot = {
    fecha_generacion: "2026-11-23T07:00:00+01:00",
    archivo_previsiones: {
      aemet: [{
        objetivo: "2026-11-22", ubicacion: "nacional", uso: "eolica",
        elaborado: "2026-11-22T06:27:53+00:00",
        capturado_en: "2026-11-22T06:27:53+00:00",
        viento_ms: 3.27, racha_ms: 9.96, tmed: null, sol: null,
      }],
      ree: [{
        objetivo: "2026-11-24", ubicacion: "peninsula",
        elaborado: "2026-11-23T10:50:53+01:00",
        capturado_en: "2026-11-23T10:50:53+01:00",
        eolica_mwh: 248335.8,
      }],
    },
  };

  const result = probe({
    action: "forecast_archive_restore",
    db_path: dbPath,
    snapshot,
    hoy: "2026-11-23",
    desde: "2026-11-22",
    hasta: "2026-11-24",
  });
  assert.equal(result.primera, 2);
  assert.equal(result.segunda, 0);
  assert.equal(result.filas.length, 2);
  assert.equal(result.filas.find((fila) => fila.fuente === "aemet").ubicacion, "nacional");
  assert.equal(result.filas.find((fila) => fila.fuente === "aemet").viento_ms, 3.27);
  assert.equal(result.filas.find((fila) => fila.fuente === "ree").eolica_mwh, 248335.8);
});

test("el bootstrap del snapshot viejo recupera el agregado nacional", (t) => {
  const dir = mkdtempSync(resolve(tmpdir(), "aero-bootstrap-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const dbPath = resolve(dir, "test.db");
  const snapshot = {
    fecha_generacion: "2026-11-22T07:38:42+01:00",
    historico: [{
      fecha: "2026-11-22",
      eolica: null,
      aemet: {
        velmedia: 3.27,
        racha: 9.96,
        sol: null,
        tmed: null,
        origen: {
          velmedia: "prevision",
          racha: "prevision",
          sol: null,
          tmed: null,
        },
      },
    }],
  };

  const result = probe({
    action: "forecast_archive_restore",
    db_path: dbPath,
    snapshot,
    hoy: "2026-11-23",
    desde: "2026-11-22",
    hasta: "2026-11-23",
  });
  assert.equal(result.primera, 1);
  assert.equal(result.segunda, 0);
  assert.equal(result.filas.length, 1);
  assert.equal(result.filas[0].fuente, "aemet");
  assert.equal(result.filas[0].ubicacion, "nacional");
  assert.equal(result.filas[0].viento_ms, 3.27);
  assert.equal(result.filas[0].elaborado, "2026-11-22T06:38:42+00:00");
});

test("la predicción se detiene con nombres explícitos si falta una feature", () => {
  const result = probe({
    action: "build_map",
    hoy: "2026-01-14",
    obs_meteo: {},
    obs_solar: {},
    obs_gen: {},
    aemet_rows: [],
    ree_rows: [],
  });
  assert.ok(result.faltan.length > 0);
  assert.ok(result.faltan.includes("eolica_prev"));
  assert.equal(result.vector_entrada, null);
});

test("el parser de observaciones AEMET conserva ceros y convierte ausencias a null", () => {
  const result = probe({
    action: "aemet_observation",
    record: {
      fecha: "2026-01-10",
      indicativo: "3469A",
      nombre: "CÁCERES",
      provincia: "CÁCERES",
      tmed: "10,2",
      tmin: "0",
      tmax: "20",
      velmedia: "0",
      racha: "Ip",
      prec: "Acum",
      sol: "0",
    },
  });
  assert.equal(result.fecha, "2026-01-10");
  assert.equal(result.indicativo, "3469A");
  assert.equal(result.tmed, 10.2);
  assert.equal(result.velmedia, 0);
  assert.equal(result.sol, 0);
  assert.equal(result.racha, null);
  assert.equal(result.prec, null);
});

test("la captura AEMET reintenta 429, usa las estaciones LR y conserva el cero", () => {
  const result = probe({
    action: "aemet_capture_simulation",
    fecha: "2026-01-10",
  });
  assert.equal(result.estaciones.length, 11);
  assert.equal(new Set(result.estaciones).size, 11);
  assert.equal(result.filas.length, 1);
  assert.equal(result.filas[0].indicativo, "4589X");
  assert.equal(result.filas[0].velmedia, 0);
  assert.equal(result.filas[0].racha, null);
  assert.equal(result.filas[0].sol, 5);
  assert.equal(result.reintento_429, true);
  assert.equal(result.dos_pasos, true);
});

test("el archivo AEMET recaptura idempotente, nuevas elaboraciones y fallos parciales", (t) => {
  const directory = mkdtempSync(resolve(tmpdir(), "aero-aemet-capture-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));

  const result = probe({
    action: "aemet_forecast_capture",
    hoy: "2026-11-02",
    db_path: resolve(directory, "capture.db"),
  });
  assert.equal(result.primera.estado, "ok");
  assert.equal(result.primera.filas, 84);
  assert.equal(result.tras_recaptura_igual, 84);
  assert.equal(result.tras_nueva_elaboracion, 168);
  assert.equal(result.parcial.estado, "parcial");
  assert.equal(result.parcial.ubicaciones_ok, 11);
  assert.equal(result.tras_parcial, 245);
});

test("ESIOS archiva solo el objetivo D+1 peninsular con el sello declarado", () => {
  const result = probe({
    action: "ree_d1",
    hoy: "2026-01-10",
    objetivo: "2026-01-11",
    capturado_en: "2026-01-10T09:00:00+01:00",
    payload: {
      indicator: {
        values_updated_at: "2026-01-10T08:00:00+01:00",
        values: [
          {
            datetime: "2026-01-11T00:00:00+01:00",
            datetime_utc: "2026-01-10T23:00:00Z",
            geo_id: 8741,
            value: 0,
          },
          {
            datetime: "2026-01-10T00:00:00+01:00",
            geo_id: 8741,
            value: 100000,
          },
          {
            datetime: "2026-01-11T00:00:00+01:00",
            geo_id: 8740,
            value: 200000,
          },
        ],
      },
    },
  });
  assert.equal(result.fila.objetivo, "2026-01-11");
  assert.equal(result.fila.ubicacion, "peninsula");
  assert.equal(result.fila.eolica_mwh, 0);
  assert.equal(result.fila.elaborado, "2026-01-10T08:00:00+01:00");
});

test("la captura REE firma ESIOS con REE_API_KEY y archiva solo D+1", () => {
  const result = probe({
    action: "ree_capture_simulation",
    hoy: "2026-01-10",
  });
  assert.equal(result.estado, "ok");
  assert.equal(result.objetivo, "2026-01-11");
  assert.equal(result.clave_en_cabecera, true);
  assert.equal(result.indicador, 1777);
  assert.equal(result.geo_id, 8741);
  assert.equal(result.fuente_guardada, "ree");
  assert.equal(result.fila_guardada.eolica_mwh, 0);
  assert.equal(result.fila_guardada.elaborado, "2026-01-10T08:00:00+01:00");
});

test("el error de producción usa real menos predicción y no imputa", () => {
  const result = probe({
    action: "prediction_error",
    fecha_objetivo: "2026-01-09",
    hoy: "2026-01-10",
    real_mwh: 120,
    prediccion_mwh: 100,
  });
  assert.equal(result, 20);

  const future = probe({
    action: "prediction_error",
    fecha_objetivo: "2026-01-11",
    hoy: "2026-01-10",
    real_mwh: 120,
    prediccion_mwh: 100,
  });
  assert.equal(future, null);
});
