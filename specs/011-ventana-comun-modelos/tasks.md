# Tareas — Spec 011

- [x] **T-11-1 — Spec.** `spec.md` con decisiones, evidencia preliminar y riesgos.
- [x] **T-11-2 — Celda del notebook.** Última celda de `main.ipynb`: entrena las 8 familias con 16 y 19 variables con origen fijo y exporta `model-predictions.json`.
  - Hecho cuando: las 7 familias sin SARIMAX se ejecutan sobre una copia aislada y la serie real coincide con la publicada.
  - Resultado: verificado en copia aislada (504 días, 72 semanas, serie real idéntica). SARIMAX sin ejecutar por la directiva de Control de aplicaciones.
- [x] **T-11-3 — Ejecutar la celda en el kernel.** Genera `frontend/src/data/model-predictions.json` con las 8 familias.
  - Hecho cuando: CA-1, CA-2 y CA-3 se cumplen sobre el archivo generado.
  - Resultado: la ejecución del kernel (25/11, 19:55) y la copia aislada dan exactamente las mismas predicciones y métricas en las 8 familias, SARIMAX incluido. CA-1, CA-2 y CA-3 verificados sobre el archivo.
- [x] **T-11-4 — Gráfica y textos.** `ModelComparisonChart.astro` describe la ventana común (504 días, 72 semanas) y avisa de que SARIMAX coincide en ambas líneas; `evolution.test.mjs` exige la ventana común.
  - Resultado: el recuadro de cada variante muestra las cinco métricas; el texto declara la ventana, el entrenamiento y lo que no es comparable.
- [x] **T-11-5 — Verificación.** `node --test frontend/tests`, `npm run build` y revisión visual de las ocho gráficas.
  - Resultado: 47/47 pruebas, `astro check` y build sin errores; en `/resultados` las dos líneas cubren de 29/6/25 a 8/11/26 en las gráficas revisadas (Ridge, Linear Regression, Lasso).
- [ ] **T-11-6 — Cierre.** `MEMORY.md`; decidir si se borra `model-predictions-19.json`.
