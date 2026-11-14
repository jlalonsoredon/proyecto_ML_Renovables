# Plan 008 — Integración del pipeline de producción en Render

Deriva de `spec.md`. Este plan documenta la implementación futura; no se ha
modificado todavía el backend ni se ha ejecutado ningún cambio en Render.

## 1. Decisiones de diseño

- **D-8-1 — Modelo:** promover el artefacto LR-19 exacto; validar orden y
  `usa_scaler`, sin reentrenar.
- **D-8-2 — Base inicial:** reemplazar con la instantánea de `src/data`, no
  fusionar. Antes, crear y verificar backup de BD y modelo Render; los datos
  exclusivos quedan solo en ese backup.
- **D-8-3 — Tablas:** usar `prediccion_diaria`/`prediccion_propia` y retirar
  `prediccion_aemet`/`predictions`/`aemet_daily` de las operaciones normales.
- **D-8-4 — Credenciales:** usar `REE_API_KEY` como clave ESIOS y no incorporar
  secretos al código/configuración.
- **D-8-5 — Datos incompletos:** no predecir con variables faltantes, mocks,
  defaults o el modelo de 16 variables.
- **D-8-6 — API:** ampliar las respuestas de predicción sin cambiar su forma
  exterior, salvo el error HTTP 503 especificado.
- **D-8-7 — Gráfica:** alinear `pred_gwh` a las últimas 30 fechas reales y
  exponer todas las emisiones propias para esas fechas.
- **D-8-8 — Planificador:** mantener las 03:00/09:00 `Europe/Madrid`; reintentar
  AEMET a las 09:00 y hacer upsert de una reemisión del mismo día.
- **D-8-9 — Retención:** no purgar previsiones ni emisiones históricas; no
  borrar automáticamente los backups.
- **D-8-10 — Comparación:** mantener una lista con las siete filas históricas
  marcadas como 16 variables y añadir LR-19/LightGBM-19 desde una copia del acta
  en `backend/modelos/familia_como_modelo.json`.
- **D-8-11 — Sin predicción:** responder 503 estructurado y no borrar una fila
  previa cuando falle un refresh.
- **D-8-12 — Readiness:** `/health` devuelve 200 solo si BD y modelo cumplen
  contrato; Render declara `healthCheckPath: /health`.

