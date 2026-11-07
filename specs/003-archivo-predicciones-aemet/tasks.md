# Tareas 003 — Archivo de previsiones meteorológicas

Deriva de `spec.md` (RF-1 a RF-13) y `plan.md` (apartados 1–10). Ciclo obligatorio por tarea: test en
rojo, implementación mínima, verde, refactor. Ninguna tarea se cierra con la puerta en rojo (RNF-6).

**Puerta:** `node --test "src/pipeline/tests/*.test.mjs"`.

## Estado

| # | Tarea | RF | Depende de | Estado |
|---|---|---|---|---|
| T-01 | Fixtures reales de los dos partes (diario y horario) | RF-2 | — | ✅ hecho |
| T-02 | Catálogo de 12 ubicaciones con su uso | RF-3 | D-3-1 | ✅ hecho (D-3-1 resuelta por precedente, ver nota) |
| T-03 | `parse_daily_parte` / `parse_hourly_parte` + tests | RF-1, RF-7, RF-8 | T-01 | ✅ hecho |
| T-04 | Esquema del archivo + upsert + tests en base en memoria | RF-2, RF-4 | T-02 | ✅ hecho |
| T-05 | `aemet_forecast.py` y paso de captura en el planificador | RF-1, RF-3, RF-6, RF-13 | T-03, T-04 | ✅ hecho (descarga real verificada) |
| T-06 | Verificar dos capturas seguidas: días nuevos y 0 duplicados | RF-4 | T-05 | ⏳ parcial: 3 capturas reales del mismo día con 0 duplicados (84 filas); falta un día nuevo |
| T-07 | `capture_targets` / `pending_days` + recuperación acotada al horizonte | RF-6 | T-05 | ✅ hecho |
| T-08 | `choose_forecast` + paridad con la consulta del backend | RF-5 | T-04 | ✅ hecho |
| T-09 | `mean_temperature`, `daylight_hours`, `sky_factor`, `estimate_sun` | RF-7 | T-03 | ✅ hecho |
| T-10 | `moving_average` y serie nacional de previsión | RF-8 | T-09 | ✅ hecho |
| T-11 | Calibración de `sol` contra la observación (correlación y sesgo) | RF-7 | T-09 | ⏳ pendiente (necesita archivo con solape) |
| T-12 | Celdas nuevas del notebook: cobertura y variables en paralelo | RF-9 | T-08, T-10 | ✅ hecho |
| T-13 | `evaluation_windows`, `decide_improvement` y tabla de veredicto | RF-10 | T-12, D-3-2 | ✅ lógica hecha; integración con el notebook pendiente |
| T-14 | Actualización condicionada del modelo y verificación de recarga | RF-11 | T-13 | ⏳ pendiente (exige decisión y reentrenamiento) |
| T-15 | Frescura de generación (independiente del archivo) | RF-12 | — | ✅ hecho |
| T-16 | Informe, `MEMORY.md` y cierre de dudas | RF-13 | T-14 | ⏳ parcial (estado de captura, trazabilidad e informe de captura hechos) |

## Detalle y criterio de cierre

### T-01 · Fixtures de los partes
- Guardar en `src/pipeline/tests/fixtures/prediccion_diaria.json` y `prediccion_horaria.json` una respuesta
  real completa (municipio 16078, 2026-11-02), para que el parseo no derive con el esquema de AEMET.
- **Cierre:** los fixtures existen y los tests los leen sin red.

### T-02 · Catálogo de 12 ubicaciones
- 7 eólicas (las de producción) + 5 solares, cada una con clave, código INE de municipio, uso y latitud.
- **Cierre:** 12 entradas, claves únicas, campos completos, 7 eólicas y 5 solares (test).
- **Nota D-3-1:** se aplica el precedente eólico (municipio de la planta) y se validan los cinco códigos
  contra la API de AEMET el 2026-11-02: Torrecillas de la Tiesa `10186`, Usagre `06136`, Mula `30029`,
  Alcalá de Guadaíra `41004`, Chiprana `50092`. Confirmar con el usuario si prefiere otro criterio.

