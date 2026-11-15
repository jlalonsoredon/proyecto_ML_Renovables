# Plan 009 — Actualizar el frontend: recorrido de las specs y métricas reales

Deriva de `spec.md` y del registro `metrics-iniciales.md`. No modifica backend,
modelo, datos de observación ni dependencias.

## 1. Decisiones de diseño

| Id | Decisión | Cubre |
|---|---|---|
| P-9-1 | Los datos congelados viven en tres JSON versionados bajo `frontend/src/data/`. Las páginas y las pruebas leen los mismos archivos. | D-9-12, RNF-10, CA-4.3 |
| P-9-2 | La lógica pura vive en un único módulo `.mjs` sin DOM, que recibe `today` como parámetro. Es JavaScript con JSDoc, no TypeScript, para que `node --test` lo importe sin transpilar en cualquier versión de Node. | D-9-21, constitución 4 y 5 |
| P-9-3 | El bloque en vivo usa un único script de cliente compartido por portada, resultados y proceso. Ese script es el único que lee el reloj y la red; delega las decisiones en el módulo puro. | D-9-16, D-9-17, CA-4.2 |
| P-9-4 | La serie de 30 días se construye pidiendo 45 días al servicio y aplicando la regla de día completo en el navegador. No se cambia el backend. | D-9-13, D-9-14, RNF-8 |
| P-9-5 | Los hitos se construyen con elementos desplegables nativos del HTML. Se generan abiertos; un script los pliega al cargar. Sin código, quedan abiertos; al imprimir, se abren todos. | CA-1.7, CA-1.8, RNF-11 |
| P-9-6 | Tiempo de espera del bloque en vivo: **60 s**, con un mensaje de carga que avisa de que el servicio puede tardar en arrancar. | CA-3.7, CE-2 |
| P-9-7 | La gráfica de comparación pasa a dibujar las nueve filas del JSON de métricas. Se retiran las ocho series semanales antiguas: usaban otra ventana y su cifra (60.418) contradecía la tabla. | CA-4.3, CA-5.1, CA-5.2, D-9-11 |
| P-9-8 | SARIMAX desaparece de la comparación: no forma parte de las siete filas históricas que publica el sistema de referencia. | CA-5.1 |
| P-9-9 | La importancia de variables pasa a datos congelados (19 filas) y se monta en el paso 3 de proceso, después de la tabla de modelos. | CA-5.5, D-9-12 |
| P-9-10 | El mix energético se mantiene congelado y declara su periodo. No se recalcula: la BD no contiene generación no renovable y su columna de porcentaje es inconsistente en los días recientes. | CA-5.4, CA-5.8 |
| P-9-11 | La serie semanal de generación renovable se recalcula desde la BD de referencia hasta la última semana completa, con las seis tecnologías. | CA-4.6, CA-5.8 |
| P-9-12 | Las gráficas de exploración escalada se mantienen congeladas y declaran su periodo de entrenamiento. Son análisis exploratorio, no métricas vigentes. | CA-5.8 |
| P-9-13 | `mockData.ts` se elimina. Solo se usaba para la predicción de ejemplo y su generador aleatorio. | CA-4.2, CA-5.7 |
| P-9-14 | Los nombres de código siguen la constitución: en inglés. Textos visibles, en español. | Constitución 7 |

### Justificación y alternativas descartadas

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| JSON + módulo `.mjs` (P-9-1, P-9-2) | Una sola fuente para tabla, gráfica y pruebas: imposible que diverjan. El `.mjs` se prueba con Node puro, sin paquetes. | Datos incrustados en cada componente, como hoy: es la causa de las tres cifras distintas. Módulo `.ts`: obliga a Node ≥ 22.18 para las pruebas. |
| Pedir 45 días y filtrar (P-9-4) | Cumple «30 días retrocediendo» con un parámetro que ya existe. | Cambiar el backend para devolver solo días completos: fuera de alcance. |
| Desplegables nativos (P-9-5) | Teclado, lector de pantalla y funcionamiento sin código vienen de serie. | Acordeón con JavaScript propio: más código y peor accesibilidad. Carrusel: descartado en la spec. |
| 60 s de espera (P-9-6) | Producción tardó más de 45 s en la primera respuesta del 2026-11-15. | 10–15 s: daría error en cada arranque en frío. Sin límite: el bloque podría quedarse cargando para siempre. |
| Retirar las series semanales (P-9-7) | Su ventana (46 semanas) no coincide con ninguna fila vigente, y mantenerlas obliga a explicar una cuarta cifra. | Conservarlas etiquetadas: válido según CA-5.2, pero añade ocho gráficas sin aportar a la comparación. |
| Mix congelado (P-9-10) | Recalcularlo exigiría datos no renovables que la BD no tiene. | Recalcular solo el reparto renovable: mezclaría dos periodos en la misma figura. |
| Eliminar `mockData.ts` (P-9-13) | Nada útil queda dentro una vez retirada la predicción de ejemplo. | Vaciarlo y conservarlo: deja un archivo muerto que invita a reintroducir datos falsos. |