### Justificación y alternativas descartadas

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| Promover el `.joblib` LR-19 exacto, sin reentrenar (D-8-1). | El artefacto actual ya pasó la selección de familia y conserva las 19 features acordadas; backend debe reproducirlo, no volver a elegirlo. | Entrenar otro modelo o copiar solo el modelo y reconstruir el scaler/features manualmente: podría cambiar resultados o el orden de columnas. |
| Reemplazar la BD activa con la instantánea de `src/data`, con backup (D-8-2). | Lo pidió el usuario como estrategia de seed; la copia de `src/data` es la base inicial aprobada. El backup conserva lo exclusivo de Render para rollback. | Fusionar registros automáticamente: exige una política de resolución de conflictos y podría mezclar emisiones históricas distintas. |
| Usar las tablas canónicas y retirar las de predicción heredadas (D-8-3). | Una sola fuente para capturas, predicciones propias, API y chart evita dual-writes divergentes. | Mantener escrituras paralelas a `predictions`/`prediccion_aemet` o migrar predicciones sin vector/orígenes inventando trazabilidad. |
| Reutilizar `REE_API_KEY` como `x-api-key` de ESIOS (D-8-4). | Es la variable ya declarada para REE en Render y el usuario la confirmó; `RENDER_API_KEY` solo autentica el MCP. | Añadir otro nombre de secreto (`ESIOS_TOKEN`) o almacenar una clave en JSON/código. |
| Detener predicción si falta una de las 19 entradas (D-8-5). | Un error visible es auditable y evita presentar valores falsos como producción. | Fallback de 16 features, promedio/default de 150.000 MWh, cero o interpolación. |
| Extender las respuestas sin cambiar su forma exterior (D-8-6). | Permite que los consumidores existentes ignoren campos nuevos; la lista de comparación se conserva. | Cambiar todos los endpoints a un nuevo objeto envolvente o exigir un despliegue coordinado del frontend. |
| En el chart, alinear la línea a las 30 fechas reales y exponer todas las emisiones (D-8-7). | Mantiene la longitud de arrays que usa Chart.js y no pierde emisiones repetidas; se selecciona la más reciente solo para la línea escalar. | Devolver toda la tabla como `pred_gwh` (desalinearía la serie) o descartar emisiones antiguas de una misma fecha. |
| Mantener scheduler 03:00/09:00 `Europe/Madrid` (D-8-8). | Conserva las horas operativas ya desplegadas; el retry solo rehace la emisión si cambia la entrada. | Cambiar horarios o crear un cron paralelo que pueda duplicar tareas. |
| No purgar forecasts, emisiones ni backups automáticamente (D-8-9). | Las elaboraciones y el backup son evidencia para auditoría y rollback. | Borrar datos una vez llega el real o limpiar backups por antigüedad sin autorización. |
| Añadir LR-19 y LightGBM-19 al array histórico (D-8-10). | Conserva siete resultados actuales como históricos y publica la comparación vigente. Se respeta el rechazo de LightGBM por 1/4 folds aunque gane el RMSE global. | Presentar métricas de 16 features como vigentes, reemplazar el array por otro tipo o inventar MAPE/accuracy; lo no medido queda `null`. |
| Usar HTTP 503 sin predicción válida (D-8-11). | Los clientes reciben un estado de error real y nunca confunden null/default con una predicción. Un refresh fallido no destruye una emisión válida previa. | Responder 200 con cero/null como predicción o continuar con fallback. El frontend actual no presenta este error correctamente; se deja documentado para una spec posterior. |
| Marcar `/health` no sano si BD/modelo no pasan (D-8-12). | Evita que Render enrute tráfico hacia una instancia que no puede servir el contrato LR-19. | Informar `ok` y dejar que cada endpoint falle después o cargar un modelo alternativo silenciosamente. |
| Mantener la lógica pura en Python y probarla desde `node --test`. | El backend ya es Python; un puente de test llama a las mismas funciones con fixtures y `hoy` fijo, sin duplicar algoritmo ni agregar paquetes. | Reimplementar la feature logic en JavaScript solo para testearla o añadir pytest/dependencias que la constitución no requiere. |
| Hacer la sustitución de volúmenes con una utilidad manual y `--apply`. | La BD y el modelo persisten entre despliegues; el backup, validación y activación atómica deben ocurrir una sola vez bajo control. | Copiar sobre los volúmenes en cada startup, lo que podría borrar datos válidos al reiniciar el servicio. |

## 2. Archivos que se crean o modifican

Los nombres de los módulos nuevos son el plan de implementación. Se pueden
ajustar solo si se conserva la responsabilidad, las reglas de la spec y sus
tests.

