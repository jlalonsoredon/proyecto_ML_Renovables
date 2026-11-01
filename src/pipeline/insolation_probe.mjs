// ─────────────────────────────────────────────
// Sonda de disponibilidad de insolación (AEMET)
// ─────────────────────────────────────────────
// Fase 0 del plan 001-fotovoltaicas (tarea T-01): comprobar, antes de invertir
// tiempo en el pipeline, si una estación publica el campo "sol".
// No forma parte del modelo: el parseo definitivo vive en el módulo del pipeline.
//
// Uso:
//   node src/pipeline/insolation_probe.mjs                 # 4452 y 9434, últimos 120 días
//   node src/pipeline/insolation_probe.mjs 4452 9434 7228
//   node src/pipeline/insolation_probe.mjs --desde 2022-01-01 --hasta 2026-06-23

import { readFileSync } from "node:fs";

export const DEFAULT_STATIONS = ["4452", "9434"];
export const DEFAULT_WINDOW_DAYS = 120;
export const PROBE_LAG_DAYS = 3; // AEMET publica con retraso; no se pide el día de hoy
export const AEMET_DAILY_PATH =
  "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos";

/**
 * Convierte un valor de AEMET a número o null.
 * AEMET usa coma decimal y marca los huecos con "", "Ip" o "Acum".
 */
export function parseSol(value) {
  if (value === null || value === undefined) return null;

  const text = String(value).trim();
  if (text === "" || text === "Ip" || text === "Acum") return null;

  const number = Number(text.replace(",", "."));
  return Number.isFinite(number) ? number : null;
}

/**
 * Resume una serie de filas AEMET ({fecha, sol}).
 * Devuelve conteos por día único, cobertura, rango y valores físicamente imposibles.
 */
export function summarizeInsolation(rows) {
  const fechas = new Set();
  const conDato = new Set();
  const invalidas = new Set();
  let invalidValues = 0;
  let maxHours = null;
  let minHours = null;

  for (const row of rows ?? []) {
    if (!row || !row.fecha) continue;

    const fecha = String(row.fecha);
    fechas.add(fecha);

    const horas = parseSol(row.sol);
    if (horas === null) continue;

    // Un día no puede tener menos de 0 ni más de 24 horas de sol.
    if (horas < 0 || horas > 24) {
      invalidValues += 1;
      invalidas.add(fecha);
      continue;
    }

    conDato.add(fecha);
    if (maxHours === null || horas > maxHours) maxHours = horas;
    if (minHours === null || horas < minHours) minHours = horas;
  }

  const days = fechas.size;
  const daysWithSol = conDato.size;

  // Hueco interno más largo: días ausentes entre dos fechas observadas.
  const ordenadas = [...fechas].sort();
  let maxGapDays = 0;
  for (let i = 1; i < ordenadas.length; i += 1) {
    const salto = dayDiff(ordenadas[i - 1], ordenadas[i]) - 1;
    if (salto > maxGapDays) maxGapDays = salto;
  }

  return {
    days,
    daysWithSol,
    missing: days - daysWithSol - invalidas.size,
    invalidValues,
    maxGapDays,
    coveragePct: days > 0 ? Math.round((daysWithSol / days) * 1000) / 10 : 0,
    maxHours,
    minHours,
    firstDate: days > 0 ? [...fechas][0] : null,
    lastDate: days > 0 ? [...fechas].at(-1) : null,
  };
}

function dayDiff(fromIso, toIso) {
  return Math.round((Date.parse(`${toIso}T00:00:00Z`) - Date.parse(`${fromIso}T00:00:00Z`)) / 86400000);
}

/**
 * Parte un rango de fechas en ventanas consecutivas que AEMET acepta.
 * El proveedor rechaza peticiones de más de 6 meses (comprobado el 2026-10-27),
 * así que se trocea en bloques de `maxDays` días (150 por defecto, ~5 meses).
 */
export function splitDateRange(from, to, maxDays = 150) {
  if (from > to) throw new Error(`rango invertido: ${from} → ${to}`);

  const ventanas = [];
  let inicio = new Date(`${from}T00:00:00Z`);
  const fin = new Date(`${to}T00:00:00Z`);

  while (inicio <= fin) {
    const candidato = new Date(inicio);
    candidato.setUTCDate(candidato.getUTCDate() + maxDays - 1);
    const hasta = candidato > fin ? fin : candidato;

    ventanas.push([isoDate(inicio), isoDate(hasta)]);
    inicio = new Date(hasta);
    inicio.setUTCDate(inicio.getUTCDate() + 1);
  }

  return ventanas;
}

/**
 * Decide si la serie sirve para el modelo solar.
 * Devuelve { ok, reason } con un motivo explícito: nunca un cero silencioso.
 */export function decideAvailability(summary, { indicativo, minDays = 1 } = {}) {
  const { days, daysWithSol, coveragePct, invalidValues } = summary;
  const quien = indicativo ?? "la estación";

  if (days === 0) {
    return {
      ok: false,
      days: 0,
      reason: `${quien}: AEMET no devolvió ningún día para la ventana pedida`,
    };
  }

  if (daysWithSol < minDays) {
    const extra = invalidValues > 0 ? `, ${invalidValues} valores imposibles` : "";
    return {
      ok: false,
      days,
      reason: `${quien}: sin insolación utilizable (${daysWithSol}/${days} días con dato${extra})`,
    };
  }

  return {
    ok: true,
    days,
    reason: `${quien}: ${daysWithSol}/${days} días con insolación (${coveragePct} %)`,
  };
}

