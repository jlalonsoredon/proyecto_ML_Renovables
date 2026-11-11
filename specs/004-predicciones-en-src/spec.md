# Spec 004 — Previsión de fuentes y predicción propia en `src/`

## 1. Contexto y objetivo

El modelo predice la generación eólica diaria peninsular de mañana, pero las dos fuentes
oficiales publican con retraso medido: **REE ~2 días** (y los 1–2 últimos llegan
**incompletos**: 34–39 % de su entorno, medido el 2026-11-02) y **AEMET ~4 días**. Hoy:

- La spec 002 incorporó `sol_lag1`/`tmed_lag1` (aceptadas en walk-forward, modelo de 18
  variables, RMSE 39.387,9 MWh · R² 0,8046 en test).
- La spec 003 montó la **lógica** del archivo de previsiones (`src/pipeline/forecast.py`,
  258 tests en verde) pero dejó la **captura en el backend con su planificador**. Como el
  backend no se ha desplegado con ese cambio, **no existe ninguna tabla de previsiones**
  en ninguna base de datos (verificado el 2026-11-07: solo `generacion` y
  `aemet_diario`).
- La frescura de generación (RF-12 de la spec 003) ya ancla los retardos en la última
  generación **completa**, pero solo en el notebook.

**Decisión del usuario (2026-11-07):** todos los cambios se hacen **únicamente en
`src/`** (`src/notebooks/`, `src/pipeline/`, `src/data/`). Backend y frontend **no se
tocan** hasta que el usuario lo indique expresamente (constitución, principio 1). Esto
**sustituye, para esta fase, la decisión de la spec 003 de capturar en el backend**: la
captura pasa al notebook y la tabla vive en `src/data/ree_generacion.db`. Cuando llegue
la fase de backend se decidirá la sincronización (D-4-4).

**Objetivo:** que el análisis disponga cada día de (1) las previsiones vigentes de AEMET
y de REE archivadas en una tabla propia, (2) un registro de las predicciones que el
propio modelo emite, y (3) un feature engineering que, cuando la observación aún no ha
llegado, construya el vector de entrada con previsión **declarando el origen de cada
variable**.

**Lo que NO cambia respecto a las specs anteriores:**

- **No se interpola** y las tablas de observación (`generacion`, `aemet_diario`)
  jamás se rellenan con previsión. Desde D-4-8, una media móvil del vector de
  entrada puede completar sus días sin observación con previsión oficial: cada
  día conserva su origen y la variable se declara `mixta` con el desglose.
- Un valor estimado siempre se identifica como tal; un hueco nunca se oculta tras un
  valor por defecto.

## 2. Usuarios

- **U1 — Analista (autor del proyecto).** Quiere que el notebook, al ejecutarse, deje
  archivadas las previsiones del día y la predicción emitida, y que sepa decir con qué
  origen (observación o previsión) se construyó cada variable.
- **U2 — Evaluador técnico (tutor, revisor).** Quiere auditar: qué previsión había cada
  día, qué predijo el modelo, con qué entrada, y qué error tuvo cuando llegó el dato
  real.
- **U3 — Operación del servicio.** Fuera de alcance en esta fase: no hay servicio en
  `src/`.
- **U4 — Visitante de la web.** *No es usuario de esta versión*: nada nuevo en la API ni
  en la interfaz.

## 3. Historias de usuario

- **HU-1.** Como U1, quiero que al ejecutar el notebook se guarden la previsión AEMET
  vigente y la previsión de generación de REE, para cubrir los días en que la observación
  aún no ha llegado.
- **HU-2.** Como U1, quiero que cada ejecución guarde la predicción que el modelo emite
  para mañana, con su vector de entrada y el origen de cada variable, para poder medir
  después su error real.
- **HU-3.** Como U1, quiero que el vector de mañana use previsión **solo donde falta
  observación**, declarándolo variable a variable, sin tocar las tablas de observación.
- **HU-4.** Como U2, quiero que repetir la ejecución el mismo día no duplique registros y
  que cada previsión recuerde su elaboración declarada, para reconstruir qué se sabía en
  un momento dado.

