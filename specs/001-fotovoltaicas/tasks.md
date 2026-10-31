# Tareas 001 — Incorporar la fotovoltaica al pipeline

> **Sustituida por `specs/002-sol-feature-eolica/tasks.md` (2026-10-29).** Las fases 0 y 1 de este
> documento (T-01 a T-16) siguen cerradas y son la base reutilizada por la spec 002. T-17 a T-25
> corresponden al modelo solar autónomo, que deja de ser objetivo: pasan a material de anexo.

Derivadas de `specs/001-fotovoltaicas/spec.md` (RF-1 a RF-11) y `specs/001-fotovoltaicas/plan.md`
(decisiones D-T1 a D-T12). Cada tarea cabe en 20–30 minutos y deja el repositorio en un estado
verificable. El orden es de dependencia: no se empieza una tarea si la anterior no está en verde.

**Puerta permanente:** `node --test "src/pipeline/tests/*.test.mjs"` debe estar en verde al cerrar
cada tarea de la fase 1 (el directorio a secas no lo acepta Node 24; verificado el 2026-10-27).
Prohibido avanzar con la puerta en rojo (constitución, principio 4).

---

## Fase 0 — Comprobación previa

- [x] **T-01 · Verificar que `4452` y `9434` publican insolación** · 25 min · RF-2
  - **Qué:** consultar AEMET para `4452 BADAJOZ/TALAVERA LA REAL` y `9434 ZARAGOZA/AEROPUERTO` y
    comprobar que devuelve `sol` para el periodo de estudio. Herramienta: sonda
    `src/pipeline/insolation_probe.mjs` (10 tests en `src/pipeline/tests/insolation_probe.test.mjs`).
  - **Depende de:** nada. **Bloquea:** todo lo demás.
  - **Hecho cuando:** ambas estaciones tienen insolación publicada y la comprobación queda anotada
    en `MEMORY.md`. Si alguna no la publicara, se pararía el plan (RF-3, riesgo R-8).
  - **Estado (2026-10-27):** ✅ cerrada con la clave renovada. Ventana completa 2022-01-01 → 2026-06-23:
    `4452` 1.633/1.635 días con insolación (99,9 %, hueco máximo 0 días, máx 14,5 h) y
    `9434` 1.632/1.635 (99,8 %, hueco máximo 0 días, máx 14,7 h). Ninguna necesita sustitución.

---

## Fase 1 — Lógica pura y puerta de tests

- [x] **T-02 · Esqueleto del módulo y excepciones** · 20 min · RF-1
  - **Qué:** crear `src/pipeline/__init__.py`, `src/pipeline/solar.py` con `CatalogError` e
    `InsolationError`, y `src/pipeline/tests/test_solar.py` con un caso trivial.
  - **Depende de:** nada.
  - **Hecho cuando:** `python -m unittest discover -s src/pipeline/tests` termina en 0 con un test
    ejecutado y el módulo importa sin dependencias externas.

- [x] **T-03 · Puerta `node --test`** · 25 min · Constitución 4 · RNF-3
  - **Qué:** `src/pipeline/tests/gate.test.mjs` que lanza `python -m unittest discover` y falla si
    el código de salida no es 0, mostrando la salida de Python.
  - **Depende de:** T-02.
  - **Hecho cuando:** `node --test "src/pipeline/tests/*.test.mjs"` devuelve 0 con la suite en verde y devuelve
    distinto de 0 al romper un test a propósito (comprobado una vez, luego revertido).

- [x] **T-04 · `study_window`** · 20 min · RF-2 · CA-2.1
  - **Qué:** ventana de estudio: inicio fijo, fin = `hoy − 3 días`.
  - **Depende de:** T-03.
  - **Hecho cuando:** un test fija que con `hoy = 2026-06-27` la ventana es
    `2022-01-01 → 2026-06-24` y que el fin siempre es anterior a `hoy`.

- [x] **T-05 · `validate_catalog`** · 25 min · RF-1 · CA-1.1, CA-1.2
  - **Qué:** cinco pares planta–estación, sin indicativos duplicados, con coordenadas y distancia,
    coherentes con el diccionario que consume la descarga.
  - **Depende de:** T-04.
  - **Hecho cuando:** pasan los tests T-1 a T-4 del plan (catálogo válido, indicativo duplicado sin
    coordenadas, catálogo incoherente con la descarga) y el error nombra el par culpable.

