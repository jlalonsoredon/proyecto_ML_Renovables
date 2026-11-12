# Plan 005 — Previsión de REE del día objetivo como variable del modelo

Deriva de `spec.md` (RF-1 a RF-5). Respeta `docs/constitution.md`: todo el
desarrollo vive en `src/` (principio 1: orden del procedimiento), el código se
añade con el mínimo cambio posible (principio 2), nada se implementa si no está
en la spec (principio 3: las dudas se resuelven aquí y se marcan como puntos de
parada), la lógica es pura y recibe `hoy` (principio 4), la puerta es
`node --test` sin paquetes nuevos (principio 5), los datos se leen con copia
previa y sin escrituras (principio 6) y la documentación y los mensajes van en
español (principio 7; se mantiene la tensión ya conocida: los nombres de función
siguen el estilo español de `prevision.py` y `evaluacion.py` aunque la
constitución pida código en inglés).

La spec enmienda lo mínimo y el plan resuelve sus ambigüedades como **decisiones
propuestas con punto de parada** (§7 y §8). No se escribe código en este
documento: los bloques son pseudocódigo.

## 1. Archivos que se crean o modifican

| Archivo | Acción | Responsabilidad | RF |
|---|---|---|---|
| `src/pipeline/prevision.py` | **modificar** | Lógica pura nueva: elegibilidad del día objetivo, relleno de 7 días, serie histórica rellenada, resumen de cobertura, métricas y referencia de la previsión sola, informe de comparación. `resolver_origenes` gana la entrada `eolica_prev` y `VARIABLES_MODELO` pasa a 19. Sin E/S, sin pandas, sin reloj. | RF-1, RF-2, RF-3, RF-4, RF-5 |
| `src/pipeline/evaluacion.py` | **modificar (mínimo)** | `resumen_folds` incluye `mae` por fold **solo si** el llamador lo aporta. Las llamadas actuales (informe solar) no cambian de forma ni de contenido. | CA-4.5 |
| `src/pipeline/tests/test_prevision.py` | **modificar** | Nuevas clases: elegibilidad, relleno, serie rellenada, cobertura, métricas/referencia, informe y mapa con `eolica_prev`. | RF-1–RF-5 |
| `src/pipeline/tests/test_evaluacion.py` | **modificar** | `resumen_folds` con y sin `mae`; la llamada sin `mae` conserva el informe actual. | CA-4.5 |
| `src/pipeline/tests/test_contrato_modelo.py` | **modificar** | Deja de exigir 18 fijas: valida el acta solar (16→18) y el acta nueva (18→19), y que la producción declarada en ambas coincida con la decisión. | CA-5.3, criterio 4 |
| `src/pipeline/tests/test_integridad_notebook.py` | **modificar** | Marca la celda nueva, comprueba que lee el archivo en solo lectura y que escribe el informe nuevo; mantiene la prohibición de escribir en `generacion`/`aemet_diario`. | RF-5, CA-5.4 |
| `src/notebooks/main.ipynb` | **modificar** | Celda nueva tras el dataset (columna `eolica_prev`, recuento y depuración de CE-1) y retoques en las celdas 69 (exclusión de la columna), 78 (mapa), 91 (tres variantes y dos decisiones), 95 (vector de mañana), 100 (dos informes) y 102 (origen archivado). | RF-1–RF-5 |
| `src/data/modelos/prevision_ree_como_feature.json` | **crear (al ejecutar)** | Acta de la decisión 18→19: criterio, folds, métricas globales, referencia de la previsión sola, cobertura y rutas. | RF-4, RF-5 |
| `src/data/modelos/sol_como_feature.json` | **regenerar** | Se conserva como acta 16→18; añade la producción real (18 o 19) y sigue declarando rutas y métricas del test. | RF-4 |
| `src/data/modelos/lr_eolica.joblib` | **regenerar solo si se acepta** | Modelo de 19 variables del análisis. No se copia a ninguna ruta de producción sin autorización (P-1). | RF-4 |
| `src/data/ree_generacion.db` | **sin cambios de esquema** | Solo lectura de `prediccion_diaria` (fuente `ree`). Copia previa obligatoria antes de ejecutar el notebook (principio 6). | RF-1, RF-5 |
| `specs/005-integrar-prevision-REE/tasks.md` | **crear (siguiente paso)** | Tareas con ciclo test-rojo → verde. | — |
| `MEMORY.md` | **modificar (al cerrar)** | Decisión, números y estado del modelo. | RF-5 |