## 4. Requisitos funcionales

### RF-1 — Tabla de previsiones de las fuentes (`prediccion_diaria`)

Una tabla en `src/data/ree_generacion.db` que archive cada día la previsión vigente de
**AEMET** (12 ubicaciones: viento, racha, temperatura y sol estimado) y de **REE**
(previsión de generación eólica peninsular), con la elaboración declarada por la fuente
como parte de su identidad.

- **CA-1.1** La identidad es `(fuente, elaborado, objetivo, ubicacion)`;
  `fuente ∈ {aemet, ree}`. Para REE la ubicación es `peninsula` y el valor es la
  generación prevista en MWh (`eolica_mwh`).
- **CA-1.2** Cada registro conserva el parte original (`parte_json`) y la fecha y hora
  real de captura (`capturado_en`), distinta de la elaboración declarada. En el relleno
  histórico el parte se reduce al valor del día y su procedencia (D-4-7); en vivo se
  conserva la respuesta completa.
- **CA-1.3** Recapturar la misma elaboración no duplica; una elaboración nueva se añade
  y nunca pisa la anterior. No hay `DELETE`: el archivo crece hacia delante. El relleno
  histórico (RF-7) añade días pasados sin contradecir esta regla: cada uno lleva su propia
  elaboración derivada y nunca reescribe una captura en vivo.
- **CA-1.4** Una fila sin elaboración declarada se guarda marcada como sin elaboración y
  **no es elegible** para reconstruir ningún día.
- **CA-1.5** El esquema de la parte AEMET replica el de `prediccion_aemet` de la spec 003
  (mismas columnas derivadas: `viento_ms`, `racha_ms`, `tmed`, `sol`, `tramos_cielo`,
  `orto`, `ocaso`, `uv_max`), para reutilizar `src/pipeline/forecast.py` sin tocarla.

### RF-2 — Tabla de predicciones propias (`prediccion_propia`)

Una tabla que registre cada predicción que el modelo emite al final del notebook.

- **CA-2.1** Una fila por `(fecha_objetivo, emitida_en)` con: `prediccion_mwh`, `modelo`
  (nombre y número de variables), `vector_entrada` (JSON con las variables usadas) y
  `origenes` (JSON variable → `observacion` | `prevision` | `mixta` | `estimada`).
- **CA-2.2** Repetir la ejecución el mismo día **sustituye** la predicción del mismo
  objetivo emitida ese día (es la misma información recalculada); nunca duplica.
- **CA-2.3** Cuando REE publica el dato real del día objetivo, la columna `real_mwh` se
  actualiza y se calcula `error_mwh`; `prediccion_mwh` nunca se sobrescribe.
- **CA-2.4** Debe poder listarse la serie de predicciones con su error para evaluar el
  modelo en producción (MAE de los últimos N días).

### RF-3 — Captura diaria desde el notebook

Celdas nuevas en el bloque de descarga del `main.ipynb`, antes del feature engineering,
que archivan las previsiones vigentes.

- **CA-3.1** La captura AEMET reutiliza la lógica de la spec 003 (catálogo de 12
  ubicaciones, descarga en dos pasos, pausa y reintento ante 429, `forecast_rows`),
  escribiendo en `prediccion_diaria` con `fuente='aemet'`.
- **CA-3.2** La captura REE archiva la previsión **D+1** de generación eólica peninsular
  del indicador **ESIOS 1777** (`geo_ids[]=8741`, energía en MWh), escribiendo con
  `fuente='ree'`, `ubicacion='peninsula'` y `elaborado = values_updated_at` de la
  respuesta (D-4-1).
- **CA-3.3** Tolerante a fallos: una ubicación o una fuente que falla queda registrada
  como incidencia y no aborta el notebook; si **ambas** fallan por completo, el aviso es
  visible, no un éxito silencioso.
- **CA-3.4** Idempotente: ejecutar el notebook dos veces el mismo día no duplica filas.
- **CA-3.5** La captura imprime su resumen: filas guardadas, horizonte obtenido, días
  pendientes y errores con su causa.
