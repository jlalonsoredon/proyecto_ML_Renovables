# Plan 004 — Previsión de fuentes y predicción propia en `src/`

Deriva de `spec.md` (RF-1 a RF-6). Respeta `docs/constitution.md`: todo en `src/`
(principio 1), lógica pura con `hoy` como parámetro (principio 4), puerta
`node --test` (principio 5), datos a salvo con copia previa (principio 6), español en
interfaz y documentación (principio 7, con la tensión ya conocida sobre comentarios).
Ningún RF se implementa sin su CA; las dudas abiertas se resuelven aquí como
**decisiones propuestas con punto de parada** (principio 2: se para y se pregunta).

## 1. Archivos que se crean o modifican

| Archivo | Acción | Responsabilidad | RF |
|---|---|---|---|
| `src/pipeline/prevision_db.py` | **crear** | Esquema y E/S de `prediccion_diaria` y `prediccion_propia`. Solo stdlib (`sqlite3`, `json`), sin pandas: testable en la puerta. Sin `DELETE` en `prediccion_diaria`. | RF-1, RF-2 |
| `src/pipeline/prevision.py` | **crear** | Lógica pura: mapa de orígenes por variable, ventanas mixtas con desglose por día, actualización de `real_mwh`. Recibe `hoy` como parámetro; sin reloj, sin red, sin pandas. | RF-4, CA-2.3, CA-2.4 |
| `src/pipeline/tests/test_prevision_db.py` | **crear** | Esquema idempotente, upsert sin duplicar, elaboración nueva se añade, sin elaboración marcada y no elegible, sustitución mismo día, histórico entre días, `real_mwh` y `error_mwh`. | RF-1, RF-2 |
| `src/pipeline/tests/test_prevision.py` | **crear** | Mapa de orígenes: calendario siempre `observacion`, `velmedia`/`racha` siempre `prevision`, ventana mixta con desglose, ventana imposible → no disponible, lag con hueco, `real` solo desde `generacion`. | RF-4, RF-5 |
| `src/notebooks/main.ipynb` | **modificar** | Celdas nuevas insertadas (RNF-4): captura (RF-3), mapa de orígenes y vector de mañana (RF-4), guardado de la predicción propia (RF-2), actualización de `real_mwh` tras la descarga REE (CA-2.3). Sin reordenar ni renombrar etapas. | RF-2, RF-3, RF-4 |
| `src/data/ree_generacion.db` | **modificar** | Dos tablas nuevas; las de observación no cambian de esquema. Copia previa obligatoria antes de la primera migración (RNF-1). | RF-1, RF-2 |
| `specs/004-predicciones-en-src/tasks.md` | **crear** (siguiente paso) | Tareas con ciclo test-rojo → verde. | — |
| `MEMORY.md` | **modificar** (al cerrar) | Decisión, métricas y estado del archivo (CA-6.2). | RF-6 |

**No se toca** (RNF-1): `backend/`, `frontend/`, `render.yaml`, las 3 copias de
producción del `.joblib`, y `src/pipeline/forecast.py` (tiene copia vendorizada en el
backend con test de paridad: tocarla aquí rompería la paridad).

## 2. Funciones puras de lógica (con `hoy` como parámetro)

En `src/pipeline/prevision.py` (reutiliza sin tocar `forecast.py`:
`choose_forecast`, `national_series`, `moving_average`, `forecast_rows`,
`parse_daily_parte`, `parse_hourly_parte` — RF-3, CA-1.5):

| Función | Firma | Qué devuelve | RF |
|---|---|---|---|
| `resolver_origenes` | `(obs_meteo, obs_solar, obs_gen, prev, objetivo, hoy, permitir_prev_gen) -> dict` | El "mapa": variable → `{valor, origen}` o `None` si no disponible. Núcleo de RF-4. | RF-4 |
| `ventana_mixta` | `(serie_obs, serie_prev, objetivo, dias, hoy) -> (valor, origen) \| None` | Ventana de `dias` terminada en `objetivo`: observación donde existe y previsión en los huecos; `mixta` si participan ambas. `None` si algún día no está en ninguna fuente (CA-4.1, D-4-8). | RF-4 |
| `origen_variable` | `(nombre, valor_obs, valor_prev) -> str` | `observacion` si hay dato observado; `prevision`/`estimada` si no. Las ventanas con ambas fuentes se declaran `mixta` (CA-4.4, CA-4.5). | RF-4 |
| `reales_pendientes` | `(predicciones, generacion, hoy) -> list` | Predicciones cuyo objetivo ya tiene generación publicada completa y `real_mwh` vacío (CA-2.3). El real sale **solo** de `generacion` (observación), nunca de `prediccion_diaria`. | RF-2, RF-5 |
| `con_error` | `(prediccion_mwh, real_mwh) -> float` | `error_mwh = real - prediccion`; sin real no se rellena (CE-7). | RF-2 |

