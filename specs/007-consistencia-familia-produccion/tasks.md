# Tareas 007 — Consistencia de la familia elegida en gráficas y trazabilidad

Deriva de `spec.md` y `plan.md`. Primero el test en rojo, luego el código
(constitución, principio 5). La puerta es `node --test`.

Copia previa en `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-007/`
(BD, wal/shm, `.joblib`, notebook y actas) antes de tocar nada.

## Bloque A — Contratos

- [x] **T-01 — Tests estáticos** (RF-1, RF-2, RF-4; CA-1.1/1.2, CA-2.2,
  CA-4.1/4.2)
  - `test_la_grafica_del_ultimo_ano_usa_el_modelo_de_produccion`.
  - `test_las_variables_de_produccion_no_presuponen_linear_regression`.
  - `test_el_comentario_de_la_prediccion_propia_no_fija_lr`.
  - Acepta: los tres fallan con el notebook actual.

## Bloque B — Notebook

- [x] **T-02 — Gráfica ligada a la familia** (RF-1; CA-1.1–CA-1.4)
  - Usar `predecir_produccion(test[COLUMNAS_MODELO])` y `FAMILIA_MODELO` en
    título y leyenda; eliminar `predicciones["Linear Regression"]`.
  - Acepta: la gráfica sigue mostrando los mismos valores si la familia es LR.

- [x] **T-03 — Nombres neutros** (RF-2; CA-2.1–CA-2.3)
  - `pipeline_prod`, `pred_prod_cargado`, `pred_prod_manana`.
  - Mantener `lr_eolica.joblib`.
  - Acepta: no quedan nombres antiguos en el código posterior a la familia.

- [x] **T-04 — Documentación** (RF-3; CA-3.1–CA-3.3)
  - Comentario de la predicción propia.
  - Nota en el markdown de PASO 7.
  - Sin datos nuevos.

## Bloque C — Verificación y cierre

- [x] **T-05 — Tests en verde**
  - `python -m unittest discover -s src/pipeline/tests`.
  - `node --test`.
  - Acepta: 0 fallos; el contrato de las 19 variables sigue verde.

- [x] **T-06 — Ejecución completa**
  - Notebook de arriba abajo con `jupyter_client`.
  - Predicción y métricas comparadas con la ejecución anterior; una sola fila
    en `prediccion_propia`; observación intacta; salidas sin claves.
  - Acepta: sin errores y sin cambios de comportamiento no justificados.

- [x] **T-07 — Cierre documental**
  - `MEMORY.md` con la spec 007 y el resultado.
  - Marcar T-01..T-07 en este archivo.
  - `git status` solo en `src/`, `specs/` y `MEMORY.md`.

## Resultado de la ejecución

Ejecutada el 2026-11-14.

- Notebook completo con `jupyter_client`, sin errores, 108 celdas y salidas
  regeneradas sin credenciales.
- Familia de producción: **Linear Regression**, 19 variables, `usa_scaler=True`.
  Walk-forward: LR gana 3 de 4 folds; LightGBM solo gana 2026.
- Test 2025-11-22 → 2026-11-10 (354 días): **RMSE 23.108,4 MWh · MAE 15.588,2 ·
  R² 0,9308**. El `.joblib` recargado reproduce las predicciones.
- Predicción para **2026-11-15: 287.484,9 MWh**, una sola fila en
  `prediccion_propia` con 19 variables. No se compara con los 227.771,5 MWh de
  la ejecución anterior porque el objetivo era 2026-11-14 y la observación ha
  avanzado; no se fuerza el valor antiguo (CE-5).
- Observación: `generacion` pasó de 10.663 a 10.669 filas; las 5 filas nuevas de
  2026-11-12 son tecnologías que faltaban y **ninguna fila existente cambió**.
  `aemet_diario` conserva intactas las 30.533 filas antiguas y añade 11 nuevas.
- **463 tests Python + 16 Node en verde.** Backend y frontend intactos; las tres
  copias de producción siguen con el modelo de 16 variables (P-1).
