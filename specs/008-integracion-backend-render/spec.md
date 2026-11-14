# Spec 008 — Integrar el pipeline de producción en el backend de Render

- **Estado:** lista para revisión e implementación; no implementada ni desplegada.
- **Fecha:** 2026-11-14.
- **Depende del comportamiento establecido en:** specs 004, 005, 006 y 007.

## 1. Contexto

El pipeline de análisis ya produce una predicción eólica peninsular diaria con
Linear Regression y 19 variables. El backend desplegado sigue usando un modelo
de 16 variables y un proceso de predicción distinto, por lo que no puede servir
el resultado del pipeline actual ni conservar su trazabilidad.

Inventario observado al redactar esta spec:

- `src/data/modelos/lr_eolica.joblib`: familia **Linear Regression**, 19
  variables, `StandardScaler`, `usa_scaler=True`; SHA-256
  `e915381e2c24fcfbc2a81ab6eca2fdede7c7729f1abe2f79e58491cf9647c702`.
- `src/data/ree_generacion.db`: tablas `generacion` (10.669 filas),
  `aemet_diario` (30.544), `prediccion_diaria` (2.900: 1.120 AEMET y 1.780
  REE) y `prediccion_propia` (8).
- La BD versionada en `backend/data/ree_generacion.db` tiene 9.684 filas de
  `generacion` y 22.426 de `aemet_diario`; no contiene las dos tablas nuevas.
  Estas cifras describen la copia local, no necesariamente el volumen vivo de
  Render.
- El backend crea además tablas heredadas (`predictions`, `aemet_daily` y
  `prediccion_aemet`) en `init_db()`. El guardado de predicciones no incluye
  el vector completo ni sus orígenes.
- `backend/app/services/model_loader.py` declara 16 variables y aplica el
  escalador de forma incondicional. `charts.py` y `prediction.py` leen o
  escriben la tabla heredada.
- `render.yaml` monta discos en `/app/data` y `/app/modelos`, pero declara
  `DB_PATH` y `MODEL_PATH` como rutas relativas. La configuración deberá dejar
  inequívoco que los archivos activos están en los discos persistentes.

La lista ordenada de variables del artefacto que se promoverá es:

```text
velmedia, racha, mes, dia_semana, dia_año,
eolica_lag1, eolica_lag2, eolica_lag3, eolica_lag7,
vel_ma3, vel_ma7, vel_ma14,
racha_ma3, racha_ma7, racha_ma14,
eolica_ma7, sol_lag1, tmed_lag1, eolica_prev
```

## 2. Objetivo y alcance

Integrar en el backend la construcción, emisión, persistencia y exposición por
API de la predicción de 19 variables, manteniendo la semántica de los datos y
orígenes del pipeline actual. El backend debe operar con sus propias copias y
servicios: no dependerá de importar código de `src/` en Render.

**Archivos dentro del alcance de implementación:** `backend/` y `render.yaml`.
También se actualizarán esta spec y `MEMORY.md`.

**Fuera de alcance:** `src/`, frontend/Vercel, otros artefactos de modelo fuera
de `backend/`, reentrenar, cambiar la familia o las 19 variables, añadir
dependencias o ejecutar ahora una migración/despliegue en Render.

## 3. Decisiones aprobadas

- **D-8-1 — Modelo:** promover a `backend/modelos/lr_eolica.joblib` una copia
  byte a byte del artefacto de `src/data/modelos/lr_eolica.joblib`. Se conserva
  Linear Regression, el nombre del archivo, el orden de las 19 variables y el
  preprocesado. No se reentrena.
- **D-8-2 — Base inicial:** reemplazar, no fusionar, la BD operativa de Render
  por una instantánea consistente de `src/data/ree_generacion.db`. Se crea
  antes una copia de seguridad recuperable de la BD de Render. Los registros
  exclusivos de Render se conservan solo en ese respaldo; no se importan a la
  BD activa.
- **D-8-3 — Tablas canónicas:** `prediccion_diaria` y `prediccion_propia` usan
  el esquema y las claves de la BD de `src/data`. Se retiran las tablas y
  lecturas/escrituras heredadas `prediccion_aemet`, `predictions` y
  `aemet_daily`; sus registros exclusivos quedan en el respaldo anterior.