### T-03 · Parseo
- Diario: viento por tramos, `tmax`/`tmin`, cielo por tramos de 6 h, `uvMax`, `elaborado`.
- Horario: temperaturas y vientos hora a hora, racha máxima, cielo horario, `orto`/`ocaso`, `elaborado`.
- **Cierre:** tests sobre los fixtures + casos de valor vacío, coma decimal y tramo mal formado.

### T-04 · Esquema y upsert
- Tabla `prediccion_aemet` con clave `(elaborado, objetivo, ubicacion)`, el parte original y `capturado_en`.
- Tabla `captura_estado` con una fila por ejecución.
- **Cierre:** recapturar la misma elaboración sustituye; una elaboración nueva añade; nunca se pisa la anterior.

### T-05 · Cliente y planificador
- Descarga en dos pasos con pausa y reintento, tolerante a fallos por ubicación.
- Paso nuevo en `run_daily_task` **antes** de la predicción; una captura sin ninguna ubicación deja error visible.
- **Cierre:** puerta en verde; descarga real verificada en T-06.

### T-06 · Dos capturas seguidas
- Ejecutar la captura dos días (o dos veces) y comprobar que el segundo día añade días nuevos y 0 duplicados.
- **Cierre:** recuento de filas antes/después y `PRAGMA integrity_check` sin cambios.

### T-07 · Recuperación
- `capture_targets` y `pending_days` con el horizonte del parte (7 días); el día sale de «recuperable» en
  cuanto la fuente publica la elaboración siguiente.
- **Cierre:** tests de recuperable/perdido y de reintento del mismo día.

### T-08 · Elección de previsión
- `choose_forecast` + consulta SQL equivalente en `forecast_db.py`.
- **Cierre:** tests de elaboración anterior/igual/posterior/ausente + paridad función/SQL.

### T-09 · Temperatura e insolación
- Media horaria, extremos como respaldo, horas de luz astronómicas, tabla de factores de cielo, recorte a
  `[0, horas de luz]`, `NO_DISPONIBLE` si falta un tramo de día.
- **Cierre:** solsticios, cambio de hora, código desconocido, cielo nocturno, día cubierto = 0.

### T-10 · Viento, racha y medias móviles
- Serie nacional por uso y media móvil de 3/7/14 sin acortar ni rellenar.
- **Cierre:** ventana incompleta → `NO_DISPONIBLE`; racha ausente invalida solo su media.

### T-11 · Calibración de `sol`
- Comparar estimado y observado en el solape; correlación y sesgo; descartar si correlación < 0,7.
- **Cierre:** informe con MAE, sesgo y n; decisión registrada.

### T-12 · Notebook: cobertura y variables en paralelo
- Dos celdas al final del bloque eólico, sin reordenar: cobertura/antigüedad y variables `*_prev`.
- **Cierre:** ejecución completa sin tocar el modelo de producción.

### T-13 · Comparación y criterio
- `evaluation_windows` (21 días, paso 7), `decide_improvement` (2 %, mayoría, mínimo 3 ventanas) y
  `truthfulness_report`.
- **Cierre:** tabla por ventana y veredicto; sin decisión si hay menos de tres ventanas.

### T-14 · Actualización condicionada
- Guardar en ruta temporal, recargar, verificar métricas y solo después sustituir; sincronizar copias.
- **Cierre:** `GET /api/prediction` responde y las 4 copias coinciden.

### T-15 · Frescura de generación
- Construir retardos y `eolica_ma7` con la última generación publicada; avisar si el último día es anómalo.
- **Cierre:** reentrenamiento documentado y métricas de referencia actualizadas.

### T-16 · Informe y cierre
- Informe con ventanas, métricas, cobertura y decisión; `MEMORY.md` al día.
- **Cierre:** el informe existe y la memoria recoge la decisión.

## Verificación de esta pasada (2026-11-02)