- **CA-3.6** El archivo se reconstruye desde `2022-01-01` (primer día de `generacion` en
  hora peninsular) hasta hoy, en bloques anuales. Un bloque solo se archiva si
  `values_updated_at` es el día anterior a su último día; si no cuadra, se informa y no se
  rellena. Cada día reconstruido se etiqueta `elaborado = objetivo − 1` y se declara
  `reconstruido` (D-4-6, D-4-7). El día de mañana lo aporta la captura en vivo.

### RF-4 — Feature engineering con origen declarado

El vector de mañana se construye con observación donde existe y con previsión donde
falta, declarando el origen de cada variable.

- **CA-4.1** `velmedia` y `racha` salen de la previsión del día objetivo.
  `vel_ma3/7/14` y `racha_ma3/7/14` se calculan día a día sobre la ventana que
  termina en el objetivo: observación AEMET si ya existe (nunca posterior a
  `hoy`); si no, previsión elegida con la regla única de la spec 003 (elaboración
  declarada ≤ objetivo, la más reciente). El origen es `observacion` o
  `prevision` si todos los días comparten fuente y `mixta` si participan ambas;
  en este último caso se guardan `dias_observados` y `dias_previstos`. Si un día
  no está en ninguna fuente, la ventana queda `NO_DISPONIBLE`: no se interpola,
  no se acorta y no se desplaza. La predicción no usa el antiguo respaldo de una
  ventana observada desfasada (D-4-8).
- **CA-4.2** `sol_lag1`, `tmed_lag1`: observación si existe el día anterior; si no,
  estimación de previsión, marcada `estimada` (el `sol` previsto ya es un proxy de horas
  de luz por estado del cielo).
- **CA-4.3** `eolica_lag1/2/3/7`, `eolica_ma7`: última generación **publicada completa**
  (RF-12 de la spec 003, ya hecho). Si faltan días dentro de la ventana y REE publica
  previsión para ellos, se completan con la previsión de REE, nunca con interpolación.
  Desde D-4-8 la media `eolica_ma7` usa la misma regla por día y declara `mixta`
  si combina observación y previsión. Activo desde D-4-3: la previsión de REE tiene
  MAE 13 194 MWh (Anexo B), mejor que el modelo (29 950 MWh en test).
- **CA-4.4** El diccionario `origenes` se imprime en la ejecución y se guarda con la
  predicción (CA-2.1): qué variables venían de observación, previsión o mezcla. Las
  ventanas `mixta` imprimen el desglose `N obs + M prev`.
- **CA-4.5** Las variables de calendario (`mes`, `dia_semana`, `dia_año`) son siempre
  `observacion`: pertenecen al día objetivo, no se estiman.

### RF-5 — Integridad de las tablas de observación

- **CA-5.1** `generacion` y `aemet_diario` no reciben jamás una fila sintética: ni
  previsión, ni interpolación, ni el dato real reconstruido.
- **CA-5.2** El entrenamiento sigue alimentándose **solo** de observación; la previsión
  entra únicamente en el vector de predicción de mañana y en la comparación de la spec
  003.

### RF-6 — Trazabilidad

- **CA-6.1** Cada ejecución deja: resumen de captura (CA-3.5), fila en
  `prediccion_propia` (CA-2.1) y recuento de variables por origen impreso.
- **CA-6.2** `MEMORY.md` recoge la decisión y las métricas al cerrar la fase.

### RF-7 — Reconstrucción del histórico de previsiones

El archivo no solo crece hacia delante: al incorporarse la credencial de ESIOS se
reconstruye la previsión de REE desde el primer día de observación.

- **CA-7.1** Rango `2022-01-01 → hoy`, en días naturales peninsulares. El día de mañana
  lo aporta la captura en vivo, para no archivar el mismo día con dos etiquetas.
- **CA-7.2** Un bloque se acepta solo si su sello `values_updated_at` es el día anterior a
  su último día; si no, se descarta y se informa. No se adivina la elaboración.
- **CA-7.3** Un día ya cubierto por cualquier elaboración no se reconstruye; reejecutar no
  duplica ni vuelve a pedir un año completo.
