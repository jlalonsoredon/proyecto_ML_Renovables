# Tareas 004 — Previsión de fuentes y predicción propia en `src/`

Deriva de `spec.md` (RF-1 a RF-7) y `plan.md` (archivos, funciones, decisiones y paradas).
Ciclo obligatorio por tarea: test en rojo, implementación mínima, verde, refactor. Ninguna
tarea se cierra con la puerta en rojo (constitución, principio 5).

**Puerta:** `node --test "src/pipeline/tests/*.test.mjs"` (descubre `test_*.py` sola).
**Alcance:** solo `src/`; nada en `backend/` ni `frontend/` (RNF-1).

## Fase 0 — Seguridad

- [x] **T-01 — Copia de seguridad de la BD** · RNF-1, constitución principio 6
  Copiar `src/data/ree_generacion.db` a la carpeta de copias con fecha en el nombre antes
  de cualquier migración.
  **Hecho cuando:** la copia existe, `PRAGMA integrity_check` da `ok` en ambas y se anota la ruta.

## Fase 1 — Persistencia (`prevision_db.py`, stdlib, testable en la puerta)

- [x] **T-02 — Esquema de las dos tablas** · RF-1, RF-2 (CA-1.1, CA-2.1)
  `ensure_schema(conn)`: `prediccion_diaria` (PK `fuente, elaborado, objetivo, ubicacion`,
  columnas superset de la spec 003 + `uso` + `eolica_mwh`) y `prediccion_propia` (PK
  `fecha_objetivo, fecha_emision`). Tests: crear dos veces no falla; no toca
  `generacion`/`aemet_diario`.
  **Hecho cuando:** tests en verde y `PRAGMA table_info` muestra ambas claves.

- [x] **T-03 — Upsert del archivo de fuentes** · RF-1 (CA-1.2–1.4, CE-8)
  `save_forecast_rows(conn, filas, fuente)`: misma elaboración sustituye sus valores,
  elaboración nueva se añade, sin `DELETE`, sin elaboración queda marcada y no elegible.
  **Hecho cuando:** tests en verde — recaptura no duplica, nueva elaboración conserva la
  anterior, `elaborado=''` queda archivado pero fuera de la elección.

- [x] **T-04 — Guardado de la predicción propia** · RF-2 (CA-2.1, CA-2.2, CE-6)
  `save_own_prediction(conn, fila)`: inserta o sustituye por `(fecha_objetivo,
  fecha_emision)`; guarda `prediccion_mwh`, `modelo`, `vector_entrada` y `origenes` (JSON).
  **Hecho cuando:** tests en verde — reejecución el mismo día sustituye sin duplicar y
  emisiones de días distintos conviven.

- [x] **T-05 — Real y error** · RF-2 (CA-2.3, CA-2.4, CE-7)
  `predictions_without_real(conn, hoy)`, `update_real(conn, objetivo, real_mwh)` y
  `con_error(prediccion, real)`.
  **Hecho cuando:** tests en verde — `error_mwh = real − prediccion`, `prediccion_mwh`
  intacto tras la actualización y sin real no se rellena nada.

## Fase 2 — Lógica pura (`prevision.py`, con `hoy` como parámetro)

- [x] **T-06 — Ventana de un solo origen** · RF-4 (CA-4.1, CE-12 de la 003)
  `ventana_mono_origen(serie_obs, serie_prev, objetivo, dias, hoy)`: íntegra de
  observación → `observacion`; si no, íntegra de previsión → `prevision`; si no, `None`.
  **Hecho cuando:** tests en verde — nunca mezcla, nunca acorta, hueco en ambas → `None`.

- [x] **T-07 — Origen por variable y calendario** · RF-4 (CA-4.4, CA-4.5)
  `origen_variable(nombre, valor_obs, valor_prev)`: vocabulario
  `observacion`/`prevision`/`estimada`; calendario siempre `observacion`; `sol` previsto
  es `estimada` y `tmed` previsto es `prevision`.
  **Hecho cuando:** tests en verde del vocabulario completo y del calendario.

- [x] **T-08 — Mapa de orígenes** · RF-4 (CA-4.1–4.5, CE-1, CE-3, CE-4)
  `resolver_origenes(obs_meteo, obs_solar, obs_gen, prev, objetivo, hoy,
  permitir_prev_gen)`: pseudocódigo del plan §3; `velmedia`/`racha` siempre `prevision`;
  ancla de generación por RF-12; `permitir_prev_gen=False` por defecto (P-2).
  **Hecho cuando:** tests en verde — las dos vías de `permitir_prev_gen`, hueco sin REE →
  `NO_DISPONIBLE` declarado, día incompleto descartado como ancla.

- [x] **T-09 — Reales solo desde observación** · RF-2, RF-5 (CA-2.3, CA-5.1)
  `reales_pendientes(predicciones, generacion, hoy)`: candidatas a recibir `real_mwh`
  mirando **solo** `generacion` (nunca `prediccion_diaria`).
  **Hecho cuando:** tests en verde — una previsión archivada no puede hacer de real.

