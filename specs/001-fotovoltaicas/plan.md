# Plan 001 — Incorporar la fotovoltaica al pipeline

Spec de referencia: `specs/001-fotovoltaicas/spec.md` (RF-1 a RF-11).
Constitución: `docs/constitution.md`. Convenciones del proyecto: `AGENTS.md`.

| | |
|---|---|
| Alcance | Datos AEMET + variables + modelo solar entrenado, evaluado y serializado |
| Fuera de alcance | API, interfaz, scheduler, reentrenamiento en producción, ERA5, hidráulica (spec §7) |
| Artefacto que se ejecuta | `src/notebooks/main.ipynb` (una sola ejecución, de arriba abajo) |
| Artefactos que se generan | `lr_solar.joblib`, `solar_metrics.json` en el mismo directorio que `lr_eolica.joblib` |
| RF cubiertos | RF-1 … RF-11 (matriz en el apartado 8) |

---

## 0. Resumen de lo que se construye

El notebook ya tiene el 70 % de las piezas: tabla `aemet_diario` con columna `sol`, descarga
incremental idempotente, diagnóstico de nulos, construcción de features y entrenamiento. Lo que
falta es:

1. Rellenar el catálogo fotovoltaico con las cinco estaciones sustitutivas (hoy los diccionarios
   están vacíos o con las estaciones antiguas sin insolación).
2. Una **puerta de validación** que aborte antes de entrenar nada si falta insolación.
3. Un **bloque espejo** del eólico que construya features solares y entrene, evalúe y guarde el
   modelo solar sin tocar ni un objeto del bloque eólico.

No se reestructura el pipeline, no se renombra nada existente y no se cambia ninguna firma
compartida con el bloque eólico (constitución, principio 1; RNF-1).

---

## 1. Conformidad con `docs/constitution.md`

| Principio | Cómo lo cumple este plan | Observación |
|---|---|---|
| 1. Simplicidad y continuidad | Solo se **añaden** celdas al final y una celda de validación; no se reescribe ninguna celda existente salvo el catálogo de estaciones fotovoltaicas (que ya existe y hoy está vacío). Comentarios y mensajes en español. | El catálogo es el único bloque existente que se edita: es un cambio de datos, no de estructura. |
| 2. La spec manda | Cada pieza del plan declara el RF/CA que cubre (apartado 8). Nada del plan implementa algo no previsto en la spec. Las decisiones que la spec deja abiertas se implementan como **parámetros con valor provisional** y se listan en el apartado 9. | D-1, D-3 y D-6 siguen abiertas; el plan no las cierra, las hace configurables. |
| 3. Lógica separada de la interfaz, funciones puras con `hoy` | Toda la lógica nueva vive en un módulo sin E/S (sin red, sin SQLite, sin `print`, sin estado global). Reciben `hoy` explícitamente las dos funciones cuyo resultado depende de la fecha (`study_window`, `solar_report`); el resto son transformaciones deterministas de sus argumentos. | Ver D-T1 y D-T2. |
| 4. Tests como puerta, `node --test`, sin instalar paquetes | La suite de lógica se escribe con `unittest` (biblioteca estándar, cero instalaciones) y se ejecuta a través de **un único test de `node --test` que la invoca**, de modo que el comando de puerta del proyecto sigue siendo literalmente `node --test`. | Ver D-T2 para la justificación y la alternativa descartada. |
| 5. Los datos del usuario son sagrados | No se borra ni se reescribe histórico: `aemet_diario` usa `INSERT OR IGNORE` y la PK `(fecha, indicativo)`. El modelo eólico no se sobrescribe (fichero distinto, RF-10). Fechas en hora local del proyecto, con la misma convención que la serie eólica. | Riesgo en el desfase de fecha REE, apartado 9. |
| 6. Idioma | Identificadores del módulo nuevo en inglés; docstrings, comentarios, mensajes y documentación en español. Nada existente se renombra. | La constitución se contradice a sí misma (principio 1 pide comentarios en castellano); se resuelve así y queda anotado en D-6. |

---