- **D-8-4 — Credenciales:** `REE_API_KEY` es la variable de Render que contiene
  la clave ESIOS enviada como `x-api-key`. `AEMET_API_KEY` conserva su uso
  actual. `RENDER_API_KEY` es solo para el MCP de Render y no se usa desde la
  aplicación. Ningún valor secreto se escribe en archivos versionados ni en
  logs.
- **D-8-5 — Datos incompletos:** si falta una variable necesaria, no se
  inventan valores, no se usa el modelo antiguo y no se devuelve un mock. Se
  registra la causa y no se emite esa predicción.
- **D-8-6 — API:** se actualizan todos los endpoints vinculados a predicción.
  Las respuestas conservan su forma exterior cuando se indica en RF-6; los
  campos nuevos son aditivos.
- **D-8-7 — Gráfica:** la ventana son las últimas 30 fechas reales disponibles
  en `generacion` (`fechas_hist`). `pred_gwh` conserva una sola serie alineada
  con esas fechas; para un objetivo con varias emisiones se usa la de
  `fecha_emision` más reciente y, en empate, `emitida_en` más reciente. La
  lista de trazabilidad incluye todas las emisiones de esos objetivos.
- **D-8-8 — Planificador:** se mantienen las 03:00 y las 09:00 en
  `Europe/Madrid`. La tarea principal captura, actualiza reales y predice. El
  reintento de las 09:00 solo recaptura AEMET cuando la captura de las 03:00
  quedó incompleta. Si la recaptura permite completar o cambia la entrada, se
  vuelve a emitir para el mismo objetivo y `fecha_emision`; el upsert evita
  duplicados.
- **D-8-9 — Retención:** el archivo de previsiones y las emisiones de días
  distintos se conservan; no se purgan automáticamente. El backup de la BD y
  del modelo anteriores se guarda fuera de la ruta activa y no se borra
  automáticamente; su eliminación requiere autorización posterior.
- **D-8-10 — Modelo-comparison:** se conserva la respuesta exterior como una
  lista. Las siete filas actuales se mantienen identificadas como referencia
  histórica de 16 variables. Se añaden dos filas de 19 variables (Linear
  Regression de producción y LightGBM candidato) con los datos del acta actual.
  MAPE y accuracy son `null` para estas filas porque el acta no los proporciona.
- **D-8-11 — Predicción no disponible:** GET y POST responden HTTP 503 con un
  error estructurado cuando no hay una predicción válida para el objetivo. GET
  devuelve una fila ya guardada para mañana si existe; un POST fallido no la
  borra ni la sustituye. El frontend no se modifica en esta spec; el manejo
  visual de este estado queda para una spec posterior.
- **D-8-12 — Readiness:** `/health` comprueba que la BD y el modelo estén
  utilizables; `render.yaml` declara `healthCheckPath: /health`. Un backend que
  no puede cargar el artefacto de 19 variables no se anuncia como sano.

## 4. Requisitos funcionales

### RF-1 — Cargar y validar el modelo de producción

- **CA-1.1** El archivo instalado en backend y en el disco persistente de Render
  es `lr_eolica.joblib` y coincide en SHA-256 con el artefacto aprobado al
  preparar el release.
- **CA-1.2** El cargador valida las claves `modelo`, `scaler`, `features`,
  `familia` y `usa_scaler`; la familia es Linear Regression y la lista ordenada
  coincide exactamente con las 19 variables de esta spec.
- **CA-1.3** La predicción usa el escalador solo cuando `usa_scaler` lo
  indica, con el mismo orden que `features`. No se completa una columna
  ausente con cero ni con otro valor por defecto.
- **CA-1.4** Si el artefacto no se puede cargar o no coincide con el contrato,
  el backend queda no preparado, `GET /health` responde HTTP 503 y no usa un
  fallback de 16 variables ni una predicción sintética. `render.yaml` declara
  `/health` como health check del servicio.
- **CA-1.5** No se modifica el modelo, su familia, el entrenamiento ni el
  artefacto bajo `src/`.

### RF-2 — Sustituir la base inicial y crear el esquema canónico

