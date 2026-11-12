# Tareas 006 — EDA de variables nuevas y familia del modelo

Deriva de `spec.md` y `plan.md`. Primero el test en rojo, luego el código
(constitución, principio 5). La puerta es `node --test`.

Copia previa en `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-006/`
(BD, wal/shm, `.joblib`, notebook y actas) antes de tocar nada.

## Bloque A — Lógica pura

- [x] **T-01 — Correlación de Pearson** (RF-1, CA-1.1, CA-1.3, CE-1)
  - Tests: `test_exploracion.py`.
  - Código: `src/pipeline/exploracion.py`.
  - Acepta: ±1 en correlación perfecta; `n` real; pares incompletos fuera;
    varianza cero y `n<2` → `r=None`; longitudes distintas → `ValueError`.

## Bloque B — Notebook

- [x] **T-02 — EDA de `eolica_prev`** (RF-1, CA-1.2, CA-1.4)
  - Dentro de `### FEATURE ENGINEERING`, después de `Evaluamos la relación de
    las variables solares` y antes del siguiente bloque principal: escalado,
    series, dispersión, heatmap y tabla de Pearson con la función pura.
  - Acepta: la variable tiene su estudio antes de entrenar; no decide sola.

- [x] **T-03 — Walk-forward antes del ranking** (RF-2, CA-2.1)
  - Mover la celda 92 tras la 79, sin el bloque de producción.
  - Acepta: `COLUMNAS_MODELO` existe antes del split; la celda no depende de
    nombres importados después.

- [x] **T-04 — Split y ranking con las columnas adoptadas** (RF-2, CA-2.2/2.3)
  - Encabezados `# Split 80/20 temporal...` e `Importancias y ranking clásico`:
    `COLUMNAS_MODELO`; aserciones de ancho train/test; escalado solo en familias
    lineales.
  - Acepta: el ranking entrena con 19 si se aceptó `eolica_prev` y lo imprime.

- [x] **T-05 — Walk-forward de familia y decisión** (RF-3, CA-3.1–3.4)
  - Celda nueva tras 91: candidata de las seis clásicas, `clone`, criterio de
    3 de 4 folds, `FAMILIA_MODELO`.
  - Acepta: el rechazo deja LinearRegression; la aceptación cambia la familia.

- [x] **T-06 — Artefacto con familia y preprocesado** (RF-4)
  - Celdas 96, 98, 103: `modelo_prod`, `predecir_produccion`, `.joblib` con
    `familia` y `usa_scaler`, modelo declarado en la predicción.
  - Acepta: la recarga reproduce las predicciones con el preprocesado correcto.

- [x] **T-07 — Acta de familia** (RF-3, CA-3.5; RF-4, CA-4.4)
  - Celda 101: `familia_como_modelo.json` con folds, globales, decisión y
    producción; `test_contrato_modelo.py` la valida.
  - Acepta: las tres actas comparten producción y son coherentes.

- [x] **T-08 — Contrato estático del notebook** (RF-1, RF-2)
  - `test_integridad_notebook.py`: celda EDA, Pearson, familia, acta y split.
  - Acepta: la suite estática pasa sin ejecutar el notebook.

## Bloque C — Ejecución y cierre

- [x] **T-09 — Ejecución completa y verificación**
  - Notebook de arriba abajo sin errores; dos ejecuciones el mismo día con la
    misma predicción y una sola fila; salidas del notebook actualizadas y sin
    claves; observación intacta; `node --test` verde.
  - Acepta: actas escritas, `.joblib` coherente y predicción guardada con su
    familia.

- [x] **T-10 — Cierre documental**
  - `MEMORY.md` con la familia elegida, números y bloqueo de backend (P-1).
  - Marcar las tareas realizadas en este archivo.

## Resultado de la ejecución (2026-11-12)

- En `### FEATURE ENGINEERING`, el EDA de `eolica_prev` quedó detrás del estudio solar;
  guarda la serie escalada, dispersión y heatmap (**3 imágenes PNG**) más la tabla Pearson
  (**r = +0,974**, n = **1.766**).
- Notebook ejecutado dos veces con kernel Jupyter real; las salidas se guardaron en el `.ipynb`
  y no contienen claves. El split muestra explícitamente `X_train (1412, 19)` y
  `X_test (354, 19)`; sus aserciones confirman las 19 columnas finales.
- Ranking con 19 columnas: LightGBM 19.756 · XGBoost 20.516 · MLP 20.633 · RF 21.058 ·
  Ridge 22.868 · **LR 23.038** · Lasso 23.039 · SARIMAX 64.186 (RMSE test).
- Walk-forward de familia (LightGBM frente a LR): 21.174/21.102/17.331/20.546 vs
  19.591/19.176/17.216/23.851 → **1 de 4 folds**: familia **rechazada**, sigue
  **LinearRegression** con 19 variables.
- `.joblib`: `{modelo, scaler, features (19), familia: "Linear Regression", usa_scaler: true}`;
  recarga `np.allclose` correcta (SHA-256 `fd01ac9b…`).
- Acta `familia_como_modelo.json`: 4 folds, métricas globales (LR 23.038 · LightGBM 19.756),
  `features_produccion` = las 19 del acta de previsión, 3 copias de producción sin sincronizar
  (parada P-1).
- Predicción 2026-11-13: **215.030,776 MWh** en ambas pasadas; una sola fila en `prediccion_propia`.
- Observación intacta: `generacion` **10.657** filas y `aemet_diario` **30.522**; ambas conservan
  la huella SHA-256 previa. Backend/frontend y las tres copias de producción no se tocaron.
- **460 tests Python + 16 Node en verde**; incluye los contratos de posición del EDA, dimensiones
  del split, salidas visibles de 19 features y redacción de credenciales.