## 2. Archivos creados y modificados

### 2.1 Creados

| Archivo | Tipo | Responsabilidad | RF |
|---|---|---|---|
| `src/pipeline/solar.py` | módulo Python | Toda la lógica pura del bloque solar: catálogo, cobertura, puerta de insolación, serie diaria nacional, features, corte temporal, métricas y registro. Sin E/S, sin `print`, sin estado global. | RF-1, RF-3, RF-4, RF-5, RF-8, RF-9, RF-11 |
| `src/pipeline/__init__.py` | módulo vacío | Hacer `src/pipeline` importable desde el notebook sin manipular `sys.path` más de lo necesario. | — |
| `src/pipeline/tests/test_solar.py` | tests (`unittest`) | Casos del apartado 7 sobre las funciones puras, con series sintéticas. | RF-1 … RF-11 (verificación) |
| `src/pipeline/tests/gate.test.mjs` | test de `node --test` | Puerta única del proyecto: invoca la suite de Python y falla si ésta falla. No contiene lógica de negocio. | Constitución 4 |
| `src/data/modelos/solar_metrics.json` | artefacto generado | Métricas del test, fecha de ejecución, catálogo usado y cobertura. | RF-9, RF-11 |

`lr_solar.joblib` también se genera, pero en el mismo directorio que `lr_eolica.joblib`
(`MODEL_DIR`), no es un fichero del repositorio y no se versiona (ver D-T10).

### 2.2 Modificados — `src/notebooks/main.ipynb`

| Celda (ancla) | Cambio | Responsabilidad | RF |
|---|---|---|---|
| Catálogo de estaciones (bloque `provincias_eolicas` / `estaciones_meteorologicas_*`, antes de la descarga AEMET) | Reescribir `provincias_fotovoltaicas` con los 5 pares nombre → indicativo y `estaciones_meteorologicas_fotovoltaicas` con coordenadas, planta asignada y distancia. Añadir las constantes `MIN_COBERTURA_SOL_PCT` y `MAX_HUECO_SOL_DIAS`. | Catálogo | RF-1, CA-1.1, CA-1.2 |
| `descargar_aemet(...)` | **Sin cambios.** Ya unifica los diccionarios de estaciones, omite días presentes en BD y espacia peticiones. | Obtención idempotente | RF-2, CA-2.2, CA-2.3, RNF-4, RNF-8 |
| `diagnostico_nulos(...)` | **Sin cambios.** Se reutiliza tal cual sobre el dataframe fotovoltaico; ya imprime % de nulos y hueco máximo. | Diagnóstico | RF-4, CA-4.1 |
| **Nueva celda** justo después de los tres `diagnostico_nulos(...)` | Puerta de validación: valida catálogo, valida valores de `sol` y aborta con `InsolationError` si alguna estación no sirve. | Parada temprana | RF-3, CA-3.1–3.3, CA-7.3 |
| **Nueva celda** entre las features eólicas y el split (o inmediatamente después, sin tocar `df_ml`, `FEATURE_COLS`, `TARGET`, `scaler`, `modelos_fit`) | Construcción de `df_solar_ml` y `FEATURE_COLS_SOLAR`: serie diaria nacional de sol y temperatura, calendario, lags y medias móviles. | Variables solares | RF-5, RF-6 |
| **Nueva celda** de split solar | Corte temporal 80/20 propio (`SPLIT_SOLAR`), sin reutilizar `SPLIT_IDX`. | Partición | RF-8, CA-8.1 |
| **Nueva celda** de entrenamiento y evaluación solar | Entrena los mismos seis algoritmos de referencia con **instancias nuevas**, scaler propio, quintiles propios, tabla comparativa con el mismo formato que la eólica. | Modelo y métricas | RF-8, RF-9 |
| **Nueva celda** al final del notebook | Guarda `lr_solar.joblib` (`{modelo, scaler, features}`), escribe `solar_metrics.json`, reordena el modelo desde disco y verifica métricas; imprime el resumen de trazabilidad. | Persistencia y trazabilidad | RF-10, RF-11 |
| `MEMORY.md` | Añadir el resultado de la ejecución (métricas y estaciones). | Trazabilidad | CA-11.2, criterio 7 |