**No se toca** (RNF-5, principio 1): `backend/`, `frontend/`, `render.yaml`,
`src/pipeline/forecast.py` (tiene copia vendorizada con test de paridad),
`src/pipeline/prevision_db.py` (el esquema ya sirve), las tres copias de
producción del `.joblib` y `backend/app/services/model_loader.py`.

## 2. Funciones puras de lógica (con `hoy` como parámetro)

En `src/pipeline/prevision.py`, junto a las funciones de la spec 004, sin
dependencias nuevas (solo `datetime`, `math`, `statistics` si hace falta):

| Función | Firma | Qué devuelve | RF |
|---|---|---|---|
| `valor_prevision_valido` | `(valor) -> bool` | `True` solo si no es `None`/NaN, es ≥ 0 y ≤ `MAXIMO_PREVISION_MWH`. El cero es válido (CE-4); el negativo y el imposible no (CE-5). No depende del reloj. | CA-2.4, CE-4, CE-5 |
| `prevision_elegible` | `(filas, objetivo, hoy, ubicacion="peninsula") -> dict \| None` | La previsión del día objetivo con elaboración `≤ min(objetivo − 1, hoy)` y valor válido; desempata por elaboración y, si hiciera falta, por captura. `None` si no hay ninguna. | CA-1.2, CA-1.3, CE-2, CE-3, CE-7 |
| `serie_prevision_objetivo` | `(filas, hoy, ubicacion="peninsula") -> dict` | `{fecha: {valor, elaborado}}`, una entrada por día, aplicando la regla anterior a cada día. Es la única fuente del relleno: solo previsiones reales. | CA-1.1, CA-1.2, CA-1.3 |
| `rellenar_prevision` | `(serie, objetivo, hoy) -> dict \| None` | Si el día tiene previsión real: `{valor, origen: "prevision"}`. Si no: media de las previsiones **reales** de los 7 días naturales que terminan en `min(objetivo − 1, hoy)`, con `origen: "estimada"` y `dias_media`. `None` si no hay ninguna. Nunca usa otro relleno. | CA-2.1, CA-2.2, CA-2.4, CA-3.2, CA-3.3, CE-1, CE-6 |
| `serie_prevision_rellenada` | `(serie, fechas, hoy) -> dict` | `{fecha: {valor, origen, dias_media}}` para todas las fechas con valor honesto; las que no lo tienen no aparecen (se cuentan aparte). Determinista: mismo orden de entrada, mismo resultado. | CA-2.1, CA-2.2, RNF-3 |
| `resumen_prevision` | `(rellenada, fechas) -> dict` | `{reales, estimadas, sin_dato, huecos: [{fecha, dias_media}]}`. `huecos` identifica cada relleno por fecha y número de previsiones reales que aportaron (CA-5.2). | CA-5.1, CA-5.2 |
| `metricas` | `(predicciones, reales) -> dict` | `{n, rmse, mae, r2}` con fórmulas de la biblioteca estándar. Se usa para el modelo y para la previsión sola, así el cálculo queda cubierto por la puerta. | CA-4.5, CA-4.6 |
| `referencia_prevision` | `(serie, generacion, fechas) -> dict` | Error de la previsión de REE sola sobre exactamente las fechas pedidas, cruzando previsión y generación observada. Ignora días sin una de las dos y lo informa con `n`. | CA-4.6 |
| `informe_prevision_ree` | `(informe, modelo, globales, referencia, cobertura) -> dict` | Copia del informe de folds con el bloque `modelo` (18/19/producción), las métricas globales, la referencia y la cobertura. No muta la entrada. | CA-4.5, CA-4.6, CA-5.3 |
| `resolver_origenes` | `(…, prevision_objetivo=None)` | **Ampliada**: añade `mapa["eolica_prev"]` con `{valor, origen}` cuando recibe la entrada rellenada; si no, `NO_DISPONIBLE`. `VARIABLES_MODELO` pasa de 18 a 19 entradas. | RF-1, RF-3, CA-3.4 |

`prevision_db.py` no cambia: `rows_between(conn, "ree")` ya lee el archivo
completo y `save_own_prediction` ya guarda `origenes` y `vector_entrada`.

## 3. Algoritmo en pseudocódigo

