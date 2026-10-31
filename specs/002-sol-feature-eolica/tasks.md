# Tareas 002 — La insolación como variable del modelo eólico

Derivadas de `spec.md` (RF-1 a RF-10) y `plan.md` (archivos, funciones puras y algoritmos). Cada tarea
cabe en 20–30 minutos y deja el repositorio en un estado verificable. El orden es de dependencia: no se
empieza una tarea si la anterior no está en verde.

**Puerta permanente:** `node --test "src/pipeline/tests/*.test.mjs"` en verde al cerrar cada tarea de
lógica. Prohibido avanzar con la puerta en rojo (RNF-7).

**Restricción de alcance:** se pueden modificar celdas del notebook, pero no su estructura ni la lógica
global (RNF-1). El bloque eólico (celdas 63–84) conserva su orden y sus nombres.

**Alcance acordado el 2026-10-31:** primero el notebook y sus tests; **backend, frontend y producción
no se tocan sin autorización expresa**. Por eso T-17 queda aplazada aunque el criterio haya aceptado.

**Dos notas de lectura de la spec**

- **CA-8.2** ("las celdas anteriores deben quedar idénticas") describe el estado **en el momento de la
  retirada** (T-02). Las modificaciones posteriores de las celdas 21, 52 y 64 son las que exigen T-04,
  T-07 y T-10, cada una con su propia verificación. No hay contradicción: son momentos distintos.
- **CA-8.1** ("85 celdas") es el conteo tras T-02. T-10 y T-15 pueden añadir celdas nuevas; el criterio
  se refiere a que el notebook deja de tener el bloque solar, no a un número congelado.

---

## Fase 0 — Precondiciones

- [x] **T-01 · Copia de seguridad y puerta en verde** · 15 min · RNF-7
  - **Estado:** ✅ 2026-10-31 · puerta 16/16 y tres copias en `%TEMP%/opencode/backup-002-20261031/`.
  - **Qué:** verificar la puerta y guardar copia de `src/data/ree_generacion.db`,
    `src/data/modelos/lr_eolica.joblib` y `modelos/lr_eolica.joblib` en el directorio temporal.
  - **Depende de:** nada. **Bloquea:** todo.
  - **Hecho cuando:** `node --test "src/pipeline/tests/*.test.mjs"` da 16/16 y existen las tres copias
    con su ruta anotada en `MEMORY.md`.

- [x] **T-02 · Retirar el bloque solar del notebook** · 15 min · RF-8
  - **Qué:** eliminar las celdas 85–90 (modelo solar autónomo) sin tocar el resto.
  - **Depende de:** nada. **Estado:** ✅ cerrada el 2026-10-31.
  - **Hecho cuando:** el notebook queda en 85 celdas, las celdas 0–84 son idénticas y no queda ninguna
    referencia a `FEATURE_COLS_SOLAR`, `df_solar_ml`, `pipeline_solar` ni `lr_solar`.
  - **Evidencia:** 91 → 85 celdas; huella SHA-256 de las celdas 0–84 verificada idéntica; copia previa
    en `%TEMP%/opencode/main-antes-eliminar-bloque-solar-20261031.ipynb`.

---

## Fase 1 — Descarga operativa (RF-1)

- [x] **T-03 · `fechas.ventana_descarga` (pura)** · 20 min · RF-1 · CA-1.1, CA-1.2
  - **Estado:** ✅ 2026-10-31 · `src/pipeline/fechas.py` (`ventana_descarga`) + 9 tests en `test_fechas.py`.
  - **Qué:** en `src/pipeline/fechas.py`, función que recibe `hoy` y la última fecha en BD y devuelve el
    rango `(inicio, fin)` pendiente de descargar, con retraso de 3 días. No trocea: el troceo en ventanas
    de 150 días ya existe en `aemet_backfill.ventanas()`.
  - **Depende de:** T-01.
  - **Hecho cuando:** pasan los tests de sin hueco → rango vacío; hueco de 3 días → rango exacto; BD
    vacía → arranca en el inicio del estudio; el `fin` nunca supera `hoy − 3 días`.