**Orden en el notebook (deliberado).** La puerta de validación va **antes** de cualquier
entrenamiento y el bloque de modelado solar va **después** del guardado del modelo eólico. Así:

- si la insolación falta, el notebook se detiene antes de refrescar el modelo eólico (decisión
  D-2 y CA-7.3);
- si la insolación existe, el bloque eólico se ejecuta y se guarda exactamente como hoy
  (CA-7.1, CA-7.2), antes de que el bloque solar pueda tocar cualquier nombre global.

---

## 3. Funciones puras de lógica

Todas viven en `src/pipeline/solar.py`, no hacen E/S, no imprimen y no dependen de estado global.
Devuelven datos o lanzan excepciones propias (`CatalogError`, `InsolationError`), nunca `None`
silencioso (RNF-5).

| Función | Entrada → salida | Recibe `hoy` | Responsabilidad | RF / CA |
|---|---|---|---|---|
| `study_window(today, lag_days)` | fecha → (inicio, fin) | **sí** | Ventana de estudio: inicio fijo del proyecto, fin = `hoy − 3 días` (mismo margen que la descarga actual). | RF-2, CA-2.1 |
| `validate_catalog(catalog, download_map)` | listas/dicts → nada o `CatalogError` | no | Exactamente 5 pares planta–estación, sin indicativos duplicados, con coordenadas y distancia, y **coherentes** con el diccionario que usa la descarga. | RF-1, CA-1.1, CA-1.2 |
| `validate_sol_values(df)` | dataframe → nada o `InsolationError` | no | Detecta `sol < 0`, no numérico y `sol > 24`. `sol = 0` es válido. | CE-3, CE-4 |
| `coverage_report(df, stations, variables)` | dataframe → dict | no | % de nulos por estación y variable, hueco máximo consecutivo y días con dato. Misma semántica que `diagnostico_nulos`, pero devolviendo datos en vez de imprimir. | RF-4, CA-4.1 |
| `assert_insolation(report, catalog, min_pct, max_gap)` | dict → nada o `InsolationError` | no | Puerta: 0 % de dato, cobertura < `min_pct` o hueco > `max_gap` ⇒ error con **planta + indicativo + motivo + acción esperada**. | RF-3, CA-3.1–3.3, CE-2 |
| `daily_national_series(df, variables)` | dataframe → dataframe diario | no | Media por fecha de las estaciones **con dato**, más la columna `n_estaciones`. Si un día no tiene ninguna estación, error. No interpola. | RF-5, CA-5.3, CE-1 |
| `build_features(daily, target, lags, windows)` | dataframes → (dataframe, lista de features) | no | Une meteorología y objetivo por fecha, añade calendario, lags, medias móviles, elimina los nulos generados por los lags y devuelve la lista de features **cerrada y ordenada**. | RF-5, RF-6, CA-5.1, CA-5.2, CA-10.3 |
| `temporal_split_index(n, ratio)` | entero → entero | no | Índice de corte cronológico (80 %). | RF-8, CA-8.1 |
| `quintile_edges(y_train, n_bins)` | serie → bordes | no | Bordes de quintiles calculados **solo con train**. | RF-9, CA-8.2 |
| `to_quintiles(values, edges)` | serie → etiquetas | no | Asigna cada valor a su tramo. | RF-9, CA-9.1 |
| `regression_metrics(y_true, y_pred, edges)` | series → dict | no | RMSE, MAE, R², MAPE y accuracy por tramos. El MAPE excluye del denominador los días con objetivo 0 y lo declara. | RF-9, CA-9.1, CE-5 |
| `solar_report(catalog, coverage, metrics, today)` | → dict serializable | **sí** | Registro de trazabilidad: qué estación se asignó a cada planta, cobertura, métricas y fecha de ejecución. | RF-11, CA-11.1, CA-11.2 |