### 3.1 Elegibilidad del día objetivo (RF-1)

```
PREVISION_ELEGIBLE(filas, objetivo, hoy, ubicacion):
    tope ← min(objetivo − 1 día, hoy)          # nunca el propio día objetivo
    candidatas ← [fila para fila en filas si
                    fila.objetivo = objetivo
                    y fila.ubicacion = ubicacion
                    y fila.elaborado ≠ vacío
                    y fecha(fila.elaborado) ≤ tope
                    y VALOR_PREVISION_VALIDO(fila.eolica_mwh)]
    si candidatas está vacía: devolver None
    elegida ← la de mayor (fila.elaborado, fila.capturado_en)
    devolver {valor, elaborado, antiguedad_dias}
```

Propiedades: una sola previsión por día (CE-2), la del propio día nunca entra
aunque sea la única (CE-3), otra ubicación no vale (CE-7) y el tope incluye la
elaboración de ayer para el objetivo de mañana (CA-3.1).

### 3.2 Relleno de un día (RF-2, RF-3)

```
RELLENAR_PREVISION(serie, objetivo, hoy):
    si objetivo ∈ serie:                                  # previsión real
        devolver {valor: serie[objetivo], origen: "prevision", dias_media: 0}

    fin ← min(objetivo − 1 día, hoy)
    ventana ← [fin − 6 … fin]                             # 7 días naturales
    valores ← [serie[d] para d en ventana si d ∈ serie]    # solo reales
    si valores está vacía: devolver None                  # CE-1, CA-3.3
    devolver {valor: media(valores), origen: "estimada",
              dias_media: len(valores), desde: ventana[0], hasta: fin}
```

El relleno nunca se alimenta de otro relleno (CE-6): la serie de entrada contiene
solo previsiones reales. El tope en `hoy` evita que un hueco futuro use días que
todavía no han ocurrido (RNF-2).

### 3.3 Serie del histórico (RF-2)

```
SERIE_RELLENADA(serie, fechas, hoy):
    resultado ← {}
    para cada fecha en fechas, en orden cronológico:
        entrada ← RELLENAR_PREVISION(serie, fecha, hoy)
        si entrada ≠ None: resultado[fecha] ← entrada
    devolver resultado
```

Los días sin entrada son los de CE-1: se cuentan, se declaran y se descartan.
En el histórico medido hoy (Anexo A) solo cae el primer día del archivo, que ya
lo eliminaban los retardos.

### 3.4 Columna de entrenamiento (RF-1, RF-2)

```
# Celda nueva inmediatamente después del dataset
abrir ARCHIVO_PATH en modo solo lectura                    # RNF-1, CA-5.4
filas_ree ← filas de prediccion_diaria con fuente = "ree"
serie ← SERIE_PREVISION_OBJETIVO(filas_ree, hoy)
rellenada ← SERIE_RELLENADA(serie, fechas de df_ml, hoy)
df_ml["eolica_prev"] ← valor de rellenada[fecha]
df_ml ← descartar y contar las filas sin eolica_prev       # CE-1
resumen ← RESUMEN_PREVISION(rellenada, fechas de df_ml)

FEATURE_COLS             ← 16 (sin eolica_prev, ya excluida en el dataset)
FEATURE_COLS_CANDIDATA   ← 18 (las 16 + sol_lag1 + tmed_lag1)
FEATURE_COLS_PREVISION   ← 19 (las 18 + eolica_prev)
```

Si el archivo no existe, la tabla no se puede leer o la serie queda vacía, la
celda **se detiene con el motivo**: sin archivo no hay variable y entrenar sin
ella ocultaría el fallo (se descarta el respaldo silencioso).

Los valores se calculan con `hoy` de la ejecución; para un día histórico el tope
es `objetivo − 1`, así que no hay fuga aunque el archivo contenga revisiones
posteriores (RNF-2).

### 3.5 Mapa de orígenes (RF-1, RF-3; amplía el de la spec 004)

```
# Celda 78
filas_ree ← archivo REE de los 14 días que terminan en OBJETIVO_MANANA
serie ← SERIE_PREVISION_OBJETIVO(filas_ree, hoy)
prevision_objetivo ← RELLENAR_PREVISION(serie, OBJETIVO_MANANA, hoy)

mapa_origenes ← RESOLVER_ORIGENES(obs_meteo, obs_solar, serie_generacion,
                                  prev, OBJETIVO_MANANA, hoy,
                                  permitir_prev_gen=True,
                                  prevision_objetivo=prevision_objetivo)
```