- **CA-2.1** `backend/data/ree_generacion.db` se actualiza desde una copia
  consistente de `src/data/ree_generacion.db`, creada con la API de backup de
  SQLite para incluir cualquier transacción confirmada en WAL. La fuente no se
  modifica.
- **CA-2.2** El cambio de Render se realiza como mantenimiento explícito:
  detener temporalmente los escritores (API y scheduler), crear una copia
  SQLite recuperable de la BD y del modelo activos, validar el respaldo y
  conservarlo fuera de las rutas activas. El reemplazo se instala desde un
  archivo temporal en el mismo volumen y se activa atómicamente; no se ejecuta
  en cada arranque. Los respaldos no se borran automáticamente.
- **CA-2.3** La BD activa contiene las observaciones y las tablas
  `prediccion_diaria` y `prediccion_propia` de la instantánea de `src/data`.
  Tras la sustitución, los registros de la instantánea son el estado inicial
  activo; los exclusivos de Render quedan únicamente en el respaldo.
- **CA-2.4** `prediccion_diaria` conserva las columnas
  `fuente`, `elaborado`, `objetivo`, `ubicacion`, `uso`, `viento_ms`,
  `racha_ms`, `tmax`, `tmin`, `tmed`, `sol`, `tramos_cielo`, `orto`, `ocaso`,
  `uv_max`, `eolica_mwh`, `parte_json` y `capturado_en`, con clave
  `(fuente, elaborado, objetivo, ubicacion)`. Se conservan los tipos,
  restricciones e índices de la tabla fuente.
- **CA-2.5** `prediccion_propia` conserva las columnas `fecha_objetivo`,
  `fecha_emision`, `emitida_en`, `prediccion_mwh`, `modelo`, `n_variables`,
  `vector_entrada`, `origenes`, `real_mwh` y `error_mwh`, con clave
  `(fecha_objetivo, fecha_emision)`, tipos, restricciones e índices de la tabla
  fuente.
- **CA-2.6** `generacion` conserva `datetime`, `tecnologia`, `tipo`,
  `valor_MWh` y `porcentaje`, con clave `(datetime, tecnologia)`.
  `aemet_diario` conserva `fecha`, `indicativo`, `nombre`, `provincia`, `tmed`,
  `tmin`, `tmax`, `velmedia`, `racha`, `prec` y `sol`, con clave
  `(fecha, indicativo)`. Ambas conservan los tipos, restricciones e índices
  fuente. Las tablas de observación no se usan para guardar previsiones ni
  predicciones.
- **CA-2.7** El inicializador de backend prepara solo los esquemas canónicos y
  las tablas operativas necesarias. Puede mantener `captura_estado` para el
  estado/reintento de capturas; no vuelve a crear ni consultar
  `prediccion_aemet`, `predictions` o `aemet_daily`.
- **CA-2.8** La migración verifica `PRAGMA integrity_check`, tablas, columnas,
  recuentos y claves antes de activar la BD. Registra el SHA-256, esquema y
  recuentos de la instantánea preparada y comprueba que la copia de Render
  coincide con ese manifiesto; no usa como constantes los recuentos de contexto
  de esta spec. Ante un fallo, conserva/restaura el respaldo y no deja una BD
  parcial como activa.

### RF-3 — Captura programada de observaciones y previsiones

- **CA-3.1** La captura de previsión AEMET reutiliza la lógica existente de
  partes diario y horario, catálogo de 12 ubicaciones, elaboración declarada,
  reintento ante `429` y archivo idempotente; guarda `fuente='aemet'` en
  `prediccion_diaria`.
- **CA-3.2** La captura REE utiliza el indicador ESIOS **1777**, previsión
  eólica peninsular D+1 en MWh. Guarda `fuente='ree'`, `ubicacion='peninsula'`,
  objetivo y sello `values_updated_at` declarado por ESIOS como `elaborado`;
  nunca inventa un sello ausente. La captura en vivo archiva el D+1 y no
  reconstruye el histórico en cada ejecución. La solicitud usa
  `x-api-key: REE_API_KEY`.
- **CA-3.3** La recaptura de una misma elaboración no duplica registros; una
  elaboración distinta se añade sin borrar las anteriores. No se eliminan
  previsiones porque ya exista observación.