**Reglas de diseño que respetan la constitución 3.** `hoy` solo se pasa a las funciones cuyo
resultado cambia con la fecha; añadirlo a las demás sería un parámetro muerto y rompería el
principio de simplicidad. Ninguna función conoce la base de datos, la red, el notebook ni el DOM.

**Conjunto de features (16, espejo exacto del eólico).** Cerrado, no "al menos":

| Bloque eólico | Equivalente solar |
|---|---|
| `velmedia`, `racha` | `sol`, `tmed` |
| `mes`, `dia_semana`, `dia_año` | `mes`, `dia_semana`, `dia_año` |
| `eolica_lag1/2/3/7` | `solar_lag1/2/3/7` |
| `vel_ma3/7/14`, `racha_ma3/7/14` | `sol_ma3/7/14`, `tmed_ma3/7/14` |
| `eolica_ma7` (sobre el target desplazado) | `solar_ma7` (sobre el target desplazado) |

`tmin` y `tmax` se descargan y se diagnostican (RF-2) pero **no entran como feature** mientras
D-3 siga abierta: el esquema eólico usa dos variables meteorológicas y el espejo exige dos.

---

## 4. Algoritmo en pseudocódigo

### 4.1 Bloque A — validación (temprano, antes de entrenar nada)

```
AL INICIO DEL PROCESO
    ventana ← (FECHA_INI, hoy − 3 días)          # study_window
    catálogo ← 5 pares planta–estación           # RF-1
    validate_catalog(catálogo, provincias_fotovoltaicas)
        SI nº de pares ≠ 5 → CatalogError
        SI indicativo repetido → CatalogError
        SI catálogo y diccionario de descarga no coinciden → CatalogError

DESCARGAR (sin cambios: descargar_aemet omite días ya presentes en BD)

LEER aemet_diario y filtrar estaciones fotovoltaicas

validate_sol_values(df_fv)                        # negativos, texto, > 24 h

informe ← coverage_report(df_fv, catálogo, [sol, tmed, tmin, tmax])
MOSTRAR informe (estación × variable: % nulos, hueco máximo, días con dato)

assert_insolation(informe, catálogo, MIN_COBERTURA_SOL_PCT, MAX_HUECO_SOL_DIAS)
    PARA CADA estación DEL catálogo:
        SI no hay ningún valor de sol en la ventana:
            → InsolationError("planta X / indicativo Y: sin insolación; revisar o sustituir")
        SI cobertura(sol) < MIN_COBERTURA_SOL_PCT:
            → InsolationError(... + "cobertura 47,2 % < 90 %")
        SI hueco_máximo(sol) > MAX_HUECO_SOL_DIAS:
            → InsolationError(... + "828 días consecutivos sin dato")
    # cualquier error detiene el notebook aquí: no se entrena ni eólico ni solar
```

### 4.2 Bloque B — modelado (al final, con nombres propios)