La entrada `eolica_prev` se pinta como cualquier otra:

- previsión real → 🔵 `prevision`;
- relleno → 🟡 `estimada` con `(N prev reales)`;
- sin dato → ⚪ `sin dato`.

### 3.6 Vector, predicción y archivo (RF-3)

```
# Celda 95
para cada variable en COLUMNAS_MODELO:
    si el mapa la tiene con valor y origen: usarla y declarar el origen
    si no: acumular en faltan_prediccion
si faltan_prediccion: detener con el motivo          # CA-3.3, CE-9

# Celda 102
vector_entrada ← valores de COLUMNAS_MODELO
origenes ← orígenes de COLUMNAS_MODELO + eolica_prev  # CA-3.4, CA-1.4
guardar predicción (upsert por fecha de emisión)
```

Si la variable se rechaza, `eolica_prev` no está en `COLUMNAS_MODELO`: el mapa
sigue declarándola, se archiva su origen y la predicción no depende de ella
(§7, punto 7).

### 3.7 Comparación walk-forward (RF-4)

```
# Celda 91
folds ← WALK_FORWARD_FOLDS(fechas, hoy)               # 4 ventanas, sin tocar

para cada fold:
    para cada variante en [16, 18, 19]:
        escalado ← ajustar SOLO con el train del fold
        modelo ← entrenar
        pred ← predecir el test del fold
        rmse, mae, r2 ← MÉTRICAS(pred, real)
    referencia_fold ← REFERENCIA_PREVISION(serie, generacion, test.del.fold)

decisión_solar     ← CRITERIO_ACEPTACION(rmse[16], rmse[18])   # acta existente
decisión_prevision ← CRITERIO_ACEPTACION(rmse[18], rmse[19])   # RF-4
producción ← 19 si decisión_prevision.aceptado, si no 18

globales   ← MÉTRICAS de las predicciones concatenadas de test (18 y 19)
referencia ← REFERENCIA_PREVISION sobre la unión de los test
```

La comparación que decide es **18 frente a 19**, con el mismo corte y el mismo
resto del vector (CA-4.1, CA-4.2). El 16 se conserva solo para que el acta solar
siga siendo reproducible. La previsión sola se mide sobre los mismos días
(CA-4.6): el Anexo A motiva, no decide.

## 4. Cómo se pinta en la interfaz

No hay pantalla nueva ni cambio web (RNF-5). La superficie es la salida del
notebook y el JSON:

| Celda | Qué se imprime | RF |
|---|---|---|
| Nueva (tras el dataset) | Días totales, con previsión real, rellenados y descartados; primera y última fecha; archivo leído; aviso con la lista de huecos y su `dias_media` | RF-1, RF-2, RF-5 |
| Mapa (78) | Fila `eolica_prev` con 🔵/🟡/⚪ y, si es relleno, `(N prev reales)`; recuento de orígenes del vector | RF-1, RF-3, CA-3.4 |
| Walk-forward (91) | Tabla por fold con RMSE/MAE/R² de 16, 18 y 19; ΔRMSE 18→19; dos veredictos (`solar`, `prevision_ree`); línea de la previsión sola | RF-4, CA-4.5, CA-4.6 |
| Predicción (95) | Valor de `eolica_prev`, su origen y el aviso si falta | RF-3 |
| Informe (100) | Ruta y decisión del acta nueva, referencia de la previsión sola, producción (18/19), copias del `.joblib` sin sincronizar | RF-4, RF-5, CA-5.3 |
| Guardado (102) | Objetivo, predicción, nº de variables y recuento de orígenes (incluido `eolica_prev`) | RF-3, CA-1.4 |

## 5. Decisiones técnicas (y alternativa descartada)

1. **Elegibilidad más estricta en funciones nuevas, sin tocar la spec 004.**
   `prevision_elegible` usa `min(objetivo − 1, hoy)`; `choose_forecast` y
   `serie_prevision_generacion` siguen con su tope `min(objetivo, hoy)` para
   viento, sol y relleno de retardos (D-5-2, D-5-6). *Descartada:* cambiar
   `choose_forecast`, que alteraría el uso ya declarado por la 004 y sus tests.
