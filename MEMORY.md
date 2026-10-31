# MEMORY.md — Aero Predictor

Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual
- Modelo de producción **en la web**: **LinearRegression + StandardScaler** de **16 variables**
  (`modelos/lr_eolica.joblib`, dict `{modelo, scaler, features}`), sin tocar desde 2026-10-29.
- **Modelo del notebook (18 variables, 2026-10-31)**: `src/data/modelos/lr_eolica.joblib`, test
  2025-11-11 → 2026-10-27 (351 días): **RMSE 39.273,3 MWh · MAE 29.418,7 · R² 0,8055**. Es el que
  ganó el walk-forward; **aún no se ha copiado a producción** (pendiente de revisión del notebook).
- Backend FastAPI en Render; frontend Astro en Vercel; scheduler diario a las 3:00 (Europe/Madrid).
- Datos: eólica diaria peninsular 2021-12-31 → 2026-10-30 (etiqueta REE); AEMET 14 estaciones
  2022-01-01 → 2026-10-27, 30.398 filas (las 5 solares con 1.761 días).
- El scheduler descarga datos y predice, pero **no reentrena** el modelo.
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

## Próximos pasos
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
- Integrar previsiones ESIOS (541 eólica, 542/543/10034 solar, PBF 12/13, 460 demanda).
- Usar la eólica mensual por CCAA como pesos/estructura (no como target).
- Actualizar README y memoria; mover claves a `.env`.
