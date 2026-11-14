# Plan 007 — Consistencia de la familia elegida en gráficas y trazabilidad

Deriva de `spec.md`. Sin dependencias nuevas y sin cambios en la lógica de
entrenamiento, selección o predicción.

## 1. Decisiones de diseño

- **D-7-1 — La gráfica usa el modelo de producción, no el ranking.**
  `predecir_produccion(test[COLUMNAS_MODELO])` aplica exactamente el
  preprocesado y el modelo que se serializan en PASO 8. No usar
  `predicciones[FAMILIA_MODELO]`, porque ese diccionario contiene los modelos
  del ranking.
- **D-7-2 — Nombres neutros, archivo histórico.**
  `pipeline_prod`, `pred_prod_cargado` y `pred_prod_manana` describen lo que
  son. `lr_eolica.joblib` se mantiene porque es el contrato del backend, de
  `render.yaml` y de los informes.
- **D-7-3 — PASO 7 solo se documenta.**
  La descarga de viento aporta 2 de las 19 variables; las demás ya están
  resueltas en `mapa_origenes`, la serie de REE y el bloque solar. Añadir
  estaciones cambiaría la media histórica y obligaría a reentrenar.
- **D-7-4 — Spec nueva, no reapertura de 006.**
  La 006 está cerrada; esta es una continuación de consistencia.
- **D-7-5 — La rama “ambos rechazados” queda fuera.**
  Hoy no se ejecuta (la previsión de REE se aceptó 4/4). Si algún día ocurre,
  la predicción usa el candidato y las gráficas el modelo guardado; decidir cuál
  debe mandar requiere una spec aparte.

## 2. Cambios por archivo

### `src/notebooks/main.ipynb`

| Encabezado | Cambio |
|---|---|
| `# Previsión Linear Regression — último año del test` | Renombrar a `# Previsión del modelo de producción — último año del test`; usar `predecir_produccion(test[COLUMNAS_MODELO])` y `FAMILIA_MODELO` |
| `### PASO 8: GUARDAR Y CARGAR MODELO DE PRODUCCIÓN` | `pipeline_lr` → `pipeline_prod`; `pred_lr_cargado` → `pred_prod_cargado` |
| `# ── Último mes histórico + predicción mañana con AEMET` | `pred_lr_cargado` → `pred_prod_cargado`; `pred_lr_manana` → `pred_prod_manana` |
| Diagnóstico de desfase | `pred_lr_cargado` → `pred_prod_cargado` |
| `# PREDICCIÓN PROPIA (spec 004): GUARDADO CON ORIGEN DECLARADO` | Comentario “la familia elegida”; `pred_lr_manana` → `pred_prod_manana` |
| `### PASO 7: PRONÓSTICO PARA MAÑANA CON DATOS AEMET` | Nota: solo descarga `velmedia` y `racha`; las otras 17 variables vienen del mapa y de REE |

### `src/pipeline/tests/test_integridad_notebook.py`

Tres tests nuevos:

1. `test_la_grafica_del_ultimo_ano_usa_el_modelo_de_produccion`.
2. `test_las_variables_de_produccion_no_presuponen_linear_regression`.
3. `test_el_comentario_de_la_prediccion_propia_no_fija_lr`.

## 3. Detalle de la gráfica

Antes:

```python
pred_lr = predicciones["Linear Regression"][mask]
error   = pred_lr - real
```

Después:

```python
pred_prod = predecir_produccion(test[COLUMNAS_MODELO])
error     = pred_prod[mask] - real
```

- Los dos paneles usan `pred_prod[mask]`.
- La leyenda usa `f"{FAMILIA_MODELO}"`.
- El título usa `f"{FAMILIA_MODELO} — Previsión vs Real (último año del test)"`.
- Se añade `print(f"Modelo: {FAMILIA_MODELO}")`.
- No se cambia el cálculo de RMSE, MAE ni error medio.

## 4. Pruebas

- Las tres pruebas nuevas se escriben antes de editar el notebook y deben fallar.
- La cobertura de las 19 variables de PASO 7 ya la comprueba
  `test_prevision.py::TestMapaOrigenes::test_el_mapa_tiene_las_19_variables_del_modelo`.
- No se añaden pruebas de gráficos: la comprobación estática del código y la
  ejecución completa del notebook son la puerta.

## 5. Verificación

1. Copia previa en
   `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-007/`: notebook, BD
   (`ree_generacion.db`, `-wal`, `-shm`), `.joblib` y actas JSON.
2. Tests nuevos en rojo.
3. Edición del notebook.
4. Tests en verde.
5. Ejecución completa con `jupyter_client`.
6. Comparación con la ejecución anterior: predicción, RMSE/MAE/R², 19 features,
   una fila en `prediccion_propia`, huellas de observación intactas.
7. `node --test` completo.
8. `git status` solo en `src/`, `specs/` y `MEMORY.md`; restaurar `.pyc`
   generados por las pruebas.

## 6. Riesgos y rollback

- **Máscara desalineada**: `pred_prod` y `mask` deben tener la misma longitud.
- **Referencias ocultas a nombres viejos**: el test 2 y un `grep` las detectan.
- **El notebook reescribe el `.joblib`**: es el comportamiento normal; la copia
  previa permite volver atrás.
- **Rollback**: restaurar notebook, BD, `.joblib` y actas desde `backup-007/`.

## 7. Fuera de alcance

- Añadir estaciones, municipios o variables AEMET.
- Cambiar las 19 variables, el criterio 3/4 o la familia.
- Copiar el modelo a producción (P-1).
- Arreglar la rama “ambos criterios rechazados”.
- Cambiar la gráfica de importancia de variables del ranking.
