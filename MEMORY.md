# MEMORY.md — Aero Predictor

Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual
- Modelo de producción **en la web**: **LinearRegression + StandardScaler** de **16 variables**
  (`modelos/lr_eolica.joblib`, dict `{modelo, scaler, features}`), sin tocar desde 2026-10-29.
- **Modelo del notebook (18 variables, ejecutado 2026-11-11)**: `src/data/modelos/lr_eolica.joblib`,
  test 2025-11-20 → 2026-11-07 (353 días): **RMSE 39.932,5 MWh · MAE 30.141,8 · R² 0,7919**, decisión
  `aceptado` (3 de 4 folds). SHA-256 `ff52ce58…`; **aún no se ha copiado a producción** (pendiente de
  autorización).
- **Spec 004 — REE integrada (2026-11-08)**: tablas `prediccion_diaria` y `prediccion_propia` en
  `src/data/ree_generacion.db`. AEMET: 574 filas (2 elaboraciones, horizonte 2026-11-07 → 11-17).
  REE (ESIOS 1777): **1.777 filas**, 1.773 reconstruidas (`2022-01-01 → 2026-11-08`) + 4 en vivo
  (`2026-11-09 → 11-12`), **0 huecos**; relleno por
  bloques anuales verificados con `values_updated_at` y segunda pasada con 0 nuevas. El mapa usa la
  previsión en `eolica_lag2/3/7` y `eolica_ma7` cuando falta observación (`permitir_prev_gen=True`).
  **380 tests Python + 16 Node en verde.** T-12 y T-19/T-20 cerradas; T-17 solo pendiente de
  D-4-4/D-4-5. Detalle en `specs/004-predicciones-en-src/` (Anexos B y C).
- **Ventana mixta (D-4-8, 2026-11-11)**: las seis medias `vel_ma*`/`racha_ma*` y `eolica_ma7` se
  resuelven día a día: observación si existe (nunca posterior a `hoy`), previsión oficial en los
  huecos. Origen `mixta` con `dias_observados`/`dias_previstos`; un día sin ninguna fuente deja la
  variable `NO_DISPONIBLE` y el notebook aborta en vez de usar el respaldo desfasado. Para 2026-11-12
  el mapa resuelve las 18 variables con `ma7` = 2 obs + 5 prev y `ma14` = 9 obs + 5 prev, y
  `prediccion_propia` guarda **294.843 MWh** (notebook ejecutado el 11-11; el modelo se reentrenó
  con RMSE 39.932 y decisión aceptada).
- Backend FastAPI en Render; frontend Astro en Vercel; scheduler diario a las 3:00 (Europe/Madrid).
- Datos: eólica diaria peninsular 2021-12-31 → 2026-11-10 (día local; 10.651 filas en `generacion`);
  AEMET 18 estaciones 2022-01-01 → 2026-11-07, **30.511 filas** (las 5 solares con cobertura verificada).
- El scheduler descarga datos y predice, pero **no reentrena** el modelo.
- **Spec 003**: archivo AEMET en backend (`prediccion_aemet`, clave `elaborado, objetivo, ubicacion`),
  captura 3:00/9:00; T-12 y T-15 hechas el 2026-11-02. La spec 004 lo sustituye en `src/` con
  `prediccion_diaria`; la captura del backend queda dormida hasta que se decida D-4-4.
- **Spec 002 ejecutada el 2026-10-31**: notebook de 87 celdas corrido de arriba abajo (115 s) y
  **criterio ACEPTADO 3 de 4 folds**. 116 tests de Python + 16 de `node --test` en verde.
- Serie solar diaria verificada contra la BD: 1.761 días continuos (2022-01-01 → 2026-10-28), sin
  saltos; `sol_lag1` sin huecos en las 1.754 filas del dataset (0 descartadas).

## Decisiones (y por qué)
- **Target diario** (no semanal): el notebook entrena con serie diaria; `src/memoria.ipynb` aún menciona "semanal" y debe corregirse.
- **LinearRegression** como modelo de producción por interpretabilidad; boosting y SARIMAX no mejoran.
- **Interpolación lineal** para huecos de viento (mejor RMSE en la mayoría de estaciones).
- **Solo eólica** en producción. La solar entra como **variable explicativa** del modelo eólico (spec 002),
  no como modelo propio: `src/pipeline/solar.py` (lógica pura, sin pandas) aporta la serie diaria de
  `sol`/`tmed`. Hidráulica sigue descartada por caudal de cuenca.