## Fase 3 — Notebook: captura

- [x] **T-10 — Celda de captura AEMET** · RF-3 (CA-3.1, CA-3.3–3.5), RF-1
  Celda nueva en el bloque de descarga (antes del feature engineering): dos pasos con
  pausa y reintento ante 429, parseo con `forecast.py` (sin tocarla), guardado con
  `save_forecast_rows(..., fuente='aemet')` y resumen impreso.
  **Hecho cuando:** ejecución real archiva las 12 ubicaciones con su horizonte, imprime
  el resumen con incidencias, y una segunda ejecución el mismo día añade 0 filas.

- [x] **T-11 — P-1: medición de la fuente REE** · D-4-1, RF-3 (CA-3.2)
  Sondear ESIOS/apidatos: qué publica de previsión eólica peninsular, horizonte,
  granularidad y si declara elaboración. Documentarlo en el Anexo de la spec.
  **Hecho cuando:** el Anexo recoge indicador/endpoint, campos y veredicto viable/no
  viable; si no viable, la spec se reduce y se informa (T-12 y T-13 parcial quedan
  bloqueadas).
  **Resultado (2026-11-07):** sin token, ESIOS 541 solo da el día en curso y
  1777/1778/10358/10359 devuelven 403; `apidatos` no tiene endpoint de previsión.
  Veredicto: no viable sin credencial. Evidencia en `spec.md`, Anexo A.
  **Reabierta y cerrada (2026-11-08):** con `x-api-key` el 1777 responde 200 y cubre
  2020→hoy; se archiva D+1 en vivo y se reconstruye el histórico (Anexo B).

- [x] **T-12 — Captura REE** · RF-3 (CA-3.2, CA-3.6), RF-1, RF-7
  `src/pipeline/esios.py` (parseo y verificación, stdlib) y dos celdas en el notebook:
  relleno histórico y captura D+1.
  Archivar la previsión de generación del indicador 1777 con `fuente='ree'`,
  `ubicacion='peninsula'` y `elaborado = values_updated_at`.
  **Hecho cuando:** filas `fuente='ree'` en `prediccion_diaria` con resumen, y
  recaptura sin duplicar.
  **Resultado (2026-11-08):** 1 774 filas (1 773 reconstruidas + 1 en vivo), 0 huecos;
  segunda pasada con 0 filas nuevas y 0 peticiones de bloques ya completos.

- [x] **T-12.3b — Relleno histórico verificado** · RF-7 (CA-7.1–7.4), D-4-6, D-4-7
  `rellenar_historico_ree` por bloques anuales: solo archiva si el sello es el día
  anterior al final del bloque, etiqueta `objetivo − 1`, acota la ventana pedida y reduce
  el parte. `prevision_db.objetivos_cubiertos` evita reconstruir días ya cubiertos.
  **Hecho cuando:** `2022-01-01 → hoy` sin huecos, 5 peticiones y reejecución idempotente.

## Fase 4 — Notebook: predicción con origen declarado

- [x] **T-13 — Celda del mapa y vector de mañana** · RF-4 (CA-4.1–4.5)
  Celda nueva que construye el vector con `resolver_origenes` y pinta la tabla
  variable → valor + origen (🟢/🔵/🟡), con aviso de `NO_DISPONIBLE` si lo hubiera.
  **Hecho cuando:** la ejecución imprime la tabla completa de las 18 variables y la
  predicción de mañana se emite con origenes declarados.

- [x] **T-14 — Celda de guardado de la predicción** · RF-2 (CA-2.1, CA-2.2), RF-6
  Tras la predicción (PASO 8): `save_own_prediction` con el vector y `origenes` del mapa;
  confirmación impresa.
  **Hecho cuando:** `prediccion_propia` tiene la fila del día con su JSON, y reejecutar
  el notebook la sustituye sin duplicar.

- [x] **T-15 — Celda de actualización de reales y MAE** · RF-2 (CA-2.3, CA-2.4), RF-6
  Tras la descarga de REE: `reales_pendientes` → `update_real` e impresión del MAE de las
  últimas N predicciones con real.
  **Hecho cuando:** una predicción de un día ya publicado recibe `real_mwh`/`error_mwh`
  y la celda imprime el MAE con su n.

## Fase 5 — Integridad, spec y cierre

- [x] **T-16 — Integridad de las tablas de observación** · RF-5 (CA-5.1), decisión 7 del plan
  Test estático: las únicas funciones del notebook que escriben en `generacion` y
  `aemet_diario` son las dos descargas ya existentes.
  **Hecho cuando:** test en verde y recuento de escritores documentado en tasks.md.