/** Descarga en dos pasos (meta-URL → datos) los días de una estación. */
export async function fetchStationDays(indicativo, { from, to, apiKey, timeoutMs = 30000 }) {
  const url =
    `${AEMET_DAILY_PATH}/fechaini/${from}T00:00:00UTC` +
    `/fechafin/${to}T23:59:59UTC/estacion/${indicativo}?api_key=${apiKey}`;

  const meta = await fetchJson(url, timeoutMs);
  if (meta.estado !== 200) {
    const error = new Error(`AEMET ${indicativo}: estado ${meta.estado} - ${meta.descripcion}`);
    error.estado = meta.estado;
    throw error;
  }

  const rows = await fetchJson(meta.datos, timeoutMs);
  return Array.isArray(rows) ? rows : [];
}

/** Descarga un rango largo troceándolo en ventanas que AEMET acepta (≤ 6 meses). */
export async function fetchStationRange(
  indicativo,
  { from, to, apiKey, maxDays = 150, timeoutMs = 30000 },
) {
  const ventanas = splitDateRange(from, to, maxDays);
  const rows = [];

  for (let i = 0; i < ventanas.length; i += 1) {
    const [desde, hasta] = ventanas[i];
    const trozo = await fetchStationDays(indicativo, { from: desde, to: hasta, apiKey, timeoutMs });
    rows.push(...trozo);

    // Respeto al límite de peticiones del proveedor (RNF-8).
    if (i < ventanas.length - 1) await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  return rows;
}

async function fetchJson(url, timeoutMs) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok && response.status !== 401) {
    throw new Error(`HTTP ${response.status} en ${url.split("?")[0]}`);
  }
  return response.json();
}

/** Lee AEMET_API_KEY de un fichero .env (admite comillas dobles). */
export function readApiKey(envPath) {
  const content = readFileSync(envPath, "utf8");
  const match = content.match(/^\s*AEMET_API_KEY\s*=\s*"?([^"\r\n]+)"?\s*$/m);
  if (!match) throw new Error(`No se encontró AEMET_API_KEY en ${envPath}`);
  return match[1].trim();
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function parseArgs(argv) {
  const options = {
    desde: null,
    hasta: null,
    stations: [...DEFAULT_STATIONS],
  };
  const stations = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--desde") options.desde = argv[++i];
    else if (arg === "--hasta") options.hasta = argv[++i];
    else stations.push(arg);
  }

  if (stations.length > 0) options.stations = stations;
  return options;
}

async function main() {
  const { desde, hasta, stations } = parseArgs(process.argv.slice(2));

  const fin = hasta ? new Date(`${hasta}T00:00:00Z`) : new Date();
  if (!hasta) fin.setUTCDate(fin.getUTCDate() - PROBE_LAG_DAYS);
  const inicio = desde ? new Date(`${desde}T00:00:00Z`) : new Date(fin);
  if (!desde) inicio.setUTCDate(inicio.getUTCDate() - DEFAULT_WINDOW_DAYS);

  const apiKey = readApiKey(new URL("../../.env", import.meta.url));
  const from = isoDate(inicio);
  const to = isoDate(fin);

  console.log(`\n🔎 Sonda de insolación AEMET — ${from} → ${to}`);
  console.log(`   Estaciones: ${stations.join(", ")}\n`);

  let fallos = 0;
  for (const indicativo of stations) {
    try {
      const rows = await fetchStationRange(indicativo, { from, to, apiKey });
      const summary = summarizeInsolation(rows);
      const veredicto = decideAvailability(summary, { indicativo });

      const marca = veredicto.ok ? "✅" : "⛔";
      console.log(`${marca} ${veredicto.reason}`);
      if (summary.days > 0) {
        console.log(
          `   días=${summary.days}  con sol=${summary.daysWithSol}  huecos=${summary.missing}` +
            `  hueco máximo=${summary.maxGapDays} días` +
            `  imposibles=${summary.invalidValues}` +
            `  rango=${summary.firstDate}→${summary.lastDate}` +
            `  máx=${summary.maxHours} h`,
        );
      }
      if (!veredicto.ok) fallos += 1;
    } catch (error) {
      fallos += 1;
      const esClave = error.estado === 401 || /apiKey/i.test(error.message);
      console.log(`⛔ ${indicativo}: ${error.message}`);
      if (esClave) {
        console.log("   → La clave de AEMET está caducada: renovarla en https://opendata.aemet.es/");
      } else if (error.name === "TimeoutError") {
        console.log("   → Tiempo de espera agotado: reintentar más tarde (límite de peticiones).");
      }
    }
    // Respeto al límite de peticiones del proveedor (RNF-8).
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  console.log("");
  process.exitCode = fallos > 0 ? 1 : 0;
}

// Solo se ejecuta como script; al importarlo desde los tests no hace nada.
if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  main().catch((error) => {
    console.error(`\n❌ ${error.message}\n`);
    process.exitCode = 1;
  });
}
