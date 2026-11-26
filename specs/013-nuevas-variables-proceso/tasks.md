# Tareas — Spec 013

- [x] **T-13-1 — Spec.** `spec.md` con decisiones, criterios y riesgos.
- [x] **T-13-2 — Datos.** `frontend/src/data/nuevas-variables.json` generado con el código de D-13-3 sobre el estado ejecutado del notebook (celdas hasta la 74, copia aislada del 25/11).
  - Resultado: 1.770 días (08/01/2022–12/11/2026); r = −0,389 (sol), −0,338 (temperatura), +0,974 (previsión de REE), iguales a los del notebook.
- [x] **T-13-3 — Celda en el notebook.** Añadida a `src/notebooks/main.ipynb` como celda 75, tras «EDA de la variable nueva (spec 006)».
  - Resultado: ejecutada sobre la copia aislada (celdas hasta la 75) genera un `nuevas-variables.json` idéntico byte a byte al publicado.
- [x] **T-13-4 — Lógica pura y pruebas.** `frontend/src/utils/new-variables.mjs` (Pearson, recta de ajuste, resumen por tramos) y `frontend/tests/new-variables.test.mjs` (CA-1, CA-2).
- [x] **T-13-5 — Gráficas.** `frontend/src/components/charts/NewVariablesCharts.astro`: tres dispersiones de Chart.js con recta de ajuste o diagonal, tooltip con fecha y valores, colores de los tokens y tabla por tramos.
- [x] **T-13-6 — Página.** `proceso.astro`: «¿Cuánta electricidad es renovable?» como primera sección, apartado «Las nuevas variables» en el paso de las variables y sin etiquetas sobre los títulos.
- [x] **T-13-7 — Verificación.**
  - Resultado: `node --test` 52/52; `npm run build` con `astro check` sin errores. En el navegador: las tres gráficas se dibujan (508×363 y 702×501 a 1.280 px; 281×201 a 375 px), el tooltip muestra fecha y valores, el tema claro recolorea puntos y recta, y la página no desborda a 375 px.
