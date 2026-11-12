# Tareas 005 — Previsión de REE del día objetivo

Deriva de `spec.md` y `plan.md`. Cada tarea se implementa **primero con su test
en rojo** y luego con el código que lo pone en verde (constitución, principio 5).
No se avanza con la puerta en rojo. La puerta es `node --test`.

Copia previa hecha en `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-005/`
(base, modelo y notebook) antes de tocar nada.

## Bloque A — Lógica pura y su contrato

- [x] **T-01 — Elegibilidad del día objetivo** (RF-1, CA-1.2/1.3, CE-2/3/4/5/7)
  - Tests en `test_prevision.py`: `TestPrevisionElegible` y
    `TestSeriePrevisionObjetivo`.
  - Código: `valor_prevision_valido`, `prevision_elegible`,
    `serie_prevision_objetivo` en `prevision.py`.
  - Acepta: elaboración `≤ min(objetivo − 1, hoy)`; gana la más reciente;
    propia del objetivo, posterior, otra ubicación, sin elaboración y valor
    imposible quedan fuera; cero válido; desempate por captura.

- [x] **T-02 — Relleno de 7 días** (RF-2, RF-3, CA-2.1/2.2/2.4, CA-3.2/3.3, CE-1/6)
  - Tests: `TestRelleno`.
  - Código: `rellenar_prevision`.
  - Acepta: real intacta; hueco = media de reales de los 7 días anteriores;
    menos de 7 usa los que haya; sin reales devuelve `None`; un relleno no
    alimenta a otro; la ventana se corta en `hoy`; un cero real cuenta.

- [x] **T-03 — Serie rellenada y cobertura** (RF-5, CA-5.1/5.2)
  - Tests: `TestSerieRellenada`.
  - Código: `serie_prevision_rellenada`, `resumen_prevision`.
  - Acepta: recuentos `reales/estimadas/sin_dato`; huecos con fecha ISO y
    `dias_media`; resultado determinista y ordenado.

- [x] **T-04 — Métricas, referencia e informe** (RF-4, CA-4.5/4.6, CA-5.3)
  - Tests: `TestMetricasYReferencia`, `TestInformePrevision`.
  - Código: `metricas`, `referencia_prevision`, `informe_prevision_ree`.
  - Acepta: RMSE/MAE/R² calculados a mano; días incompletos fuera; conjunto
    vacío sin métricas; el informe añade modelo, globales, referencia y
    cobertura sin mutar la entrada y es serializable a JSON.

- [x] **T-05 — Mapa de 19 variables** (RF-1, RF-3, CA-3.4)
  - Tests: ampliar `TestMapaOrigenes` y actualizar el contrato de 18 a 19.
  - Código: `VARIABLES_MODELO` con `eolica_prev` y parámetro
    `prevision_objetivo` en `resolver_origenes`.
  - Acepta: real → `prevision`; relleno → `estimada` con `dias_media`; sin
    dato → no disponible; origen desconocido no entra.

- [x] **T-06 — MAE opcional en `resumen_folds`** (CA-4.5)
  - Tests en `test_evaluacion.py`.
  - Código: `evaluacion.resumen_folds` añade `mae` por fold solo si se aporta.
  - Acepta: con `mae` aparece; sin `mae` el informe solar no cambia; longitud
    incoherente falla.

## Bloque B — Notebook y contrato de los informes

- [x] **T-07 — Celda nueva del dataset** (RF-1, RF-2, RF-5, CA-5.4)
  - Test: `test_integridad_notebook.py` (marca, solo lectura, lógica pura).
  - Notebook: celda tras el dataset con `serie_prevision_objetivo`,
    `serie_prevision_rellenada`, columna `eolica_prev`, descarte contado de
    CE-1 y `FEATURE_COLS_PREVISION`; celda 69 excluye la columna.
  - Acepta: el archivo se abre en solo lectura; no se escribe en observación;
    la suite estática pasa.