En `src/pipeline/prevision_db.py` (E/S, no puras pero stdlib y testables en memoria):

| Función | Qué hace | RF |
|---|---|---|
| `ensure_schema(conn)` | Crea las dos tablas, idempotente. | RF-1, RF-2 |
| `save_forecast_rows(conn, filas, fuente)` | Upsert por `(fuente, elaborado, objetivo, ubicacion)`: misma elaboración sustituye sus valores, nueva añade. Sin `DELETE` (CA-1.3). | RF-1 |
| `save_own_prediction(conn, fila)` | Inserta o **sustituye** por `(fecha_objetivo, fecha_emision)` (CA-2.2; ver decisión 3). | RF-2 |
| `predictions_without_real(conn, hoy)` | Lista las que tienen objetivo ya publicado y `real_mwh` nulo. | RF-2 |
| `update_real(conn, objetivo, real_mwh)` | Escribe `real_mwh` y `error_mwh`; jamás toca `prediccion_mwh` (CA-2.3). | RF-2 |
| `rows_between(conn, fuente, desde, hasta)` | Lectura del archivo por fuente y rango. | RF-1, RF-4 |

## 3. Algoritmo del mapa (pseudocódigo)

Núcleo de RF-4. Construye el vector de mañana declarando el origen de cada variable.

```
MAPA_ORIGENES(objetivo, hoy, permitir_prev_gen):              # RF-4, CA-4.1–CA-4.5
    entradas:
        obs_meteo  ← {fecha: (velmedia, racha)}   # aemet_diario, media estaciones
        obs_solar  ← {fecha: (sol, tmed)}         # serie_solar (observación)
        obs_gen    ← {fecha: MWh}                 # generacion; días incompletos
                                                  #   descartados por RF-12
        prev_viento, prev_racha, prev_sol, prev_tmed
                   ← national_series(prediccion_diaria, fuente='aemet',
                                      elegida por choose_forecast)   # regla única 003
        prev_gen   ← {fecha: MWh}                 # prediccion_diaria, fuente='ree'

    mapa ← {}
    # Calendario: siempre del día objetivo, nunca estimado (CA-4.5)
    mapa["mes"], mapa["dia_semana"], mapa["dia_año"] ← calendario(objetivo), "observacion"

    # Viento y racha del día objetivo: mañana NO se puede observar → siempre previsión
    si objetivo in prev_viento y prev_racha:
        mapa["velmedia"] ← prev_viento[objetivo], "prevision"
        mapa["racha"]    ← prev_racha[objetivo],  "prevision"
    si no:
        mapa["velmedia"], mapa["racha"] ← NO_DISPONIBLE     # sin respaldo (CE-3)

    # Medias móviles: cada día observación si existe, previsión si no (CA-4.1, D-4-8)
    para cada (nombre, serie_obs, serie_prev, dias) en [
        ("vel_ma3", obs_viento, prev_viento, 3), …, ("racha_ma14", obs_racha, prev_racha, 14)]:
        para cada día de la ventana(dias, objetivo):
            si día <= hoy y en serie_obs: valor ← serie_obs[día]      # días_observados += 1
            si no, si en serie_prev:     valor ← serie_prev[día]      # días_previstos += 1
            si no:                       mapa[nombre] ← NO_DISPONIBLE  # sin interpolar ni acortar
        origen ← observacion | prevision | mixta según las fuentes usadas
        mapa[nombre] ← media(valores), origen (+ desglose si mixta)

    # Sol y temperatura del día anterior (CA-4.2)
    si (objetivo - 1) in obs_solar:
        mapa["sol_lag1"], mapa["tmed_lag1"] ← obs_solar[objetivo-1], "observacion"
    si no, si (objetivo - 1) in prev_sol / prev_tmed:
        mapa["sol_lag1"]  ← prev_sol[objetivo-1],  "estimada"   # sol previsto es proxy
        mapa["tmed_lag1"] ← prev_tmed[objetivo-1], "prevision"  # tmed viene directa
    si no:
        NO_DISPONIBLE

    # Generación: última publicada completa; hueco solo con previsión REE si D-4-3 lo admite
    ancla ← ultimo_dia_completo(obs_gen)                     # RF-12 (ya existe)
    para cada lag en (1, 2, 3, 7):
        dia ← ancla - (lag - 1)
        si dia in obs_gen:                    mapa[f"eolica_lag{lag}"] ← obs_gen[dia], "observacion"
        si no, si permitir_prev_gen y dia in prev_gen:
                                              mapa[f"eolica_lag{lag}"] ← prev_gen[dia], "prevision"
        si no:                                NO_DISPONIBLE
    eolica_ma7 ← misma regla sobre la ventana de 7 que termina en ancla

    si alguna variable es NO_DISPONIBLE:
        avisar(lista de variables sin origen)               # honestidad, RNF-2
    devolver mapa
```