- **CA-7.4** El parte reconstruido se reduce al valor del día, la ventana y el sello, y se
  marca `reconstruido: true` (D-4-7). El día natural se lee siempre de `datetime` (hora
  local), nunca de `datetime_utc`.

## 5. Requisitos no funcionales

- **RNF-1 — Alcance `src/` estricto.** No se toca `backend/`, `frontend/`, `render.yaml`
  ni ninguna copia de producción del `.joblib`. La BD afectada es solo
  `src/data/ree_generacion.db`, con copia previa obligatoria.
- **RNF-2 — Honestidad.** Sin interpolación ni valores por defecto que oculten
  huecos. La mezcla solo se permite dentro de una media móvil del vector de
  entrada, día a día y con origen `mixta` y desglose; las tablas de observación
  permanecen puras. Lo estimado va siempre marcado.
- **RNF-3 — Test primero.** La lógica nueva (esquema, upsert, elección de origen,
  actualización de `real_mwh`) vive en `src/pipeline/` con sus tests; la puerta
  `node --test "src/pipeline/tests/*.test.mjs"` debe quedar en verde al cerrar cada
  tarea.
- **RNF-4 — Cambio mínimo en el notebook.** Celdas nuevas insertadas, sin reordenar ni
  renombrar las etapas existentes.
- **RNF-5 — Sin dependencias nuevas** (la captura usa `requests`, ya presente en el
  proyecto).
- **RNF-6 — Español** en comentarios, mensajes y documentación.
- **RNF-7 — Respeto a las fuentes:** pausas entre peticiones y reintento con espera ante
  429 (ya medido en AEMET).

## 6. Casos límite

- **CE-1.** Primer día del archivo: `2022-01-01`, que corresponde a `2021-12-31T23:00:00Z`.
  El relleno reconstruye hacia atrás desde la primera observación y la captura en vivo
  cubre D+1; ningún día anterior se inventa.
- **CE-2.** REE no publica previsión de generación para mañana: las variables de
  generación se quedan con la última publicada completa (RF-12) y el origen se declara.
- **CE-3.** El parte diario de AEMET llega sin racha (situación ya observada): respaldo
  del parte horario; si tampoco la trae, la racha queda no disponible y sus medias no se
  construyen.
- **CE-4.** Ventana con observación a medias: cada día toma observación si existe
  y previsión si no. La variable queda `mixta`, con `dias_observados` y
  `dias_previstos`; si falta un día en ambas fuentes queda no disponible.
- **CE-5.** Previsión de REE para un día que ya tiene generación publicada: se archiva
  igualmente (sirve para calibrar su error), pero el origen usado es `observacion`.
- **CE-6.** El modelo emite predicción para un objetivo que ya tiene predicción ese día:
  se sustituye (CA-2.2), conservando el histórico de emisiones anteriores.
- **CE-7.** `real_mwh` llega días tarde: se actualiza cuando aparezca, sin límite de
  tiempo; la ausencia de dato real no se rellena.
- **CE-8.** Dos elaboraciones del mismo día (la fuente publica dos partes): ambas se
  archivan; la elección usa la más reciente elegible.

## 7. Fuera de alcance

- Cualquier cambio en `backend/` o `frontend/` (incluidos el scheduler, `init_db` y las
  copias del modelo de producción).
- Exponer nada nuevo en la API o en la web.
- Reentrenar el modelo de producción ni tocar `FEATURE_COLS`.
- Interpolación de huecos de ningún tipo.
- Rellenar `generacion` o `aemet_diario` con previsión.

## 8. Criterios de finalización

1. Existen `prediccion_diaria` y `prediccion_propia` en `src/data/ree_generacion.db` y
   dos ejecuciones el mismo día no duplican registros.
2. La captura archiva el día en curso y el horizonte de las dos fuentes, con resumen e
   incidencias visibles.
3. Cada ejecución guarda la predicción emitida con su vector y el origen por variable.
4. El vector de mañana usa observación donde existe y previsión solo en los días
   que faltan; las ventanas completas declaran `observacion`, `prevision` o
   `mixta`, con el desglose por día en el último caso.
