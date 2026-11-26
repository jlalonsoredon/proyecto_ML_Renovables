# Spec 017 — Toda la web como el diseño

Estado: implementada (26/11/2026).

## Contexto

Tras la spec 016, Proceso seguía el lienzo de diseño, pero el resto de la web no: la cabecera, el pie, Inicio y Resultados conservaban la versión de la spec 012. Además, el contenedor de la web era más estrecho que el del lienzo (1.200 px frente a 1.240 px de contenido), así que en Proceso las nubes de puntos se apilaban en vez de ir de dos en dos. El usuario pidió el 26/11/2026 que todas las páginas de producción repliquen el lienzo y un favicon con el nuevo logo.

## Decisiones

- **D-17-1 — Contenedor.** 1.240 px de contenido con márgenes de clamp(20 px, 5vw, 72 px), como el lienzo. Tarjetas a 20 px de radio y botones de 48 px de alto.
- **D-17-2 — Logo.** Rotor de tres palas en el acento con el centro en tinta, y «AERO» (700) + «Predictor» (400, gris), en Space Grotesk (`Logo.astro`).
- **D-17-3 — Cabecera.** Logo a la izquierda, enlaces y selector de tema de dos botones (Oscuro y Claro, el activo en el acento); en móvil los enlaces pasan a una segunda fila y el selector solo muestra los iconos.
- **D-17-4 — Pie.** Logo, descripción, tres columnas (navegación, fuentes de datos y contacto) y una franja inferior. La mención al bootcamp de KeepCoding pasa a la franja inferior.
- **D-17-5 — Favicon.** El rotor sobre fondo oscuro redondeado: `favicon.svg`, PNG de 16 y 32 px y `apple-touch-icon.png` de 180 px. La imagen para compartir incorpora el logo.
- **D-17-6 — Inicio.** Cabecera con la rejilla y las líneas de viento decorativas, tarjeta «instrumento» (viento, ráfagas, modelo y minigráfica de los últimos 14 días), las tres razones, la gráfica de 30 días en su tarjeta, los cuatro pasos y el cierre con líneas de viento.
- **D-17-7 — Resultados.** Tarjeta de predicción en dos columnas (cifra con líneas de viento a la izquierda, ficha a la derecha), gráfica de 30 días con los colores del lienzo (real en tinta, modelo en verde discontinuo, mañana como rombo verde, viento en azul y racha en ámbar) y comparación de modelos con controles comunes a las ocho gráficas (series y periodo), escala compartida, métricas en recuadros, lectura con pasos y tabla.
- **D-17-8 — Mejoras.** Líneas de viento en el bloque de contacto; los enlaces a las specs apuntan a `/proceso#sdd` (la antigua ancla `#evolucion` ya no existe).
- **D-17-9 — Proceso.** Las nubes del sol y la temperatura van de dos en dos también con la columna de la web.
- **D-17-10 — Sin cambios de datos.** La lógica de la gráfica de 30 días (ventana de días completos, estados de la previsión, días rellenados con la previsión de AEMET) no cambia; solo su aspecto y sus controles. Se mantiene Chart.js.

## Criterios de aceptación

- **CA-1** Inicio, Resultados, Proceso, Mejoras, cabecera y pie siguen la composición del lienzo.
- **CA-2** El favicon y el logo son el rotor de tres palas.
- **CA-3** Sin desbordamiento horizontal a 375 px; los dos temas funcionan.
- **CA-4** `node --test` y `npm run build` pasan.
