# Tareas 009 — Actualizar el frontend: recorrido de las specs y métricas reales

Deriva de `spec.md` y `plan.md`. Todas las tareas están cerradas y verificadas
el 2026-11-16. La puerta fue `node --test` en `frontend/`, `astro check` y
`npm run build`.

> Cambio posterior al plan: a petición del usuario se recuperaron las gráficas
> por modelo con tres líneas (real, 16 y 19 variables). Sustituyen a la tabla y
> a la gráfica de barras del paso 3; la tabla de nueve filas queda en el paso 6.
> Ver T-9-11 y la sección 10.2 de `spec.md`.

## Bloque A — Pruebas y lógica

- [x] **T-9-01 — Pruebas primero** (RF-7)
  - `frontend/tests/evolution.test.mjs` con día completo, ventana, comparabilidad,
    formato, estado de predicción e integridad de los JSON.
  - Hecho cuando: las pruebas fallan antes de la implementación y pasan después.

- [x] **T-9-02 — Lógica pura** (RF-2, RF-3, RF-5, RF-7)
  - `frontend/src/utils/evolution.mjs`, sin DOM ni reloj, con `today` inyectado.
  - Hecho cuando: `node --test tests/` en verde y ninguna función lee red o reloj.

## Bloque B — Datos congelados

- [x] **T-9-03 — Métricas de modelos** (RF-2, RF-5)
  - `model-metrics.json`: línea base, referencia y nueve filas con protocolo,
    estado, decisión y motivo.
  - Hecho cuando: la tabla del paso 6 y la comparación leen el mismo archivo.

- [x] **T-9-04 — Series de referencia** (RF-5, RF-6)
  - `reference-series.json` extraído de la BD en solo lectura: 19 importancias y
    253 semanas renovables hasta 2026-11-08.
  - Hecho cuando: la suma de importancias es 1 ± 0,001 y la extracción queda
    anotada con fecha y SHA-256 en `metrics-iniciales.md`.

- [x] **T-9-05 — Series por modelo** (RF-5)
  - `model-predictions.json` y `model-predictions-19.json`: real semanal,
    predicción de 16 variables y predicción de 19 variables.
  - Hecho cuando: las ocho familias tienen las dos series y el «real» coincide
    con la BD.

## Bloque C — Contenido y componentes

- [x] **T-9-06 — Recorrido de las nueve specs** (RF-1)
  - `spec-timeline.json` con resumen llano, detalle técnico y glosario.
  - Hecho cuando: los nueve hitos están ordenados, completos y con una de las
    cuatro categorías permitidas.

- [x] **T-9-07 — Componentes nuevos** (RF-1, RF-2, RF-3)
  - `SpecTimeline.astro`, `MetricsComparison.astro` y `LivePredictionStatus.astro`.
  - Hecho cuando: los tres se montan sin errores y sin JavaScript dejan el
    contenido visible.

- [x] **T-9-08 — Paso 6 y anclaje** (RF-1, RF-2, RF-3)
  - Sección `#evolucion` al final de `/proceso`, después del cierre, con enlace
    desde la cabecera y desde el paso 3.
  - Hecho cuando: el anclaje funciona con la cabecera fija y en móvil.

- [x] **T-9-09 — Coherencia de textos y cifras** (RF-4)
  - Cuatro páginas y `cta/data.ts` sin «0.579», «60.418» ni la predicción de
    ejemplo; `mockData.ts` eliminado.
  - Hecho cuando: la búsqueda de cifras antiguas no encuentra apariciones fuera
    de la línea base y de las filas históricas.

## Bloque D — Gráficas

- [x] **T-9-10 — Gráficas congeladas** (RF-5)
  - Serie renovable recalculada y mix, exploración, mapa y predicción con su
    periodo y su fuente declarados.
  - Hecho cuando: cada figura dice qué periodo representa y de dónde sale.

- [x] **T-9-11 — Gráficas por modelo** (RF-5)
  - `ModelComparisonChart.astro` con una tarjeta por familia: real, 16 variables
    y 19 variables, más las métricas de cada versión con su ventana.
  - Hecho cuando: las ocho gráficas se dibujan en `/proceso` y `/resultados` y
    ninguna resta métricas de protocolos distintos.

- [x] **T-9-12 — Bloque en vivo y predicción de 30 días** (RF-3, RF-4)
  - Un script compartido, espera de 60 s, caducidad por fecha objetivo y ventana
    de días completos construida con 45 días del servicio.
  - Hecho cuando: funciona con el servicio local, con el publicado y apagado.

## Bloque E — Cierre

- [x] **T-9-13 — Verificación manual** (RF-4, RF-5, RNF-4, RNF-5, RNF-11)
  - Consola limpia en cuatro páginas, 360 px sin desbordamiento, modo oscuro,
    teclado, impresión, sin JavaScript y servicio apagado.
  - Hecho cuando: no aparece ningún defecto nuevo en esos escenarios.

- [x] **T-9-14 — Registro y memoria** (RF-6, todos)
  - Anotación fechada en `metrics-iniciales.md` y actualización de `MEMORY.md`.
  - Hecho cuando: el registro conserva la línea base sin reescribirla y la
    memoria refleja el estado implementado.

## Resultado

- **28/28 pruebas** en `frontend/`; `astro check` con 0 errores; build de las
  4 páginas.
- Gráficas con LR-19 de la exportación del 2026-11-15 (23.215,1 / 0,9301) y
  resto de la web con el modelo de producción (23.108,4 / 0,9308). No se restan.
- Pendiente fuera del repositorio: quitar la celda 108 de `main.ipynb` y
  decidir la liberación de la spec 008 en Render.