- [x] **T-04 · Reactivar la descarga en la celda 21** · 30 min · RF-1 · CA-1.1–CA-1.3
  - **Estado:** ✅ 2026-10-31 · ejecutada con `.venv` (Python 3.11.9).
  - **Qué se hizo al final:** la celda 21 **llama a `descargar_aemet`** (la función de la celda 19, que
    estaba definida y sin usar) con el rango que devuelve `fechas.ventana_descarga`. La primera versión
    duplicaba la descarga con `aemet_backfill.rellenar` y dejaba la función huérfana: corregido.
  - **Evidencia:** 1.ª pasada: `2026-10-26 → 2026-10-28`, **22 registros guardados**. 2.ª pasada en
    adelante: el rango se reduce a `2026-10-28` (el único día que falta) y AEMET responde «No hay datos
    que satisfagan esos criterios» en las 11 estaciones; la celda imprime
    «❌ Descarga incompleta: 11 error(es)» agrupado por causa (`sin_url_datos`) con estación y rango, y
    el notebook continúa sin fingir que el histórico está completo (CA-1.3). Duración de la descarga:
    ~130 s (pausa de 15 s por petición). No se ha visto un corte de red a mitad de tramo.
  - **Depende de:** T-03.
  - **Hecho cuando:** una ejecución completa descarga los días que faltan sin errores y el resumen
    muestra los tramos; un fallo simulado de un tramo aparece con su rango y su error.

- [x] **T-05 · Comprobar la idempotencia** · 15 min · RF-1 · CA-1.4, CA-1.5 · CE-9
  - **Estado:** ✅ 2026-10-31, con un matiz que conviene leer.
  - **Evidencia:** `SELECT COUNT(*) FROM aemet_diario` = **30.398 antes y después** de las pasadas 2.ª,
    3.ª y 4.ª; 0 registros guardados y 0 duplicados (`descargar_aemet` omite los días que ya están en BD
    vía `_fechas_en_bd_aemet`, y la tabla tiene clave primaria `(fecha, indicativo)`).
    **Matiz:** la 2.ª pasada no informa de «no hay nada que descargar», como pedía el enunciado, sino
    que reintenta **el único día pendiente** (2026-10-28), que AEMET todavía no publica. No se vuelve a
    pedir nada que ya esté en la BD, que es el riesgo real de CA-1.4/CE-9; pero mientras exista un
    hueco al final del rango, el recuento no baja a cero.
  - **Depende de:** T-04.
  - **Hecho cuando:** la segunda ejecución informa de 0 tramos y `SELECT COUNT(*) FROM aemet_diario`
    devuelve el mismo valor antes y después.

---

## Fase 2 — Criterio único de fecha (RF-2)

- [x] **T-06 · `fechas.fecha_madrid` (pura)** · 25 min · RF-2 · CA-2.1–CA-2.4
  - **Estado:** ✅ 2026-10-31 · `fechas.fecha_madrid` + 14 tests, incluidos los dos cambios de hora.
  - **Qué:** conversión UTC → día peninsular sin `zoneinfo` (no hay `tzdata` en el entorno), con el
    cambio de hora calculado a partir del último domingo de marzo y octubre.
  - **Depende de:** T-01.
  - **Hecho cuando:** pasan los tests de `2026-01-15T23:00:00Z` → `2026-01-16`; `2026-07-15T22:00:00Z` →
    `2026-07-16`; `22:00Z` del último domingo de marzo (sigue en UTC+1); `01:00Z` del último domingo de
    octubre (ya en UTC+1); 31 de diciembre → 1 de enero; y una entrada inválida lanza error explícito.

