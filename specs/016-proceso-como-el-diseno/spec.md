# Spec 016 — Proceso igual que el diseño

Estado: implementada (26/11/2026).

## Contexto

Tras las specs 013 y 015, la página Proceso de la web seguía sin coincidir con el lienzo de diseño («Restyling completo del frontend de AeroPredictor»). El lienzo agrupa el contenido en cuatro fases y un glosario, cada una con su título a la izquierda y preguntas a la derecha, y usa gráficas con controles propios. La web apilaba pasos sueltos y conservaba gráficas de la plantilla. El usuario pidió igualarlas el 26/11/2026.

## Decisiones

- **D-16-1 — Estructura.** Cabecera con índice de capítulos (EDA, modelos, predicción diaria, SDD y glosario) y bloques de dos columnas: título y entradilla a la izquierda, preguntas a la derecha. Mismos textos que el lienzo.
- **D-16-2 — Contenido por bloque.**
  - **Explorar los datos (EDA):** reparto renovable (spec 015), fuentes y mapa de parques con selector, generación renovable semanal, relación viento–producción (series en escala común, histograma, nube de puntos y correlaciones), limpieza de datos y métodos de relleno, decisiones del EDA, las 19 variables y las nuevas variables (spec 013).
  - **Construir los modelos:** las ocho familias, cómo se mide un modelo (R² y RMSE del modelo vigente) e importancia de variables según LightGBM.
  - **Predecir cada día:** los cuatro pasos y qué pasa si falta un dato.
  - **SDD:** ciclo de trabajo, reglas de la constitución y las specs en acordeón.
  - **Glosario:** en acordeón.
- **D-16-3 — Se mantiene Chart.js.** Las gráficas del lienzo se reproducen con Chart.js: botones de serie, selector de periodo (todo, últimos 2 años, último año), tooltip con los valores y tabla de datos. El histograma y las nubes de puntos siguen los mismos criterios.
- **D-16-4 — Mapa real.** El mapa sigue siendo de Leaflet con OpenStreetMap (mapa de referencia real, petición del usuario); se añade el selector de parques y la ficha del lienzo.
- **D-16-5 — Datos del notebook (constitución, punto 1).**
  - La celda 75 de `main.ipynb` añade al JSON de las nuevas variables el viento medio y la racha, con su correlación con la producción.
  - Una celda nueva tras el ranking de familias (88) exporta `frontend/src/data/importancia-lgbm.json`: número de divisiones en que LightGBM usa cada variable.
- **D-16-6 — Correlaciones coherentes.** Las fichas de correlación usan las del notebook sobre los 1.770 días de la nube (viento +0,658, racha +0,699), no las de la exportación antigua (0,42 y 0,50), que no correspondían a los mismos días. El lienzo se corrige igual.
- **D-16-7 — Lo que sale de Proceso.** La comparación de los ocho modelos sigue en Resultados (Proceso enlaza a ella). «Antes y ahora» y el estado de la previsión en directo dejan Proceso, como en el lienzo; sus componentes se conservan.

## Criterios de aceptación

- **CA-1** Proceso tiene los cinco bloques del lienzo, en su orden y con sus textos.
- **CA-2** Las gráficas tienen botones de serie cuando hay más de una, lectura de valores y tabla de datos.
- **CA-3** Los JSON nuevos salen de las celdas del notebook y las pruebas comprueban sus correlaciones.
- **CA-4** Sin desbordamiento horizontal a 375 px; los dos temas funcionan.
- **CA-5** `node --test` y `npm run build` pasan.