- **CA-3.4** La descarga de observaciones AEMET diaria cubre las seis estaciones
  eólicas (`4589X`, `8175`, `3013`, `6001`, `9299X`, `9031C`) y las cinco
  solares (`3469A`, `4452`, `7228`, `5783`, `9434`) usadas por el pipeline.
  Deduplica por indicativo: no incluye el indicativo inválido `9299` ni cuenta
  dos veces `9299X`. El backfill de 35 días usa el mismo catálogo y solo pide
  las fechas/estaciones que falten.
- **CA-3.5** La descarga y escritura AEMET conserva los campos necesarios para
  viento, racha, temperatura e insolación. Las unidades se normalizan igual que
  en `src`: el viento de previsión AEMET se convierte de km/h a m/s; no se
  reinterpreta la unidad de la observación histórica.
- **CA-3.6** La actualización de generación REE comprueba huecos internos del
  periodo reciente, no solo la fecha máxima global. Las filas existentes de
  observación no se sustituyen silenciosamente. Para decidir si el último día
  es completo se usa la regla vigente: comparar con la mediana de los siete
  días anteriores, exigir al menos cinco valores de entorno y descartar el día
  si su generación eólica es menor al 60 % de esa mediana.
- **CA-3.7** A las 03:00 `Europe/Madrid`, el flujo ejecuta, en orden:
  capturas AEMET y REE; descarga de observaciones REE y AEMET; actualización de
  reales pendientes; construcción del vector y emisión/guardado de la
  predicción de mañana.
- **CA-3.8** A las 09:00 se conserva el reintento AEMET. Si el flujo de las
  03:00 no pudo predecir o el reintento aporta datos que cambian la entrada, se
  vuelve a construir y guardar el mismo objetivo con la clave idempotente del
  mismo día de emisión.
- **CA-3.9** Un fallo de captura queda visible en logs y no se presenta como
  éxito silencioso. No impide intentar las otras descargas ni reconciliar
  observaciones ya disponibles. Tras completar los intentos, el builder usa
  solo los datos archivados; predice si y solo si las 19 entradas son válidas,
  e informa las fuentes/variables que impidieron predecir.

### RF-4 — Construir el vector de 19 variables y declarar su origen

- **CA-4.1** El backend construye exactamente las 19 variables y en el orden
  del artefacto. El código que implementa la lógica en `backend/` conserva
  paridad funcional con las reglas actuales de `src/pipeline/prevision.py`,
  `src/pipeline/forecast.py` y `src/pipeline/prevision_db.py`, sin importar
  dichos módulos en Render.
- **CA-4.2** `mes`, `dia_semana` y `dia_año` corresponden al objetivo en fecha
  peninsular. `velmedia` y `racha` del objetivo son la media de los valores
  no nulos y válidos disponibles en las siete ubicaciones AEMET de uso eólico;
  no se exige que las siete hayan respondido. Para cada día y ubicación se
  elige la elaboración más reciente no posterior a `min(objetivo, hoy)`. Si
  ninguna ubicación aporta una variable, esta queda no disponible.
- **CA-4.3** Las ventanas `vel_ma3/7/14` y `racha_ma3/7/14` se resuelven día a
  día sobre fechas naturales: observación de las seis estaciones eólicas
  únicas si el día ya es observable; en otro caso, previsión AEMET elegible de
  las ubicaciones eólicas. Se agregan solo valores disponibles, sin duplicar
  `9299X`. La previsión de cada día `d` debe tener elaboración no posterior a
  `min(d, hoy)`. Si participan ambas fuentes el origen es `mixta` y se conserva
  el desglose de días. Si falta un día en ambas fuentes, la ventana no está
  disponible: no se acorta, desplaza ni interpola.
- **CA-4.4** `sol_lag1` y `tmed_lag1` son las medias nacionales de las cinco
  estaciones solares del día natural anterior. Usan observación si existe; si
  falta, usan la previsión AEMET elegible de las mismas ubicaciones, con
  elaboración no posterior a `min(día_anterior, hoy)`. El `sol` derivado del
  estado del cielo se marca `estimada`; `tmed` prevista se marca `prevision`.