- [x] **T-06 · `validate_sol_values`** · 20 min · RF-3 · CE-3, CE-4
  - **Qué:** rechazar `sol < 0`, no numérico y `sol > 24`; aceptar `0.0` como valor válido.
  - **Depende de:** T-05.
  - **Hecho cuando:** pasan T-9 y T-10 del plan y el mensaje distingue "valor imposible" de "dato
    ausente".

- [x] **T-07 · `coverage_report`** · 30 min · RF-4 · CA-4.1
  - **Qué:** % de nulos por estación y variable, hueco máximo consecutivo y días con dato; devuelve
    datos, no imprime.
  - **Depende de:** T-06.
  - **Hecho cuando:** con una serie sintética de 30 días y 3 nulos seguidos el informe da 10 % y
    hueco 3 (test T-5), y dos llamadas seguidas devuelven lo mismo.

- [x] **T-08 · `assert_insolation`** · 25 min · RF-3 · CA-3.1, CA-3.2, CA-3.3 · CE-2
  - **Qué:** puerta con `MIN_COBERTURA_SOL_PCT = 90` y `MAX_HUECO_SOL_DIAS = 7` como constantes
    nombradas; error con planta, indicativo, motivo y acción esperada.
  - **Depende de:** T-07.
  - **Hecho cuando:** pasan T-6, T-7 y T-8 del plan: 0 % aborta, 47 % con hueco de 828 días aborta,
    94,6 % con hueco de 3 días pasa; el mensaje contiene el indicativo y la planta.

- [x] **T-09 · `daily_national_series`** · 25 min · RF-5 · CA-5.3
  - **Qué:** media diaria de las estaciones con dato y columna `n_estaciones`; sin interpolar;
    error si un día no tiene ninguna estación.
  - **Depende de:** T-08.
  - **Hecho cuando:** pasan T-11 y T-12 del plan (3 de 5 estaciones → media de 3; 0 de 5 → error con
    la fecha).

- [x] **T-10 · `build_features`** · 30 min · RF-5, RF-6 · CA-5.1, CA-5.2, CA-10.3
  - **Qué:** merge meteorología–objetivo, calendario, lags 1/2/3/7, medias móviles 3/7/14 de `sol` y
    `tmed`, `solar_ma7` sobre el objetivo desplazado, y lista de features cerrada de 16.
  - **Depende de:** T-09.
  - **Hecho cuando:** pasan T-13, T-14 y T-15 del plan: la lista devuelve exactamente las 16
    features en orden, ningún valor de la fila *t* usa el objetivo de *t* o posterior, y con un
    hueco interno `solar_lag7` sigue apuntando a 7 días naturales antes (la fila se elimina, no se
    desplaza).

- [x] **T-11 · `temporal_split_index`** · 20 min · RF-8 · CA-8.1
  - **Qué:** corte cronológico 80/20.
  - **Depende de:** T-10.
  - **Hecho cuando:** pasa T-16 del plan: 10 filas → corte en 8, train anterior a test, sin solape,
    y `n = 0` produce un error explícito.

- [x] **T-12 · `quintile_edges` y `to_quintiles`** · 20 min · RF-9 · CA-8.2, CA-9.1
  - **Qué:** bordes de quintiles calculados solo con train y asignación de tramos.
  - **Depende de:** T-11.
  - **Hecho cuando:** con una serie conocida los bordes son los esperados y ningún valor de test
    interviene en su cálculo.

- [x] **T-13 · `regression_metrics`** · 25 min · RF-9 · CA-9.1 · CE-5
  - **Qué:** RMSE, MAE, R², MAPE y accuracy por tramos; el MAPE excluye los días con objetivo 0 y
    declara cuántos excluyó.
  - **Depende de:** T-12.
  - **Hecho cuando:** pasan T-17 y T-18 del plan: valores exactos en un caso calculado a mano y sin
    división por cero cuando el objetivo tiene un día a 0.

