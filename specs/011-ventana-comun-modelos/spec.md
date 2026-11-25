# Spec 011 — Ventana común para las comparativas de 16 y 19 variables

Estado: implementada (25/11/2026). Pendiente solo decidir si se borra `model-predictions-19.json`.

## Contexto

La spec 009 dejó cada variante en su propia ventana (D-9-8): las 16 variables, del 29/06/2025 al 10/05/2026 (46 semanas, pipeline anterior a la spec 002), y las 19, del 23/11/2025 al 11/11/2026 (354 días, split 80/20). En las gráficas de `/proceso` eso deja la línea de 16 variables sin llegar al final y la de 19 sin empezar al principio, porque el eje semanal es la unión de las dos ventanas.

Petición del 25/11/2026: las dos líneas deben cubrir del 29/06/2025 al 08/11/2026. Esta spec sustituye el punto «Recalcular la línea base con otro protocolo» que la 009 dejó fuera de alcance, solo para estas gráficas.

## Decisiones

- **D-11-1 — Ventana.** 72 semanas. La gráfica usa medias semanales de lunes a domingo, etiquetadas por su domingo (`resample("W")`): la primera etiqueta, 29/06/2025, es la media del 23 al 29 de junio. En días, la ventana va del 23/06/2025 al 08/11/2026 (504 días, sin huecos ni nulos).
- **D-11-2 — Protocolo.** Origen fijo. Cada familia se entrena solo con los días anteriores al 23/06/2025 (1.262 días, desde el 08/01/2022) y predice los 504 días sin reentrenar. Los retardos del target son los observados (predicción a un día vista). SARIMAX pronostica los 504 días seguidos con velmedia y racha como exógenas.
- **D-11-3 — Familias.** Las ocho del ranking del PASO 6, con sus mismos hiperparámetros y semillas.
- **D-11-4 — 16 variables.** Son `FEATURE_COLS` del pipeline actual (día natural peninsular, spec 002). No son la serie antigua en hora UTC, así que sus cifras no sustituyen la línea base histórica de la 009 (RMSE 60.433 MWh), que se conserva con su protocolo (D-9-10, D-9-11).
- **D-11-5 — SARIMAX.** No usa las variables 16 o 19, así que sus dos líneas coinciden y la gráfica lo declara.
- **D-11-6 — Alcance.** No se toca `COLUMNAS_MODELO`, el modelo de producción, la base de datos ni el backend. La cifra del modelo vigente (RMSE 23.108,4 sobre 354 días) sigue con su protocolo y no se compara con las de esta ventana.
- **D-11-7 — Entrega.** La última celda de `src/notebooks/main.ipynb` calcula y escribe `frontend/src/data/model-predictions.json` (mismo patrón que la exportación de la 009). `model-predictions-19.json` queda sin uso.

## Evidencia preliminar

Copia aislada de `src/` (sin red, sin escribir en la base ni en los modelos). El conjunto de datos reproduce el del notebook: la serie real semanal coincide con la publicada (diferencia máxima 0) y la regresión lineal de 19 variables con el split 80/20 da RMSE 23.246,7 y R² 0,9301, frente a 23.215,1 y 0,9301 de la exportación del 15/11. SARIMAX se ejecutó después desde PowerShell y en el kernel, con el mismo resultado: RMSE 61.898 y R² 0,4559 en ambas líneas (antes, 63.565 y 0,4756 con 19 variables en otra ventana). Es el único modelo que no observa el target durante el test: pronostica 504 días seguidos.

| Familia | RMSE 16 | R² 16 | RMSE 19 | R² 19 |
|---|---|---|---|---|
| LightGBM | 36.833 | 0,8073 | 18.376 | 0,9520 |
| XGBoost | 36.814 | 0,8075 | 18.811 | 0,9497 |
| Random Forest | 38.074 | 0,7941 | 19.050 | 0,9485 |
| Red neuronal (MLP) | 39.097 | 0,7829 | 19.643 | 0,9452 |
| Ridge | 39.361 | 0,7800 | 20.356 | 0,9412 |
| Linear Regression | 39.442 | 0,7791 | 20.519 | 0,9402 |
| Lasso | 39.442 | 0,7791 | 20.520 | 0,9402 |

## Criterios de aceptación

- **CA-1** Las 8 familias tienen 72 valores semanales sin `null` en 16 y en 19 variables.
- **CA-2** `real`, `semanas` y su alineación coinciden con la serie publicada.
- **CA-3** `protocolo16` y `protocolo19` solo difieren en `variables`.
- **CA-4** La gráfica y sus textos describen la ventana común; no dicen que las métricas se midieron en periodos distintos.
- **CA-5** `node --test frontend/tests` y `npm run build` pasan.

## Riesgos

- Desde la herramienta de shell Bash de la sesión, Windows bloqueaba la extensión compilada de `statsmodels` («Una directiva de Control de aplicaciones bloqueó este archivo»); desde PowerShell y desde el kernel carga bien.
- El notebook está abierto en Jupyter: guardarlo desde el navegador sobrescribe la celda añadida.
- Las cifras de 16 variables pasan de ~60.000 a ~39.000 MWh de RMSE. Es la diferencia entre el pipeline anterior y el actual, no una mejora del modelo; la web debe decirlo.
