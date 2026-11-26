# Spec 013 — Las nuevas variables en Proceso

Estado: implementada en el frontend (26/11/2026). Pendiente: añadir al notebook la celda de exportación (D-13-3).

## Contexto

La propuesta de diseño revisada el 26/11/2026 (lienzo «Restyling completo del frontend de AeroPredictor») añadió a Proceso un apartado sobre las variables que se incorporaron al modelo después de las 16 originales: horas de sol y temperatura del día anterior (`sol_lag1`, `tmed_lag1`, spec 002) y la previsión eólica de REE (`eolica_prev`, specs 005 y 006). En el notebook se estudian en «Evaluamos la relación de las variables solares…» y en «EDA de la variable nueva (spec 006): previsión de REE». La web real no las muestra. El usuario pidió llevarlo a la web conservando Chart.js.

## Decisiones

- **D-13-1 — Alcance.** Solo `frontend/src/pages/proceso.astro`, un componente nuevo de gráficas, una utilidad pura, sus pruebas y un JSON de datos. No cambian el backend, la API, el modelo, la BD ni `FEATURE_COLS`.
- **D-13-2 — Orden.** «¿Cuánta electricidad es renovable?» pasa a ser la primera sección de Proceso, como en el lienzo. El apartado «Las nuevas variables» va en el paso de las variables, antes de la importancia de cada variable.
- **D-13-3 — Origen de los datos (constitución, punto 1).** Los datos salen del notebook. Celda de exportación propuesta, al final de la sección EDA de la previsión de REE:

  ```python
  # Exporta las nuevas variables para la web (spec 013)
  cols = ["sol_lag1", "tmed_lag1", "eolica_prev", TARGET]
  datos = df_ml[["fecha"] + cols].dropna().sort_values("fecha")
  corr = datos[cols].corr(method="pearson")[TARGET]
  salida = {
      "fuente": "Notebook src/notebooks/main.ipynb (df_ml), spec 013. Pearson calculado sobre los mismos días.",
      "periodo": {"desde": str(datos["fecha"].iloc[0])[:10], "hasta": str(datos["fecha"].iloc[-1])[:10], "dias": int(len(datos))},
      "correlacion": {c: round(float(corr[c]), 3) for c in ["sol_lag1", "tmed_lag1", "eolica_prev"]},
      "fecha": datos["fecha"].astype(str).str[:10].tolist(),
      "sol_lag1": datos["sol_lag1"].round(2).tolist(),
      "tmed_lag1": datos["tmed_lag1"].round(2).tolist(),
      "eolica_prev_gwh": (datos["eolica_prev"] / 1000).round(1).tolist(),
      "eolica_gwh": (datos[TARGET] / 1000).round(1).tolist(),
  }
  with open("../../frontend/src/data/nuevas-variables.json", "w", encoding="utf-8") as f:
      json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
  ```

  El notebook está abierto en Jupyter con cambios locales sin subir: editarlo desde fuera chocaría con esa copia y guardarlo desde el navegador sobrescribiría la celda. Por eso esta vez el JSON se generó con este mismo código sobre el estado ya ejecutado del notebook (copia aislada de `src/` del 25/11, celdas hasta la 74). La celda la añade el usuario.
- **D-13-4 — Datos.** `frontend/src/data/nuevas-variables.json`: 1.770 días (08/01/2022–12/11/2026). Producción y previsión en GWh con un decimal. Las correlaciones coinciden con las que imprime el notebook: sol −0,389, temperatura −0,338, previsión de REE +0,974.
- **D-13-5 — Lógica pura (constitución, punto 4).** `frontend/src/utils/new-variables.mjs`: Pearson, recta de ajuste y resumen por tramos. Sin DOM.
- **D-13-6 — Gráficas.** Tres diagramas de dispersión de Chart.js, en `<canvas>` (1.770 puntos por gráfica sin cargar el DOM): sol del día anterior, temperatura del día anterior y previsión de REE frente a la producción real. Las dos primeras con su recta de ajuste; la de REE con la diagonal y = x. Tooltip con fecha y valores, colores de los tokens del tema y tabla desplegable por tramos (número de días y producción media).
- **D-13-7 — Criterios comunes de las gráficas.** Ancho fluido sin desplazamiento horizontal, lectura de valores al pasar o tocar, y tabla de datos. Lo mismo que en el lienzo.
- **D-13-8 — Etiquetas.** Se quitan de Proceso las etiquetas sobre los títulos («Paso N», «Proceso del proyecto»), como en el lienzo. Inicio, Resultados y Mejoras las conservan hasta otra spec.

## Criterios de aceptación

- **CA-1** El JSON tiene 1.770 días y todas las series tienen la misma longitud que `fecha`.
- **CA-2** Las correlaciones recalculadas con la utilidad sobre el JSON difieren de las guardadas en menos de 0,002.
- **CA-3** Proceso empieza por «¿Cuánta electricidad es renovable?» y muestra las tres gráficas nuevas con su tabla.
- **CA-4** Sin desbordamiento horizontal a 375 px y las gráficas siguen el tema claro y oscuro.
- **CA-5** `node --test` y `npm run build` pasan.

## Riesgos

- Mientras la celda no esté en el notebook, regenerar el JSON depende de repetir el procedimiento de D-13-3.
- La correlación no implica causa: los textos lo dicen.