- **Fotovoltaica**: 5 pares planta–estación (`3469A`, `4452`, `7228`, `5783`, `9434`) que aportan la
  serie diaria de `sol`/`tmed`; si falla la insolación, el notebook se detiene (no se imputa nada).
- **Spec 002**: solo `sol_lag1` y `tmed_lag1` (día natural anterior), sin medias móviles ni generación
  solar en MWh. Se comparan 16 vs 18 variables en walk-forward y solo se guarda el modelo si mejora
  el RMSE de forma estricta en ≥3 de los 4 folds.
- **Ventana mixta mejor que ventana mono-origen** (D-4-8, 2026-11-11): la regla anterior exigía la
  media entera de observación o entera de previsión, así que con `aemet_diario` parado en 11-07 la
  media de 7 días caía al respaldo desfasado. La nueva regla completa cada día y declara el desglose.
  Sin medir todavía contra el real: 11-11 343.909 → 341.541 MWh y 11-12 305.294 → 294.843 MWh. Los
  coeficientes de las medias son negativos por colinealidad con `velmedia`/`racha`, así que el signo
  del delta no demuestra mejora; hará falta ≥5 días de reales (Anexo C de la spec 004).

## Aprendizajes y errores a evitar
- `9299X` está duplicado (Borja y La Muela) y `"9299"` es inválido → se duplica Tarazona en la media.
- `get_historical_data()` mezcla formatos de fecha; usar `SUBSTR(datetime, 1, 10)`.
- Métricas de `charts.py`/README desactualizadas frente a las reales; `metrics.json` no existe.
- Fallbacks/mock (150.000 MWh) pueden enmascarar fallos; revisar `avisos`.
- REE CCAA solo da **mensual/anual**; `time_trunc=day` con `geo_limit=ccaa` falla.
- AEMET: dos pasos + rate limit; viento en km/h.
- El pronóstico diario AEMET puede omitir `rachaMax` en todas las localidades; agregar solo rachas
  disponibles y, si no hay ninguna, usar explícitamente la media histórica reciente (o detenerse
  si no hay histórico).
- AEMET solar (2026-10-27): las 5 estaciones publican `sol` (2022→2026). Cobertura real: 3469A 100 %,
  4452 99,9 %, 7228 98,3 %, 5783 94,2 % (hueco máx. 3 d), 9434 99,8 %. AEMET **rechaza rangos >
  6 meses** por petición → `src/pipeline/aemet_backfill.py` trocea en ventanas de 150 días.
- Serie solar real: 1.629 filas × 16 features (2022-01-07 → 2026-06-23); split 1.303 train / 326 test
  (test 2025-08-02 → 2026-06-23, el mismo corte que la eólica). Referencia trivial (media de train):
  RMSE 65.462 MWh, R² −0,32, Accuracy 12,3 %.
- La puerta de cobertura se mide sobre el rango con datos: la ventana de estudio (`hoy−3`) va 123 días
  por delante del último dato de AEMET, y contarla como hueco tumbaba el pipeline.
- LightGBM 4.7.0 en Windows provocó `access violation` en `fit()` incluso con datos sintéticos; LightGBM
  4.6.0 pasó el ajuste con la configuración del notebook.
- La evaluación SARIMAX debe cortar por la fecha del primer día de `test` y realinear el pronóstico a
  sus fechas: `asfreq("D")` añade días ausentes y su longitud no coincide con `y_test`.
- La descarga histórica REE debe comprobar días de eólica existentes por tramo en hora peninsular;
  la fecha máxima global podía hacer que se omitieran huecos internos.
- Al unir la generación diaria REE con AEMET, convertir los timestamps UTC a `Europe/Madrid` antes
  de extraer la fecha: `23:00Z` (invierno) y `22:00Z` (verano) representan la medianoche peninsular
  del día siguiente. Comprobado el 2026-10-31: la correlación viento↔eólica vale 0,678 con
  `fecha_madrid` en el mismo día, pero 0,679 con corte UTC desplazado un día → el corte UTC va un día
  por detrás. La suma total solo difiere en los bordes (139.410,7 del 2021-12-31 − 125.540,1 del
  2026-10-27), no por pérdida de datos.