- [x] **T-14 · `solar_report`** · 20 min · RF-11 · CA-11.1, CA-11.2
  - **Qué:** dict serializable con catálogo (planta → estación → distancia), cobertura, métricas y
    fecha de ejecución recibida como `hoy`.
  - **Depende de:** T-13.
  - **Hecho cuando:** pasan T-19 y T-20 del plan: dos llamadas con la misma entrada producen el
    mismo resultado y el dict contiene los 5 pares, la cobertura y la fecha.

> **Fase 1 cerrada el 2026-10-27.** `src/pipeline/solar.py` implementa las once funciones con
> biblioteca estándar y `src/pipeline/tests/test_solar.py` las cubre con **51 casos**:
> `python -m unittest discover -s src/pipeline/tests -p "test_*.py"` → `Ran 51 tests … OK`.
> La puerta `node --test "src/pipeline/tests/*.test.mjs"` da **16/16** (15 de la sonda AEMET + 1
> adaptador) y se comprobó que **falla** al romper un test de Python a propósito, volviendo a verde
> al revertirlo (T-03).
>
> Decisión tomada al cerrar T-10: las medias móviles se calculan sobre la **ventana natural** (el
> `sol_ma3` de un día usa D, D-1 y D-2, promediando solo los que tienen dato), no sobre «los últimos
> 3 valores disponibles». Así un hueco largo no arrastra valores de otra estación del año a una
> ventana corta. El test de T-10 se ajustó a esta regla.

---

## Fase 2 — Notebook: catálogo, descarga y puerta

- [x] **T-15 · Poblar el catálogo fotovoltaico** · 30 min · RF-1 · CA-1.1, CA-1.2
  - **Qué:** reescribir `provincias_fotovoltaicas` y `estaciones_meteorologicas_fotovoltaicas` con
    `3469A`, `4452`, `7228`, `5783`, `9434`, sus coordenadas, la planta asignada y la distancia.
    Añadir las constantes de umbral.
  - **Depende de:** Fase 1 cerrada.
  - **Hecho cuando:** `validate_catalog` no lanza sobre los datos del notebook, hay 5 pares sin
    duplicados y el bloque eólico del notebook ejecuta igual que antes.
  - **Estado (2026-10-27):** ✅ `provincias_fotovoltaicas` tiene los 5 pares y
    `estaciones_meteorologicas_fotovoltaicas` las coordenadas del inventario de AEMET más la planta
    asignada. Celda nueva que calcula la distancia (haversine) y llama a `validate_catalog`. Las
    celdas 14, 15 y 16 del notebook se ejecutaron fuera de Jupyter (no necesitan pandas) y la salida
    fue: 5 pares, indicativos únicos `3469A, 4452, 7228, 5783, 9434`, distancias 55,7 / 69,6 / 15,5 /
    21,6 / 81,6 km.

- [x] **T-16 · Descargar el histórico de las 5 estaciones** · 30 min + espera · RF-2 · CA-2.1, CA-2.2, CA-2.3 · RNF-4, RNF-8
  - **Qué:** ejecutar la descarga existente (`descargar_aemet`) sin modificarla, de forma separada
    del modelado por el coste en tiempo (riesgo R-6). AEMET rechaza rangos superiores a **6 meses**
    por petición: con `dias_por_tramo = 3` son ~545 peticiones por estación (varias horas por
    estación); la sonda `insolation_probe.mjs` ya trocea en bloques de 150 días.
  - **Depende de:** T-15.
  - **Hecho cuando:** las 5 estaciones tienen una fila por día en la ventana, `aemet_diario` no
    gana filas al relanzar la descarga y `diagnostico_nulos` muestra `sol` para las cinco.
  - **Estado (2026-10-27):** ✅ descargado con `src/pipeline/aemet_backfill.py` (45 peticiones,
    6.587 filas nuevas, 0 errores) tras copia de seguridad de la BD fuera del repositorio. Las cinco
    estaciones tienen **1.635 filas** (2022-01-01 → 2026-06-23), una por día. Días con `sol`:
    `3469A` 1.635 (0,0 %), `4452` 1.633 (0,1 %), `7228` 1.607 (1,7 %), `5783` 1.540 (5,8 %),
    `9434` 1.632 (0,2 %). Segunda pasada en simulación: **55/55 ventanas completas, 0 peticiones**
    (idempotente). `aemet_diario` pasa de 22.426 a 29.013 filas.