2. **Relleno en lógica pura, no con pandas.** Se prueba con la puerta, no
   encadena rellenos y el tope `hoy` es explícito. *Descartada:* `rolling` o
   `ffill` en el notebook (arrastra valores obsoletos, oculta huecos y no se
   puede probar sin pandas).
3. **Ventana de 7 días naturales con al menos una previsión real.**
   *Descartada:* media expansiva o `ffill` (usa datos más viejos de lo
   declarado y falsea `dias_media`).
4. **El cero es dato y el negativo/imposible se descarta con umbral físico.**
   `MAXIMO_PREVISION_MWH = 720.000` (30 GW × 24 h, cota de la capacidad
   peninsular). *Descartada:* umbral por percentiles o z-score anual
   (depende de los datos de cada ejecución y rompe el determinismo).
5. **Una columna `eolica_prev` y el origen fuera de las features.** El origen se
   archiva en `origenes`, no como variable del modelo (no está en la spec).
   *Descartada:* una dummy de origen (variable nueva no prevista) y `NaN`
   silencioso (aquí el día se descarta contado, CE-1).
6. **El mapa tiene 19 entradas siempre; la lista del modelo decide.** Así la
   variable se puede rastrear aunque se rechace (CA-5.1/5.2) y la decisión no
   cambia la forma del mapa. *Descartada:* añadir la entrada solo si se acepta
   (el rechazo dejaría el informe sin datos de la variable).
7. **Tres variantes en los mismos folds: 16 (referencia), 18 (vigente) y 19
   (candidata).** La decisión se toma 18→19 (CA-4.1) y el acta 16→18 se sigue
   regenerando. *Descartada:* comparar contra 16 (modelo ya superado) o repetir
   el walk-forward en dos ejecuciones (dos cortes y dos verdades).
8. **Dos actas JSON, una por decisión.** `sol_como_feature.json` queda como acta
   16→18 y `prevision_ree_como_feature.json` nace como acta 18→19; las dos
   declaran la producción real y las rutas. *Descartada:* un único archivo con
   dos decisiones (mezcla contratos y obliga a reescribir el acta solar).
9. **`resumen_folds` acepta `mae` opcional.** Añade la clave solo si el
   llamador la pasa, de modo que el informe solar no cambia. *Descartada:*
   duplicar el constructor del informe en `prevision.py` (dos formatos que se
   desincronizan).
10. **La previsión sola se mide sobre los mismos días que el modelo.**
    Referencia por fold y global con `metricas` y `referencia_prevision`.
    *Descartada:* comparar con el 19.969 del Anexo A, medido sobre otro periodo.
11. **Entrenamiento con la revisión final elegible; archivo con el vector del
    momento de predecir.** El histórico usa la última elaboración `≤ objetivo −
    1` (existe antes del día objetivo, no hay fuga); la predicción guardada
    conserva el valor que se usó al emitirla (CE-8, CA-1.4). *Descartada:*
    reconstruir el vector archivado con revisiones posteriores (falsearía lo
    emitido).
12. **Si se acepta, solo se guarda el `.joblib` del análisis.** Las tres copias
    de producción siguen en 18 hasta autorización expresa (P-1); la web no se
    toca. *Descartada:* sincronizar las cuatro copias en el mismo movimiento
    (RNF-5 y principio 1).

## 6. Estrategia de tests (`node --test`)

La puerta `gate.test.mjs` descubre `src/pipeline/tests/test_*.py` con
`python -m unittest discover`. Todo el código nuevo es de biblioteca estándar,
así que corre sin pandas ni sklearn. Orden de trabajo: **test rojo → implementar
→ verde**, sin avanzar con la suite en rojo (principio 5).