- [x] **T-07 · La serie eólica usa `fecha_madrid`** · 20 min · RF-2 · CA-2.5
  - **Estado:** ✅ 2026-10-31 · celda 52 ejecutada y diferencia explicada.
  - **Evidencia:** los dos cortes dan **1.761 días** con las mismas fechas. La suma difiere en
    **13.871 MWh** (281.910.015 con corte UTC · 281.923.886 con `fecha_madrid`) y se explica entera por
    los bordes: cada etiqueta REE (22:00Z/23:00Z) marca el inicio del día local, así que
    `Madrid[d] = valor[d−1]` y la diferencia es exactamente
    `v(2021-12-31)=139.410,7 − v(2026-10-27)=125.540,1`. No se pierde ni se duplica ningún dato.
    Contraste independiente del modelo (correlación viento↔eólica): con `fecha_madrid` el máximo cae
    en el desfase 0 (**r = 0,678**); con corte UTC el máximo cae en el desfase **+1** (0,679), es decir
    el corte UTC va un día por detrás.
  - **Qué:** sustituir en la celda 52 la conversión con pandas/`Europe/Madrid` por la función pura,
    conservando el resto del `merge`.
  - **Depende de:** T-06.
  - **Hecho cuando:** la serie diaria resultante conserva el número de días y la suma total, o cada
    diferencia se explica día a día y queda anotada.

- [x] **T-08 · La serie solar usa la misma función** · 20 min · RF-2, RF-3 · CA-2.5
  - **Estado:** ✅ 2026-10-31 · la celda 33 construye la serie con `solar.daily_national_series`: 1.759 días continuos (2022-01-01 → 2026-10-25), dentro del rango de REE, sin saltos.
  - **Qué:** construir la serie diaria de `sol`/`tmed` con `solar.daily_national_series` y fechas
    coherentes con la serie eólica; dejar de cortar por `SUBSTR` sobre UTC.
  - **Depende de:** T-07.
  - **Hecho cuando:** ambas series se construyen con la misma función, cubren al menos el periodo de la
    serie eólica y un día sin ninguna estación con dato detiene la ejecución indicando la fecha
    (CA-3.2).

---

## Fase 3 — Variables del día anterior (RF-3, RF-4)

- [x] **T-09 · `solar.lag_series` (pura)** · 20 min · RF-4 · CA-4.1, CA-4.2, CA-4.4
  - **Estado:** ✅ 2026-10-31 · `solar.lag_series` + 10 tests en `test_solar.py`.
  - **Qué:** devolver el valor del día natural anterior y `None` si ese día no existe o no tiene dato.
    Sin arrastrar el último valor disponible.
  - **Depende de:** T-01.
  - **Hecho cuando:** pasan los tests de día anterior con dato, día ausente de la serie, día con valor
    nulo, primer día de la serie, cambio de mes y 29 de febrero.

- [x] **T-10 · Construir `sol_lag1` y `tmed_lag1` en el notebook** · 25 min · RF-3, RF-4 · CA-4.3
  - **Estado:** ✅ 2026-10-31 · celda 64 ejecutada.
  - **Evidencia:** `df_ml` (1.754, 20); **0 de 1.754 filas sin dato solar** (0,00 %), así que no se
    descarta ninguna; 16 base + 18 candidatas, con `sol_lag1` y `tmed_lag1` al final. Sin medias
    móviles de sol/tmed y sin generación solar en MWh.
  - **Qué:** unir la serie diaria a `df_ml` por fecha y añadir las dos columnas con `lag_series`,
    informando de las filas descartadas. Sin medias móviles ni generación solar.
  - **Depende de:** T-08, T-09.
  - **Hecho cuando:** se informa del número de filas perdidas, el modelo sigue usando las 16 variables
    hasta la fase 5, y la lista final de variables candidatas es de 18 con esos dos nombres exactos.

- [x] **T-11 · Verificar que el mapa fecha→valor no se desplaza** · 20 min · RF-4 · CE-1, CE-4
  - **Estado:** ✅ 2026-10-31 · conteos por año idénticos a los de la serie eólica (365/365/366/365/298) y 2024-01-16 / 2024-07-16 contrastados contra la BD: el mapa no se desplaza.
  - **Qué:** comprobar a mano un día de enero y otro de julio contra la BD, y que los conteos por año
    coinciden con los de la serie eólica.
  - **Depende de:** T-10.
  - **Hecho cuando:** las dos fechas elegidas muestran el valor del día anterior correcto y los conteos
    anuales cuadran. **Si algo se desplaza, no se continúa hasta resolverlo.**

