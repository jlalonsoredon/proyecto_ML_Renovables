# Plan 002 — La insolación como variable del modelo eólico

Deriva de `specs/002-sol-feature-eolica/spec.md` (RF-1 a RF-10) y respeta `docs/constitution.md`.
Las tareas ejecutables están en `tasks.md`; este documento fija el diseño.

## 0. Alcance y dos avisos sobre el encargo

**Aviso 1 — No hay mapa.** La spec 002 no contiene ningún mapa geográfico y ningún RF lo pide. El
encargo menciona "algoritmo del mapa": en este proyecto el único "mapa" que existe es el **mapa de
correspondencia fecha → valor** entre la serie de generación y la serie meteorológica. El apartado 3.1
documenta ese algoritmo, que es donde de verdad se juega la corrección del resultado (un desplazamiento
de un día falsea todas las métricas). No se inventa un mapa geográfico porque no hay requisito que lo
sostenga y RNF-2 exige cambio mínimo.

**Aviso 2 — No hay interfaz nueva.** U3 queda fuera de alcance explícitamente: esta versión no expone
nada en la web. La "interfaz" de esta funcionalidad es la **salida del notebook** (tablas y avisos) y el
**informe de trazabilidad**; el único efecto visible en el producto es el valor de la predicción y sus
avisos, si el criterio de aceptación se cumple. El apartado 4 lo detalla.

**Restricción de fondo:** se pueden tocar celdas del notebook, pero no su estructura ni la lógica global.
Todo lo nuevo con lógica propia vive en `src/pipeline/`, sin pandas, para poder probarse en la puerta.

---

## 1. Archivos: qué se crea, qué se modifica y de qué responde cada uno

### 1.1 Se crean

| Archivo | Responsabilidad | RF |
|---|---|---|
| `src/pipeline/fechas.py` | Convertir un instante UTC de REE en día natural peninsular. Única fuente de verdad de la fecha. Sin dependencias. | RF-2 |
| `src/pipeline/evaluacion.py` | Calcular los folds del walk-forward, decidir si la mejora es aceptable y agregar el resumen por fold. Sin pandas. | RF-5, RF-6 |
| `src/pipeline/tests/test_fechas.py` | Contrato de `fechas.py`: bordes de cambio de hora, cambio de año, bisiesto, entradas inválidas. | RF-2 |
| `src/pipeline/tests/test_evaluacion.py` | Contrato de `evaluacion.py`: folds sin solape, folds omitidos, criterio 3 de 4. | RF-5, RF-6 |
| `src/data/modelos/sol_como_feature.json` | Informe de trazabilidad generado por el notebook: fecha, métricas por fold, cobertura, decisión. | RF-9 |

### 1.2 Se modifican

| Archivo | Cambio | RF |
|---|---|---|
| `src/notebooks/main.ipynb` · celda 21 | Reactivar la descarga AEMET por tramos con la lógica de `aemet_backfill`, con resumen de días pedidos, insertados y omitidos. | RF-1 |
| `src/notebooks/main.ipynb` · celda 52 | Sustituir la conversión con pandas/`Europe/Madrid` por `fechas.fecha_madrid`. | RF-2 |
| `src/notebooks/main.ipynb` · tras la 64 | Añadir `sol_lag1` y `tmed_lag1` a `df_ml` mediante `solar.lag_series`, informando de las filas perdidas. | RF-3, RF-4 |
| `src/notebooks/main.ipynb` · tras la 76 | Bloque de walk-forward: entrena las dos variantes por fold e imprime RMSE y R²; aplica el criterio. | RF-5, RF-6 |
| `src/notebooks/main.ipynb` · celda 79 | Dejar explícito en la salida cuándo `racha` proviene del fallback y con cuántos días se estimó. | RF-10 |
| `src/notebooks/main.ipynb` · celda 82 | Guardado condicionado: solo sobrescribe el `.joblib` si el criterio se cumple; copia previa y verificación de recarga. | RF-7 |
| `src/pipeline/solar.py` | Añadir `lag_series` (valor del día natural anterior). Se mantiene el resto del módulo. | RF-3, RF-4 |
| `src/pipeline/tests/test_solar.py` | Casos nuevos de `lag_series`. | RF-3, RF-4 |
| `backend/app/services/model_loader.py` | `FEATURE_COLS` de 16 a 18, solo en el camino de aceptación. | RF-7 |
| `.joblib` en las rutas de `MODEL_PATH` | Sincronizar las copias solo si se acepta. | RF-7 |
| `MEMORY.md` | Decisión, métricas de referencia, rutas actualizadas, dudas abiertas. | RF-9 |
| `specs/002-sol-feature-eolica/tasks.md` | Estado de las tareas al cerrarlas. | — |