| Suite | Casos | RF/CA |
|---|---|---|
| `test_prevision.py` · `TestPrevisionElegible` | Elaboración en `objetivo − 1` es elegible; en el propio objetivo no (aunque sea la única); posterior no; gana la más reciente; tope en `hoy` para un objetivo futuro; otra ubicación no; sin elaboración no; NaN/negativo/fuera de rango no; cero sí; desempate por captura | CA-1.2, CA-1.3, CE-2, CE-3, CE-4, CE-5, CE-7 |
| `test_prevision.py` · `TestRelleno` | Día con previsión real → `prevision`; hueco con 7 y con 3 reales → media y `dias_media`; hueco sin reales anteriores → `None`; un relleno no alimenta a otro; la ventana se corta en `hoy`; un cero real entra en la media | CA-2.1, CA-2.2, CA-2.4, CA-3.2, CA-3.3, CE-1, CE-6 |
| `test_prevision.py` · `TestSerieRellenada` | Recuentos `reales/estimadas/sin_dato`; huecos con fecha y `dias_media`; dos llamadas idénticas dan lo mismo; orden de fechas irrelevante | CA-5.1, CA-5.2, RNF-3 |
| `test_prevision.py` · `TestMetricasYReferencia` | RMSE/MAE/R² con un caso calculado a mano; días sin previsión o sin real fuera; conjunto vacío → `n = 0` y métricas `None` | CA-4.5, CA-4.6 |
| `test_prevision.py` · `TestInformePrevision` | Añade modelo, globales, referencia y cobertura; conserva folds y criterio; no muta la entrada; serializable a JSON | CA-4.5, CA-4.6, CA-5.3 |
| `test_prevision.py` · `TestMapaOrigenes` (ampliado) | 19 variables y `eolica_prev` presente; real → `prevision`; relleno → `estimada` con `dias_media`; sin dato → no disponible; sin argumento → no disponible | RF-1, RF-3, CA-3.4 |
| `test_evaluacion.py` | `resumen_folds` con `mae` lo incluye por fold; sin `mae` el informe no cambia; longitudes incoherentes siguen fallando | CA-4.5 |
| `test_contrato_modelo.py` | Acta solar: base 16 y variante 18 = base + solares. Acta nueva: base 18 y variante 19 = base + `eolica_prev`; referencia y cobertura presentes; producción idéntica en las dos actas y coherente con la decisión (19 si aceptada, 18 si rechazada); rutas con SHA-256 | CA-4.5, CA-5.3, criterio 4 |
| `test_integridad_notebook.py` | Existe una sola celda nueva con su marca; usa `prevision.serie_prevision_objetivo`, `rellenar_prevision` y `resolver_origenes(..., prevision_objetivo=...)`; abre el archivo en solo lectura; escribe el informe nuevo; ninguna celda escribe en `generacion`/`aemet_diario` | RF-5, CA-5.4 |
| Verificación manual | Copia de la BD y del modelo; notebook completo de arriba abajo; dos ejecuciones el mismo día (misma predicción y una sola fila); observación intacta por recuento; informe nuevo legible sin reejecutar | RF-1–RF-5, criterios §9 |

La suite actual (16 tests de Node y 380 de Python) debe seguir en verde; el
primer paso de cada tarea es el test que falla.

## 7. Ambigüedades del QA y cómo se resuelven

| Ambigüedad | Resolución propuesta |
|---|---|
| La 004 elige elaboración `≤ objetivo`; la 005 exige `≤ objetivo − 1` | Se implementan funciones nuevas con el tope estricto; la 004 no cambia (decisión 1). |
| CA-2.1 solo admite perder filas en el arranque, pero un hueco de más de 7 días tampoco tiene relleno | Se generaliza CE-1: se pierde la fila cuando no hay **ninguna** previsión real en su ventana de 7 días. **Enmienda de redacción de CA-2.1** (P-4). |
| CE-8 («la previsión que se usó») frente a CA-1.3 («la más reciente elegible») | El histórico usa la revisión final elegible (siempre anterior al objetivo, sin fuga); el vector archivado conserva el valor del momento de emitir. Son dos instantes distintos y ambos quedan declarados (decisión 11). |
| Dos elaboraciones elegibles del mismo día | Gana la más reciente; empate por `capturado_en`. El esquema impide duplicar `(fuente, elaborado, objetivo, ubicación)`, así que el empate solo puede venir de datos externos. |
| ¿Qué informe se escribe y dónde? | Dos actas en `src/data/modelos/` (decisión 8); la nueva es `prevision_ree_como_feature.json`. |
| `test_contrato_modelo` exige 18 fijas | Pasa a validar las dos actas y a cruzar la producción declarada con la decisión (tabla §6). |
| ¿La predicción se detiene si la variable se rechaza? | No: CA-3.3 y CE-9 aplican cuando `eolica_prev` forma parte del modelo. Si se rechaza, se declara su origen y la predicción sigue con 18. **Aclaración de la spec** (P-4). |
| ¿Sobre qué días se mide la previsión sola? | Sobre los mismos días de test del modelo, por fold y en conjunto (decisión 10). |
| Umbral de valor imposible | `720.000 MWh`, cota física declarada; no se recorta a cero (CE-5). |
| Nombre de la variable y tamaño del mapa | `eolica_prev`; `VARIABLES_MODELO` pasa a 19 siempre (decisión 6). |

