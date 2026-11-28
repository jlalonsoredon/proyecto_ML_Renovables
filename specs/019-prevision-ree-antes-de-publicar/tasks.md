# Tareas — Spec 019

- [x] **T-19-1 — Spec.** `spec.md` con el diagnóstico, las decisiones, los criterios y los riesgos.
- [x] **T-19-2 — Función pura `isProvisional`.** En `frontend/src/utils/forecast.mjs`, con pruebas en `frontend/tests/forecast.test.mjs`.
  - Hecho cuando: CA-1 (frontend) en verde.
- [x] **T-19-3 — Espejo en el backend.** `es_provisional` en `backend/app/services/forecast_cache.py`, con pruebas en `backend/tests`.
  - Hecho cuando: CA-1 (backend) en verde.
- [x] **T-19-4 — Caché.** `forecast_cache.refresh` no reutiliza un snapshot provisional sin `force`.
  - Hecho cuando: CA-3 en verde.
- [x] **T-19-5 — Workflow.** Crons de 12:17 y 15:17 (Europe/Madrid) y la guarda que no omite snapshots provisionales.
  - Hecho cuando: CA-2 en verde.
- [x] **T-19-6 — Tarjeta.** Distintivo «Provisional» y texto de D-19-5 en `PrediccionCard.astro` (Inicio y Resultados), a partir de `cardView`.
  - Hecho cuando: CA-4 comprobado en el navegador en los dos temas.
- [x] **T-19-7 — Verificación.** `node --test`, `npm run build` y pruebas del backend; tras desplegar, comprobar CA-5 en el snapshot del día siguiente.
  - Resultado parcial: frontend 61/61 (3 nuevas en `tests/provisional.test.mjs`); backend 40/41 con la prueba nueva en verde; la que falla (hash del modelo de `src/data/modelos`, `1f1cdd4d…` frente a `e915381e…`) ya fallaba antes de esta spec. `npm run build` sin errores. La guarda, ejecutada en local sobre el snapshot del 28/11, decide «Se ejecuta… provisional: sí». Tarjeta revisada en Inicio y Resultados, en los dos temas.
  - CA-5 (28/11): la ejecución manual #56 con `force` (12:11) publicó la predicción del 29/11 con `eolica_prev = "prevision"`: 99.924 MWh frente a los 183.860 MWh provisionales de las 07:39. Producción sirve el snapshot `2026-11-28T110524Z` sin «Provisional».
- [x] **T-19-9 — Disparadores externos.** cron-job.org lanza el workflow a las 07:27 y a las 11:27 (D-19-8).
- [x] **T-19-8 — Cierre.** `MEMORY.md` y `DESIGN.md` (nuevo distintivo de la tarjeta).