5. Las tablas de observación quedan intactas (verificado por recuento y huella).
6. `real_mwh` se actualiza cuando REE publica y el error es consultable.
7. Puerta `node --test` en verde con los tests nuevos; notebook completo ejecutado.
8. `MEMORY.md` recoge la decisión, las métricas y el estado del archivo.
9. El archivo de REE cubre `2022-01-01 → mañana` sin huecos, con los bloques
   reconstruidos verificados y la segunda ejecución sin filas nuevas.

## 9. Dudas abiertas

- **[RESUELTA] D-4-1 — Fuente de la previsión REE.** El indicador **ESIOS 1777**
  (`Previsión diaria D+1 eólica`, energía en MWh, `geo_ids[]=8741`) con cabecera
  `x-api-key` devuelve 200 desde 2020. El 541 no sirve (potencia cada 15 min, solo el día
  en curso); 1778 es intradiaria H+3; 10358 suma eólica y fotovoltaica; 1775 es demanda.
  Solo se archiva **D+1** en vivo; el histórico se reconstruye con RF-7.
- **[RESUELTA] D-4-2 — Una tabla o dos.** Tabla única `prediccion_diaria` con columna
  `fuente`: medido, las dos tablas ocupan lo mismo (1 836 KB) y duplicarían el código de
  lectura y escritura.
- **[RESUELTA] D-4-3 — Previsión REE en los lags.** Sí, con `permitir_prev_gen=True`. La
  previsión de REE tiene MAE 13 194 MWh y RMSE 19 969 MWh (Anexo B), mejor que el modelo
  en test (29 950 / 39 703). La observación sigue teniendo prioridad y la previsión se
  marca `prevision`.
- **[RESUELTA] D-4-6 — ¿Se reconstruye el histórico?** Sí: `2022-01-01 → hoy` por bloques
  anuales verificados (RF-7, CA-3.6). La serie 1777 llega a 2019, pero 2019 tiene sello de
  carga en bloque y 2018 está vacía; el primer real de `generacion` es `2022-01-01`.
- **[RESUELTA] D-4-7 — Tamaño del parte reconstruido.** En el relleno, `parte_json` se
  reduce a valor, ventana, sello y `reconstruido: true` (~388 B de media frente a los
  ~50 KB de la respuesta completa); en vivo se conserva la respuesta entera.
- **[RESUELTA] D-4-8 — Ventana mixta con origen declarado (2026-11-11).** Se
  sustituye la exigencia de ventana íntegra de un solo origen por la resolución
  día a día: observación si existe y previsión oficial en los huecos. Una ventana
  con ambas fuentes se marca `mixta` y declara cuántos días aporta cada una;
  sigue prohibido interpolar, acortar la ventana o rellenar las tablas de
  observación. La regla se aplica también a `eolica_ma7`. Si una ventana no se
  puede completar, la predicción se detiene en vez de usar el respaldo
  desfasado. Comparación inicial en el Anexo C.
- **[NECESITA ACLARACIÓN] D-4-4 — ¿Sustituye esto a la captura del backend?** Se asume
  que sí hasta la fase backend (el scheduler de la spec 003 queda dormido); entonces se
  decidirá si el backend lee esta tabla o replica la captura.
- **[NECESITA ACLARACIÓN] D-4-5 — Retención.** ¿Se conservan todas las elaboraciones
  indefinidamente (como en la spec 003) o se purgan las que ya tienen observación?

## Anexo A — Evidencia medida

**Retraso de publicación** (medido en las specs anteriores):

| Fuente | Último dato | Consultado | Retraso |
|---|---|---|---|
| AEMET observación | 2026-10-27 | 2026-10-31 | 4 días |
| AEMET observación | 2026-10-28 | 2026-11-01 | 4 días |
| REE generación | 2026-10-30 (incompleto) | 2026-11-02 | 3 días |

**Días incompletos de REE** (medido el 2026-11-02): el último día publicado valía el
39 % de la mediana de los 7 anteriores y el penúltimo el 34 %; el último día completo
era 2026-10-28. `forecast.generation_lags` ya los señala y descarta.