Propiedades que fija el algoritmo: la mezcla solo existe **entre variables** (cada una
con su origen declarado, CE-4), nunca **dentro de una ventana** ni de una variable;
`velmedia`/`racha` son `prevision` por naturaleza aunque haya observación reciente;
sin dato no se inventa.

## 4. Cómo se pinta en la interfaz

No hay interfaz web (fuera de alcance, §7). La superficie es la **salida del notebook**:

| Celda | Qué imprime | RF |
|---|---|---|
| Captura (RF-3) | Resumen por fuente: filas guardadas, horizonte obtenido, días pendientes, incidencias con causa; aviso visible si ambas fuentes fallan (CA-3.3, CA-3.5) | RF-3, RF-6 |
| Mapa de orígenes (RF-4) | Tabla variable → valor + origen (`observacion` 🟢 / `prevision` 🔵 / `estimada` 🟡), y aviso con las variables no disponibles si las hay (CA-4.4) | RF-4, RF-6 |
| Guardado predicción (RF-2) | Confirmación con `fecha_objetivo`, modelo, nº de variables y recuento de orígenes | RF-2, RF-6 |
| Actualización de reales (CA-2.3) | Cuántas predicciones reciben `real_mwh` en esta ejecución y MAE de las últimas N (CA-2.4) | RF-2 |

## 5. Decisiones técnicas (y alternativa descartada)

1. **Dos módulos nuevos en `src/pipeline/` en vez de tocar `forecast.py`.** El canónico
   tiene copia vendorizada en el backend con test de paridad: modificarlo aquí exigiría
   tocar el backend (prohibido, RNF-1) o romper la paridad. *Descartada:* añadir las
   funciones a `forecast.py`.
2. **Tabla única `prediccion_diaria` con el esquema de la spec 003 + `fuente` +
   `eolica_mwh` + `uso`.** Las funciones puras de `forecast.py` reciben filas como
   dicts e ignoran las claves extra (`fuente`, `eolica_mwh`), así que se reutilizan sin
   tocarlas y CA-1.5 se cumple de verdad (cierra QA nº 15). `uso` se conserva
   (`eolica`/`solar` en AEMET, `generacion` en REE) para `national_series`. *Descartada:*
   dos tablas (D-4-2, pendiente de confirmación del usuario, P-3).
3. **Clave de `prediccion_propia` = `(fecha_objetivo, fecha_emision)`** (fecha, no
   timestamp): reejecutar el mismo día sustituye (CA-2.2) sin duplicar, y días distintos
   conservan el histórico (cierra QA nº 6). Se registra además `emitida_en` completa.
   *Descartada:* clave con hora (duplicaba) — el precio, perder la emisión intradiaria
   anterior, se acepta y se documenta (QA nº 17).
4. **La captura AEMET se implementa en el notebook** con el patrón de dos pasos que ya
   usa PASO 7 y el parseo puro y testeado de `forecast.py`. *Descartada:* importar
   `backend/app/services/aemet_forecast.py` (arrastra pandas, import relativo, y viola
   el espíritu de RNF-1; cierra QA nº 18).
5. **`real_mwh` se actualiza en la propia ejecución del notebook**, tras la descarga de
   REE, y solo desde `generacion` (cierra QA nº 8 y nº 29). *Descartada:* proceso aparte.
6. **Captura REE tras punto de parada P-1:** primero se mide qué publica ESIOS/apidatos
   (indicador, horizonte, marca de elaboración) y se documenta en el Anexo; solo
   entonces se implementa CA-3.2 (D-4-1). *Descartada:* capturar a ciegas con un
   indicador supuesto (podría no declarar elaboración y sería inelegible por CA-1.4).