## 2. Archivos que se crean o modifican

| Acción | Archivo | Responsabilidad | RF |
|---|---|---|---|
| Crear | `frontend/src/data/spec-timeline.json` | Nueve hitos (número, título, categorías, resumen, partida, cambio, resultado, detalle técnico) y glosario. | RF-1 |
| Crear | `frontend/src/data/model-metrics.json` | Línea base, referencia y nueve filas con protocolo (variables, ventana, días), estado, decisión y motivo. | RF-2, RF-5 |
| Crear | `frontend/src/data/reference-series.json` | Importancia de 19 variables, serie semanal renovable recalculada y metadatos de periodo y fuente de cada gráfica congelada. | RF-5 |
| Crear | `frontend/src/utils/evolution.mjs` | Funciones puras de la sección 4. | RF-2, RF-3, RF-5, RF-7 |
| Crear | `frontend/src/utils/live-prediction.mjs` | Script de cliente: lee reloj y red, aplica el tiempo de espera, llama al módulo puro y pinta el resultado. | RF-3, RF-4 |
| Crear | `frontend/src/components/evolution/SpecTimeline.astro` | Línea de tiempo y glosario. | RF-1 |
| Crear | `frontend/src/components/evolution/MetricsComparison.astro` | Comparación principal, aviso de no comparabilidad y tabla de nueve filas. | RF-2 |
| Crear | `frontend/src/components/evolution/LivePredictionStatus.astro` | Bloque de estado actual de la sección 6. | RF-3 |
| Crear | `frontend/tests/evolution.test.mjs` | Pruebas de la lógica pura y de la integridad de los JSON. | RF-7 |
| Modificar | `frontend/src/pages/proceso.astro` | Enlace de anclaje, paso 6, tabla del paso 3 desde el JSON, textos corregidos e importancia de variables. | RF-1, RF-2, RF-4, RF-5 |
| Modificar | `frontend/src/pages/resultados.astro` | Retirar el ejemplo, usar el bloque compartido y corregir el texto de R². | RF-3, RF-4 |
| Modificar | `frontend/src/pages/index.astro` | Retirar el ejemplo y usar el bloque compartido. | RF-3, RF-4 |
| Modificar | `frontend/src/components/sections/cta/data.ts` | Sustituir «R² de 0.579» por la cifra de referencia con su protocolo. | RF-4 |
| Modificar | `frontend/src/components/charts/ModelComparisonChart.astro` | Nueve filas desde el JSON, sin series semanales. | RF-5 |
| Modificar | `frontend/src/components/charts/PredictionChart.astro` | Eliminar el script duplicado y construir la serie de 30 días completos. | RF-4, RF-5 |
| Modificar | `frontend/src/components/charts/FeatureImportanceChart.astro` | Leer el JSON en vez del servicio. | RF-5 |
| Modificar | `frontend/src/components/charts/RenewableLineChart.astro` | Serie desde el JSON y periodo declarado. | RF-5 |
| Modificar | `frontend/src/components/charts/EnergyPieChart.astro` | Periodo y fuente declarados. | RF-5 |
| Modificar | `frontend/src/components/charts/EolicaScaledCharts.astro` | Periodo declarado. | RF-5 |
| Modificar | `frontend/src/components/charts/WindMap.astro` | Nota de estación compartida. | RF-5 |
| Eliminar | `frontend/src/data/mockData.ts` | Predicción de ejemplo y generador aleatorio. | RF-4, RF-5 |
| Anotar | `specs/009-actualización-frontend/metrics-iniciales.md` | Fecha, consulta y SHA-256 de la BD usada para extraer los datos. | RF-6 |
| Modificar | `specs/009-actualización-frontend/tasks.md`, `MEMORY.md` | Seguimiento y cierre. | Todos |