---

## Fase 4 — Walk-forward y criterio (RF-5, RF-6)

- [x] **T-12 · Fijar la línea base reproducible** · 20 min · RF-6 · CA-6.3
  - **Estado:** ✅ 2026-10-31 · línea base de 16 variables medida por fold en la celda 77 (mismos folds
    y mismas fechas que la variante, con escalado por fold).
  - **Evidencia:** RMSE base por fold: **2023 41.291 · 2024 39.958 · 2025 40.095 · 2026 39.324** MWh
    (R² 0,8107 / 0,7732 / 0,7646 / 0,7898). Reproducible ejecutando el notebook: dos pasadas seguidas
    dieron exactamente las mismas cifras y el mismo SHA-256 del `.joblib`.
  - **Qué:** anotar RMSE, MAE, R², MAPE, Accuracy, días de test y rango de fechas del modelo de 16
    variables, ya con los datos refrescados (T-05) y la fecha unificada (T-07). Debe ser reproducible
    con un comando conocido.
  - **Depende de:** T-05, T-07.
  - **Hecho cuando:** la cifra de referencia está anotada y se reproduce al reejecutar esa parte del
    notebook.

- [x] **T-13 · `evaluacion.walk_forward_folds` (pura)** · 25 min · RF-5 · CA-5.1, CA-5.4
  - **Estado:** ✅ 2026-10-31 · `evaluacion.walk_forward_folds` + 12 tests; sobre las fechas reales da 2023/2024/2025/2026 sin omitir ninguno.
  - **Qué:** folds anuales que reciben `hoy`, con entrenamiento siempre anterior al año evaluado, mínimo
    de 200 días de train y 100 de test, y folds omitidos con motivo.
  - **Depende de:** T-01.
  - **Hecho cuando:** pasan los tests de cuatro folds esperados, ausencia de solape, train siempre
    anterior a test, fold con train corto omitido y años no consecutivos.

- [x] **T-14 · `evaluacion.criterio_aceptacion` (pura)** · 20 min · RF-6 · CA-6.1–CA-6.3
  - **Estado:** ✅ 2026-10-31 · `evaluacion.criterio_aceptacion` + 9 tests (empate, folds omitidos, mínimo).
  - **Qué:** recibir los RMSE por fold de las dos variantes y devolver aceptación y motivo, exigiendo
    mejora estricta en al menos 3 de los folds válidos.
  - **Depende de:** T-13.
  - **Hecho cuando:** pasan los tests de 3 de 4 → aceptado; 2 de 4 → rechazado; 4 de 4 → aceptado; 4 de
    4 con un fold peor → aceptado; empate exacto → no cuenta; fold omitido → motivo "folds
    insuficientes".

- [x] **T-15 · Comparar las dos variantes en el notebook** · 30 min · RF-5, RF-6 · CA-5.2, CA-5.3, CA-5.5
  - **Estado:** ✅ 2026-10-31 · celda 77 ejecutada. **Criterio ACEPTADO (3 de 4 folds).**
  - **Evidencia:**
    | año | test | base RMSE | var RMSE | Δ | base R² | var R² |
    |---|---|---|---|---|---|---|
    | 2023 | 365 | 41.291 | 39.524 | −1.767 | 0,8107 | 0,8266 |
    | 2024 | 366 | 39.958 | 39.997 | **+39** | 0,7732 | 0,7727 |
    | 2025 | 365 | 40.095 | 39.085 | −1.009 | 0,7646 | 0,7763 |
    | 2026 | 300 | 39.324 | 38.697 | −627 | 0,7898 | 0,7965 |

    Mismas fechas y escalado ajustado solo con el train del fold (`StandardScaler().fit(train_f)`).
    Modelo de producción resultante (18 variables), test 2025-11-11 → 2026-10-27 (351 días):
    **RMSE 39.273,3 · MAE 29.418,7 · R² 0,8055**.
  - **Qué:** entrenar por fold las variantes de 16 y 18 variables, con el escalado ajustado solo con el
    train del fold, e imprimir RMSE y R² por fold más el veredicto del criterio.
  - **Depende de:** T-10, T-12, T-14.
  - **Hecho cuando:** se imprime la tabla de los folds con las dos variantes sobre exactamente las
    mismas fechas, y el veredicto coincide con `criterio_aceptacion` aplicado a mano.