- **CA-4.5** Los retardos eólicos y `eolica_ma7` se anclan en la última
  generación diaria completa, determinada con CA-3.6. Los retardos 1/2/3/7
  apuntan a los días naturales relativos a esa ancla. Donde falta observación,
  se usa la previsión REE del mismo día con elaboración no posterior a
  `min(día, hoy)`. `eolica_ma7` resuelve sus siete días uno por uno, con
  observación prioritaria y previsión en los huecos. Se conserva
  `observacion`, `prevision` o `mixta` y el desglose.
- **CA-4.6** `eolica_prev` representa la previsión REE de generación eólica del
  objetivo, con ubicación `peninsula`, elaboración declarada no posterior a
  `min(objetivo - 1 día, hoy)` y valor entre 0 y 720.000 MWh. De existir varias,
  gana la elaboración más reciente y, en empate, la captura más reciente. Si
  no existe, se estima con la media de previsiones reales válidas de los siete
  días naturales anteriores, terminando en `min(objetivo - 1 día, hoy)`. No se
  usan rellenos como entradas de esa media. El origen es `prevision` o
  `estimada`, respectivamente; sin valores reales anteriores no hay
  predicción.
- **CA-4.7** Cada valor del vector queda emparejado con su origen
  (`observacion`, `prevision`, `mixta` o `estimada`). Un valor ausente conserva
  origen ausente; si falta una de las 19 variables, no se llama al modelo.
- **CA-4.8** La selección de previsión evita fuga temporal: ninguna elaboración
  posterior al momento de emisión puede intervenir. Las fechas objetivo son
  días naturales de `Europe/Madrid`. `generacion.datetime` conserva su
  timestamp ISO UTC; antes de agrupar o unirlo con AEMET se convierte a
  `Europe/Madrid` y se extrae la fecha local. No se usa la fecha UTC como día
  peninsular.

### RF-5 — Guardar la predicción y reconciliar su valor real

- **CA-5.1** La predicción programada guarda una fila en `prediccion_propia`
  con objetivo, día e instante de emisión, valor en MWh, familia, 19 variables,
  vector JSON y orígenes JSON.
- **CA-5.2** Repetir el cálculo para el mismo objetivo y día de emisión hace
  upsert sobre `(fecha_objetivo, fecha_emision)`: no duplica y conserva un real
  ya conocido, recalculando su error si cambia la predicción.
- **CA-5.3** Cuando REE publica la generación real completa del objetivo
  (suma diaria de la tecnología `Eólica`, fecha natural `Europe/Madrid` y
  validada con CA-3.6), se actualizan `real_mwh` y
  `error_mwh = real_mwh - prediccion_mwh` para todas las emisiones de ese
  objetivo. La predicción original no se sustituye por el valor real. Una
  previsión REE nunca se usa como real.
- **CA-5.4** La ausencia de real deja `real_mwh` y `error_mwh` nulos; no se
  imputa. Una observación de REE todavía incompleta no cierra la predicción.

### RF-6 — Exponer los datos de producción por la API

- **CA-6.1** `GET /api/prediction` y `POST /api/prediction/refresh` usan el
  mismo servicio de construcción y persistencia. GET devuelve la fila ya
  guardada para mañana solo si `modelo` es Linear Regression,
  `n_variables=19` y `vector_entrada`/`origenes` satisfacen el contrato; si no,
  calcula y guarda. POST fuerza un recálculo y hace upsert del mismo día. Ambos
  conservan los campos actuales (`fecha`, `prediccionMWh`, `modelo`, `features`)
  y añaden `n_variables`, `vector_entrada`, `origenes`, `fecha_emision` y
  `emitida_en`. Las dos claves JSON deben ser exactamente las 19 del artefacto,
  los valores deben ser finitos y los orígenes pertenecer al vocabulario
  aprobado. `features.velmedia` y `features.racha` conservan su significado.
- **CA-6.2** `GET /api/forecast` conserva `fecha`, `velmedia`, `racha` y
  `estaciones`, pero los deriva del archivo AEMET elegible que usa el vector,
  no de una segunda consulta en vivo que pudiera discrepar. Añade `ree` con
  `fecha`, `eolica_mwh`, `elaborado`, `origen` y `dias_media` (si es estimada).
  Si falta una fuente, su subobjeto es `null` y `avisos` explica la causa.