- [ ] **T-17 · Celda de puerta en el notebook** · 20 min · RF-3, RF-7 · CA-3.1–3.3, CA-7.3
  - **Qué:** celda justo después de los tres `diagnostico_nulos(...)` que llama a
    `validate_sol_values`, `coverage_report` y `assert_insolation`.
  - **Depende de:** T-16.
  - **Hecho cuando:** con los datos reales imprime el informe de las 5 estaciones y continúa; y al
    vaciar `sol` de una estación a mano, la ejecución se detiene en esa celda con un error que
    nombra planta e indicativo.

---

## Fase 3 — Notebook: modelado solar

- [ ] **T-18 · Features solares** · 30 min · RF-5, RF-6 · CA-5.1–5.3, CA-6.1
  - **Qué:** celda que construye `df_solar_ml` y `FEATURE_COLS_SOLAR` con `build_features`, sin
    tocar `df_ml`, `FEATURE_COLS`, `TARGET` ni `scaler`. Informa del recorte si el objetivo no
    cubre la ventana.
  - **Depende de:** T-17.
  - **Hecho cuando:** imprime 16 features y el nº de días y rango de fechas del dataset solar; las
    variables eólicas siguen existiendo con el mismo contenido tras ejecutar la celda.

- [ ] **T-19 · Split solar** · 20 min · RF-8 · CA-8.1, CA-8.3
  - **Qué:** `SPLIT_SOLAR` con `temporal_split_index`, sin reutilizar `SPLIT_IDX`.
  - **Depende de:** T-18.
  - **Hecho cuando:** imprime nº de días y rango de fechas de train y test, el test empieza después
    del último día de train y `SPLIT_IDX` conserva su valor eólico.

- [ ] **T-20 · Entrenamiento y evaluación solar** · 30 min · RF-8, RF-9 · CA-8.2, CA-9.1, CA-9.3
  - **Qué:** seis familias con **instancias nuevas**, `StandardScaler` propio y quintiles propios;
    tabla comparativa con el mismo formato que la eólica más la referencia trivial (media de train).
  - **Depende de:** T-19.
  - **Hecho cuando:** se imprime la tabla con RMSE, MAE, R², MAPE y accuracy para los 6 modelos y
    la media de train; las métricas eólicas impresas antes no cambian y `modelos_fit`/`scaler`
    eólicos siguen intactos (comparado con una reimpresión tras la celda).

- [ ] **T-21 · Guardar y recargar el modelo solar** · 25 min · RF-10 · CA-10.1–10.3
  - **Qué:** `lr_solar.joblib` con `{modelo, scaler, features}` en `MODEL_DIR`, recarga desde disco
    y verificación de métricas. No se copia a las otras rutas del proyecto (D-T10).
  - **Depende de:** T-20.
  - **Hecho cuando:** el fichero existe, al recargarlo reproduce las métricas de test al decimal,
    `features` coincide exactamente con `FEATURE_COLS_SOLAR` y `lr_eolica.joblib` no ha cambiado de
    contenido (misma suma de verificación).

- [ ] **T-22 · Registro de trazabilidad** · 20 min · RF-11 · CA-11.1, CA-11.2
  - **Qué:** escribir `solar_metrics.json` con `solar_report` e imprimir el resumen planta →
    estación → cobertura → métricas.
  - **Depende de:** T-21.
  - **Hecho cuando:** el JSON es válido, contiene los 5 pares, la cobertura, las métricas y la fecha
    de ejecución, y el resumen de consola coincide con su contenido.

