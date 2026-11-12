# Spec 006 — EDA de variables nuevas y familia del modelo

Estado: cerrada (2026-11-12).
Depende de: spec 002 (bloque solar), spec 004 (previsiones en `src/`) y
spec 005 (`eolica_prev`).

## 1. Problema

El notebook decide qué **familia** de modelo usar (LinearRegression, Ridge,
Lasso, Random Forest, XGBoost, LightGBM, MLP, SARIMAX) en un split 80/20 que
todavía entrena con las **16 variables** originales. Las variables nuevas de
las specs 002 y 005 se estudian en el walk-forward, pero **no pasan por el
ranking de familias**: la comparación que justificó LinearRegression se quedó
congelada y nunca vio `sol_lag1`, `tmed_lag1` ni `eolica_prev`.

Además, cada variable nueva se añade sin un estudio previo común: el bloque
solar tiene su análisis de Pearson y sus gráficas (celdas 72–73), pero
`eolica_prev` entró sin ese paso y una variable futura volvería a improvisarlo.

## 2. Objetivo

1. Estudiar **cada variable candidata** con el mismo patrón que la fotovoltaica:
   escalado, series temporales, dispersión y correlación de Pearson contra el
   resto, antes de entrenar con ella.
2. Entrenar el **ranking de familias con las columnas ya adoptadas**
   (`COLUMNAS_MODELO`), no con las 16 de siempre.
3. Si otra familia supera a LinearRegression de forma estricta y repetida,
   **sustituirla como modelo de previsión**; si no, se queda LinearRegression.
4. Dejar constancia en un acta y en `MEMORY.md`.

## 3. Fuera de alcance

- Backend y frontend. El backend no tiene `prediccion_diaria` ni puede calcular
  `eolica_prev` (la captura de previsiones de REE en backend es la deuda
  D-4-4/T-17 de la spec 004). Copiar el modelo a producción sigue siendo un
  punto de parada con autorización expresa.
- Añadir variables nuevas distintas de `eolica_prev`: la spec deja la
  herramienta, no inventa features.

## 4. Requisitos funcionales

### RF-1 — Estudio de cada variable nueva

Antes de entrar en el modelo, toda variable candidata pasa por el mismo estudio
que el bloque solar.

- **CA-1.1** Se calcula la correlación de Pearson de la variable con el target y
  con el resto de variables del vector, con su número de días válidos.
- **CA-1.2** Se dibujan, como en la fotovoltaica: serie temporal escalada frente
  a la generación, dispersión frente al target y mapa de calor de Pearson.
- **CA-1.3** El cálculo es una función pura y probada: pares incompletos fuera,
  varianza cero o menos de dos pares devuelven `r = None`, nunca un cero
  silencioso.
- **CA-1.4** El estudio informa; la decisión de adoptar la variable sigue siendo
  del walk-forward de su spec.
- **CA-1.5** En `src/notebooks/main.ipynb`, el estudio de `eolica_prev` queda
  dentro de `### FEATURE ENGINEERING`, inmediatamente después del estudio solar
  y antes del bloque principal siguiente. Incluye serie temporal escalada,
  dispersión, heatmap y correlación de Pearson.

### RF-2 — El ranking entrena con las columnas adoptadas

- **CA-2.1** El walk-forward de variables se ejecuta **antes** del split y del
  ranking: cuando el ranking entrena, `COLUMNAS_MODELO` ya está decidido.
- **CA-2.2** El split 80/20, el ranking de familias y las importancias usan
  `COLUMNAS_MODELO`, no `FEATURE_COLS`.
- **CA-2.3** El escalado se ajusta solo con el train y solo para las familias
  que lo necesitan (lineales); los árboles entrenan con los valores originales.

### RF-3 — Familia del modelo

- **CA-3.1** La candidata es la mejor de las seis familias clásicas del ranking
  (Linear Regression, Ridge, Lasso, Random Forest, XGBoost y LightGBM), que
  comparten la misma receta de entrenamiento. MLP y SARIMAX se mantienen como
  referencia y no optan al cambio.
- **CA-3.2** La candidata se compara con LinearRegression en el mismo
  walk-forward de cuatro folds, con el mismo `COLUMNAS_MODELO`.