- **CA-6.3** `GET /api/feature-importance` conserva su formato de lista y
  devuelve las 19 variables del modelo cargado; no mezcla coeficientes del
  modelo nuevo con una lista de variables antigua. Mantiene el cálculo actual
  `abs(coeficiente) / sum(abs(coeficientes))` y el orden descendente.
- **CA-6.4** `GET /api/model-comparison` devuelve una lista. Conserva las siete
  filas históricas y sus campos actuales, añadiendo `n_variables=16` y
  `historico=true`; sus nombres actuales no se cambian. Añade dos filas llamadas
  `Linear Regression (19 variables)` y `LightGBM (19 variables)`, con
  `n_variables=19`, `historico=false`, `rol` (`produccion` o
  `candidata_rechazada`), `n`, `rmse`, `mae`, `r2`, `decision`, `motivo` y
  `folds` (`año`, `rmse`, `mae`, `r2`). La fila LR toma `metricas_globales.base`
  y `folds[].base` del acta; la fila LightGBM toma `metricas_globales.variante`
  y `folds[].variante`. La fila LR declara `decision="vigente"`; LightGBM
  declara `decision="rechazado"` y usa el motivo del acta (mejora estricta en
  1 de 4 folds), aunque su RMSE global sea menor. Estos datos provienen de una
  copia versionada en
  `backend/modelos/familia_como_modelo.json` del acta
  `src/data/modelos/familia_como_modelo.json`; Render no lee `src/`. En las
  filas nuevas `mape` y `accuracy` son `null` (no están en el acta), nunca cero
  ni valores heredados. `rmse` y `mae` se expresan en MWh; `r2` no tiene unidad.
  `METRICS_PATH` apunta a esa copia y el handler
  transforma el acta a la lista definida aquí, no devuelve el objeto JSON crudo.
- **CA-6.5** `GET /api/prediction-chart` conserva las claves actuales y los
  últimos 30 días reales disponibles de `generacion`. `pred_gwh` tiene la
  misma longitud/orden que `fechas_hist`; por fecha objetivo selecciona la
  última emisión. Además devuelve `predicciones_propias` con todas las
  emisiones cuyos objetivos están en `fechas_hist`, ordenadas por
  `fecha_objetivo`, `fecha_emision` y `emitida_en`; cada fila incluye las
  columnas canónicas de la tabla (valores en MWh). `pred_gwh` conserva GWh y
  para una fecha objetivo selecciona la mayor `fecha_emision`, desempata por
  `emitida_en`. El endpoint es de lectura: no consulta fuentes ni ejecuta el
  modelo. `manana` conserva su forma y toma la fila del objetivo siguiente de
  `prediccion_propia`, añadiendo vector, orígenes y metadatos de emisión.
- **CA-6.6** En `/api/prediction-chart`, las unidades existentes se mantienen;
  los campos que reflejan directamente la tabla conservan MWh y se identifican
  explícitamente como tales. Sin predicción disponible, los valores son `null`
  (`manana.pred_gwh=null`, `manana.estado="no_disponible"`) y `avisos` explica
  la causa; `manana.es_fallback` se conserva como `false`, porque no se usa
  ningún fallback. No se devuelve 150.000 MWh ni el último real como predicción.
- **CA-6.7** Si `/api/prediction` no tiene una predicción válida guardada para
  mañana y no puede construirla, o si `/api/prediction/refresh` no puede
  construir una nueva, responde HTTP 503 con
  `{"detail": "...", "fecha": "...", "faltan": [...], "avisos": [...]}`.
  El POST fallido no borra una fila previa. No se usan el fallback histórico
  ni los mocks actuales. El mismo contrato aplica en pruebas sin claves o sin
  red.
- **CA-6.8** `/api/historical`, `/api/energy-mix` y los demás endpoints no
  relacionados con predicción conservan su contrato, aunque lean los datos de
  observación de la BD sustituida.

### RF-7 — Configurar los discos y las credenciales de Render