- No tocar `FEATURE_COLS` sin reentrenar y sincronizar notebook/backend.
- **AEMET omite `periodo` cuando el valor vale para las 24 h** (últimos días del parte diario): sin
  tratarlo como `00-24` se perdían viento y cielo de 3 de los 7 días. Medido el 2026-11-02.
- **El parte horario se queda a medias en su último día** (solo 00–06): coger su cielo descartaba el del
  diario. `merge_tramos` combina hora a hora y prefiere el dato más fino sin dejar huecos.
- **Siete horas de temperatura no son la media del día**: por debajo de 12 horas se usa `(tmax+tmin)/2`.
- **AEMET devuelve 429 con facilidad** (2 en una captura de 24 peticiones): el reintento con espera de
  60 s lo resuelve; sin él se perdían ubicaciones.
- **La frontera con pandas convierte SQL NULL en `NaN`, no en `None`**: `choose_forecast`/`national_series`
  lo propagaban y la predicción de mañana acababa con un valor que no era ni observación ni previsión
  (medido 2026-11-07). El notebook normaliza a `None` al leer y `prevision._es_ausente` rechaza `NaN`.
- **Los kernels Jupyter conservan módulos en `sys.modules`**: si cambia un `src/pipeline/*.py` después del
  `import`, hay que recargarlo con `importlib.reload()` o reiniciar el kernel antes de ejecutar celdas que
  usan funciones nuevas. Las celdas de relleno REE y del mapa recargan `prevision_db`/`prevision` si falta
  la función nueva; para el resto de módulos, reiniciar el kernel.
- **Ningún módulo carga `.env`**: el backend depende de las variables de entorno inyectadas (Render).
  Para una prueba local hay que pasar la clave explícitamente.
- **REE publica los 1-2 últimos días incompletos** (2026-11-02: 2026-10-30 al 39 % y 2026-10-29 al 34 %
  de la mediana de los 7 anteriores). No sirven de retardo: `forecast.generation_lags` los señala y
  descarta, y el ancla retrocede al último día completo (el modelo antes los usaba en silencio).
- **ESIOS 1777 devuelve un día más que `end_date`** y un único `values_updated_at`, que corresponde a la
  última actualización anterior a `end_date` (el día previo al último objetivo). Sin acotar la ventana se
  archiva un día de más; sin comprobar el sello se etiqueta una revisión posterior como si fuera la
  original. El relleno usa `bloque_verificable(indicador, hasta)` y `hasta − 1 día`.
- **La previsión D+1 de REE es mejor que el modelo**: MAE 13.194 / RMSE 19.969 MWh (2022-2026) frente a
  29.950 / 39.703 en test. El MAE sube a 52.098 si se alinea por día UTC; con `fechas.fecha_madrid` baja
  a 13.194. El sesgo de 2026 es +13.120 MWh (sobreestima).

## Próximos pasos
- **Spec 004**: T-12, T-19 y T-20 cerradas (relleno histórico + captura REE + ventana mixta). Quedan
  **T-17** solo por D-4-4 (captura del backend) y D-4-5 (retención), medir la ventana mixta contra el
  real (≥5 días) y la decisión de copiar el modelo de 18 variables a producción. Las celdas REE están
  tras la descarga AEMET; el mapa y reales, en su sitio.
- **Spec 003: T-01 a T-10, T-12 y T-15 hechas y en verde** (380 tests de Python tras `gate.test.mjs`).
  Quedan: T-06 (segunda captura en otro día), T-11 (calibración de `sol`, necesita solape), T-13
  integración y T-14 (bloqueadas por D-3-2: cómo entrenar con 2 meses de previsión y 4 años de
  observación). Estado y verificación en `specs/003-archivo-predicciones-aemet/tasks.md`.
