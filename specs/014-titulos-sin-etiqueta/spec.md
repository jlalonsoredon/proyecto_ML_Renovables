# Spec 014 — Títulos sin etiqueta en Inicio, Resultados y Mejoras

Estado: implementada (26/11/2026).

## Contexto

La spec 013 quitó de Proceso las etiquetas en mayúsculas que había encima de los títulos, siguiendo las reglas de diseño de impeccable recogidas en `DESIGN.md` («La regla del título sin etiqueta»). Inicio, Resultados y Mejoras las conservaban y quedaron pendientes. El lienzo de diseño ya las aplica en todas las páginas desde el 26/11/2026. El usuario pidió completar las tareas pendientes.

## Decisiones

- **D-14-1 — Alcance.** `frontend/src/pages/index.astro`, `resultados.astro` y `mejoras.astro`, y la nota de `DESIGN.md`. Sin cambios de datos, lógica, backend ni API.
- **D-14-2 — Etiquetas.** Se quitan las etiquetas que van encima de un título (`.a-eyebrow` antes de un `h1` o `h2`).
- **D-14-3 — Excepciones.** «Predicción para mañana» de la tarjeta de predicción se mantiene: es el título de la tarjeta y la referencia de su `aria-labelledby`. La numeración 01–04 de los pasos de Inicio también se mantiene, porque indica el orden del proceso.
- **D-14-4 — «Tres razones para fiarse».** Deja de ser una cifra grande con tarjetas iguales (el patrón de cifra-héroe que `DESIGN.md` desaconseja) y pasa a una lista de tres razones con la cifra dentro del texto, igual que en el lienzo. Los datos no cambian: R² 0,9308 en un test de 354 días.

## Criterios de aceptación

- **CA-1** Ninguna página tiene `.a-eyebrow` salvo la tarjeta de predicción.
- **CA-2** Las cifras de Inicio no cambian.
- **CA-3** Sin desbordamiento horizontal a 375 px.
- **CA-4** `node --test` y `npm run build` pasan.