| Acción | Archivo | Responsabilidad | RF |
|---|---|---|---|
| Modificar | `backend/app/services/model_loader.py` | Cargar/validar el artefacto LR-19, el orden y `usa_scaler`; no usar fallback. | RF-1 |
| Modificar | `backend/app/services/db_ree.py` | Esquema canónico; lectura de observaciones por día local; persistencia y consulta de predicciones propias y reales. | RF-2, RF-5 |
| Modificar | `backend/app/services/forecast_db.py` | Guardar/leer AEMET y REE en `prediccion_diaria`; conservar solo el estado operativo de captura que necesite el reintento. | RF-2, RF-3 |
| Mantener | `backend/app/services/forecast_logic.py` | Copia vendorizada de `src/pipeline/forecast.py`; se usa sin editar para preservar la paridad y sin importar `src/` en Render. | RF-3, RF-4 |
| Modificar | `backend/app/services/aemet_client.py` | Descargar las 6 estaciones eólicas y 5 solares con todos los campos; backfill solo de faltantes. | RF-3 |
| Modificar | `backend/app/services/aemet_forecast.py` | Capturar el catálogo de 12 ubicaciones y guardar en la tabla común. | RF-3 |
| Modificar | `backend/app/services/ree_client.py` | Descargar observaciones REE, recuperar huecos recientes y normalizar fechas UTC a día Madrid. | RF-3, RF-4, RF-5 |
| Crear | `backend/app/services/ree_forecast_logic.py` | Parseo/validación pura del payload ESIOS 1777 y de sus fechas, portando la lógica de `src/pipeline/esios.py` sin modificar `src/`. | RF-3, RF-4 |
| Crear | `backend/app/services/ree_forecast.py` | Transporte HTTP de ESIOS 1777 con `REE_API_KEY`; delega parseo y selección al módulo puro. | RF-3 |
| Crear | `backend/app/services/prediction_features.py` | Funciones puras para las 19 variables, su origen y la lista de faltantes; usa la copia backend de `forecast_logic.py`. | RF-4 |
| Crear | `backend/app/services/prediction_service.py` | Orquestar fuentes archivadas, vector, modelo y upsert; servicio compartido por API y scheduler. | RF-1, RF-5, RF-6 |
| Modificar | `backend/app/tasks/scheduler.py` | Secuencia diaria, reintento de las 09:00, actualización de reales y logs. | RF-3, RF-5 |
| Modificar | `backend/app/main.py` | Inicialización del esquema, tareas, health check y fábrica de app de test sin scheduler/backfill. | RF-2, RF-7 |
| Modificar | `backend/app/api/prediction.py` | GET/refresh/forecast usando el servicio y respuestas 503 acordadas. | RF-6 |
| Modificar | `backend/app/api/charts.py` | Importance de 19 features, comparación histórica+nueva y chart desde `prediccion_propia`. | RF-6 |
| Crear | `backend/migrate_render_snapshot.py` | Utilidad manual `--apply`: backup, validación y reemplazo atómico de BD/modelo/acta; nunca arranca con FastAPI. | RF-2, RF-7 |
| Reemplazar | `backend/data/ree_generacion.db` | Instantánea consistente de `src/data/ree_generacion.db`; se registra su manifiesto. | RF-2 |
| Reemplazar | `backend/modelos/lr_eolica.joblib` | Copia byte a byte del modelo aprobado de 19 variables. | RF-1 |
| Crear | `backend/modelos/familia_como_modelo.json` | Copia del acta vigente que alimenta `/api/model-comparison`; Render no lee `src/`. | RF-6 |
| Modificar | `render.yaml` | Rutas absolutas persistentes, `METRICS_PATH`, `healthCheckPath` y variables externas. | RF-7 |
| Crear | `backend/tests/logic_probe.py` | Adaptador JSON que llama las funciones Python reales y operaciones SQLite temporales; no implementa reglas duplicadas. | RF-2, RF-4, RF-5 |
| Crear | `backend/tests/prediction_contract.test.mjs` | Contrato del artefacto y casos de funciones puras mediante `node:test` y el adaptador. | RF-1, RF-4 |
| Crear | `backend/tests/persistence_api.test.mjs` | Snapshot/schema, capturas simuladas, upserts, error real y pruebas HTTP locales con BD temporal; sin red externa. | RF-2, RF-3, RF-5, RF-6, RF-7 |
| Modificar | `specs/008-integracion-backend-render/plan.md`, `tasks.md`, `MEMORY.md` | Plan, seguimiento y cierre. | Todos |

`backend/requirements.txt` no cambia. No se modifican `src/`, frontend, otros
artefactos de modelo ni la BD fuente.

### Trazabilidad RF → archivos y tests

| RF | Implementación prevista | Puerta de prueba |
|---|---|---|
| RF-1 — Modelo | `model_loader.py`, `prediction_service.py`, `.joblib` | `prediction_contract.test.mjs`: hash, familia, scaler, 19 columnas, fallo sin fallback. |
| RF-2 — BD canónica y snapshot | `db_ree.py`, `forecast_db.py`, `migrate_render_snapshot.py`, `backend/data/ree_generacion.db` | `persistence_api.test.mjs`: esquema, claves, manifiesto, integridad, upsert y rollback en temporales. |
| RF-3 — Capturas programadas | `aemet_client.py`, `aemet_forecast.py`, `ree_client.py`, `ree_forecast_logic.py`, `ree_forecast.py`, `scheduler.py` | `persistence_api.test.mjs`: clientes simulados, `429`, recaptura, huecos recientes y orden de tareas. |
| RF-4 — Features/orígenes | `prediction_features.py`, `forecast_logic.py`, `ree_forecast_logic.py` | `prediction_contract.test.mjs`: mapa completo, ventanas mixtas, fecha local, elegibilidad, relleno honesto y vector. |
| RF-5 — Emisión/real | `prediction_service.py`, `db_ree.py`, `scheduler.py` | `persistence_api.test.mjs`: upsert mismo día, varias emisiones, real y signo del error. |
| RF-6 — API | `api/prediction.py`, `api/charts.py`, acta de familia | `persistence_api.test.mjs`: contratos 200/503, vector/orígenes, chart y filas comparativas. |
| RF-7 — Render/readiness | `main.py`, `render.yaml`, `migrate_render_snapshot.py` | `persistence_api.test.mjs`: `/health`, rutas/env/healthcheck y operación simulada de snapshot. |

## 3. Orden de trabajo

