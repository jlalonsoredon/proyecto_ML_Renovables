/**
 * Puerta única del proyecto: `node --test` ejecuta la lógica del bloque solar,
 * escrita en Python con la biblioteca estándar (plan, decisión D-T2).
 *
 * Si la suite de Python falla, este test falla y con él el comando de puerta.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");

test("la lógica del bloque solar pasa su suite de Python", () => {
  const run = spawnSync(
    "python",
    ["-m", "unittest", "discover", "-s", "src/pipeline/tests", "-p", "test_*.py"],
    { cwd: repoRoot, encoding: "utf8" },
  );

  // En Windows `spawnSync` no lanza si el binario no existe: lo delata `error`.
  assert.equal(run.error, undefined, `no se pudo lanzar python: ${run.error?.message}`);

  // La salida de unittest va por stderr; se adjunta para que el fallo sea legible.
  assert.equal(
    run.status,
    0,
    `la suite de Python falló (código ${run.status}):\n${run.stdout}\n${run.stderr}`,
  );
});
