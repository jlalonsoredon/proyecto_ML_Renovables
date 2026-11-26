# Spec 018 — Mapa de parques como el diseño

Estado: implementada (27/11/2026).

## Contexto

La spec 016 mantuvo en Proceso el mapa de Leaflet con OpenStreetMap (D-16-4), con el selector y la ficha del lienzo. El 27/11/2026 el usuario pidió replicar el mapa tal como está en el lienzo de diseño.

## Decisiones

- **D-18-1 — Mapa dibujado.** Se sustituye Leaflet por el mapa SVG del lienzo: contorno simplificado de la península, frontera con Portugal discontinua, retícula de latitud y longitud cada 2°, seis ciudades de referencia, rótulos de países y mares, y los siete parques numerados. Misma proyección que el lienzo (longitud lineal, latitud escalada por cos 40°).
- **D-18-2 — Selección.** La lista de parques resalta el elegido con un anillo mayor y más opaco y un borde claro en el punto; la ficha muestra la provincia, la estación de observación y las coordenadas.
- **D-18-3 — Sin dependencias externas.** La página deja de cargar Leaflet y las teselas de OpenStreetMap. `WindMap.astro` queda sin uso.
- **D-18-4 — Colores del tema.** El mapa usa los tokens y sigue el tema claro y oscuro.

## Criterios de aceptación

- **CA-1** El mapa y la ficha coinciden con el lienzo.
- **CA-2** Sin desbordamiento horizontal a 375 px; los dos temas funcionan.
- **CA-3** `node --test` y `npm run build` pasan.