### 1.3 No se toca

`docs/constitution.md` (D-2-6), `solar.py` más allá de `lag_series`, el bloque eólico en su orden, los
endpoints del backend, el frontend, el scheduler y las dos bases de datos (salvo la descarga de RF-1 en
`aemet_diario`).

---

## 2. Funciones puras de lógica

Todas viven en `src/pipeline/`, no importan pandas ni sklearn y no acceden a red ni a disco.

| Función | Firma (conceptual) | ¿Recibe `hoy`? | RF |
|---|---|---|---|
| `fecha_madrid` | instante ISO UTC → `"YYYY-MM-DD"` | No | RF-2 |
| `ventana_descarga` | `hoy`, última fecha en BD, retraso → rango `(inicio, fin)` pendiente | **Sí** | RF-1 |
| `lag_series` | serie diaria + clave → lista alineada con `None` donde no hay día anterior | No | RF-4 |
| `walk_forward_folds` | lista de fechas, `hoy`, mínimo de días → folds con índices de train y test | **Sí** | RF-5 |
| `criterio_aceptacion` | RMSE por fold de las dos variantes, folds omitidos → aceptación y motivo | No | RF-6 |
| `resumen_folds` | métricas por fold → estructura lista para imprimir y para el JSON | No | RF-9 |

**Nota sobre "hoy como parámetro".** La constitución pide que los cálculos de fechas reciban `hoy`. Se
cumple donde la función depende del día actual (`ventana_descarga`, `walk_forward_folds`). **No** se
cumple en `fecha_madrid`, `lag_series`, `criterio_aceptacion` ni `resumen_folds` porque son
transformaciones sin estado: añadirles un parámetro que no usan sería un parámetro decorativo y
falsearía su contrato. Se deja anotado como desviación consciente en el apartado 7.

---

## 3. Algoritmos en pseudocódigo

### 3.1 Mapa de correspondencia fecha → valor (el núcleo del riesgo) · RF-2, RF-3, RF-4

Objetivo: que el día natural peninsular de la generación y el día natural de la observación
meteorológica sean el mismo día, y que el retardo de un día sea el día natural anterior, no el último
día con dato.

```
FUNCIÓN fecha_madrid(instante_utc):
    t ← interpretar instante_utc como fecha-hora sin zona (se descarta la "Z")
    SI t es inválido ENTONCES error explícito con el valor recibido
    inicio_verano ← último domingo de marzo de año(t) a las 01:00
    fin_verano    ← último domingo de octubre de año(t) a las 01:00
    SI inicio_verano ≤ t < fin_verano ENTONCES desfase ← 2
    SI NO desfase ← 1
    DEVOLVER (t + desfase horas) como "YYYY-MM-DD"

FUNCIÓN lag_series(serie_diaria, clave):
    # serie_diaria: mapa fecha → registro, ordenado
    resultado ← lista vacía
    PARA CADA fecha EN serie_diaria ordenada:
        anterior ← fecha − 1 día
        SI anterior NO existe EN serie_diaria ENTONCES
            añadir NADA            # hueco real: no se arrastra el último valor
        SI NO SI serie_diaria[anterior][clave] es nulo ENTONCES
            añadir NADA            # dato ausente ese día
        SI NO
            añadir serie_diaria[anterior][clave]
    DEVOLVER resultado
```