1. Crear pruebas unitarias para el contrato del modelo, reglas de features,
   elección/origen de previsiones, persistencia y API. Confirmar que fallan
   antes de implementar.
2. Crear una copia consistente de `src/data/ree_generacion.db` con SQLite
   Backup API; guardar huella, esquema y recuentos de esa instantánea (no usar
   como constantes las cifras de este documento). Reemplazar la copia local
   `backend/data/ree_generacion.db`, conservando copia previa.
3. Copiar el `.joblib` aprobado y el acta
   `familia_como_modelo.json` a `backend/modelos/`. Validar SHA, familia,
   scaler, orden y cantidad de variables.
4. Adaptar esquema e inicialización de backend a `aemet_diario`,
   `prediccion_diaria` y `prediccion_propia`; dejar de crear/consultar las
   tablas de predicción heredadas.
5. Implementar captura REE 1777 D+1 y ampliar la captura AEMET observada para
   las 11 estaciones y columnas necesarias. Mantener idempotencia, rate limits,
   backfill AEMET solo de faltantes y causas de error visibles.
6. Implementar un único constructor de features que reproduzca las reglas de
   origen, ventana mixta, elegibilidad temporal, generación completa y
   `eolica_prev` de las specs 004/005.
7. Integrar en el scheduler el orden de captura, actualización de reales y
   predicción; probar el reintento de las 09:00 y el upsert del mismo día.
8. Actualizar los endpoints, preservar campos existentes y añadir el vector,
   orígenes, previsión REE y serie de `prediccion_propia`. Mantener la lista de
   `/api/model-comparison`, marcando sus filas antiguas como históricas y
   añadiendo las dos filas de 19 variables.
9. Alinear `DB_PATH`/`MODEL_PATH` y `healthCheckPath` con los discos/health
   check de `render.yaml`. Para el
   cambio de producción, pausar escritores; respaldar BD y modelo fuera de las
   rutas activas; verificar hashes; instalar temporales en los volúmenes; validar
   y activar atómicamente. Mantener los respaldos hasta autorización explícita
   de borrado. No ejecutar este paso al arrancar FastAPI.
10. Ejecutar tests y validación local sin depender de red real. Solo después de
    revisar el backup, hashes y resultado, realizar el release en Render y
    comprobar health/API. Ante una diferencia, restaurar el backup.

## 4. Funciones puras y contrato de variables

El reloj se consulta una sola vez en el límite de la aplicación: el scheduler o
la ruta obtiene `hoy` como fecha de `Europe/Madrid` y lo pasa al servicio. Las
funciones siguientes no leen reloj, BD, red, entorno ni archivos; reciben los
datos ya preparados y, cuando hay una decisión temporal, reciben `hoy`.

| Función prevista | Entradas principales | Resultado | RF |
|---|---|---|---|
| `aggregate_observations(rows, station_ids, variable, hoy)` | Filas diarias, catálogo y fecha local | Serie diaria de medias válidas; ignora estaciones no incluidas y fechas futuras. | RF-4 |
| `select_aemet_forecast(rows, objetivo, ubicacion, hoy)` | Archivo AEMET y objetivo | Fila con elaboración más reciente `<= min(objetivo, hoy)`, o ausente. | RF-4 |
| `aemet_national_series(rows, uso, hoy)` | Filas AEMET elegibles y tipo eólico/solar | Serie diaria por fecha y medias de valores disponibles, sin inventar datos. | RF-4 |
| `parse_ree_d1(payload, objetivo, hoy, capturado_en)` | JSON ESIOS 1777, objetivo y captura | Fila `fuente=ree` solo si `values_updated_at` existe, objetivo/zona coinciden y la elaboración es elegible; si no, motivo de descarte. | RF-3, RF-4 |
| `resolve_window(observaciones, previsiones, objetivo, dias, hoy)` | Series por fecha, ventana y objetivo | Media y origen (`observacion`, `prevision`, `mixta`) con conteos; no disponible si falta un día. | RF-4 |
| `latest_complete_generation(series, hoy)` | Generación eólica por día local | Ancla válida y avisos; descarta últimos días bajo el umbral de frescura. | RF-4, RF-5 |
| `select_ree_forecast(rows, objetivo, hoy)` | Archivo REE y objetivo de lag | Última previsión válida con elaboración `<= min(objetivo, hoy)`. | RF-4 |
| `resolve_generation_features(observada, ree_forecasts, objetivo, hoy)` | Series REE observada/previsión y fecha | Lags y `eolica_ma7`, con origen por variable y ancla completa. | RF-4 |
| `resolve_eolica_prev(rows, objetivo, hoy)` | Previsiones REE archivadas | D+1 elegible hasta `min(objetivo-1, hoy)` o media de siete previsiones reales previas; sin relleno encadenado. | RF-4 |
| `build_prediction_map(observaciones, previsiones, generacion, hoy)` | Datos normalizados ya cargados | Mapa con objetivo, 19 entradas, valores, orígenes, desglose y faltantes. | RF-4 |
| `ordered_vector(mapa, model_features)` | Mapa y orden del `.joblib` | Vector numérico en el orden del artefacto, o lista de columnas inválidas. | RF-1, RF-4 |
| `prediction_error(fecha_objetivo, real_mwh, prediccion_mwh, hoy)` | Fecha y valores reales/predichos | Error `real - predicción` solo si el objetivo ya ocurrió y existe real válido. | RF-5 |