```
diario ← daily_national_series(df_fv, [sol, tmed])
    PARA CADA fecha DEL calendario completo entre inicio y fin:
        disponibles ← estaciones CON valor ese día
        SI disponibles = ∅ → InsolationError(fecha)
        valor ← media de disponibles        # nunca se interpola ni se rellena
        n_estaciones ← |disponibles|

objetivo ← generación diaria peninsular "Solar fotovoltaica"
           (misma extracción y misma convención de fecha que "Eólica")

SI rango(objetivo) ⊄ rango(diario) → INFORMAR del recorte antes de entrenar
datos ← merge(diario, objetivo, por fecha)        # intersección
datos ← datos SIN nulos en sol, tmed ni objetivo
INFORMAR días descartados y rango común

(df_solar, FEATURE_COLS_SOLAR) ← build_features(datos)
    calendario: mes, dia_semana, dia_año
    PARA lag EN [1,2,3,7]: solar_lagN ← objetivo desplazado N días
    PARA w EN [3,7,14]:    sol_maW   ← media móvil de sol, ventana W
                            tmed_maW  ← media móvil de tmed, ventana W
    solar_ma7 ← media móvil de (objetivo desplazado 1 día), ventana 7
    eliminar filas con nulos generados por los lags
    # los desplazamientos se hacen sobre fechas consecutivas: un hueco
    # elimina la fila, nunca desplaza los retardos

SPLIT_SOLAR ← temporal_split_index(n, 0.80)
train, test ← primeras SPLIT_SOLAR filas / resto
INFORMAR nº de días y rango de fechas de cada parte

scaler_solar ← nuevo StandardScaler()            # nunca el scaler eólico
ajustar scaler_solar SOLO con train
bordes ← quintile_edges(y_train)                 # SOLO con train

PARA CADA algoritmo EN [LinearRegression, Ridge, Lasso, RandomForest,
                        XGBoost, LightGBM]:
    instancia ← NUEVA instancia (no reutilizar las del bloque eólico)
    entrenar con train (escalado solo los lineales)
    predecir test
    métricas ← regression_metrics(y_test, pred, bordes)
MOSTRAR tabla comparativa con el mismo formato que la tabla eólica
COMPARAR contra el modelo de referencia trivial (media de train)

guardar lr_solar.joblib = {modelo: LinearRegression ajustado,
                           scaler: scaler_solar,
                           features: FEATURE_COLS_SOLAR}
recargar desde disco y verificar que reproduce las mismas métricas de test
escribir solar_metrics.json = solar_report(catálogo, informe, métricas, hoy)
MOSTRAR resumen de trazabilidad (planta → estación → cobertura → métricas)
```

---

## 5. Cómo se pinta en la interfaz

**No aplica.** La spec §7 excluye expresamente este apartado: *"Fuera de alcance: exponer la
predicción solar en la API o en la interfaz web"*. No se añaden endpoints, ni gráficos, ni
componentes; el backend y el frontend no se tocan.

Lo único que "se pinta" es la **salida del propio proceso**: el informe de cobertura por
estación (RF-4), la tabla comparativa de modelos con el mismo formato que la eólica (RF-9) y el
resumen de trazabilidad (RF-11). Todo en la consola del notebook, en español.

Si en el futuro se quisiera exponer, haría falta una spec nueva: esta funcionalidad termina en
el `.joblib`.

---

## 6. Decisiones técnicas y alternativas descartadas

| # | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|
| D-T1 | Lógica pura en `src/pipeline/solar.py`; el notebook solo orquesta. | Es la única forma de cumplir el principio 3 (lógica separada) y el 4 (tests) sin duplicar código. | **Todo dentro del notebook**: cero archivos nuevos, pero la lógica queda acoplada a celdas con estado global y no se puede probar. Descartada. |
| D-T2 | La puerta de tests es `node --test`, que invoca `python -m unittest` y falla si éste falla. | Cumple literalmente el principio 4 (`node --test`, sin instalar paquetes) sin reimplementar la lógica. Node 24 ya está en el entorno. | **Reimplementar las funciones en JS para probarlas**: duplica la lógica y garantiza divergencia. **Solo `unittest`**: incumple el principio 4. Ambas descartadas. |
| D-T3 | Si falta `sol` en una estación: error y parada. Si falta en un día concreto: media de las estaciones disponibles; si no hay ninguna, error. | Respeta la decisión del usuario (nada de imputar) y evita que un hueco puntual de una estación invente un valor. | **Interpolar por estación** (como el viento): contamina el target con datos fabricados. **Rellenar con ERA5**: prohibido en la spec §7. Ambas descartadas. |
| D-T4 | Umbrales `MIN_COBERTURA_SOL_PCT = 90` y `MAX_HUECO_SOL_DIAS = 7`, como parámetros nombrados. | Calibrados con los datos reales: `5783` tiene 94,6 % y hueco de 3 días (pasa); `9574B` 47,2 % y 828 días (no pasa); `3463Y`, `4427X`, `7012C` 0 % (no pasan). Un umbral de 0 % haría fallar siempre al pipeline. | **Cualquier ausencia aborta**: imposible con estaciones reales. **Umbral fijo incrustado**: si mañana se ajusta, hay que tocar código. Descartadas. Valor final pendiente de D-1. |
| D-T5 | Dos estructuras vivas: `provincias_fotovoltaicas` (dict que consume la descarga) y `estaciones_meteorologicas_fotovoltaicas` (lista con coordenadas que consume el análisis), con una comprobación de coherencia. | `descargar_aemet` ya recorre los tres diccionarios; cambiarlo afectaría al bloque eólico. | **Unificar en un solo catálogo**: más limpio, pero cambia una firma compartida y arriesga CA-7.1. Descartada. |
| D-T6 | El modelo solar se entrena con las **mismas seis familias** que el eólico y se guarda el `LinearRegression`. | CA-9.3 exige presentarlo junto a los modelos de referencia en el mismo formato; el proyecto ya eligió LinearRegression como modelo de producción por interpretabilidad. | **Solo LinearRegression**: incumple CA-9.3. **Guardar el mejor por RMSE**: rompe la comparabilidad y el criterio de producción. Descartadas. |
| D-T7 | Instancias **nuevas** de cada algoritmo y `StandardScaler` **nuevo** para el bloque solar. | `evaluar()` hace `fit()` sobre el objeto recibido: reutilizar `modelos_fit` reentrenaría los modelos eólicos con datos solares y corrompería el `.joblib` eólico (CA-7.2, CA-10.2). | **Reutilizar `modelos_fit` y `scaler`**: efecto colateral silencioso, imposible de detectar por las métricas impresas. Descartada. |
| D-T8 | Quintiles propios (`quintile_edges(y_train_solar)`), no `BIN_EDGES`. | `BIN_EDGES` está calculado sobre la eólica (~100.000–300.000 MWh); con el objetivo solar daría una accuracy sin sentido. | **Reutilizar `to_bins`**: métrica engañosa. Descartada. |
| D-T9 | Nombres con sufijo `_SOLAR` / `_solar` y bloque al final del notebook. | Evita que `FEATURE_COLS`, `TARGET`, `df_ml` o `SPLIT_IDX` se sobrescriban antes del guardado eólico (CA-7.2, CA-10.2, CA-10.3). | **Intercalar el bloque solar antes del split eólico**: reutiliza nombres y arriesga pisar el modelo en silencio. Descartada. |
| D-T10 | `lr_solar.joblib` junto a `lr_eolica.joblib` en `MODEL_DIR`; no se copia a las otras rutas del proyecto. | El despliegue y las copias del `.joblib` están fuera de alcance (spec §7). Copiarlo a `modelos/` daría la falsa impresión de que el backend ya lo usa. | **Copiarlo a las cuatro rutas**: toca artefactos de producción sin cambiar el backend. Descartada. |
| D-T11 | Se replica la convención de fecha del bloque eólico (`datetime` → `YYYY-MM-DD`), sin corregir el posible desfase UTC/local. | Corregirlo obligaría a reentrenar el modelo eólico y cambiaría sus métricas (RF-7, RNF-2). | **Corregir el desfase para el bloque solar**: los dos modelos dejarían de ser comparables y el eólico quedaría desalineado. Descartada; se registra como riesgo. |
| D-T12 | `solar_metrics.json` como soporte del registro (RF-11), más una línea en `MEMORY.md`. | CA-11.1/11.2 piden que quede constancia; un JSON es verificable por máquina y no depende de que alguien copie la salida de la consola. | **Solo imprimir por consola**: se pierde al cerrar el notebook. Descartada. |

---

## 7. Estrategia de tests

**Puerta única del proyecto:** `node --test` (constitución, principio 4). `gate.test.mjs` lanza
`python -m unittest discover -s src/pipeline/tests -p "test_*.py"` y falla si el código de salida
es distinto de 0, mostrando la salida de Python. No se instala ningún paquete: `unittest` es
biblioteca estándar y Node 24 ya está disponible.

```bash
node --test "src/pipeline/tests/*.test.mjs"    # puerta (Node 24 no acepta el directorio a secas)
python -m unittest discover -s src/pipeline/tests -v   # diagnóstico directo
```