- [x] **T-08 — Mapa y vector de mañana** (RF-3, CA-3.3, CA-1.4)
  - Notebook: celdas 78, 95 y 102.
  - Acepta: el mapa declara `eolica_prev`; la predicción se detiene solo si
    falta una variable del modelo; el origen se archiva con la predicción.

- [x] **T-09 — Walk-forward de tres variantes** (RF-4, CA-4.1–4.6)
  - Notebook: celda 91 con 16/18/19, decisión 18→19, métricas globales,
    referencia por fold y total.
  - Acepta: la decisión se toma entre 18 y 19; `COLUMNAS_MODELO` sale de ella;
    la referencia se mide en los mismos días de test.

- [x] **T-10 — Dos actas y contrato del modelo** (RF-4, RF-5, CA-5.3)
  - Notebook: celda 100 escribe `sol_como_feature.json` (16→18) y
    `prevision_ree_como_feature.json` (18→19).
  - Test: `test_contrato_modelo.py` valida las dos actas y cruza la producción.
  - Acepta: las dos actas comparten la producción real y es coherente con la
    decisión (19 aceptada, 18 rechazada).

## Bloque C — Ejecución y cierre

- [x] **T-11 — Ejecución completa y verificación** (criterios §9)
  - Copia previa vigente; notebook de arriba abajo sin errores; dos ejecuciones
    el mismo día dan la misma predicción y una sola fila; observación intacta;
    `node --test` en verde.
  - Acepta: informes escritos y legibles; predicción guardada con su origen.

- [x] **T-12 — Cierre documental**
  - `MEMORY.md` con la decisión, números y estado del modelo.
  - Enmiendas de redacción de la spec 005 (CA-2.1, CA-3.3/CE-9, CE-8) según
    P-4 del plan.
  - Marcar las tareas realizadas en este archivo.

## Cierre (2026-11-11)

- **Puerta:** `node --test` → 16/16 Node; la suite Python que lanza la puerta,
  `430 tests OK` (0 omitidos). Antes de la 005 eran 380 + 16.
- **Ejecución completa:** notebook de arriba abajo en 132 s y 192 s (dos
  pasadas). 105 celdas, ninguna celda de código con error.
- **Decisión 18→19: ACEPTADA** en 4 de 4 folds.

  | fold | 16 RMSE | 18 RMSE | 19 RMSE |
  |---|---|---|---|
  | 2023 | 41.291 | 39.524 | 19.591 |
  | 2024 | 39.958 | 39.997 | 19.176 |
  | 2025 | 40.095 | 39.085 | 17.216 |
  | 2026 | 39.811 | 39.195 | 23.847 |

  Global: 18 → 19.945 RMSE · 13.534 MAE · R² 0,9479. Previsión de REE sola:
  21.175 RMSE · 13.832 MAE (1.407 días). El modelo de 19 mejora a la previsión
  sola, así que no se limita a copiarla.
- **Cobertura:** 1.765 días del dataset con previsión real, **0 rellenos**, 0 sin
  dato (el día 2021-12-31 lo descartaban ya los retardos).
- **Predicción de mañana:** `2026-11-12` · **341.667,36 MWh** ·
  `LinearRegression (19 variables)` · `eolica_prev: prevision`. Dos ejecuciones
  el mismo día dan el mismo valor y **una sola fila** (5 en total).
- **Observación intacta:** `generacion` 10.651 filas y `aemet_diario` 30.511,
  con la misma huella que la copia previa de `backup-005/`.
- **Modelo:** `src/data/modelos/lr_eolica.joblib` (19 features, SHA-256
  `0fcb2dcc…`). Las 3 copias de producción siguen sin tocar, como pedía P-1.
- **Actas:** `src/data/modelos/sol_como_feature.json` (16→18) y
  `prevision_ree_como_feature.json` (18→19), ambas con producción de 19 y las
  mismas `rutas`.