> **Estado de las fases 2 y 3 (2026-10-27).** El código de T-17 a T-22 está escrito en
> `main.ipynb` (celda de la puerta tras los tres `diagnostico_nulos` y cinco celdas al final:
> variables, split, entrenamiento, guardado y trazabilidad). Las 89 celdas compilan y las celdas
> 14–16 se ejecutaron de verdad fuera de Jupyter.
>
> **Lo que no se ha podido ejecutar aquí:** el entorno de trabajo no tiene `pandas`,
> `scikit-learn`, `joblib` ni `xgboost`/`lightgbm`, así que el notebook completo no corre. Por eso
> T-17 a T-24 quedan abiertas: su criterio de cierre exige ver el notebook ejecutado de arriba abajo.
> Lo que sí está verificado es la lógica que esas celdas llaman, **con los datos reales y sin pandas**
> (`solar.py` + `sqlite3`): catálogo de 5 pares (55,7 / 69,6 / 15,5 / 21,6 / 81,6 km), puerta de
> insolación en verde, serie diaria de **1.635 días con 4,92 estaciones de media y ningún día vacío**,
> dataset de **1.629 filas × 16 features** (2022-01-07 → 2026-06-23) y partición **1.303 train /
> 326 test** (2025-08-02 → 2026-06-23).
>
> **T-16:** la descarga se hace con `src/pipeline/aemet_backfill.py` (biblioteca estándar) porque
> `descargar_aemet` necesita pandas. Ventanas de 150 días por el límite de 6 meses de AEMET,
> `INSERT OR IGNORE` e idempotencia comprobada al relanzar.

---

## Fase 4 — Verificación y cierre

- [ ] **T-23 · No regresión del modelo eólico** · 25 min · RF-7 · CA-7.1, CA-7.2
  - **Qué:** ejecutar el notebook completo de arriba abajo partiendo de un `.joblib` eólico
    respaldado.
  - **Depende de:** T-22.
  - **Hecho cuando:** las métricas eólicas de test son RMSE 59.150,8 · MAE 45.986,5 · R² 0,5931 y
    el modelo eólico guardado conserva sus 16 features.

- [ ] **T-24 · Escenario de fallo de punta a punta** · 20 min · RF-3, RF-7 · CA-3.1, CA-7.3
  - **Qué:** provocar el fallo sustituyendo temporalmente un indicativo válido por uno inexistente
    y ejecutar el notebook.
  - **Depende de:** T-23.
  - **Hecho cuando:** el notebook se detiene en la celda de la puerta, antes de cualquier
    entrenamiento, con un mensaje que nombra planta e indicativo; y al revertir el cambio vuelve a
    completarse.

- [ ] **T-25 · Cerrar memoria y criterios de finalización** · 20 min · RF-11 · Criterio 7
  - **Qué:** anotar en `MEMORY.md` estaciones, cobertura, métricas del modelo solar y referencia a
    `spec.md`/`plan.md`/`tasks.md`; marcar las casillas de esta lista.
  - **Depende de:** T-24.
  - **Hecho cuando:** `MEMORY.md` recoge las estaciones y las métricas de la ejecución final y los
    siete criterios de finalización de la spec se pueden comprobar sin abrir el notebook.

---

## Cobertura de requisitos

| RF | Tareas |
|---|---|
| RF-1 | T-02, T-05, T-15 |
| RF-2 | T-01, T-04, T-16 |
| RF-3 | T-06, T-08, T-17, T-24 |
| RF-4 | T-07, T-16 |
| RF-5 | T-09, T-10, T-18 |
| RF-6 | T-10, T-18 |
| RF-7 | T-17, T-20, T-23, T-24 |
| RF-8 | T-11, T-19, T-20 |
| RF-9 | T-12, T-13, T-20 |
| RF-10 | T-21 |
| RF-11 | T-14, T-22, T-25 |

## Bloqueos conocidos

- **T-01** cerrada el 2026-10-27 con la clave renovada: `4452` 99,9 % y `9434` 99,8 % de días con
  `sol` en 2022-01-01 → 2026-06-23, sin huecos consecutivos. Ninguna estación se sustituye (R-8).
- **T-08** usa valores provisionales de umbral (90 % / 7 días) mientras D-1 siga abierta.
- **T-14** y **T-22** dependen de que la fecha de ejecución sea la del proyecto (D-T11), no de una
  corrección de zona horaria.
- **D-2** confirmada: un fallo solar aborta también el bloque eólico (T-24 lo verifica).
- **D-6**: la puerta es `node --test` mediante adaptador (T-03); si se decide lo contrario, T-03 se
  reescribe y no afecta al resto.