Regla de trabajo: no se avanza con la puerta en rojo. Los tests son de lógica pura, sin red, sin
SQLite y sin notebook; usan series sintéticas de 10–40 días construidas a mano.

| # | Caso | Espera | RF / CA |
|---|---|---|---|
| T-1 | Catálogo con 5 pares correctos | no lanza | CA-1.1 |
| T-2 | Catálogo con un indicativo repetido | `CatalogError` con el indicativo | CA-1.1 |
| T-3 | Catálogo sin coordenadas o sin distancia | `CatalogError` | CA-1.2 |
| T-4 | Catálogo que no coincide con el diccionario de descarga | `CatalogError` | RF-1, D-T5 |
| T-5 | Serie con 3 días nulos de 30 | informe con 10 % y hueco 3 | CA-4.1 |
| T-6 | Estación con `sol` al 100 % nulo | `InsolationError` con planta e indicativo | CA-3.1, CA-3.3 |
| T-7 | Estación con 47 % (caso CASPE) y umbral 90 | `InsolationError` que cita la cobertura | CE-2, D-T4 |
| T-8 | Estación con 94,6 % y hueco de 3 días | pasa la puerta | D-T4 |
| T-9 | `sol = 0.0` | valor válido, no nulo | CE-3 |
| T-10 | `sol = 30` y `sol = -1` | error de rango | CE-4 |
| T-11 | Día con 3 de 5 estaciones | media de las 3 y `n_estaciones = 3` | CA-5.3 |
| T-12 | Día sin ninguna estación | `InsolationError` con la fecha | CA-5.3 |
| T-13 | Serie con hueco interno | la fila se elimina; `solar_lag7` sigue siendo el valor de 7 días naturales antes | CA-5.3 |
| T-14 | Comprobación de no fuga | ninguna feature de la fila *t* usa el objetivo de *t* ni posterior | CA-5.2 |
| T-15 | Lista de features | exactamente 16 y en el orden declarado | CA-5.1, CA-10.3 |
| T-16 | 10 filas, ratio 0,80 | corte en 8; train anterior a test; sin solape | CA-8.1 |
| T-17 | Métricas con valores calculados a mano | RMSE, MAE y R² exactos | CA-9.1 |
| T-18 | Objetivo con un día a 0 | el MAPE no divide por cero y declara el día excluido | CE-5 |
| T-19 | Dos ejecuciones con la misma entrada | resultados idénticos | RNF-3 |
| T-20 | Registro de trazabilidad | 5 pares planta–estación, cobertura y fecha de ejecución | CA-11.1, CA-11.2 |

**Verificación manual (no automatizable sin red):** ejecutar el notebook completo y comprobar
(a) que las métricas eólicas coinciden con las registradas —RMSE 59.150,8 · MAE 45.986,5 ·
R² 0,5931—, (b) que se genera `lr_solar.joblib` sin alterar `lr_eolica.joblib`, y (c) que forzar
una estación sin `sol` detiene el notebook antes de entrenar. Esto cierra el criterio 5 y el 6.

---

## 8. Trazabilidad RF → piezas del plan

| RF | Requisito | Dónde se cubre | Tests |
|---|---|---|---|
| RF-1 | Catálogo planta–estación | catalogo del notebook + `validate_catalog` | T-1 … T-4 |
| RF-2 | Obtención del histórico | `descargar_aemet` (sin cambios) + `study_window` | T-5 (datos), verificación manual |
| RF-3 | Validación de insolación | celda de puerta + `assert_insolation` | T-6, T-7, T-8 |
| RF-4 | Diagnóstico de cobertura | `diagnostico_nulos` + `coverage_report` | T-5 |
| RF-5 | Variables fotovoltaicas | `daily_national_series` + `build_features` | T-11 … T-15 |
| RF-6 | Objetivo del modelo | extracción del target + recorte informado en `build_features` | T-13, T-15 |
| RF-7 | Alineación con el pipeline | orden de celdas, nombres con sufijo, instancias nuevas | T-19 + verificación manual |
| RF-8 | Entrenamiento | celda de split y entrenamiento + `temporal_split_index` | T-16 |
| RF-9 | Evaluación | celda de evaluación + `regression_metrics` | T-17, T-18 |
| RF-10 | Persistencia | celda de guardado (`lr_solar.joblib`) | T-15, verificación manual |
| RF-11 | Trazabilidad | `solar_report` + `solar_metrics.json` + `MEMORY.md` | T-20 |

