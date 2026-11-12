# Plan 006 — EDA de variables nuevas y familia del modelo

Deriva de `spec.md`. Sin dependencias nuevas en `src/`; todo el cálculo pesado
sigue en el notebook y la lógica reutilizable en `src/pipeline/`.

## 1. Decisiones de diseño

- **D-6-1 — Una sola función pura para Pearson.**
  `src/pipeline/exploracion.py` con `correlacion_pearson(xs, ys)`: stdlib puro
  (`math`), devuelve `{n, r}`. Pares ausentes fuera; `n < 2` o varianza cero →
  `r = None`. Es lo único que necesita test unitario: el resto son gráficas.
- **D-6-2 — EDA dentro de FEATURE ENGINEERING y después del solar.**
  La construcción de `eolica_prev` permanece tras el feature engineering base.
  El estudio de REE se presenta inmediatamente después del encabezado
  `Evaluamos la relación de las variables solares`, todavía dentro de
  `### FEATURE ENGINEERING` y antes de `### BLOQUE DE PREVISIÓN (spec 003)`.
  Replica el patrón solar: escalado, series, dispersión y heatmap. La tabla de
  correlaciones se imprime con la función pura.
- **D-6-3 — Walk-forward antes del ranking.**
  La celda del walk-forward de variables (hoy 92) se mueve detrás del mapa de
  orígenes (79) y antes del split (81). Así `COLUMNAS_MODELO` existe cuando el
  ranking entrena. El bloque de "modelo de producción" que hoy vive al final de
  esa celda se separa a una celda nueva tras el ranking.
- **D-6-4 — El ranking usa `COLUMNAS_MODELO`.**
  Split, `X_train/X_test`, importancias y gráficas. `FEATURE_COLS` solo queda
  como referencia histórica del acta solar.
- **D-6-5 — Candidata = mejor de las seis clásicas.**
  MLP (target normalizado) y SARIMAX (serie endógena) tienen recetas distintas y
  no se pueden clonar con el mismo walk-forward sin reescribirlas. La candidata
  sale de las seis que comparten `evaluar()`.
- **D-6-6 — Cambio de familia con `criterio_aceptacion`.**
  Se reutiliza la función de la spec 002: RMSE estricto y ≥3 de 4 folds. Sin
  lógica nueva que probar.
- **D-6-7 — El artefacto declara el preprocesado.**
  `{modelo, scaler, features, familia, usa_scaler}`. La recarga aplica el scaler
  solo si `usa_scaler`; la comprobación `np.allclose` se hace contra
  `predecir_produccion`.
- **D-6-8 — Backend fuera de alcance (punto de parada P-1).**
  El backend no tiene `prediccion_diaria` ni captura de previsiones de REE, así
  que no puede construir `eolica_prev` (ni `sol_lag1`/`tmed_lag1`, deuda T-17 de
  la 004). Copiar el modelo de 19 variables o la familia nueva a producción
  rompería la predicción. La spec deja el análisis y el acta; la adopción web
  necesita su propia spec con la captura de REE en backend.

## 2. Cambios por archivo

### `src/pipeline/exploracion.py` (nuevo)

```python
def correlacion_pearson(xs, ys) -> dict:
    """{n, r} de los pares completos; None si no se puede calcular."""
```

- Filtra `None` y `NaN` (con `math.isnan`).
- `n < 2`, varianza cero o longitudes distintas → `ValueError` solo para
  longitudes; varianza cero → `r=None`.

### `src/pipeline/tests/test_exploracion.py` (nuevo)

Casos: correlación perfecta ±1, valores conocidos, `n`, pares incompletos,
`n<2`, varianza cero, longitudes distintas y determinismo.

### `src/notebooks/main.ipynb`

| Cambio | Detalle |
|---|---|
| `### FEATURE ENGINEERING` | Construcción de `eolica_prev`; EDA tras el estudio solar y antes del bloque spec 003 |
| `# Walk-forward 2023–2026...` antes del split | Walk-forward 16/18/19, sin el bloque de producción; imports locales de sklearn |
| `# Split 80/20 temporal...` | Split con `COLUMNAS_MODELO` y aserciones de ancho para train/test |
| Importancias y ranking clásico | Usan las matrices `X_train`/`X_test` derivadas de `COLUMNAS_MODELO` |
| `# FAMILIA DEL MODELO...` | Walk-forward de familia + decisión + modelo de producción + `predecir_produccion` |
| `### PASO 7: PRONÓSTICO...` | Predicción de mañana con `predecir_produccion`; etiqueta con `FAMILIA_MODELO` |
| `### PASO 8: GUARDAR Y CARGAR...` | `.joblib` con familia y `usa_scaler`; recarga con el mismo preprocesado |
| `# Informes de trazabilidad...` | Tercer acta `familia_como_modelo.json` |
| `# PREDICCIÓN PROPIA...` | Modelo declarado con la familia real |

### `src/pipeline/tests/test_contrato_modelo.py`

Clase `TestActaFamilia`: base LinearRegression, variante = familia del acta,
decisión coherente con `features_produccion`, folds y métricas, y producción
compartida con las otras dos actas.

### `src/pipeline/tests/test_integridad_notebook.py`

Marca de la celda EDA, llamada a `exploracion.correlacion_pearson`, presencia de
`FAMILIA_MODELO`, `predecir_produccion`, `familia_como_modelo.json` y
`COLUMNAS_MODELO` en el split.

## 3. Orden de ejecución

1. Tests en rojo (`test_exploracion`, contrato e integridad).
2. `exploracion.py` (verde de su suite).
3. Script de edición del notebook y verificación estática (`ast.parse`).
4. Ejecución completa del notebook.
5. `node --test` y comprobación de actas, observación y predicción.
6. `MEMORY.md`, marcar tareas y cerrar.

## 4. Riesgos

- **El walk-forward se mueve de sitio.** Depende de `evaluacion`, `prevision`,
  `StandardScaler` y las métricas; se añaden imports explícitos en la celda
  movida para no depender del orden.
- **`modelo_lr` se usa en tres celdas.** Se renombra a `modelo_prod` y se
  centraliza la predicción en `predecir_produccion`, para que un árbol no
  reciba datos escalados.
- **La familia candidata puede ser un árbol.** `clone` de sklearn funciona con
  XGBoost y LightGBM; la semilla queda fijada en el ranking.
- **`predicciones["Linear Regression"]` de la celda 93** ahora se entrena con
  19 columnas; el gráfico sigue siendo válido como referencia.

## 5. Verificación

- `node --test` (16 Node + suite Python) en verde.
- Notebook completo dos veces el mismo día: misma predicción y una sola fila.
- Observación intacta por recuento y huella.
- Actas legibles y coherentes entre sí.
- `git status`: sin cambios en `backend/` ni `frontend/`.
