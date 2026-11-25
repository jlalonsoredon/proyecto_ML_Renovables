# Spec 012 — Migración del rediseño al frontend real (Astro)

Estado: propuesta (25/11/2026). Sin implementar.

## Contexto

El 25/11/2026 se diseñó un restyling completo del frontend como artefacto de diseño («Restyling completo del frontend de AeroPredictor»): Inicio, Resultados, Proceso, Mejoras, página de estados de la tarjeta, imagen para compartir, navegación y pie. El diseño solo existe en el artefacto. En `/mejoras` la tarjeta «Restyling completo del frontend» ya consta como completada (commit `f537895`), así que esta spec es la que convierte esa marca en realidad: **hasta que se implemente, el texto de esa tarjeta debe revisarse** (ver D-12-9).

## Decisiones

- **D-12-1 — Alcance.** Cuatro páginas (`index`, `resultados`, `proceso`, `mejoras`), navegación, pie y tema. No cambia backend, contrato de la API, modelo, BD ni `FEATURE_COLS`.
- **D-12-2 — Chart.js se conserva.** Decisión del usuario: se mantiene por su interacción (filtrar series, tooltips, zoom/periodos). Las gráficas del diseño en SVG propio sirven de referencia visual, no de implementación.
- **D-12-3 — Tema claro/oscuro.** Selector en la cabecera, oscuro por defecto, persistido en `localStorage` (`aero-tema`) y aplicado antes del primer pintado para evitar parpadeo. Se implementa con variables CSS (`--bg`, `--surface`, `--surface2`, `--line`, `--ink`, `--muted`, `--accent`, `--accentInk`, `--warm`, `--sky`, `--coral`, `--violet`, `--grid`). Las gráficas Chart.js leen esas variables y se redibujan al cambiar de tema. No se usa la preferencia del sistema.
- **D-12-4 — Contraste.** Todos los pares texto/fondo de ambos temas ≥ 4,5:1 (WCAG AA).
- **D-12-5 — Estados de la tarjeta.** La tarjeta de predicción muestra los cuatro estados reales de `forecast.mjs` (vigente, pendiente, caducado, no disponible) con sus mensajes actuales. En «no disponible» no se muestra ninguna cifra ni se rellena con otro dato.
- **D-12-6 — Accesibilidad de gráficas.** Cada gráfica ofrece tabla de datos desplegable (`<details>`), controles táctiles y de teclado (anterior/siguiente, `aria-pressed` en los filtros) y respeta `prefers-reduced-motion`.
- **D-12-7 — Proceso didáctico.** Planteado como EDA, para público no técnico: gráficas filtrables, importancia de variables con escala proporcionada (referencia: gráfica LightGBM de 19 variables), mapa de referencia real para los parques eólicos, sección de evolución que explica que el proyecto se hizo con SDD y lista de specs en acordeón.
- **D-12-8 — Mejoras.** Hoja de ruta con las specs relacionadas por mejora; solo lectura. Datos desde `mejoras.astro` y `SpecTimeline`.
- **D-12-9 — Honestidad de la tarjeta de Mejoras.** Mientras esta spec no esté implementada, la tarjeta «Restyling completo del frontend» debe describirse como diseño aprobado o pasar a pendiente; al cerrar la spec se marca completada con enlace a la 012.
- **D-12-10 — Pie y contacto.** Se conservan los enlaces a la web del autor, GitHub y LinkedIn.
- **D-12-11 — Responsive.** Móvil (390 px), tableta (~820 px) y escritorio (1440 px). Gráficas con relación 4:3 en ≤ 640 px y desplazamiento horizontal solo donde el texto sea estático.
- **D-12-12 — Imagen para compartir.** Imagen Open Graph de 1200×630 enlazada en el `<head>` común.
- **D-12-13 — Sin dependencias nuevas.** Leaflet ya está en el proyecto y sirve para el mapa; si hace falta un proveedor de teselas, se pregunta antes (uso, atribución, límites).

## Criterios de aceptación

- **CA-1** Las cuatro páginas reproducen el diseño en los tres anchos, sin desbordes horizontales.
- **CA-2** El tema se cambia desde la cabecera, persiste entre páginas y recargas, y las gráficas lo siguen.
- **CA-3** Las gráficas de Resultados y Proceso siguen siendo Chart.js y mantienen filtros, tooltips y selección de periodo.
- **CA-4** Los cuatro estados de la tarjeta se ven correctamente y «no disponible» no muestra cifra.
- **CA-5** Contraste AA verificado en ambos temas.
- **CA-6** Cada gráfica tiene tabla de datos y es operable con teclado.
- **CA-7** `node --test` y `npm run build` (incluye `astro check`) pasan.
- **CA-8** Se mantienen sin cambios el contrato de la API y las cifras mostradas.

## Riesgos

- Reescribir páginas con tests de texto (`frontend/tests/*.test.mjs`) puede romper aserciones que dependen de cadenas actuales.
- Chart.js no hereda variables CSS: hay que leerlas con `getComputedStyle` y redibujar al cambiar de tema.
- Mapa con teselas externas: dependencia de un servicio de terceros y de su política de uso.
- La tarjeta de Mejoras ya afirma que el rediseño está hecho (ver D-12-9).