---

## Fase 5 — Decisión y persistencia (RF-7)

- [x] **T-16 · Guardado condicionado y verificación** · 25 min · RF-7 · CA-7.2, CA-7.4 · CE-12
  - **Estado:** ✅ 2026-10-31 · celda 83 ejecutada por el camino de **aceptación**.
  - **Evidencia:** `src/data/modelos/lr_eolica.joblib` pasó de `70b6e90f…` (16 variables) a
    `4a4aeba8…` (18); la copia previa `lr_eolica-previo-20261031.joblib` se conservó. Recarga OK:
    `features` = las 18 usadas al entrenar, y `np.allclose` entre las predicciones del modelo recargado
    y las del modelo en memoria. Métricas tras recargar, idénticas al entrenamiento:
    RMSE 39.273,3 · MAE 29.418,7 · R² 0,8055. **El camino de rechazo no se ha ejecutado nunca**
    (el criterio aceptó a la primera); queda verificado por inspección, no por ejecución.
  - **Qué:** en la celda 82, guardar solo si el criterio se cumple; guardar antes una copia del `.joblib`
    vigente; verificar que el guardado recarga y reproduce sus métricas.
  - **Depende de:** T-15.
  - **Hecho cuando:** con el criterio rechazado el hash del `.joblib` no cambia y el notebook lo
    informa; con el criterio aceptado el modelo recarga y sus `features` son las 18 usadas al entrenar.

- [ ] **T-17 · Sincronizar `FEATURE_COLS` y las copias del modelo** · 25 min · RF-7 · CA-7.1, CA-7.3
  - **Estado:** ⏸️ **Aplazada por decisión del usuario (2026-10-31): primero se revisa el notebook, y
    solo después se toca backend y producción.** Los cambios de backend que se habían hecho sin
    consultar se revirtieron con `git checkout`: `model_loader.py` y `db_ree.py` vuelven a `HEAD`
    (`FEATURE_COLS` de 16) y las tres copias de producción vuelven a la huella `3704300d…`.
  - **Qué:** solo en el camino de aceptación, actualizar `FEATURE_COLS` en el notebook y en
    `backend/app/services/model_loader.py`, y sincronizar todas las copias que apunta `MODEL_PATH`.
  - **Depende de:** T-16.
  - **Hecho cuando:** la lista de 18 variables coincide en notebook y backend, las rutas actualizadas
    están anotadas, y `uvicorn app.main:app` responde en `/health` y `/api/prediction` con el modelo
    nuevo.
  - **Ya preparado (sin aplicar):** el informe `sol_como_feature.json` registra las 4 rutas con su
    huella y marca las 3 de producción como `sincronizada: false`; la celda 86 imprime el aviso
    «⚠️ Copias sin sincronizar: modelos, backend/modelos, src/model/production» hasta que se haga.

---

## Fase 6 — Trazabilidad y cierre (RF-9, RF-10)

- [x] **T-18 · `evaluacion.resumen_folds` (pura)** · 20 min · RF-9 · CA-9.1
  - **Estado:** ✅ 2026-10-31 · `evaluacion.resumen_folds` + 6 tests (serializable a JSON).
  - **Qué:** agregar métricas por fold, resultado del criterio y cobertura en una estructura lista para
    imprimir y para el JSON, con `hoy` como fecha de ejecución.
  - **Depende de:** T-14.
  - **Hecho cuando:** pasan los tests de estructura completa, fold omitido presente con su motivo y
    lista vacía rechazada con error.