**Campos confirmados:** `aemet_diario` tiene `tmed/tmin/tmax/velmedia/racha/prec/sol`
(`sol` = insolación en **horas**, no radiación; `prec` se ignora). El parte de previsión
de AEMET declara `elaborado` y no publica horas de insolación ni `rachaMax` en el parte
diario (respaldo: parte horario).

**Estado del notebook:** 104 celdas; la captura AEMET (T-10), el relleno histórico y la
captura REE (T-12), el mapa de orígenes (T-13), el guardado de la predicción propia (T-14)
y la actualización de reales (T-15) están integrados. El modelo guardado en
`src/data/modelos/` usa 18 variables.

**Previsión de REE (T-11, medido el 2026-11-07):**

| Endpoint | Sin credencial | Qué devuelve | Veredicto |
|---|---|---|---|
| `GET https://api.esios.ree.es/indicators/541` | 200 | 96 valores de 15 min del día en curso (`geo_id=8741`, Península), `values_updated_at`; no declara elaboración ni horizonte D+1 | No sirve para previsión D+1 |
| `GET .../indicators/541?start_date=...&end_date=...` | 403 | `{"Status":403,"message":"Forbidden"}` | Requiere token |
| `GET .../indicators/1777` (previsión diaria D+1 eólica) | 403 | Forbidden | Requiere token |
| `GET .../indicators/1778` (previsión intradiaria H+3 eólica) | 403 | Forbidden | Requiere token |
| `GET .../indicators/10358` y `10359` | 403 | Forbidden | Requiere token |
| `https://apidatos.ree.es/es/datos/generacion/prevision-*` | 404/500 | no hay endpoint de previsión | No viable |

**Veredicto T-11:** sin un token de ESIOS en `.env` no se puede capturar la previsión de
generación de REE con horizonte D+1 ni con elaboración declarada. La spec 004 se reduce a
la captura AEMET y a la predicción propia; **T-12 queda bloqueada** hasta que el usuario
aporte credencial y confirme D-4-3. El esquema de `prediccion_diaria` ya admite
`fuente='ree'`, así que la captura se podrá añadir sin migrar tablas.

> **Superado el 2026-11-08:** el usuario aportó la credencial de ESIOS. Con `x-api-key` el
> 1777 responde 200, D-4-3 queda resuelta y T-12 se cierra con el relleno histórico del
> Anexo B.

**Ejecución end-to-end (2026-11-07):** 12 ubicaciones AEMET × 7 días = 84 filas; segunda
ejecución el mismo día: 0 filas nuevas. El mapa declara 18 variables (8 observación,
3 previsión, 7 sin dato por ventana incompleta) y la predicción propia queda archivada
con su vector y sus orígenes (8 observación, 3 previsión, 7 estimadas). La actualización
de reales se verificó sobre una copia de la base: `real_mwh = 79 869,3`,
`error_mwh = −10 130,7`, MAE de 1 día.

## Anexo B — Histórico de la previsión de REE

**Qué se archiva (medido el 2026-11-08):** 1 773 días reconstruidos
(`2022-01-01 → 2026-11-08`) más 1 día en vivo (`2026-11-09`) = **1 774 filas**
`fuente='ree'`, 0 huecos. El primer relleno hizo 5 peticiones (una por año) y la segunda
pasada, 0; el día en vivo se recaptura y sustituye su misma elaboración.

**Verificación por bloque:** los cinco bloques (2022…2026) pasaron
`values_updated_at.date() == hasta − 1 día`. 2019 existe en ESIOS pero con sello de carga
en bloque (2019-12-26), así que se descarta; 2018 y anteriores están vacíos.

**Tamaño:** el parte reconstruido ocupa 388 B de media (máximo 638 B) porque guarda solo
el valor del día, la ventana y el sello. La respuesta completa se conserva únicamente en
las capturas en vivo.

**Error de la previsión frente al real** (día natural de Madrid, 1 772 días con real):