No cambian `package.json`, el backend, la BD, el modelo ni `src/`.

### Trazabilidad RF → archivos y pruebas

| RF | Implementación | Puerta |
|---|---|---|
| RF-1 | `spec-timeline.json`, `SpecTimeline.astro`, `proceso.astro` | Prueba de integridad: 9 hitos ordenados, campos completos, categorías válidas. Revisión manual con teclado y sin JS. |
| RF-2 | `model-metrics.json`, `MetricsComparison.astro`, `evolution.mjs` | Pruebas: comparabilidad, diferencia solo entre comparables, «no disponible». |
| RF-3 | `live-prediction.mjs`, `LivePredictionStatus.astro`, `evolution.mjs` | Pruebas de estado. Revisión manual con el servicio local, el publicado y sin servicio. |
| RF-4 | Páginas, `data.ts`, `PredictionChart.astro` | Búsqueda de cifras antiguas en el código; consola limpia en cuatro páginas. |
| RF-5 | Gráficas y `reference-series.json` | Pruebas de ventana; revisión visual de periodos y fuentes. |
| RF-6 | `metrics-iniciales.md` | Revisión de la anotación. |
| RF-7 | `evolution.test.mjs` | `node --test` en verde. |

## 3. Orden de trabajo

1. **Pruebas primero.** Escribir `evolution.test.mjs` con los casos de la
   sección 5 y comprobar que fallan.
2. **Lógica pura.** Implementar `evolution.mjs` hasta que las pruebas pasen.
3. **Datos de métricas.** Construir `model-metrics.json` desde el registro de
   línea base, el acta de familia del backend y las siete filas históricas del
   sistema de referencia.
4. **Datos de series.** Extraer de la BD de referencia, en solo lectura, la
   importancia de variables y la serie semanal hasta la última semana completa.
   Anotar consulta, fecha y SHA-256 en el registro.
5. **Contenido del recorrido.** Redactar los nueve hitos y el glosario a partir
   de cada `spec.md` y `tasks.md`, citando solo cifras medidas en cada spec.
6. **Componentes nuevos.** Línea de tiempo, comparación y bloque en vivo.
7. **Paso 6.** Montarlo en proceso con su anclaje.
8. **Coherencia.** Sustituir cifras y textos antiguos en las cuatro páginas;
   eliminar `mockData.ts`.
9. **Gráficas.** Comparación, importancia, serie renovable, mix, exploración,
   mapa y predicción frente a real.
10. **Verificación.** Pruebas, build y revisión manual de la sección 6.

## 4. Funciones puras

Ninguna lee reloj, red, DOM ni almacenamiento. Las que deciden sobre fechas
reciben `today` como cadena `YYYY-MM-DD` en hora peninsular.

| Función | Entradas | Resultado | RF |
|---|---|---|---|
| `isCompleteDay(series, index)` | Serie diaria de eólica y posición | `true` si hay al menos cinco valores entre los siete días anteriores y el día alcanza el 60 % de su mediana. | RF-5, RF-7 |
| `selectCompleteWindow(series, size)` | Serie diaria y tamaño | Descarta días finales incompletos y devuelve los `size` últimos, o los que haya con su número. | RF-5, RF-7 |
| `areComparable(rowA, rowB)` | Dos filas | `true` solo si coinciden variables, ventana y días, y ninguna ventana es desconocida. | RF-2, RF-7 |
| `metricDelta(rowA, rowB, metric)` | Dos filas y métrica | Diferencia si son comparables y ambos valores son válidos; si no, `null`. | RF-2, RF-7 |
| `formatMetric(value, metric)` | Valor y tipo | Cadena en formato español o «no disponible» si el valor falta o es implausible. | RF-2, RF-7 |
| `isPlausibleMetric(value, metric)` | Valor y tipo | Rechaza no finitos, errores negativos y R² mayor que 1. | RF-2, RF-7 |
| `rowStatus(row)` | Fila de métricas | «vigente», «histórico» o el estado que declare la fila. | RF-2, RF-7 |
| `predictionStatus(response, today)` | Respuesta del servicio o `null` | Estado (`ok`, `caducado`, `no_disponible`), versión declarada y campos ausentes. | RF-3, RF-7 |
| `formatDateEs(isoDate)` | Fecha `YYYY-MM-DD` | Fecha larga en español, sin conversión de zona. | RF-3, RF-7 |