**Puerta:** `node --test "src/pipeline/tests/*.test.mjs"` → 16 tests de Node en verde; la suite de Python que
lanza `gate.test.mjs` son 248 tests, también en verde (`OK`, 0 fallos).

**Captura real contra AEMET** (base de datos temporal, no la versionada): 12 ubicaciones capturadas, 84 filas,
7 días de horizonte, elaboración `2026-11-02T15:45:08`, 0 errores, 0 duplicados tras tres ejecuciones y 0
valores ausentes de viento, racha y sol para los tres primeros días. AEMET devolvió 429 en dos peticiones y el
reintento con espera las resolvió (RNF-7).

**Tres defectos encontrados con datos reales, corregidos con su test:**

1. **Días lejanos sin `periodo`.** AEMET omite `periodo` cuando el valor vale para todo el día (del 11-06 en
   adelante): el viento y el cielo de tres de los siete días se perdían. Ahora el tramo implícito es `00-24`.
2. **Parte horario a medias.** En el último día de su horizonte el horario solo publica de 00 a 06; se cogía
   su cielo y se descartaba el del diario, dejando el día sin insolación. Ahora `merge_tramos` combina hora a
   hora: manda el horario donde tiene dato y el diario rellena el resto.
3. **Temperatura media nocturna.** Promediar las siete horas publicadas daba 2,6 °C donde el día promediaba
   8 °C. Con menos de 12 horas se usa la media de extremos (CA-7.1).

**Pendiente por imposibilidad material o por decisión abierta:** T-06 (hace falta otro día), T-11 (hace falta
archivo con solape previsión/observación), T-13 integración y T-14 (bloqueadas por D-3-2).

**Verificación del 2026-11-02 (segunda pasada, T-12 y T-15):**

- **Puerta:** `node --test "src/pipeline/tests/*.test.mjs"` → 16 tests de Node en verde; la suite de Python
  completa (`unittest discover` sobre `src/pipeline/tests`) son **258 tests en verde** (los 248 anteriores
  más los 10 nuevos de `TestFrescuraGeneracion`).
- **Notebook (91 celdas) ejecutado completo en 51 s** sin tocar el orden ni los nombres de etapa: se
  insertaron 4 celdas entre el feature engineering (64) y el split (ahora 70). El `.joblib` del notebook
  sigue en `src/data/modelos/` (18 variables, test 2025-11-12 → 2026-10-29: **RMSE 39.387,9 MWh · MAE
  29.533,6 · R² 0,8046**); las copias de producción intactas. Cambio de métricas respecto a la pasada
  anterior: 2 días nuevos de datos descargados (CA-12.4 documentado), no el cambio de la spec.
- **T-12.** Celda de cobertura (lee `prediccion_aemet` en **solo lectura**, `ARCHIVO_PATH` o la BD del
  backend; una elaboración por día/ubicación vía `choose_forecast`) y celda de 10 variables `*_prev` en
  `df_ml_prev`, en paralelo a `df_ml`. Con el archivo de un solo día: 1.756 de 1.756 filas declaradas
  descartadas, por variable (CA-9.3, CA-9.4). `FEATURE_COLS` intacta; `FEATURE_COLS_PREV` (18) preparada
  para T-13. El `sol` de previsión se declara proxy estimado, no observación.
- **T-15.** Lógica pura en `forecast.py` (`generation_freshness`, `generation_lags`; 10 tests) con copia
  vendorizada y paridad en verde. Hallazgo con datos reales: **REE publica los dos últimos días
  incompletos** (2026-10-30 al 39 % y 2026-10-29 al 34 % de la mediana de los 7 anteriores). El día
  incompleto se señala y se descarta: el ancla de `eolica_lag1/2/3/7` y `eolica_ma7` retrocede al último
  día completo (2026-10-28, 6 días antes de mañana) en vez de arrastrar la última meteorología (CA-12.1,
  CA-12.2). La predicción de mañana pasó de ~162 GWh a ~203 GWh (Linear Regression) al dejar de usar el
  día parcial. No toca las filas de entrenamiento (sus retardos son relativos a su propia fecha).