- [ ] **T-17 — Enmienda de la spec y cierre de dudas** · plan §7
  *D-4-1, D-4-2, D-4-3, D-4-6 y D-4-7 quedan resueltas y documentadas en el Anexo B;
  D-4-4 (captura del backend) y D-4-5 (retención) siguen abiertas y así se declaran.*
  Actualizar `spec.md`: RF-7 y CA-3.6, CA-4.3 activa, criterios de finalización y estado
  de las decisiones.
  **Hecho cuando:** `spec.md` ya no contiene las contradicciones detectadas por QA.
  **Estado (2026-11-08):** RF-7, CA-3.6 y Anexo B añadidos; CA-4.3 y CE-1 actualizadas.
  Queda pendiente solo la decisión de backend (D-4-4) y retención (D-4-5).

- [x] **T-18 — Ejecución completa, puerta y memoria** · RF-6 (CA-6.1, CA-6.2), criterios §8
  Notebook completo de arriba abajo, puerta en verde, `MEMORY.md` con decisión, métricas
  y estado del archivo.
  **Hecho cuando:** ejecución end-to-end sin errores, `node --test` en verde con las
  suites nuevas, y `MEMORY.md` actualizado.

## Dependencias

```
T-01 → T-02 → T-03 ─┬→ T-10 ──────────────┐
               T-04 → T-05                │
T-06 → T-07 → T-08 → T-09                 ├→ T-13 → T-14 → T-15 ┐
               T-11 → T-12 → T-12.3b ─────┘                     ├→ T-18
               T-16 (independiente, tras T-02) ─────────────────┘
               T-17 (tras confirmaciones del usuario) ──────────┘
```

**Paradas (plan §7):** P-1 quedó resuelta con la credencial de ESIOS (T-12 cerrada);
P-2 se activa con D-4-3 (`permitir_prev_gen=True`); P-3 solo condiciona D-4-4 y D-4-5.

## Cierre (2026-11-07)

- **Copia de seguridad:** `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-004/ree_generacion-antes-spec004-20261107-211803.db`; `PRAGMA integrity_check` = `ok` en original y copia.
- **Puerta:** `node --test "src/pipeline/tests/*.test.mjs"` → **16/16 tests Node en verde**; descubre **326 tests Python** (`Ran 326 tests`, `OK`).
- **Notebook:** 101 celdas, ejecución completa con `.venv/Scripts/python.exe` (3.11.9). 12 ubicaciones AEMET × 7 días = **84 filas**; segunda ejecución el mismo día → **0 nuevas**.
- **Predicción propia:** 1 fila para 2026-11-08, **156.080 MWh**, 18 variables y JSON de orígenes (`observacion=8`, `prevision=3`, `estimada=7`). Reejecutar sustituye sin duplicar.
- **Reales:** verificación sobre una copia de la base; `real_mwh` y `error_mwh` se rellenan solo desde `generacion` y el MAE sale con su `n`.
- **Integridad:** las únicas escrituras en `generacion`/`aemet_diario` siguen siendo las dos descargas existentes (`test_integridad_notebook`, 5 tests).
- **Bloqueos vivos:** T-12 (sin credencial ESIOS), T-17 (D-4-2/D-4-4/D-4-5) y T-18 queda cerrada con la puerta y `MEMORY.md` actualizados.
  *Superado el 2026-11-08: T-12 cerrada con la credencial de ESIOS; ver «Cierre de T-12».*

## Cierre de T-12 (2026-11-08)

- **Relleno histórico:** 1 773 filas reconstruidas (`2022-01-01 → 2026-11-08`), 5
  peticiones (una por año), los cinco bloques con sello válido y 0 huecos.
- **Captura en vivo:** 1 fila para `2026-11-09`, elaborada `2026-11-08T10:50:40+01:00`.
  Total del archivo: **1 774 filas `fuente='ree'`**, rango `2022-01-01 → 2026-11-09`.
- **Idempotencia:** segunda pasada → 0 filas nuevas, 5 bloques «ya completo», 0 peticiones
  de histórico y la misma fila en vivo sustituida.
- **Parte reconstruido:** 388 B de media (máximo 638 B), con `reconstruido`, `regla`,
  `ventana`, `sello_ventana` y el valor del día.
- **Mapa:** con la generación observada parada en 2026-11-06, `eolica_lag2/3/7` y
  `eolica_ma7` salen `prevision`; `eolica_lag1` sigue `observacion`.
- **Puerta:** `node --test "src/pipeline/tests/*.test.mjs"` → 16/16 Node;
  **378 tests Python**, `OK`.
- **Verificación de las celdas:** ejecutadas directamente contra
  `src/data/ree_generacion.db` (dos pasadas). No se reejecutó el notebook completo para no
  reescribir sus 104 celdas de salida; la estructura y las prohibiciones de escritura las
  cubre `test_integridad_notebook` (9 tests).
- **Copia previa:** `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-relleno-ree/`.