Las funciones que toman decisiones temporales o estadísticas reciben el `hoy`
inyectado, no `date.today()`/`datetime.now()`. La única excepción es
`ordered_vector`, que solo reordena/valida un mapa y no calcula fechas ni
estadísticas. Las conversiones del timestamp UTC de REE a fecha local son
funciones puras: reciben el timestamp y la zona horaria de destino. El vector
final usa `features` del artefacto como orden autoritativo.

### Algoritmo del mapa — pseudocódigo

```text
ENTRADA: hoy (Europe/Madrid), observaciones AEMET/REE,
         archivo AEMET/REE y lista ordenada de features del modelo

objetivo ← día siguiente a hoy
mapa ← vacío

mapa[mes, dia_semana, dia_año] ← calendario(objetivo), origen observacion

Para cada una de las 7 ubicaciones eólicas:
    elegir para objetivo la última previsión AEMET con elaborado <= hoy
velmedia, racha ← media de valores disponibles
asignar origen prevision; si no hay valores, marcarlos no disponibles

Para cada ventana de viento/racha de 3, 7 y 14 días terminada en objetivo:
    para cada día d de la ventana:
        si d <= hoy y hay observación en estaciones únicas:
            usar observación
        si no, elegir la previsión AEMET más reciente con elaborado <= min(d, hoy)
        si no hay ninguna fuente para d:
            marcar la ventana no disponible; no acortarla ni desplazarla
    si todos los días tienen fuente:
        promediar; origen observacion, prevision o mixta
        si mixta, conservar cantidad de días por fuente

Para sol_lag1 y tmed_lag1 en objetivo - 1:
    usar media observada de las 5 estaciones solares si existe
    si falta, usar la previsión AEMET elegible de esas ubicaciones
    marcar sol previsto como estimada y tmed previsto como prevision

serie_generacion ← agrupar Eólica por fecha Europe/Madrid
ancla ← última fecha <= hoy que pasa la regla de generación completa
calcular eolica_lag1/2/3/7 respecto de ancla
para cada día ausente, usar previsión REE elegible del mismo día
calcular eolica_ma7 sobre los 7 días naturales hasta ancla
aplicar prioridad observación, previsión en huecos y origen mixto

ree_d1 ← previsión de objetivo, ubicación peninsula,
          elaborada <= min(objetivo - 1 día, hoy), valor entre 0 y 720000 MWh
si no existe ree_d1:
    tomar las previsiones REE reales válidas de los 7 días naturales previos
    si hay alguna, usar su media y origen estimada
    si no hay ninguna, marcar eolica_prev no disponible

faltantes ← nombres de features sin valor finito u origen válido
si faltantes no está vacío:
    devolver mapa + faltantes; no invocar el modelo
vector ← valores del mapa en el orden exacto del artefacto
devolver objetivo, mapa, vector y resumen de orígenes
```

El orden debe coincidir exactamente con el `features` del artefacto:

1. `velmedia`
2. `racha`
3. `mes`
4. `dia_semana`
5. `dia_año`
6. `eolica_lag1`
7. `eolica_lag2`
8. `eolica_lag3`
9. `eolica_lag7`
10. `vel_ma3`
11. `vel_ma7`
12. `vel_ma14`
13. `racha_ma3`
14. `racha_ma7`
15. `racha_ma14`
16. `eolica_ma7`
17. `sol_lag1`
18. `tmed_lag1`
19. `eolica_prev`

El builder entrega tanto los valores como un mapa de orígenes. Ninguna columna
puede faltar en el momento de llamar a `modelo.predict`.

## 5. Flujo programado

### 03:00 `Europe/Madrid`