## 8. Puntos de parada (principio 3)

- **P-1 — D-5-8, modelo de destino.** Propuesta: si se acepta, el modelo de 19
  se guarda solo en `src/data/modelos/lr_eolica.joblib`; la web sigue con 18
  hasta autorización. No se copia a `modelos/`, `backend/modelos/` ni
  `src/model/production/`.
- **P-2 — D-5-9, umbral de mejora.** Propuesta: mejora estricta con umbral 0
  (cualquier reducción del RMSE), como en la spec 002. Si se quiere un mínimo
  porcentual, debe decidirse antes de ejecutar la comparación.
- **P-3 — Ubicación del acta.** Propuesta: acta nueva
  `prevision_ree_como_feature.json` y `sol_como_feature.json` como acta 16→18.
  Si se prefiere un único archivo, se decide antes de escribir la celda 100.
- **P-4 — Enmiendas de redacción de la spec 005.** (a) CA-2.1: el hueco sin
  relleno es el que no tiene ninguna previsión real en 7 días; (b) CA-3.3/CE-9:
  la parada aplica cuando la variable está en el modelo; (c) CE-8: se aclara la
  diferencia entre revisión de entrenamiento y vector archivado.

## 9. Cobertura de requisitos

| RF | Dónde se cubre |
|---|---|
| RF-1 | `prevision_elegible` + `serie_prevision_objetivo` + columna `eolica_prev` + entrada del mapa + archivo del vector (§2, §3.1, §3.4, §3.5) |
| RF-2 | `rellenar_prevision` + `serie_prevision_rellenada` + celda nueva del dataset (descarte contado de CE-1) + `test_prevision.py` (§3.2–§3.4) |
| RF-3 | `prevision_objetivo` en `resolver_origenes` + celda 95 (parada CA-3.3) + celda 102 (origen archivado) + mapa (§3.5, §3.6) |
| RF-4 | Celda 91 (tres variantes, criterio 18→19, referencia) + `metricas` + `referencia_prevision` + `informe_prevision_ree` + acta nueva (§3.7, §4) |
| RF-5 | `resumen_prevision` + `huecos` + acta 18→19 + lectura en solo lectura + `test_integridad_notebook` + `MEMORY.md` (§2, §6) |
| RNF-1 | Origen `prevision`/`estimada` en el mapa y en el archivo; nada no elegible entra; sin respaldos silenciosos (§3) |
| RNF-2 | Tope `min(objetivo − 1, hoy)` y ventana de relleno cerrada en `hoy`; observación solo hasta `hoy` (§3.1, §3.2) |
| RNF-3 | `hoy` como parámetro único de reloj; misma entrada, mismo resultado (tests de determinismo) |
| RNF-4 | Una variable, una regla de relleno, dos funciones de informe; sin dependencias ni cambios de esquema |
| RNF-5 | Solo `src/pipeline`, `src/notebooks`, `src/data` y `specs/`; backend y frontend intactos |
| RNF-6 | Mensajes, comentarios y documentos en español |

## 10. Verificación y números esperados

- **Archivo actual:** 1.777 filas `ree`, una elaboración por día, todas a un día
  del objetivo (2022-01-01 → 2026-11-12, valores 22.028–466.903 MWh). Con la
  regla de la 005, el histórico de generación (1.775 días) da **1.774 días con
  previsión real, 0 rellenos y 1 día sin dato** (2021-12-31, que los retardos ya
  descartaban). El camino `estimada` se ejercita con datos sintéticos en los
  tests y en cuanto el archivo tenga un hueco.
- **Predicción de mañana:** la previsión del 2026-11-12 se elaboró el 11 a las
  10:50, así que es elegible y el mapa la declarará `prevision`.
- **Comprobaciones al cerrar:** `node --test` en verde; notebook completo sin
  errores; acta nueva escrita y legible; `prediccion_propia` con una sola fila
  por emisión; `generacion` y `aemet_diario` con el mismo recuento y huella que
  antes de la celda nueva (se abren en solo lectura); decisión y números en
  `MEMORY.md`.
