# Spec 007 — Consistencia de la familia elegida en gráficas y trazabilidad

Estado: cerrada (2026-11-14).
Depende de: spec 004 (predicción propia), spec 005 (`eolica_prev`) y
spec 006 (familia del modelo).

## 1. Problema

La spec 006 dejó `FAMILIA_MODELO` como la familia de producción, pero el tramo
posterior del notebook sigue acoplado a Linear Regression:

1. La gráfica `# Previsión Linear Regression — último año del test` usa
   `predicciones["Linear Regression"]` y títulos/etiquetas fijos. Si el
   walk-forward aceptara otra familia, la gráfica seguiría mostrando LR.
2. Los nombres `pipeline_lr`, `pred_lr_cargado` y `pred_lr_manana`, y un
   comentario de la predicción propia, presuponen LR aunque la lógica ya usa
   `FAMILIA_MODELO` y `usa_scaler`.

Además, el bloque PASO 7 descarga solo `velmedia` y `racha`; las otras 17
variables se resuelven en el mapa de orígenes y en la serie de REE. Esa
cobertura no está explicada y puede hacer pensar que falta ampliar la descarga.

## 2. Objetivo

Dejar todo el tramo posterior a `# ELECCIÓN DEL MEJOR MODELO` consistente con
`FAMILIA_MODELO`, sin cambiar el modelo, las 19 variables, los datos ni la
decisión del walk-forward.

## 3. Fuera de alcance

- Añadir estaciones, municipios o variables AEMET nuevas.
- Cambiar `COLUMNAS_MODELO`, `FEATURE_COLS`, el criterio 3/4 o la familia.
- Reentrenar por motivos distintos de la ejecución normal del notebook.
- Copiar el `.joblib` a `modelos/`, `backend/modelos/` o
  `src/model/production/` (sigue bloqueado por P-1).
- Cambiar el nombre del archivo `lr_eolica.joblib`.
- Arreglar la rama “ambos criterios rechazados”: la predicción usaría el
  candidato y las gráficas el modelo guardado. Decidir cuál manda requiere una
  spec aparte.

## 4. Requisitos funcionales

### RF-1 — La gráfica del último año sigue a la familia

- **CA-1.1** La gráfica usa `predecir_produccion(test[COLUMNAS_MODELO])`, no
  `predicciones["Linear Regression"]`.
- **CA-1.2** El título y la leyenda usan `FAMILIA_MODELO`.
- **CA-1.3** El error y las métricas impresas salen de las mismas predicciones
  del modelo de producción.
- **CA-1.4** Si la familia es Linear Regression, los valores de la gráfica y las
  métricas no cambian respecto de la ejecución anterior.

### RF-2 — Nombres de producción neutros

- **CA-2.1** Las variables de producción se llaman `pipeline_prod`,
  `pred_prod_cargado` y `pred_prod_manana`.
- **CA-2.2** No quedan `pipeline_lr`, `pred_lr_cargado`, `pred_lr_manana` ni
  `pred_lr` en el código posterior a la elección de familia.
- **CA-2.3** El archivo `lr_eolica.joblib` conserva su nombre: es el contrato que
  usan el backend, `render.yaml` y los informes.

### RF-3 — Documentación del alcance de PASO 7

- **CA-3.1** El comentario de la predicción propia dice “la familia elegida”,
  no “LinearRegression”.
- **CA-3.2** El markdown de PASO 7 explica que la descarga solo aporta
  `velmedia` y `racha`, y que las otras 17 variables vienen del mapa de orígenes
  y de la serie de REE.
- **CA-3.3** No se añaden datos, estaciones ni municipios.

### RF-4 — Contratos estáticos

- **CA-4.1** `test_integridad_notebook.py` comprueba que la gráfica usa el
  modelo de producción y `FAMILIA_MODELO`, y que no contiene referencias fijas
  a LR.
- **CA-4.2** El mismo archivo comprueba que no quedan los nombres antiguos en el
  código posterior a la elección de familia.
- **CA-4.3** El test existente
  `test_el_mapa_tiene_las_19_variables_del_modelo` sigue en verde.
- **CA-4.4** `node --test` pasa completo.

## 5. Requisitos no funcionales

- **RNF-1 — Cambio mínimo.** Solo se toca la presentación y los nombres; la
  lógica de entrenamiento, selección y predicción no cambia.
- **RNF-2 — Sin fuga ni reentrenamiento extra.** La gráfica usa el modelo ya
  entrenado; no se ajusta nada nuevo.
- **RNF-3 — Determinismo.** Dos ejecuciones con los mismos datos dan la misma
  predicción y las mismas métricas.
- **RNF-4 — Ámbito.** Solo `src/`, `specs/` y `MEMORY.md`. Backend y frontend
  intactos.
- **RNF-5 — Idioma.** Documentación, mensajes y comentarios en español.
- **RNF-6 — Datos sagrados.** La observación de REE y AEMET no se modifica;
  solo se lee.

## 6. Criterios de aceptación

1. La gráfica del último año usa `predecir_produccion` y `FAMILIA_MODELO`; no
   contiene `predicciones["Linear Regression"]`.
2. No quedan `pipeline_lr`, `pred_lr_cargado` ni `pred_lr_manana` en el código
   posterior a `# FAMILIA DEL MODELO`.
3. PASO 7 documenta las fuentes de las 19 variables y no amplía la descarga.
4. El notebook ejecuta de arriba abajo sin errores, mantiene la predicción y las
   métricas si los datos no cambian, deja una sola fila en `prediccion_propia` y
   conserva las huellas de `generacion` y `aemet_diario`.
5. `node --test` y la suite Python en verde.
6. Backend, frontend y las tres copias de producción no se tocan.

## 7. Casos límite

- **CE-1 — La familia elegida es Linear Regression.** La gráfica y las métricas
  deben coincidir con la ejecución anterior.
- **CE-2 — La familia elegida es LightGBM.** `predecir_produccion` aplica el
  preprocesado correcto (`usa_scaler=False`) y la gráfica cambia de etiqueta.
- **CE-3 — Ambos criterios rechazados.** Fuera de alcance; el comportamiento
  actual no se altera.
- **CE-4 — Falta una columna del vector.** `predecir_produccion` falla con el
  motivo; no se rellena con un valor por defecto.
- **CE-5 — Los datos cambian entre ejecuciones.** Se comparan métricas y
  predicción con tolerancia y se documenta la diferencia; no se fuerza el valor
  anterior.

## 8. Cierre

Cerrada el 2026-11-14. La gráfica del último año usa
`predecir_produccion(test[COLUMNAS_MODELO])` y `FAMILIA_MODELO`; los nombres
`pipeline_prod`, `pred_prod_cargado` y `pred_prod_manana` sustituyen a los
antiguos; PASO 7 documenta que la descarga AEMET solo aporta `velmedia` y
`racha`; y la predicción propia habla de “la familia elegida”.

Ejecución completa: familia **Linear Regression**, 19 variables; test
2025-11-22 → 2026-11-10 (354 días) con **RMSE 23.108,4 MWh · MAE 15.588,2 ·
R² 0,9308**; predicción **287.484,9 MWh** para 2026-11-15, una sola fila en
`prediccion_propia`. La observación existente no se modificó: las 5 filas
nuevas de `generacion` en 2026-11-12 completan tecnologías que faltaban y
`aemet_diario` conserva sus 30.533 filas antiguas. **463 tests Python + 16 Node
en verde.** Backend, frontend y las tres copias de producción no se tocaron;
siguen con el modelo de 16 variables (P-1).