El reloj se consulta una vez, en el script de cliente, con la zona
`Europe/Madrid`, y se pasa como `today`.

## 5. Estrategia de pruebas con `node --test`

**Puerta:** `node --test` desde la raíz. Para aislar, ejecutarlo dentro de
`frontend/`. Sin paquetes nuevos, solo `node:test` y `node:assert`.

- **Día completo:** día normal, día bajo el 60 %, día a cero, menos de cinco
  valores previos, varios días finales incompletos seguidos.
- **Ventana:** 45 días con el último incompleto devuelven 30; con 20 días
  completos devuelven 20 y su número.
- **Comparabilidad:** línea base frente a referencia sin diferencia; LR-19
  frente a LightGBM-19 con diferencia; ventana desconocida nunca comparable.
- **Formato:** separador de miles, coma decimal, `null`, `NaN`, R² de 1,2 y
  RMSE negativo.
- **Estado de predicción:** contrato de 19 variables completo; contrato antiguo
  sin `n_variables` ni `fecha_emision`; respuesta vacía; fecha de ayer
  (caducado); fecha de hoy y de mañana; cambio de mes y de año.
- **Integridad de datos:** nueve hitos del 001 al 009, categorías dentro de las
  cuatro permitidas, nueve filas de métricas, ninguna métrica cero donde la
  fuente dice «no disponible», 19 variables de importancia que suman 1 ± 0,001.
- Las pruebas no usan red, reloj ni DOM.

Estado previo conocido: la suite raíz tiene un fallo preexistente en
`src/pipeline/tests/gate.test.mjs` (`ENOBUFS`). La puerta de esta spec son las
pruebas de `frontend/tests/` en verde y ningún fallo nuevo en la raíz.

## 6. Verificación manual

1. `npm run build` sin errores.
2. Con el servicio local: las cuatro páginas sin errores de consola y la sección
   6 con 19 variables.
3. Con el servicio publicado: el bloque declara la versión antigua y marca los
   campos ausentes.
4. Con el servicio apagado: aviso tras el tiempo de espera y resto legible.
5. Sin JavaScript: hitos abiertos y bloque en vivo con su explicación.
6. A 360 px, modo oscuro, zoom al 200 %, teclado y vista de impresión.
7. Búsqueda en el código de «0.579», «60.418», «57.9», «207354» y
   «Math.random»: ninguna aparición fuera del registro y de las filas
   históricas.

## 7. Riesgos

- **Porcentajes inconsistentes en la BD:** la columna `porcentaje` suma más del
  100 % en días recientes. No afecta al plan porque el mix no se recalcula
  (P-9-10). Se registra como hallazgo para otra spec.
- **Nombres de variable mal codificados en el servicio:** la sección usa los del
  JSON, nunca los del servicio (CE-15).
- **Entorno publicado sin la spec 008:** el bloque en vivo mostrará 16
  variables y cifras distintas de la referencia hasta la liberación. Es el
  comportamiento acordado (D-9-16).
- **Contenido de los hitos:** es la tarea más larga y la más propensa a
  atribuir mejoras no medidas. Cada cifra se revisa contra su spec antes de
  cerrar la tarea.

## 8. Decisiones del plan que conviene confirmar

1. **LightGBM-19 con estado propio.** La spec le asigna «histórico» (CA-2.5),
   pero es una candidata descartada, no una referencia antigua. Propuesta:
   añadir un quinto estado, «rechazado», y ajustar la spec.
2. **Retirar las series semanales** de la comparación (P-9-7).
3. **Mix congelado** con su periodo declarado (P-9-10).
4. **Eliminar `mockData.ts`** (P-9-13).
5. **Crear 9 archivos nuevos** (sección 2), como exige preguntar `AGENTS.md`.