- **CA-7.1** `DB_PATH` señala explícitamente el archivo en el disco persistente
  montado en `/app/data` (`/app/data/ree_generacion.db`); `MODEL_PATH` señala
  `/app/modelos/lr_eolica.joblib` y `METRICS_PATH` señala
  `/app/modelos/familia_como_modelo.json`, ambos en el disco montado en
  `/app/modelos`.
- **CA-7.2** El release copia el modelo aprobado y el acta vigente al disco
  persistente de modelos, y registra/verifica la huella del `.joblib` y la
  coherencia de sus 19 features con el acta. Un `.joblib` antiguo en el volumen
  no debe ocultar el artefacto aprobado.
- **CA-7.3** `AEMET_API_KEY` y `REE_API_KEY` se declaran como variables externas
  (`sync: false`); no se escriben sus valores en `render.yaml`, logs, respuestas
  API ni archivos de prueba.
- **CA-7.4** La actualización de la BD y del modelo en los volúmenes es un paso
  explícito de release: pausar el servicio, respaldar BD y modelo, instalar
  copias temporales, validar integridad/hash y activar atómicamente. Si falla
  cualquier validación, se restaura el respaldo antes de reanudar el servicio.
  Los respaldos se guardan fuera de las rutas activas y se conservan hasta una
  autorización explícita de borrado. No se sustituye la BD ni el modelo en el
  arranque normal de FastAPI.
- **CA-7.5** `render.yaml` declara `healthCheckPath: /health`. GET `/health`
  responde 200 (`{"status":"ok"}`) solo si la BD canónica está accesible y el
  artefacto cargado cumple el contrato de 19 variables; de lo contrario responde
  503 (`{"status":"error","detail":"..."}`).

## 5. Requisitos no funcionales

- **RNF-1 — Alcance estricto:** la implementación toca `backend/` y
  `render.yaml`; no modifica `src/` ni frontend.
- **RNF-2 — Fidelidad:** para el mismo vector válido, el artefacto de backend
  reproduce la predicción del `.joblib` actual dentro de tolerancia numérica.
  No se reentrena ni cambia de familia.
- **RNF-3 — Honestidad:** no hay interpolación, mocks ni valores por defecto en
  las 19 entradas. Toda estimación queda marcada y trazable.
- **RNF-4 — Persistencia segura:** la instantánea se valida antes de activarla;
  hay backup recuperable y rollback probado. No se reemplaza desde `src` en
  cada arranque.
- **RNF-5 — Idempotencia:** recapturas y reintentos no duplican previsiones ni
  emisiones de un mismo objetivo y día.
- **RNF-6 — Determinismo temporal:** la lógica recibe una fecha de referencia
  explícita y usa `Europe/Madrid` para objetivo y emisión; las pruebas no
  dependen del reloj ni de llamadas reales a las APIs.
- **RNF-7 — Seguridad de credenciales:** secretos solo en el entorno de Render;
  no se registra la cabecera de autenticación.
- **RNF-8 — Dependencias:** no se añaden paquetes; se usan las dependencias
  fijadas en `backend/requirements.txt`.
- **RNF-9 — Contrato:** se mantienen las claves actuales de API y se añaden
  campos, sin requerir cambios en frontend en esta spec.
- **RNF-10 — Tests primero:** las pruebas de regresión y de la nueva lógica se
  escriben antes de implementar; no se avanza con tests en rojo.
- **RNF-11 — Error API honesto:** el 503 no incluye una predicción nula
  convertida a cero ni un valor de relleno. El frontend actual queda intacto;
  mejorar su presentación del estado no disponible es trabajo posterior.

## 6. Casos límite

- **CE-1 — No hay previsión REE D+1:** se usa el relleno de siete previsiones
  reales anteriores con origen `estimada`; si no hay ninguna, no se emite.
- **CE-2 — ESIOS no autentica o falla:** se registra la incidencia. No se usa
  una previsión vacía, el endpoint 541 ni una clave distinta de `REE_API_KEY`.
- **CE-3 — AEMET parcial:** se pueden usar ubicaciones disponibles si el
  vector completo sigue siendo calculable; una variable/ventana obligatoria
  ausente detiene la predicción con su nombre y causa.