- [x] **T-19 · Informe `sol_como_feature.json`** · 20 min · RF-9 · CA-9.1, CA-9.2
  - **Estado:** ✅ 2026-10-31 · celda 86 ejecutada.
  - **Evidencia:** `src/data/modelos/sol_como_feature.json` (5.175 B) con `fecha_ejecucion`,
    `criterio` + `detalle` por fold, `folds` (4), `cobertura` (5 estaciones), `modelo` (features base,
    variante y producción), `metricas_test`, `racha` y `rutas`. Recargado con `json.load` en la propia
    celda. Lo vigila `src/pipeline/tests/test_contrato_modelo.py` (5 tests).
  - **Qué:** escribir desde el notebook el informe con fecha, métricas por fold, cobertura de las
    estaciones, criterio y decisión.
  - **Depende de:** T-18, T-15.
  - **Hecho cuando:** el fichero existe, se puede cargar con `json.load`, contiene los folds y la
    cobertura, y coincide con lo impreso por el notebook.

- [ ] **T-20 · Aviso visible del fallback de `racha`** · 15 min · RF-10 · CA-10.1–CA-10.3
  - **Estado:** 🟡 Implementada en la celda 80 y **no ejercitada**: en la ejecución del 2026-10-31, AEMET
    devolvió `rachaMax` en Borja (50 km/h = 13,89 m/s), así que el agregado usó el pronóstico y el
    informe registró `racha.usado = false` con motivo «rachaMax disponible en el pronóstico de AEMET».
    El camino del aviso («⚠️ racha estimada con N días…») solo se recorrió en la primera pasada del día,
    donde varias estaciones se quedaron sin `rachaMax`; no se conserva esa salida, así que CA-10.1 está
    **implementado y no demostrado**.
  - **Qué:** en la celda 79, dejar explícito cuándo `racha` viene del fallback y con cuántos días se
    estimó, y dejarlo también en el informe de T-19. Sin cambios en el contrato de la API.
  - **Depende de:** T-19.
  - **Hecho cuando:** el aviso aparece en la salida del notebook y en el JSON, y la respuesta de
    `/api/prediction` conserva exactamente los mismos campos.
  - **Pendiente:** forzar el caso (un día sin ningún `rachaMax`) y guardar la salida como evidencia.

- [x] **T-21 · `MEMORY.md` y cierre** · 15 min · RF-9 · CA-9.3
  - **Estado:** ✅ 2026-10-31 · `MEMORY.md` actualizado con la decisión, las métricas y las dudas abiertas.
  - **Qué:** decisión, métricas de referencia por fold, rutas del `.joblib` actualizadas y dudas que
    siguen abiertas.
  - **Depende de:** T-20.
  - **Hecho cuando:** `MEMORY.md` refleja el estado real, no cita cifras que ya no se reproduzcan y no
    quedan dudas resueltas sin anotar.

---

## Resumen

| Fase | Tareas | RF cubiertos |
|---|---|---|
| 0 | T-01, T-02 | RNF-7, RF-8 |
| 1 | T-03 – T-05 | RF-1 |
| 2 | T-06 – T-08 | RF-2, RF-3 |
| 3 | T-09 – T-11 | RF-3, RF-4 |
| 4 | T-12 – T-15 | RF-5, RF-6 |
| 5 | T-16, T-17 | RF-7 |
| 6 | T-18 – T-21 | RF-9, RF-10 |

**Puntos de parada**

1. **T-11** — si el mapa fecha→valor se desplaza, no se sigue: invalidaría todas las métricas.
2. **T-15** — si el criterio rechaza la mejora, la Fase 5 se cierra sin tocar producción y se salta a
   T-18. El trabajo no se pierde: queda documentado.
3. **T-16** — si el modelo no recarga, se restaura la copia previa y se cierra sin desplegar (CE-12).
4. **D-2-2 sin cerrar** — afecta a T-14; antes de implementarlo hay que decidir si el criterio exige solo
   el signo o una magnitud mínima.