Propiedades que fija el algoritmo: un hueco **no** desplaza el retardo (no hay "último valor
disponible"); el primer día siempre queda vacío; el resultado tiene la misma longitud que la serie de
entrada.

Encaje en el notebook:

```
df_ml ← df_ml unido por fecha con la serie diaria de sol y tmed
df_ml["sol_lag1"]  ← lag_series(serie_solar, "sol")
df_ml["tmed_lag1"] ← lag_series(serie_solar, "tmed")
informar cuántas filas quedan sin las dos variables y se descartan
```

### 3.2 Ventanas de descarga · RF-1

```
FUNCIÓN ventana_descarga(hoy, ultima_fecha_bd, retraso = 3):
    fin ← hoy − retraso días            # AEMET publica con retraso
    SI ultima_fecha_bd es nula ENTONCES inicio ← fecha_fija_de_estudio
    SI NO inicio ← ultima_fecha_bd + 1 día
    SI inicio > fin ENTONCES DEVOLVER rango vacío
    DEVOLVER (inicio, fin)
```

El troceo en ventanas de 150 días **no se reimplementa**: lo hace `aemet_backfill.ventanas(inicio, fin)`,
que ya está probado y respeta el límite de AEMET. Esta función solo decide *desde dónde hasta dónde* hay
que descargar, que es la parte que depende de `hoy`.

Regla de parada: si un tramo falla, se informa del tramo y del error y **no** se continúa como si el
histórico estuviera completo (CA-1.3).

### 3.3 Walk-forward de cuatro folds · RF-5

```
FUNCIÓN walk_forward_folds(fechas_ordenadas, hoy, mín_train = 200, mín_test = 100):
    primer_año ← año de la primera fecha
    último_año ← año de (hoy − 1 día)     # el año en curso nunca es fold completo
    folds ← lista vacía
    PARA CADA año EN primer_año+1 … último_año:
        train ← índices con fecha < 1 de enero de año
        test  ← índices con fecha en el año
        SI tamaño(train) < mín_train O tamaño(test) < mín_test ENTONCES
            añadir fold marcado como OMITIDO con el motivo
        SI NO
            añadir fold con train, test y rango de fechas
    DEVOLVER folds
```

Propiedades: los folds no se solapan, el entrenamiento de cada fold es siempre anterior a su prueba, y
las dos variantes (16 y 18 variables) usan **exactamente** los mismos índices.

### 3.4 Criterio de aceptación · RF-6

```
FUNCIÓN criterio_aceptacion(rmse_base, rmse_variante, folds_omitidos, mínimo = 3):
    válidos ← folds con las dos métricas presentes y no omitidos
    mejoras ← contar folds donde rmse_variante < rmse_base   # estricto: empate NO cuenta
    SI tamaño(válidos) < 4 − máximo_omisiones_admitido ENTONCES
        DEVOLVER rechazado con motivo "folds insuficientes"
    SI mejoras ≥ mínimo ENTONCES
        DEVOLVER aceptado con el detalle por fold
    SI NO
        DEVOLVER rechazado con el detalle por fold
```

### 3.5 Resumen y trazabilidad · RF-9

```
FUNCIÓN resumen_folds(folds, métricas_por_variante, decisión, cobertura, hoy):
    DEVOLVER estructura con: fecha de ejecución (hoy), por fold (año, días de train y test,
    RMSE y R² de cada variante), mejoras, resultado del criterio y motivo,
    cobertura de las estaciones y decisión final
```

Esa estructura es la que se imprime en el notebook y la que se escribe en
`src/data/modelos/sol_como_feature.json`.

---

## 4. Interfaz: qué se pinta y dónde

**No hay interfaz web en esta spec** (U3 fuera de alcance). Lo que se pinta es la salida del notebook,
con este orden:

1. **Cobertura de insolación** (ya existe, celda 33): tabla por estación con días, porcentaje y hueco.
2. **Descarga**: tramos solicitados, días insertados y omitidos, y aviso si un tramo falló. · RF-1
3. **Features**: cuántas filas se pierden por no tener día anterior. · RF-4
4. **Tabla del walk-forward**: por fold, RMSE y R² de las dos variantes y la diferencia. · RF-5
5. **Veredicto**: aceptado o rechazado, con el número de folds en que mejora. · RF-6
6. **Aviso de `racha`**: si viene del fallback, con cuántos días se estimó. · RF-10
7. **Cierre**: decisión, rutas del `.joblib` actualizadas y ruta del JSON de trazabilidad. · RF-7, RF-9

**Efecto en el producto:** si el criterio se cumple, el modelo servido pasa a 18 variables y las
predicciones cambian. El contrato de la API (`/api/prediction`, `/api/prediction-chart`) no cambia: misma
forma de respuesta, mismo campo `avisos`. No se añade nada al frontend.

---

## 5. Decisiones técnicas y alternativas descartadas

1. **Función de fecha propia, sin `zoneinfo` ni `pytz`.** · RF-2
   - *Por qué:* el entorno no tiene `tzdata` (verificado: `ZoneInfoNotFoundError`), y la regla europea
     cabe en diez líneas. Además el resultado no depende de la máquina.
   - *Descartada:* `zoneinfo` con `Europe/Madrid` (falla sin tzdata y cambia con la versión de la base
     horaria); conversión con pandas (introduce dependencia en la lógica pura y no se puede probar en la
     puerta).

2. **Cortar la fecha después de convertir a hora peninsular, nunca por `SUBSTR`.** · RF-2
   - *Por qué:* en invierno, `23:00Z` ya es el día siguiente en Madrid. Cortar en UTC desplaza un día
     entero y el error es invisible.
   - *Descartada:* normalizar todo a UTC (obligaría a reinterpretar la serie histórica de REE y las
     fechas de AEMET, que ya vienen en día natural local).

3. **Dos variables, del día anterior, sin medias móviles.** · RF-4
   - *Por qué:* medido, las medias móviles no aportan (0,7788 con y sin ellas) y multiplican columnas;
     el día anterior conserva el 75 % de la mejora de la insolación del mismo día.
   - *Descartada:* insolación del mismo día (fuga: no está disponible al predecir mañana); generación
     solar en MWh (su escala crece un 130 % con la capacidad instalada); medias móviles de 3/7/14 días.

4. **Serie diaria por media de estaciones con dato.** · RF-3
   - *Por qué:* es la lógica ya validada en `solar.daily_national_series` y no exige ponderaciones que no
     tenemos.
   - *Descartada:* media ponderada por capacidad de planta (no hay serie de capacidad instalada en el
     proyecto); imputación de huecos (RNF-5 lo prohíbe).

5. **Walk-forward de cuatro folds anuales en lugar de un único split 80/20.** · RF-5, RF-6
   - *Por qué:* con 351 días, el error estándar del RMSE es ≈1.500 MWh; la diferencia medida entre
     variantes (≈1.000) no se distingue del ruido en un solo corte. Los cuatro folds dan un patrón
     estable (mejora en 4 de 4 en la medición preliminar).
   - *Descartada:* split único del notebook (CA-6.3 lo prohíbe); `TimeSeriesSplit` mensual (12 folds de
     30 días, demasiado cortos para estimar RMSE estable y para el calendario anual de la eólica).

6. **Criterio por signo del RMSE, 3 de 4 folds.** · RF-6
   - *Por qué:* es el criterio que el usuario ha fijado; el signo es robusto y no exige un umbral
     arbitrario.
   - *Descartada:* exigir un ΔR² mínimo global (depende de la varianza del año); promediar métricas
     (prohibido por CA-6.3). Queda abierta D-2-2 sobre añadir una magnitud mínima.

7. **Descarga reutilizando la lógica de `aemet_backfill`.** · RF-1
   - *Por qué:* ya está probada (45 peticiones, 6.587 filas, 0 errores) y es idempotente; AEMET rechaza
     rangos mayores de seis meses.
   - *Descartada:* reactivar la llamada original con el rango completo (falla por límite de la API y no
     es reanudable).

8. **`lag_series` sobre el mapa de días, no `shift()` de pandas.** · RF-4
   - *Por qué:* `shift(1)` asume que las filas son días consecutivos; con un hueco, desplaza el retardo y
     hace pasar por "ayer" un dato de anteayer. La función pura lo impide por construcción y se prueba.
   - *Descartada:* `shift` + `reindex` en el notebook (correcta solo si el índice está completo, condición
     que nadie comprueba).

9. **Guardado condicionado con copia previa y verificación de recarga.** · RF-7
   - *Por qué:* el `.joblib` es el artefacto de producción; sobrescribirlo antes de saber si mejora deja
     el servicio sin vuelta atrás.
   - *Descartada:* guardar siempre y decidir después con el fichero ya escrito; escribir un `.joblib`
     nuevo con otro nombre (el backend apunta a una ruta fija).

10. **Informe en JSON junto al modelo.** · RF-9
    - *Por qué:* es el formato que ya usa `solar_metrics.json` y permite auditar sin reejecutar.
    - *Descartada:* dejar la decisión solo en la salida del notebook (se pierde al cerrar el kernel).

---

## 6. Estrategia de tests con `node --test`

**Puerta única:** `node --test "src/pipeline/tests/*.test.mjs"`. El runner es Node; la lógica es Python.
`gate.test.mjs` ya lanza `python -m unittest discover -s src/pipeline/tests` y falla si el código de
salida no es 0. Los ficheros de test nuevos se recogen automáticamente: no hay que tocar la puerta.

**Ciclo por tarea:** test primero en rojo, implementación mínima, verde, refactor. Prohibido cerrar una
tarea con la puerta en rojo (RNF-7).

| Módulo | Casos obligatorios | RF |
|---|---|---|
| `test_fechas.py` | `23:00Z` de enero → día siguiente; `22:00Z` de julio → día siguiente; `22:00Z` del último domingo de marzo (sigue en UTC+1); `01:00Z` del último domingo de octubre (ya en UTC+1); `00:00Z` exacto; 31 de diciembre → 1 de enero; 28 de febrero en bisiesto; entrada vacía o no ISO → error explícito | RF-2 |
| `test_evaluacion.py` (folds) | cuatro folds con los años esperados; sin solape; train siempre anterior a test; fold con train corto → omitido con motivo; fold sin datos → omitido; años no consecutivos | RF-5 |
| `test_evaluacion.py` (criterio) | 3 de 4 mejora → aceptado; 2 de 4 → rechazado; 4 de 4 → aceptado; 4 de 4 pero un fold peor → aceptado; empate exacto → no cuenta como mejora; un fold omitido → motivo "folds insuficientes"; listas de distinta longitud → error | RF-6 |
| `test_solar.py` (`lag_series`) | día anterior con dato; día anterior ausente → `None`; día anterior con nulo → `None`; primer día → `None`; cambio de mes y de año; 29 de febrero | RF-4 |
| `test_aemet_backfill.py` (ventanas) | sin hueco → lista vacía; hueco de 3 días → un tramo; hueco de 400 días → tres tramos de ≤150; respeto del retraso de 3 días; BD vacía → arranca en el inicio del estudio | RF-1 |

**Lo que la puerta no puede cubrir** (y cómo se verifica):

| Cambio | Verificación manual |
|---|---|
| Celdas del notebook | Ejecución completa y comparación de la tabla de folds con la medición preliminar del anexo A |
| `join` fecha→valor | Comprobación a mano de un día de enero y otro de julio contra la BD (T-10) |
| Descarga real | Segunda ejecución: 0 peticiones y mismo `COUNT(*)` en `aemet_diario` (T-07) |
| `.joblib` | Recarga y reproducción de métricas; lista de variables idéntica en notebook y backend |
| Backend | `uvicorn app.main:app` y `GET /api/prediction` con el modelo de 18 variables |

**Criterio de parada:** si la puerta falla, no se avanza. Si el criterio de aceptación rechaza la
mejora, la Fase 5 se cierra sin tocar producción y se documenta.

---

## 7. Cumplimiento de la constitución

| Principio | Cómo se cumple | Desviación |
|---|---|---|
| Simplicidad y continuidad | Dos módulos nuevos, una función añadida a `solar.py`; el bloque eólico conserva su orden y sus nombres | RF-7 cambia el modelo de producción y RF-8 elimina celdas: es el objeto de la spec, no una reestructuración |
| La spec manda | Todo el plan referencia un RF; ninguna pieza queda sin requisito | D-2-2 sigue abierta y afecta a `criterio_aceptacion`: debe cerrarse antes de T-12 |
| Lógica separada de la interfaz, con `hoy` como parámetro | La lógica vive en `src/pipeline/`, sin pandas ni red; `ventana_descarga` y `walk_forward_folds` reciben `hoy` | `fecha_madrid`, `lag_series`, `criterio_aceptacion` y `resumen_folds` no dependen del día actual y no lo reciben (parámetro decorativo) |
| Tests como puerta, sin instalar paquetes | `node --test` lanza la suite de Python; la lógica nueva solo usa la biblioteca estándar | La medición del notebook sí requiere pandas y sklearn, que no se instalan: se ejecuta en la máquina del usuario |
| Datos del usuario sagrados | Copia previa de BD y `.joblib` antes de tocar nada; el guardado es condicional y reversible | El principio está redactado para `localStorage`; aquí se traduce a copias de fichero |
| Idioma | Comentarios, mensajes y documentación en español (AGENTS.md) | La constitución pide código en inglés: se sigue el criterio del proyecto y se deja anotado en D-2-6 |

---

## 8. Matriz de cobertura de requisitos

| RF | Archivos / piezas | Se prueba en |
|---|---|---|
| RF-1 Descarga operativa | celda 21 + `ventana_descarga` | `test_aemet_backfill.py`, T-06/T-07 |
| RF-2 Fecha única | `fechas.py`, celda 52 y la unión de la serie solar | `test_fechas.py`, T-03–T-05 |
| RF-3 Serie diaria | `solar.daily_national_series` (existente) + unión en el notebook | `test_solar.py`, T-09 |
| RF-4 Variables del día anterior | `solar.lag_series`, bloque tras la celda 64 | `test_solar.py`, T-08–T-10 |
| RF-5 Walk-forward | `evaluacion.walk_forward_folds`, bloque tras la 76 | `test_evaluacion.py`, T-11/T-13 |
| RF-6 Criterio de aceptación | `evaluacion.criterio_aceptacion` | `test_evaluacion.py`, T-12/T-13 |
| RF-7 Reentrenamiento y persistencia | celda 82, `model_loader.py`, `.joblib` | Verificación manual, T-14 |
| RF-8 Retirada del bloque solar | notebook (ya ejecutado) | Verificado: 85 celdas, T-15 |
| RF-9 Trazabilidad | `evaluacion.resumen_folds`, `sol_como_feature.json`, `MEMORY.md` | T-16/T-18 |
| RF-10 Aviso de `racha` | celda 79 + JSON | T-17 |
| RNF-6/7 Lógica pura y puerta | `src/pipeline/*`, `gate.test.mjs` | `node --test "src/pipeline/tests/*.test.mjs"` |

---

## 9. Riesgos y puntos de parada

1. **El `join` se desplaza un día** → la mejora medida sería falsa. Parada en T-10 hasta resolverlo.
2. **La mejora no se repite en 3 de 4 folds** → no se toca producción; se documenta y se cierra igual.
3. **El modelo de 18 variables no recarga** → se restaura la copia previa del `.joblib` (CE-12).
4. **La descarga falla a mitad** → se informa del tramo; no se mide con histórico incompleto.
5. **Cambio de cobertura de una estación entre folds** → la variable cambia de definición; se anota en
   el informe antes de decidir.
6. **D-2-2 sin cerrar** → el criterio queda a medias; se para y se pregunta (constitución, principio 2).
