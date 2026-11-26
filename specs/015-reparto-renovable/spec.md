# Spec 015 — Reparto renovable como en el diseño

Estado: implementada (26/11/2026).

## Contexto

La spec 013 llevó a la web el orden y los textos de Proceso, pero la sección «¿Cuánta electricidad es renovable?» siguió usando el componente de la plantilla: tartas de Chart.js con colores fijos (rojo y verde), leyenda por defecto, bordes blancos y la tabla siempre visible. El lienzo de diseño la muestra con dos anillos, la cifra principal en el centro, colores del tema, leyenda en filas con su valor, tabla desplegable y una nota. El usuario comparó ambas el 26/11/2026 y pidió que coincidan.

## Decisiones

- **D-15-1 — Alcance.** Solo `frontend/src/components/charts/EnergyPieChart.astro`. Los datos (porcentajes del notebook, `reference-series.json`) no cambian.
- **D-15-2 — Anillos.** Dos gráficas `doughnut` de Chart.js (se conserva Chart.js): renovable frente a no renovable, con «58,33 % renovable» en el centro, y el reparto de la generación renovable, con «40,16 % es eólica» en el centro.
- **D-15-3 — Colores.** Desde los tokens del tema y recalculados al cambiarlo: renovable y eólica en el acento; solar fotovoltaica en ámbar; hidráulica en azul; solar térmica en coral; otras renovables en violeta; residuos renovables y no renovable en el gris suave.
- **D-15-4 — Leyenda y datos.** Leyenda HTML en filas con su porcentaje (se lee sin pasar el cursor), tabla desplegable «Ver los datos en tabla» con el porcentaje sobre el total y dentro de las renovables, y una nota con la conclusión, la fuente y el periodo.

## Criterios de aceptación

- **CA-1** La sección se ve como en el lienzo en tema oscuro y claro.
- **CA-2** Sin colores fijos de la plantilla en el componente.
- **CA-3** Sin desbordamiento horizontal a 375 px.
- **CA-4** `node --test` y `npm run build` pasan.