- **CA-3.3** Solo sustituye a LinearRegression si el RMSE mejora de forma
  estricta en **al menos 3 de los 4 folds**.
- **CA-3.4** Si no se acepta, el modelo de producción sigue siendo
  LinearRegression y el rechazo se documenta con su motivo.
- **CA-3.5** El acta nueva declara familia candidata, familia de producción,
  métricas por fold y globales, decisión y motivo.

### RF-4 — Artefacto y trazabilidad

- **CA-4.1** El `.joblib` guarda `modelo`, `scaler`, `features`, `familia` y
  `usa_scaler`, de modo que la recarga sepa preprocesar igual.
- **CA-4.2** La verificación en disco reproduce las predicciones del modelo
  entrenado, use o no escalado.
- **CA-4.3** La predicción guardada declara la familia y el número de variables.
- **CA-4.4** El acta y `MEMORY.md` quedan escritos y son legibles sin ejecutar
  el notebook. Copiar el artefacto a producción sigue siendo un punto de parada.

## 5. Requisitos no funcionales

- **RNF-1 — Honestidad.** Un ranking con un único split no basta para cambiar de
  familia: hace falta el walk-forward (CA-3.3).
- **RNF-2 — Sin fuga.** Escalado ajustado solo con el train de cada fold; la
  familia se elige sin mirar el test del fold que evalúa.
- **RNF-3 — Determinismo.** Las familias usan `random_state=42`; dos ejecuciones
  con la misma entrada dan el mismo resultado.
- **RNF-4 — Simplicidad.** Una función pura nueva, dos celdas nuevas y el
  reordenamiento mínimo del notebook. Sin dependencias nuevas en `src/`.
- **RNF-5 — Ámbito.** Solo `src/` y `specs/`. Backend y frontend intactos.
- **RNF-6 — Idioma.** Documentación, mensajes y comentarios en español.

## 6. Criterios de aceptación

1. `eolica_prev` tiene su estudio de Pearson y sus gráficas en el bloque
   `### FEATURE ENGINEERING`, después del solar y antes de entrenar.
2. El ranking de familias entrena con `COLUMNAS_MODELO`.
3. La familia candidata se somete al criterio de 3 de 4 folds y la decisión
   queda escrita.
4. El `.joblib` y la predicción guardada declaran familia, columnas y
   preprocesado.
5. `node --test` en verde y el notebook ejecutado de arriba abajo dos veces con
   la misma predicción.
6. Observación intacta y copias de producción sin tocar.

## 7. Casos límite

- **CE-1 — Variable con varianza cero.** Pearson no se calcula; se informa y la
  variable no se usa como candidata.
- **CE-2 — Empate de RMSE entre familias.** El criterio exige mejora estricta:
  un empate no cambia la familia.
- **CE-3 — Fold omitido.** El fold sin año completo no cuenta para la decisión.
- **CE-4 — Familia candidata con semilla distinta.** Todas usan `random_state=42`
  para que la comparación sea reproducible.
- **CE-5 — La candidata es LinearRegression.** No hay cambio de familia; el acta
  lo declara como "sin cambio".
- **CE-6 — Falta una columna del vector.** El notebook se detiene con el motivo,
  como en la spec 004; no se rellena con un valor por defecto.

## 8. Cierre

- Se cumplieron CA-1.1–CA-1.5: el EDA de `eolica_prev` aparece tras el estudio
  solar dentro de `### FEATURE ENGINEERING`, con sus gráficas guardadas.
- Train, test y ranking clásico usan `COLUMNAS_MODELO`: 19 predictores tras la
  aceptación del walk-forward 18→19.
- La comparación de familia rechazó LightGBM (mejora en 1/4 folds); la producción
  sigue siendo Linear Regression con 19 variables.
- El `.joblib`, las actas, la predicción guardada y `MEMORY.md` quedaron
  coherentes. La adopción en backend sigue fuera de alcance y bloqueada por P-1.
- Validación: `node --test` (16 Node) y `unittest` (460 Python) en verde; el
  notebook completo se ejecutó dos veces y mantuvo una predicción idéntica.