- **CE-4 — Día de generación REE incompleto:** se descarta como ancla y como
  real hasta que la observación esté completa; no se rellena la tabla
  `generacion`.
- **CE-5 — Falta un día en una ventana móvil:** se consulta la otra fuente según
  la regla de origen; si ambas faltan, la ventana queda no disponible. No se
  acorta ni se desplaza.
- **CE-6 — Reintento de las 09:00:** una nueva emisión del mismo objetivo en el
  mismo día actualiza la fila; no crea una segunda fila.
- **CE-7 — Artefacto incompatible:** si falta una columna, cambia el orden o
  falla la carga, el servicio no predice ni vuelve al modelo antiguo.
- **CE-8 — Reemplazo de BD fallido:** la instantánea no se activa; se conserva
  la BD anterior o se restaura desde su respaldo.
- **CE-9 — Datos exclusivos de Render:** no pasan a la BD activa; permanecen
  en el backup fechado y recuperable acordado en D-8-2/D-8-3.
- **CE-10 — Cambio de día o DST:** `fecha_objetivo`/`fecha_emision` usan el día
  local peninsular, sin desplazamiento de un día por extraer la fecha UTC.
- **CE-11 — Métricas que faltan:** las filas LR-19/LightGBM-19 no tienen MAPE ni
  accuracy en el acta; la API devuelve `null`, no los copia de las métricas
  históricas de 16 variables ni los calcula con otra muestra.
- **CE-12 — El frontend recibe HTTP 503:** los endpoints mantienen el error
  estructurado. No se adapta el frontend en esta spec; su representación visual
  queda pendiente y no se reemplaza el error por una predicción falsa.

## 7. Criterios de finalización

1. El modelo del backend y el del volumen Render coinciden con el artefacto
   autorizado, validan las mismas 19 variables ordenadas y reproducen su salida
   para entradas fijas.
2. La BD local de backend y la BD activa de Render corresponden a la
   instantánea de `src/data` aplicada en el release; las comprobaciones de
   integridad y esquema pasan.
3. Existe y se puede restaurar el backup fechado de la BD y del modelo Render
   anteriores. Los registros exclusivos anteriores no se mezclan con la
   instantánea activa.
4. Captura AEMET/REE y descarga de observaciones son idempotentes, dejan
   incidencias visibles y cubren los campos/estaciones necesarios.
5. La tarea diaria crea o actualiza la fila de `prediccion_propia` con 19
   valores y sus orígenes; el reintento no duplica; `real_mwh`/`error_mwh` se
   completan solo al llegar la observación válida.
6. La falta de un feature obligatorio detiene la predicción sin usar fallbacks
   silenciosos.
7. Los endpoints incluidos en RF-6 devuelven el modelo/datos nuevos y
   conservan el contrato existente acordado; `/api/model-comparison` identifica
   por separado las filas históricas de 16 variables y las dos filas actuales
   de 19 variables.
8. Los tests Python del backend, `node --test` y las comprobaciones manuales
   de `/health`, `/api/prediction`, `/api/forecast` y `/api/prediction-chart`
   pasan.
9. No hay cambios en `src/` ni frontend; no se han añadido dependencias ni se
   ha reentrenado el modelo.

## 8. Fuera de alcance

- Modificar o ejecutar `src/notebooks/main.ipynb` o `src/pipeline/`.
- Cambiar el frontend, sus tipos o el modo de renderizado de las gráficas.
- Reentrenar, volver a evaluar o cambiar la familia/modelo/variables.
- Sincronizar cambios desde Render de vuelta a `src/data`.
- Mantener en la BD activa las filas exclusivas de la BD Render anterior.
- Reemplazar el artefacto raíz `modelos/lr_eolica.joblib` o
  `src/model/production/lr_eolica.joblib`.
- Cambiar el `ModelComparisonChart` estático del frontend; aunque la API se
  actualice, esa gráfica seguirá con sus datos actuales hasta una futura spec
  de frontend.
- Ejecutar el despliegue o reemplazo de datos en Render durante la redacción de
  esta spec; la operación real requiere seguir el procedimiento de backup,
  validación y rollback de esta spec.