- **Spec 003 y plan 003 redactados el 2026-11-01** (`specs/003-archivo-predicciones-aemet/`): archivo propio de
  previsiones AEMET, porque AEMET **no publica archivo de predicciones** y la observación llega con
  **4 días** de retraso (medido 10-31 → último 10-27 y 11-01 → último 10-28; 3 estaciones). Decisiones del
  usuario: captura **en el backend con su planificador**; cubrir **también** `vel_ma*`/`racha_ma*` (6
  variables, exige parte horario porque `rachaMax` del diario llega vacío); reintentar y recuperar
  mientras la previsión siga viva; decisión con **≥2 % de RMSE en más de la mitad de ventanas móviles de
  21 días**; **nada visible en API/web**. Dudas abiertas D-3-1…D-3-7 en la spec.
  El `plan.md` vive en la misma carpeta: 2 módulos puros en `src/pipeline/` (+2 de test), 3 en backend
  (`aemet_forecast`, `forecast_db` y copia vendorizada `forecast_logic` con test de paridad), una línea en
  `db_ree.init_db`, un paso en la tarea diaria, 2 celdas al final del notebook y `RETRASO_PUBLICACION_DIAS`
  a 4. Puntos de parada: P-2 (D-3-1), P-3 (D-3-3) y P-4 (D-3-2). **P-1 cerrado el 2026-11-01**: el parte
  declara su elaboración (`elaborado: 2026-11-01T08:59:08`, horizonte 11-01→11-07) y nunca contiene días
  anteriores a sí mismo, así que la identidad es `(elaboración declarada, día objetivo, ubicación)` y
  `E ≤ D` se cumple por construcción; la recuperación termina al publicarse la elaboración siguiente.
- **Spec 002 (`specs/002-sol-feature-eolica/`) ejecutada el 2026-10-31** y **aceptada**: walk-forward
  2023–2026 con mejora estricta en 3 de 4 folds (RMSE 41.291→39.524 / 39.958→39.997 / 40.095→39.085 /
  39.324→38.697). El bloque solar autónomo (antiguas celdas 85–90) se eliminó; el notebook quedó en
  87 celdas. Informe: `src/data/modelos/sol_como_feature.json` (folds, cobertura, decisión, rutas).
- **Pendiente de autorización del usuario: T-17**. Copiar `src/data/modelos/lr_eolica.joblib` a
  `modelos/`, `backend/modelos/` y `src/model/production/`, y poner `FEATURE_COLS` a 18 en
  `backend/app/services/model_loader.py` (+ `get_solar_lag1` en `db_ree.py`). El informe ya registra
  las 4 rutas y marca las 3 de producción como `sincronizada: false`.
- **No se toca backend ni frontend sin preguntar**: el 2026-10-31 se revirtieron cambios de backend
  hechos sin consultar (`git checkout` de `model_loader.py`, `db_ree.py` y las 3 copias del `.joblib`,
  que volvieron a la huella `3704300d…` de 16 variables).
- **La celda 21 llama a `descargar_aemet`** (celda 19), no a una descarga paralela. `fechas.ventana_descarga`
  solo decide el rango; el troceo, la omisión de días ya guardados y las pausas siguen siendo de la
  función existente. Corregido el 2026-10-31 tras duplicarla con `aemet_backfill.rellenar`.
- **`src/pipeline/aemet_backfill.py` ya no lo usa el notebook** (solo lo cubren sus 9 tests). Queda a la
  espera de decidir si se retira o se conserva como herramienta de relleno masivo.
- `specs/001-fotovoltaicas/`: T-01 a T-16 cerradas (lógica + catálogo + datos). Siguen abiertas D-1
  (umbral de huecos), D-3, D-6 y D-7 (R² mínimo).
- Medido (2026-10-29): `sol`/`tmed` del día anterior mejoran el R² entre +0,001 y +0,013 en 4/4 folds;
  la solar del mismo día y las medias móviles no aportan más. Generación solar (MWh) descartada como
  feature por la deriva de capacidad (+130 % en 4 años).
- Unificar feature engineering notebook ↔ `model_loader` y añadir reentrenamiento programado.
- Corregir duplicado `9299X` y métricas hardcodeadas.
- Integrar previsiones ESIOS **1777** (eólica D+1): hecho en la spec 004. El 541 queda descartado
  (potencia intradiaria, no energía diaria); 1779 (fotovoltaica) no se incluye para no cambiar el esquema.
- Usar la eólica mensual por CCAA como pesos/estructura (no como target).
- Actualizar README y memoria; mover claves a `.env`.