Criterios de finalización de la spec: 1 y 2 → verificación manual + T-1; 3 → T-5; 4 → T-17;
5 → verificación manual (a); 6 → T-6; 7 → T-20 y `MEMORY.md`.

---

## 9. Riesgos y dudas que bloquean

| # | Riesgo | Impacto | Mitigación en el plan |
|---|---|---|---|
| R-1 | **D-1 abierta**: no hay umbral de huecos acordado. | El valor 90 % / 7 días es provisional; si se cambia, solo se toca una constante. | Parámetros nombrados, no números incrustados. |
| R-2 | **D-2 confirmada pero frágil**: un fallo solar impide refrescar el eólico. | Un rate limit de AEMET un día cualquiera deja el modelo eólico sin actualizar. | La puerta solo aborta por datos, no por red: los errores de descarga ya se agrupan y se informan; el operador puede relanzar. Aun así, conviene revisar D-2. |
| R-3 | **D-3 abierta**: ¿entran `tmin`/`tmax`? | El plan los descarga y diagnostica, pero no los usa. | El conjunto de 16 es cerrado y documentado; añadirlos sería un cambio de spec, no de plan. |
| R-4 | **D-6 abierta**: la constitución es de otro proyecto. | `node --test` se cumple vía adaptador; "código en inglés" se aplica solo al módulo nuevo. | D-T2 y tabla del apartado 1. |
| R-5 | **D-7 abierta**: no hay R² mínimo aceptable. | El plan informa métricas y las compara con el modelo trivial, pero no bloquea. | La comparación con la media de train deja el juicio a la vista. |
| R-6 | **Coste de la primera descarga**: `dias_por_tramo = 3` sobre ~4,5 años son ~545 peticiones **por estación**, con pausas de 15–70 s. Cinco estaciones nuevas ⇒ varias horas. | Primera ejecución muy lenta; riesgo de rate limit. | No se cambia el parámetro (afecta al bloque eólico). Se recomienda lanzar la descarga aparte y después el modelado. Decisión de ampliar el tramo: pendiente, no incluida. |
| R-7 | **Desfase de fecha REE**: la serie diaria viene etiquetada a las 23:00 UTC del día anterior. | Un día de desfase en el target, igual que en el modelo eólico. | Se replica la convención (D-T11); corregirla exigiría reentrenar el eólico. |
| R-8 | **`sol` de `4452` y `9434` sin verificar** (clave AEMET caducada). | Si no publican insolación, la puerta aborta el notebook entero. | Es el comportamiento pedido; la puerta lo dirá con planta e indicativo. Conviene verificar antes de implementar. |
| R-9 | Los datos `sol` pueden venir en décimas de hora o minutos si AEMET cambia la unidad. | Features con escala absurda, sin error visible. | `validate_sol_values` acota 0–24; un cambio de unidad a minutos lo detectaría como error. |

---

## 10. Orden de implementación (cada paso verificable)

1. Crear `src/pipeline/solar.py` con las funciones puras y `src/pipeline/tests/test_solar.py`.
2. Crear `gate.test.mjs` y poner la puerta en verde (`node --test`).
3. Actualizar el catálogo del notebook y añadir la celda de puerta de validación.
4. Ejecutar solo descarga + diagnóstico y comprobar las cinco estaciones (aquí se resuelven R-6 y R-8).
5. Añadir features y split solar; comprobar que el bloque eólico sigue dando las mismas métricas.
6. Añadir entrenamiento, evaluación y guardado; comprobar `lr_solar.joblib` y `solar_metrics.json`.
7. Actualizar `MEMORY.md` con estaciones, cobertura y métricas.

Ningún paso requiere dependencias nuevas (RNF-7) ni toca `backend/` o `frontend/`.