1. Capturar previsiones AEMET y REE y guardar las elaboraciones.
2. Actualizar observaciones recientes de REE y AEMET.
3. Encontrar predicciones cuyo objetivo ya tenga generación real completa;
   actualizar `real_mwh` y `error_mwh`.
4. Resolver las entradas de mañana, abortar si falta una variable obligatoria,
   predecir con el artefacto validado y guardar el vector, orígenes y emisión.

### 09:00 `Europe/Madrid`

1. Reintentar AEMET solo cuando la captura de las 03:00 quedó incompleta.
2. Si la predicción no se pudo generar o el reintento cambia la entrada
   disponible, reconstruirla y hacer upsert para el mismo objetivo y día de
   emisión. No crear duplicados.

## 6. Interfaz y exposición de datos

Esta spec no modifica archivos del frontend.

- `frontend/src/pages/index.astro` y `resultados.astro` conservan la respuesta
  actual de `/api/prediction` (`fecha`, `prediccionMWh`, `modelo`,
  `features.velmedia`, `features.racha`). Los campos nuevos de trazabilidad son
  aditivos y las páginas actuales los ignoran.
- `PredictionChart.astro` conserva `fechas_hist`, `real_gwh`, `pred_gwh`,
  `manana`, viento y `avisos`; la serie histórica cambia de fuente a
  `prediccion_propia`. Los valores siguen siendo GWh en las series existentes.
  La nueva lista `predicciones_propias` queda disponible para una futura UI,
  pero no se dibuja todavía.
- `FeatureImportanceChart.astro` recibe la misma lista `{feature, importance}`
  y muestra 19 barras sin cambiar el componente.
- `ModelComparisonChart.astro` contiene datos estáticos y no consume
  `/api/model-comparison`; seguirá mostrando sus valores actuales. La lista
  nueva del API queda disponible para una futura spec de frontend.
- La condición HTTP 503 no se representa correctamente en todas las páginas
  actuales: esta spec prioriza no inventar una predicción. La gestión visual
  del error es explícitamente trabajo de frontend posterior.

## 7. Estrategia de tests con `node --test`

**Puerta obligatoria:** desde la raíz del repositorio, ejecutar `node --test`.
Para aislar los tests nuevos, ejecutarlo con `backend/tests/` como directorio
de trabajo. No se instalan paquetes.

- Los `.test.mjs` usan los módulos incorporados `node:test`, `node:assert` y
  `node:child_process`. El runner de Node envía fixtures JSON al adaptador
  `logic_probe.py`; este importa y ejecuta las funciones Python reales con el
  `hoy` suministrado y devuelve JSON. Las aserciones y los resultados esperados
  viven en Node; el adaptador no duplica la lógica.
- El entorno de tests configura la ruta del intérprete mediante `PYTHON` (o un
  ejecutable Python ya disponible en PATH), crea bases temporales y elimina
  esos temporales al finalizar.
- **RF-1:** cargar el artefacto aprobado, validar claves, familia, escalador,
  SHA y orden exacto de 19 features; entrada incompatible no predice y hace
  fallar readiness.
- **RF-2/RF-3:** comparar esquema/manifest de snapshot, integridad SQLite,
  captura idempotente, clave primaria, días ausentes y ausencia de escrituras
  de forecast en `generacion`/`aemet_diario`.
- **RF-4:** probar selección de elaboración no futura, zona Madrid/DST,
  ventanas mixtas, días sin fuente, umbral de frescura REE, previsión D+1,
  relleno de siete previsiones reales y lista exacta de faltantes.
- **RF-5:** probar upsert de misma fecha de emisión, conservación del real,
  múltiples fechas de emisión, signo `real - predicción` y no uso de real
  incompleto.
- **RF-6/RF-7:** iniciar la app de test sin scheduler ni backfill, con clientes
  AEMET/ESIOS sustituidos por fixtures y BD temporal; usar `fetch` de Node sobre
  loopback para comprobar 200/503, JSON, `/health`, `/api/prediction`,
  `/api/forecast`, model-comparison y alineación de `pred_gwh`.
- Las pruebas no hacen llamadas a internet, no requieren credenciales ni
  tocan la BD/versiones de Render. El release se verifica aparte con
  `PRAGMA integrity_check`, manifiestos, SHA-256 y restauración del backup.
- Tras autorización del release, smoke checks de `/health`,
  `/api/prediction`, `/api/forecast` y `/api/prediction-chart` confirman el
  estado del servicio y de los discos persistentes.