| Año | Días | MAE (MWh) | RMSE (MWh) | Sesgo (MWh) | MAPE |
|---|---:|---:|---:|---:|---:|
| 2022 | 365 | 10 735 | 14 407 | −2 531 | 7,7 % |
| 2023 | 365 | 12 061 | 17 450 | +120 | 8,2 % |
| 2024 | 366 | 13 642 | 19 950 | +2 260 | 9,1 % |
| 2025 | 365 | 12 516 | 17 945 | −1 400 | 9,3 % |
| 2026 | 311 | 17 680 | 28 720 | +13 120 | 12,4 % |
| **Total** | **1 772** | **13 194** | **19 969** | — | — |

El sesgo de 2026 (+13 120 MWh) indica sobreestimación en el tramo reciente. La alineación
importa: con el día UTC (`SUBSTR(datetime,1,10)`) el MAE sube a 52 098 MWh; con
`fechas.fecha_madrid`, baja a 13 194. Todo el archivo usa el día natural peninsular.

**Efecto en el mapa:** `serie_prevision_generacion` elige por día la elaboración declarada
más reciente y no posterior al objetivo. La observación conserva prioridad; si falta un
día de generación se completa con REE. Desde D-4-8, `eolica_ma7` también declara
`mixta` cuando su ventana reparte días entre observación y previsión.

## Anexo C — Ventana mixta (D-4-8, 2026-11-11)

**Motivo medido:** para objetivo 2026-11-12, `aemet_diario` terminaba el 11-07 y
el archivo AEMET cubría 11-07→11-17. La ventana `ma7` necesitaba 11-06→11-12:
faltaba solo el 11-06 en previsión, mientras 11-08→11-12 no eran observables.
La ventana `ma14` necesitaba 10-30→11-12. La antigua regla no podía aprovechar
juntos los dos orígenes y el respaldo dejaba fuera 11-07→11-11.

**Regla nueva:** cada día toma observación si ya está disponible y previsión si
no; si faltan ambas, la ventana es `NO_DISPONIBLE`. Una ventana con dos fuentes
se marca `mixta` y guarda el desglose. Se aplica a las seis medias de viento y
racha y a `eolica_ma7`.

**Comparación inicial sobre el vector guardado**, cambiando solo las medias que
antes usaban el respaldo desfasado. El valor «respaldo» es la predicción
archivada en `prediccion_propia` con la regla anterior; el notebook vuelve a
imprimir esta comparación en cada ejecución con su propio respaldo:

| Objetivo | Variable | Respaldo | Mixta | Días obs + prev |
|---|---|---:|---:|---:|
| 2026-11-11 | `vel_ma7` | 2,794 | 3,161 | 2 + 5 |
| 2026-11-11 | `racha_ma7` | 8,767 | 8,968 | 2 + 5 |
| 2026-11-11 | `vel_ma14` | 2,628 | 2,906 | 9 + 5 |
| 2026-11-12 | `vel_ma7` | 2,582 | 3,671 | 2 + 5 |
| 2026-11-12 | `racha_ma7` | 8,197 | 9,686 | 2 + 5 |
| 2026-11-12 | `vel_ma14` | 2,603 | 3,162 | 9 + 5 |

| Objetivo | Predicción con respaldo | Predicción con ventana mixta | Real |
|---|---:|---:|---:|
| 2026-11-11 | 343.909 MWh | 341.541 MWh | Pendiente |
| 2026-11-12 | 305.294 MWh | 294.843 MWh | Pendiente |

La fila del 11-12 es la ejecución real del notebook del 2026-11-11: `prediccion_propia`
guarda **294.843 MWh** con `vel_ma7`, `vel_ma14`, `racha_ma7` y `racha_ma14` como `mixta`,
`vel_ma3`/`racha_ma3` como `prevision`, ocho variables `observacion` y `sol_lag1`
`estimada`. Con el archivo de hoy, el notebook recalcula el respaldo antiguo en
305.789 MWh; los 305.294 MWh eran la emisión archivada con la regla anterior.

Estas diferencias **no demuestran todavía una mejora**: el real llega después y
los coeficientes de las medias compiten con los del viento del día objetivo. La
evaluación debe comparar el error absoluto de ambas variantes contra el real y,
cuando AEMET publique los días, contrastar la ventana mixta con la ventana
íntegramente observada. No se concluye mejora con menos de 5 días.