7. **Integridad de observación reinterpretada** (cierra QA nº 21): el criterio 5 se
   verifica como «las únicas funciones que escriben en `generacion`/`aemet_diario` son
   las dos descargas ya existentes» (comprobación estática en tests + recuento de
   sentencias), no como huella inmutable, porque el propio notebook las hace crecer
   legítimamente. **Requiere enmienda menor de la spec** (criterio 5), marcada aquí.
8. **Timestamps en hora local peninsular** (`emitida_en`, `capturado_en`), coherente con
   la constitución (cierra QA nº 27).
9. **La predicción archivada es la del modelo de producción del notebook** (LR con las
   18 variables que guarda PASO 8), no las de los 9 modelos del ranking (cierra QA nº 7).
10. **`velmedia`/`racha` se declaran siempre `prevision`** en el mapa (mañana no es
    observable), lo que hace explícito que el vector de producción siempre mezcla
    orígenes entre variables (cierra QA nº 19: la regla anti-mezcla se aplica a ventanas
    y variables, no al vector completo).

## 6. Estrategia de tests (`node --test`)

La puerta `gate.test.mjs` descubre `src/pipeline/tests/test_*.py` automáticamente; los
módulos nuevos usan solo stdlib, así que corren con el Python del sistema (sin pandas):

| Suite | Cubre | RF/CA |
|---|---|---|
| `test_prevision_db.py` | Esquema idempotente (2×), upsert sin duplicar, elaboración nueva se añade y conserva la anterior, fila sin elaboración marcada y no elegible, sustitución mismo día, histórico entre días, `update_real` calcula `error_mwh` y no toca `prediccion_mwh`, real nunca se rellena a mano | CA-1.2–1.4, CA-2.2–2.4, CE-6, CE-7, CE-8 |
| `test_prevision.py` | Calendario siempre `observacion`; `velmedia`/`racha` siempre `prevision`; ventana íntegra de observación; ventana con huecos completada con previsión y marcada `mixta` con su desglose; nunca usa observación posterior a `hoy`; ventana imposible → no disponible sin acortar; lag con hueco sin REE → no disponible; con previsión REE (D-4-3) → `prevision`/`mixta`; `reales_pendientes` solo mira `generacion`; día incompleto descartado por RF-12 no sirve de ancla | CA-4.1–4.5, CA-5.1, CE-1–CE-5 |
| Verificación manual (como en spec 003) | Descarga real AEMET (y REE tras P-1), dos ejecuciones el mismo día sin duplicar, notebook completo, integridad de `generacion`/`aemet_diario` por recuento de escritores | RF-3, RF-5, criterios §8 |

## 7. Puntos de parada (principio 2)

- **P-1 — D-4-1 (fuente REE):** antes de implementar CA-3.2 se mide ESIOS/apidatos y se
  documenta; si no hay previsión utilizable, la spec se reduce a AEMET + predicción
  propia y se informa.
- **P-2 — D-4-3 (previsión REE en lags):** `permitir_prev_gen` queda en `False` hasta
  que el usuario decida; el mapa ya contempla las dos vías y el test cubre ambas.
- **P-3 — D-4-2/D-4-4/D-4-5:** tabla única, captura backend dormida y retención total
  quedan como decisiones propuestas pendientes de confirmación expresa del usuario.
- **Enmienda de spec pendiente:** criterio 5 de §8 (ver decisión 7) y el alcance de
  CA-4.3 (condicionado a D-4-3). Se proponen al usuario junto con este plan.

## 8. Cobertura de requisitos

| RF | Dónde se cubre |
|---|---|
| RF-1 | `prevision_db.py` + `test_prevision_db.py` + celda de captura (CA-3.1) |
| RF-2 | `prevision_db.py` (`save_own_prediction`, `update_real`) + `prevision.py` (`reales_pendientes`, `con_error`) + celda de guardado y celda de reales |
| RF-3 | Celdas de captura en el bloque de descarga + `forecast.py` (parseo, sin tocar) |
| RF-4 | `prevision.py` (mapa) + celda del vector de mañana + `test_prevision.py` |
| RF-5 | Diseño (sin escritores nuevos) + verificación estática en tests + `reales_pendientes` solo con `generacion` |
| RF-6 | Resúmenes de captura, tabla de orígenes, confirmación de guardado, `MEMORY.md` al cerrar |
