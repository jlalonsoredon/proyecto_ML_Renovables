# Plan 003 — Archivo de previsiones meteorológicas para el modelo eólico

Deriva de `specs/003-archivo-predicciones-aemet/spec.md` (RF-1 a RF-13) y respeta `docs/constitution.md`.
Las tareas ejecutables irán en `tasks.md`; este documento fija el diseño. No contiene código: los bloques
del apartado 3 son pseudocódigo.

## 0. Alcance y tres avisos sobre el encargo

**Aviso 1 — No hay mapa geográfico.** La spec 003 no pide ninguna representación cartográfica (ni siquiera
hay interfaz). En este proyecto, «el mapa» es el **mapa de correspondencia entre una previsión y un valor**:
dado un día objetivo y una ubicación, qué elaboración era la válida y qué número sale de ella. Es donde se
juega la corrección de todo lo demás —una elaboración posterior al día objetivo convertiría el backtest en
una medición con información del futuro—, y el apartado 3.1 lo documenta. No se inventa un mapa geográfico:
no hay requisito que lo sostenga y el principio 1 de la constitución exige el mínimo cambio.

**Aviso 2 — No hay interfaz nueva.** La spec lo excluye en §7 y RNF-8 lo prohíbe. La «interfaz» de esta
funcionalidad es la **salida del notebook** (cobertura, antigüedad, tabla de ventanas, veredicto) y el
**registro del servicio** (resumen de captura). El único efecto visible en el producto es el valor de la
predicción si RF-11 llega a activarse. El apartado 4 lo detalla y lista lo que se descartó pintar.

**Aviso 3 — Dos desplegables, una lógica.** El backend se despliega con `rootDir: backend` (`render.yaml`),
así que no puede importar nada de `src/`. La captura vive en el backend (decisión del usuario, D-3 del
plan de origen), pero la lógica de derivación también la necesita el análisis. Se resuelve con una **copia
vendorizada y un test de paridad que la puerta ejecuta en cada pasada** (D-T2). Es deuda controlada y se
declara en el apartado 7.

**Restricción de fondo:** no se reordena el notebook, no se renombran sus etapas, no se toca el frontend y
no se cambia ningún contrato de la API. Todo lo nuevo con lógica propia vive en `src/pipeline/`, sin pandas
y sin red, para poder probarse en la puerta.

---

## 1. Archivos: qué se crea, qué se modifica y de qué responde cada uno

### 1.1 Se crean

| Archivo | Responsabilidad | RF |
|---|---|---|
| `src/pipeline/forecast.py` | **Lógica pura de la spec 003.** Normaliza los partes (diario y horario) con la elaboración que declaran, deriva temperatura y sol estimado, elige la previsión válida, construye medias móviles de previsión, calcula ventanas de evaluación y aplica el criterio de decisión. Solo biblioteca estándar. | RF-2, RF-5, RF-6, RF-7, RF-8, RF-9, RF-10 |
| `src/pipeline/tests/test_forecast.py` | Contrato de `forecast.py`: mapa de elaboraciones, huecos, ventanas incompletas, cielo nocturno, insolación fuera de rango, criterio de mayoría. | RF-5–RF-10 |
| `src/pipeline/tests/test_forecast_parity.py` | **Test de paridad**: la copia del backend y el módulo canónico producen el mismo resultado sobre los mismos partes; si divergen, la puerta falla. | RF-2, RF-7, RF-8 |
| `src/pipeline/tests/fixtures/prediccion_diaria.json` | Parte diario real capturado (anonimizado de clave), guardado como fixture para que el parseo no derive con el esquema de AEMET. | RF-1, RF-7, RF-8 |
| `src/pipeline/tests/fixtures/prediccion_horaria.json` | Parte horario real: el que trae `orto`/`ocaso` y la racha que falta en el diario. | RF-7, RF-8 |
| `backend/app/services/aemet_forecast.py` | **Cliente de predicción**: descarga en dos pasos (meta-URL → datos) los 12 municipios, reintenta, respeta el límite de peticiones y devuelve la elaboración declarada junto con las filas listas para guardar. Sin decisiones de negocio. | RF-1, RF-3, RF-6 |
| `backend/app/services/forecast_db.py` | **Persistencia del archivo**: crea el esquema, hace el upsert idempotente y responde las lecturas (última captura, filas por rango, estado de la captura). Sin lógica de derivación. | RF-2, RF-4, RF-13 |
| `backend/app/services/forecast_logic.py` | Copia vendorizada de `src/pipeline/forecast.py`, para que el backend derive las variables en la fase de RF-11 sin depender del árbol de análisis. La igualdad se exige en la puerta. | RF-7, RF-8, RF-11 |

### 1.2 Se modifican

| Archivo | Cambio | RF |
|---|---|---|
| `backend/app/tasks/scheduler.py` | Añadir `capture_forecast()` **antes** de `run_prediction()` en `run_daily_task`, con resumen de capturados, pendientes y errores; una captura sin ninguna fila deja traza de error. Incluye el reintento del mismo día. | RF-1, RF-6, RF-13 |
| `backend/app/services/db_ree.py` | **Una línea** en `init_db()` que invoca la creación del archivo de previsiones. No se toca ninguna función existente. | RF-2 |
| `backend/app/main.py` | Nada obligatorio: la tabla se crea desde `init_db()`, que ya corre en el arranque. Solo se añade el registro del nuevo paso en el log si se considera necesario. | RF-2 |
| `src/notebooks/main.ipynb` | **Dos celdas nuevas al final del bloque eólico**, sin reordenar: (a) cobertura, antigüedad y construcción de las variables de previsión en paralelo; (b) ventanas móviles, criterio y veredicto. Se apoyan en `df_ml` ya construido. | RF-9, RF-10, RF-13 |
| `src/pipeline/fechas.py` | `RETRASO_PUBLICACION_DIAS` de 3 a **4** (medido). Con 3, cada ejecución pide un día que no puede existir y grita «descarga incompleta» a diario, lo que enmascara un fallo real y rompe la honestidad del diagnóstico. | RF-13, RNF-3 |
| `src/pipeline/tests/test_fechas.py` | Caso del retraso de 4 y de la ventana vacía con ese retraso. | RF-13 |
| `MEMORY.md` | Decisión, métricas, estado del archivo y dudas abiertas. | RF-13 |
| `.joblib` en las rutas de `MODEL_PATH` y `backend/app/services/model_loader.py` | **Solo si RF-10 acepta**: conjunto de variables nuevo, recarga verificada y copias sincronizadas. | RF-11 |

### 1.3 No se toca

`docs/constitution.md` (D-2-6 sigue abierta), el frontend completo, los routers `backend/app/api/*`, el
contrato de `/api/prediction` y `/api/prediction-chart`, `model_loader.py` mientras dure la comparación, la
tabla `aemet_diario` (no se rellena nunca con previsiones) y el orden de las celdas existentes del notebook.

---

## 2. Funciones puras de lógica

Viven en `src/pipeline/forecast.py`, no importan pandas ni `sklearn`, no acceden a red ni a disco y no
consultan el reloj: **el día actual entra siempre como parámetro**. Identificadores en inglés (constitución,
principio 6) y comentarios y mensajes en español, igual que `insolation_probe.mjs`.

| Función | Firma conceptual | ¿Recibe `hoy`? | RF |
|---|---|---|---|
| `parse_daily_parte` | JSON del parte diario → elaboración declarada y lista de días normalizados (viento por tramo, `tmax`, `tmin`, cielo por tramo, `uvMax`) | No | RF-1, RF-7, RF-8 |
| `parse_hourly_parte` | JSON del parte horario → elaboración declarada y lista de días normalizados (temperaturas y vientos horarios, `orto`, `ocaso`, racha máxima) | No | RF-7, RF-8 |
| `capture_targets` | `hoy`, días ya archivados, horizonte → días objetivo a pedir hoy (en curso, siguientes y pendientes recuperables) | **Sí** | RF-1, RF-6 |
| `pending_days` | `hoy`, días esperados, días ya archivados, horizonte de la elaboración vigente → `{recuperables, perdidos}` | **Sí** | RF-6 |
| `choose_forecast` | filas del archivo, día objetivo, ubicación, `hoy` → `(valores, elaboración, antigüedad)` o `NO_DISPONIBLE` | **Sí** | RF-5 |
| `forecast_age_days` | elaboración, día objetivo → días naturales de antigüedad | No | RF-5 |
| `mean_temperature` | temperaturas horarias, o `tmax`/`tmin` → media del día o `NO_DISPONIBLE` | No | RF-7 |
| `daylight_hours` | latitud, fecha → horas de luz astronómicas en `(0, 24]` | No | RF-7 |
| `sky_factor` | código de estado del cielo → factor en `[0, 1]` | No | RF-7 |
| `estimate_sun` | tramos de cielo, latitud, fecha, `orto`/`ocaso` → horas estimadas o `NO_DISPONIBLE` | No | RF-7 |
| `forecast_national_series` | filas de una misma agregación (eólica o solar) → serie diaria de previsión por fecha | No | RF-7, RF-8 |
| `moving_average` | serie diaria, día objetivo, ventana (3/7/14) → media o `NO_DISPONIBLE` si falta algún día | No | RF-8 |
| `coverage_summary` | filas del archivo, `hoy` → días cubiertos, huecos, antigüedad media y ubicaciones caídas | **Sí** | RF-9, RF-13 |
| `evaluation_windows` | primer y último día disponibles, tamaño 21, paso 7, mínimo de entrenamiento, `hoy` → ventanas con índices de entrenamiento y prueba | **Sí** | RF-10 |
| `decide_improvement` | RMSE por ventana de cada variante, umbral 2 %, regla de mayoría → `{aceptada, motivo, ventanas_ganadas, ventanas_evaluadas}` | No | RF-10 |
| `truthfulness_report` | error de la previsión frente a la observación en el solape → MAE, sesgo y número de pares | No | RF-10 |

**Nota sobre «hoy» como parámetro.** Se cumple donde la función depende del día actual (`capture_targets`,
`pending_days`, `choose_forecast`, `coverage_summary`, `evaluation_windows`). No se añade a las
transformaciones sin estado (`parse_*`, `daylight_hours`, `sky_factor`, `estimate_sun`, `moving_average`,
`decide_improvement`): un parámetro que no se usa sería decorativo y falsearía el contrato. Misma desviación
consciente que en el plan 002, anotada en el apartado 7.

---

## 3. Algoritmos en pseudocódigo

### 3.1 Mapa de correspondencia (elaboración, día objetivo, ubicación) → valor · RF-2, RF-5, RF-8

Es el núcleo del riesgo: si se elige una elaboración posterior al día objetivo, el resultado es una medición
con información del futuro y todas las métricas salen mejores de lo que serán en producción.

```
MAPA_PREVISION(archivo, D, L, hoy):
    tope ← mínimo(D, hoy)                       # nunca una elaboración futura
    candidatas ← archivo donde objetivo = D, ubicación = L,
                             elaboración conocida y elaboración ≤ tope
    si candidatas está vacío:
        devolver NO_DISPONIBLE                  # nunca 0, nunca la observación
    e* ← la mayor elaboración de candidatas      # la más reciente, con hora
    fila ← candidatas con elaboración = e*       # única por clave
    devolver (valores(fila), antigüedad = D − día(e*))
```

Cuatro reglas que el diseño hereda de la spec y que el pseudocódigo obliga a respetar:

1. **La elaboración es la que declara la fuente, no la de nuestra descarga.** Se guarda `elaborado` tal cual;
   `capturado_en` es procedencia, no identidad. Descargar mañana un parte elaborado ayer no lo convierte en
   información de mañana, y contar con la fecha de captura convertiría el backtest en una medición con
   información del futuro.
2. **Una fila por clave.** `(elaboración, objetivo, ubicación)` es la identidad: recapturar la misma
   elaboración sustituye sus valores; una elaboración nueva es una fila nueva y no pisa la anterior.
3. **La antigüedad viaja con el valor.** Sin ella no se puede informar de CA-5.5 ni distinguir «la previsión
   es mala» de «la previsión llegó tarde».
4. **No hay respaldo.** Si no hay elaboración elegible, el valor es `NO_DISPONIBLE` y la fila del modelo se
   descarta; nunca se completa con la observación del día ni con una interpolación (RNF-2, CE-12).

Agregación por uso, cuando hace falta una serie nacional:

```
SERIE_NACIONAL(archivo, D, uso, hoy):
    valores ← []
    por cada ubicación L con uso indicado:
        v ← MAPA_PREVISION(archivo, D, L, hoy)
        si v es NO_DISPONIBLE: contar ausencia y continuar
        valores.añadir(v)
    si valores está vacío: devolver NO_DISPONIBLE
    registrar cuántas ubicaciones aportaron (la cobertura se informa, no se esconde)
    devolver media(valores)
```

### 3.2 Captura diaria y recuperación · RF-1, RF-3, RF-4, RF-6, RF-13

```
CAPTURA_DIARIA(hoy):
    horizonte ← días que cubre hoy la elaboración vigente     # medido: 7 en el parte diario
    esperados ← días de hoy−horizonte hasta hoy+horizonte     # lo máximo recuperable hacia atrás
    archivados ← claves (objetivo, ubicación) ya presentes en el archivo
    a_pedir ← capture_targets(hoy, archivados, horizonte)
    resumen ← vacío
    por cada ubicación del catálogo (7 eólicas + 5 solares):
        parte ← descargar diario y horario (2 pasos, con pausa y reintento)
        si falla:
            anotar incidencia con ubicación y causa
            continuar con la siguiente ubicación     # captura parcial, no abortar
        elaborado ← parte.elaborado                  # la elaboración la declara la fuente
        si elaborado falta:
            guardar el registro marcado como sin elaboración conocida   # no elegible
        por cada día del parte que esté en a_pedir:
            normalizar valores del día
            upsert (elaboración = elaborado, objetivo = día, ubicación) con el parte original
            # misma elaboración recapturada → sustituye; elaboración nueva → fila nueva
    pendientes ← pending_days(hoy, esperados, archivados, horizonte)
    escribir estado de la captura (fecha, elaboración servida, capturadas, guardadas, pendientes, errores)
    si no se capturó ninguna ubicación:
        terminar en fallo visible                  # CA-13.2
    imprimir resumen con causa de cada error y la elaboración que estaba sirviendo la fuente
```

Puntos que el pseudocódigo fija y que no son obvios:

- **La captura es parcial tolerante.** Una ubicación caída no cancela las demás (CA-3.3).
- **El reintento es del mismo día** (CA-1.5, CA-6.1): la tarea se repite a media mañana. Si la fuente sigue
  sirviendo una elaboración anterior que contiene el día pendiente, la recuperación es válida —la elaboración
  es la declarada, no la de hoy—. En cuanto la fuente publica la elaboración siguiente, ese día desaparece del
  horizonte y pasa a hueco definitivo (CA-6.3, CA-6.4). **La recuperación tardía con elaboración posterior al
  objetivo es, por tanto, imposible por construcción, no por política.**
- **No se guardan días fuera del horizonte** que el mapa va a consultar: el archivo crece con lo que se usa.
- **La elaboración servida se registra en el resumen.** Es el dato que permite detectar que el planificador
  corre antes de la publicación del día (D-3-3) sin adivinar.

### 3.3 Derivación de las variables de previsión · RF-7, RF-8

```
VARIABLES_DIA(D, hoy):
    # temperatura y sol, por ubicación y agregados
    por cada ubicación solar L:
        t ← media de temperaturas horarias, o (tmax+tmin)/2 si no hay horario
        h ← daylight_hours(latitud(L), D)
        si algún tramo del cielo está vacío: s ← NO_DISPONIBLE
        si no: s ← suma sobre tramos de (horas del tramo × sky_factor(código))
        recortar s a [0, h]                        # CE-10
    tmed_prevista ← media de t sobre las ubicaciones solares con dato
    sol_previsto  ← media de s sobre las ubicaciones solares con dato

    # viento y racha, con su media móvil
    por cada ubicación eólica L y cada día d de la ventana de 14:
        v[d] ← viento medio del día (del parte válido para d)
        r[d] ← racha del parte diario; si vacía, del horario; si tampoco, NO_DISPONIBLE
    si falta cualquier día de la ventana:
        vel_maN ← NO_DISPONIBLE                     # CA-8.4, CE-12: no se calcula con lo que haya
    si no:
        vel_maN ← media de v sobre los N últimos días hasta D
        racha_maN ← análoga, o NO_DISPONIBLE si falta una racha
    devolver (tmed_prevista, sol_previsto, vel_ma*, racha_ma*)
```

Reglas que el pseudocódigo hace explícitas:

- **Ninguna ventana mezcla orígenes.** La media de 14 días se construye con 14 previsiones, una por día, cada
  una la que era válida para su propio día. No se completa con observación (RNF-2, CA-8.5).
- **La ventana incompleta no se acorta.** Es `NO_DISPONIBLE`, no una media de los días disponibles (CA-8.4).
- **`sol` es una estimación y se declara como tal.** Se guarda junto al valor un indicador de origen; el
  modelo nunca lo recibe como si fuera una observación.

Calibración previa a usarla (CA-7.7):

```
CALIBRAR_SOL(archivo, observado):
    pares ← (sol_estimado, sol_observado) de los días con ambos
    si pares < mínimo_muestral: devolver "insuficiente"
    medir correlación y sesgo sobre la media nacional
    si correlación < 0,7: descartar sol; el modelo se queda solo con tmed
    si no: usar el estimado, informando correlación y sesgo
```

### 3.4 Comparación en ventanas móviles · RF-9, RF-10

```
COMPARAR(archivo, observado, hoy):
    serie_prevista ← variables construidas solo con previsión
    serie_base     ← variables actuales (las que usa producción)
    ventanas ← evaluation_windows(primer día con ambas series, último día, 21, 7, hoy)
    por cada ventana:
        entrenar variante base con las fechas de entrenamiento de la ventana
        predecir las fechas de prueba
        ídem variante con previsión, con las MISMAS fechas
        descartar y contar las filas sin previsión completa (CA-9.4)
        calcular RMSE de las dos
    si ventanas evaluadas < 3: no decidir, informar (CA-10.4)
    decidir con decide_improvement (umbral 2 %, más de la mitad)
    informar además del error de la previsión frente a la observación (CA-10.6)
```

Detalles que el pseudocódigo fija:

- **Mismas fechas, mismo escalado.** El escalado se ajusta solo con el entrenamiento de cada ventana; si no, la
  comparación mide la fuga, no la mejora.
- **El descarte se cuenta, no se esconde.** Cada fila sin previsión completa resta días de evaluación y aparece
  en el informe.
- **Sin dos meses no hay veredicto.** Menos de tres ventanas es «evidencia insuficiente», no un rechazo.

### 3.5 Decisión y actualización condicionada · RF-10, RF-11

```
SI criterio aceptado (≥2 % en más de la mitad de las ventanas):
    reentrenar con el conjunto nuevo
    guardar en una ruta temporal y recargar
    si la recarga no reproduce las métricas: restaurar la copia previa y registrar     # CA-11.4
    sincronizar todas las copias que usa cada entorno y anotarlas en el informe       # CA-11.3
SI NO:
    no tocar el modelo de producción y dejar la decisión registrada                   # CA-10.5
```

Orden obligatorio: **primero se escribe en una ruta temporal y se verifica; solo después se sobrescribe**. El
modelo servido nunca queda en un estado que no haya sido recargado y comprobado.

### 3.6 Frescura de las variables de generación · RF-12

```
LAGS_DE_GENERACION(hoy):
    serie ← generación de REE hasta la última fecha publicada   # no se recorta a la fecha meteorológica
    si el día más reciente está muy por debajo de su entorno:
        señalarlo y no usarlo en silencio                        # CA-12.2
    devolver eolica_lag1/2/3/7 y eolica_ma7 desde esa serie
```

Este bloque no depende del archivo y puede cerrarse por separado (CA-12.3). Toca la definición de cinco
variables del modelo: exige reentrenar para que las métricas sean comparables y así debe documentarse
(CA-12.4).

---

## 4. Interfaz: qué se pinta y dónde

**No hay interfaz web en esta spec** (§7 y RNF-8). Lo que se pinta es la salida del notebook y el registro del
servicio:

| Superficie | Qué se pinta | RF |
|---|---|---|
| Salida del notebook · cobertura | días con archivo, días esperados, huecos, antigüedad media de la previsión usada y ubicaciones sin dato | RF-9, RF-13 |
| Salida del notebook · variables | cuántas filas se descartan por no tener previsión completa y por qué variable | RF-9 |
| Salida del notebook · tabla de ventanas | por ventana: fechas, RMSE de cada variante y diferencia; y el error de la previsión frente a la observación | RF-10 |
| Salida del notebook · veredicto | aceptado o rechazado, ventanas ganadas sobre evaluadas, motivo y decisión | RF-10, RF-13 |
| Registro del servicio | por captura: ubicaciones capturadas, días guardados, pendientes, errores con causa | RF-1, RF-13 |
| Estado de la captura | una fila por ejecución, consultable para saber si el archivo se está llenando | RF-13 |

**Lo que se descartó pintar** (y por qué):

- **Tarjeta o panel nuevo en la web.** §7 lo excluye; además obligaría a endpoint nuevo y a tocar el frontend,
  contra RNF-8.
- **Endpoint nuevo de estado del archivo.** Sería la forma natural de dar visibilidad a U3, pero cambia el
  contrato de la API, que la spec prohíbe. La visibilidad se resuelve en el registro y en la tabla de estado.
- **Avisos nuevos en `/api/prediction`.** El campo `avisos` existe, pero añadir motivos nuevos cambia lo que
  consume el frontend sin que esta spec lo autorice.

**Efecto en el producto:** ninguno mientras RF-11 no se active. Si se activa, cambia el valor de la predicción
y las variables del modelo; la forma de la respuesta y la interfaz siguen idénticas.

---

## 5. Decisiones técnicas y alternativas descartadas

1. **Archivo en tabla propia, no una columna `origen` en la observación.** · RF-2
   - *Por qué:* `aemet_diario` tiene clave `(fecha, indicativo)`; meter previsiones obliga a sobrescribir el día
     cuando llega la observación y la serie cambia de fuente sin rastro. Dos orígenes, dos tablas.
   - *Descartada:* columna `origen` en la tabla existente (rompe la clave y contamina la observación); fichero
     plano (no permite consultas ni upsert por clave).

2. **La identidad de la previsión es la elaboración que declara el parte.** · RF-2, RF-4, RF-5
   - *Por qué:* el parte trae `elaborado` (medido: `2026-11-01T08:59:08`) y su horizonte empieza en ese mismo
     día. Usar la fecha de captura como elaboración haría que un parte descargado por la mañana «valiera» para
     días que la fuente elaboró antes, y que una recaptura creara elaboraciones falsas. Con la elaboración
     declarada, la regla `E ≤ D` se cumple por construcción y solo puede violarla una fuente que reelabore el
     pasado —exactamente lo que RF-5 debe bloquear—.
   - *Descartada:* elaboración = día de captura (mezcla procedencia con información y provoca el conflicto con
     la recuperación); elaboración = primer día del horizonte (es una inferencia, no un dato: fallaría en
     cuanto la fuente cambiara el tamaño del horizonte); elaboración = día natural únicamente (dos
     elaboraciones del mismo día colapsarían en una y se perdería la que se usó).
   - *Consecuencia:* se guarda el parte original en la misma fila, para poder recalcular el proxy cuando AEMET
     ya no sirva ese parte.

3. **Idempotencia por elaboración: recapturar sustituye, elaborar de nuevo añade.** · RF-4
   - *Por qué:* dos capturas del mismo parte deben dejar el archivo igual (CA-4.1), pero una elaboración
     nueva del mismo día objetivo es información nueva y no puede pisar a la anterior (CA-4.2, CA-2.3). Al
     llevar la hora en la clave, las dos cosas salen gratis y sin lógica condicional.
   - *Descartada:* upsert sobre `(día, objetivo, ubicación)` (obliga a decidir a mano si la actualización
     sustituye o acumula, y pierde la elaboración que realmente se usó); `INSERT OR IGNORE` (congela la primera
     versión y oculta actualizaciones); añadir una fila nueva en cada captura (duplica sin criterio).

4. **Regla anti-fuga como función pura, y la misma regla expresada en la consulta del backend.** · RF-5, RF-11
   - *Por qué:* el análisis necesita la regla en memoria y el backend la necesita en SQL; el test de paridad
     compara ambas sobre el mismo fixture, así que una divergencia rompe la puerta en vez de aparecer en
     producción.
   - *Descartada:* solo SQL (no se puede probar sin base de datos); solo función y traer toda la tabla al
     backend (lee de más y duplica la antigüedad en cada petición de predicción).

5. **Copia vendorizada de la lógica en el backend, con test de paridad.** · RF-1, RF-7, RF-8, RF-11
   - *Por qué:* el backend se despliega con `rootDir: backend`, así que no ve `src/`. La alternativa a copiar es
     no compartir y dejar que las dos partes calculen distinto, que es peor.
   - *Descartada:* mover la captura fuera del backend (contradice la decisión del usuario y obliga a mantener un
     proceso programado aparte); paquete compartido instalable (dependencia nueva, RNF-9); implementar la lógica
     en JavaScript y llamarla desde Python (subproceso en el camino caliente de la predicción).
   - *Coste asumido:* un archivo duplicado y un test que lo vigila. Es deuda declarada, no un patrón a repetir.

6. **Previsión diaria para los 12 municipios y horaria también para los 12.** · RF-7, RF-8
   - *Por qué:* la racha del parte diario llega vacía (medido) y CA-7.1 manda usar la temperatura horaria cuando
     existe. Pedirla solo para las eólicas dejaría `tmed` calculada de dos formas distintas según la ubicación.
   - *Descartada:* horaria solo para las 7 eólicas (ahorra 10 peticiones y rompe la uniformidad de `tmed`); solo
     diaria (imposible: sin racha, las tres medias de racha no existen).

7. **Sol estimado por horas de luz × factor de cielo, calibrado contra la observación.** · RF-7
   - *Por qué:* la previsión no trae insolación y no hay proveedor oficial que la publique. El cálculo
     astronómico es determinista, sin dependencias, y el factor de cielo es la única pieza que se calibra con
     datos.
   - *Descartada:* usar `uvMax` directamente (otra escala, y el modelo aprendió horas de sol); regresión con
     `uvMax` como primera opción (necesita muestra que aún no existe); interpolar la insolación observada (fuga
     de información y RNF-2).

8. **Medias móviles íntegramente de previsión, no mixtas.** · RF-8
   - *Por qué:* una media mitad observada, mitad prevista tiene un error que no se puede atribuir a nada y
     cambia de composición con la latencia de AEMET. La serie de previsión es homogénea por construcción.
   - *Descartada:* completar con observación los días ya publicados (rompe RNF-2 y hace que la feature cambie de
     definición según el día); usar `shift`/`rolling` de pandas sobre el índice (con un hueco desplaza la
     ventana, mismo defecto que en `lag_series`).

9. **Ventanas móviles de 21 días con paso 7, en lugar de los cuatro folds anuales.** · RF-10
   - *Por qué:* con dos meses de archivo no hay cuatro años que evaluar; la ventana móvil da varias
     observaciones del mismo fenómeno y el criterio de mayoría evita decidir con una sola.
   - *Descartada:* reutilizar `evaluacion.walk_forward_folds` (exige años completos de archivo); un único split
     (prohibido por CA-10.1 y por la propia spec 002).

10. **Criterio de magnitud mínima, no solo el signo.** · RF-10
    - *Por qué:* lo fijado por el usuario: 2 % de RMSE en más de la mitad de las ventanas. Con muestras cortas,
      el signo solo acepta mejoras de 200 MWh que caben en el ruido.
    - *Descartada:* solo el signo (riesgo de aceptar casualidad); umbral en MWh absolutos (depende del nivel de
      generación de cada año); un solo estadístico agregado (prohibido por CA-10.3).

11. **La captura corre en el backend, con su planificador.** · RF-1, RF-6
    - *Por qué:* decisión del usuario. Es el único proceso que ya corre solo todos los días y sigue vivo si la
      máquina del analista está apagada; el archivo no admite huecos irreemplazables.
    - *Descartada:* script con tarea programada del sistema (no sobrevive a un portátil apagado); captura al
      ejecutar el notebook (huecos en cuanto pasen días sin ejecutar).
    - *Coste asumido:* obliga a desplegar y a duplicar la lógica (decisión 5).

12. **Recuperación acotada al horizonte de la fuente, nunca interpolación.** · RF-6
    - *Por qué:* mientras la fuente siga sirviendo una elaboración que contenga el día pendiente, recuperarlo es
      lícito —la elaboración es la declarada, no la de hoy— y cuesta una petición. En cuanto publica la
      elaboración siguiente, el día desaparece de su horizonte: ahí termina la recuperación y empieza el hueco,
      que se registra y se cuenta. La regla no depende de nuestra buena voluntad: es una propiedad del
      proveedor.
    - *Descartada:* interpolar el hueco (RNF-2); dar el día por perdido al primer fallo (tira días
      recuperables); contar la fecha de captura como elaboración (haría «válido» un parte que no lo es y abriría
      la puerta a la fuga); guardar el parte recuperado sin su elaboración real (imposible saber después qué se
      usó).

13. **El parte original se guarda por día objetivo, no el sobre completo.** · RF-2
    - *Por qué:* el mapa consulta por día; guardar el sobre de siete días repetiría la misma información en siete
      filas y haría ambiguo qué se actualiza en un upsert.
    - *Descartada:* guardar el sobre entero en cada fila (duplicación ×7); guardar solo números (imposible
      recalibrar el proxy cuando la muestra crezca).

14. **`RETRASO_PUBLICACION_DIAS` a 4.** · RF-13
    - *Por qué:* medido dos días seguidos en tres estaciones. Con 3, la descarga pide todos los días un día
      inexistente, informa de fallo permanente y convierte el aviso en ruido: un fallo real pasaría inadvertido.
    - *Descartada:* dejar el 3 y filtrar el aviso (mantiene la petición inútil y oculta el diagnóstico).

---

## 6. Estrategia de tests con `node --test`

**Puerta única:** `node --test "src/pipeline/tests/*.test.mjs"`. El runner es Node; la lógica es Python.
`gate.test.mjs` ya lanza `python -m unittest discover -s src/pipeline/tests` y falla si el código de salida no
es 0. Los ficheros nuevos se recogen solos: **no hay que tocar la puerta**, y todo lo de esta spec queda
gateado por `node --test` como exige la constitución (principio 4), sin instalar nada (`unittest` y
`sqlite3` son biblioteca estándar).

**Ciclo por tarea:** test primero en rojo, implementación mínima, verde, refactor. Prohibido cerrar una tarea
con la puerta en rojo (RNF-6).

| Módulo | Casos obligatorios | RF |
|---|---|---|
| `test_forecast.py` · mapa | elaboración anterior al objetivo → válida; elaboración igual al objetivo → válida y preferida; elaboración posterior → descartada aunque sea la única; dos elaboraciones válidas → gana la más reciente; sin elaboraciones → `NO_DISPONIBLE`; elaboración ausente → no elegible; antigüedad correcta en días; captura posterior a la elaboración no altera la elegibilidad | RF-5 |
| `test_forecast.py` · identidad | misma elaboración recapturada → un solo registro y valores actualizados; elaboración nueva del mismo objetivo → dos registros y gana la nueva; la elaboración anterior se conserva | RF-2, RF-4 |
| `test_forecast.py` · captura | horizonte completo; horizonte corto informado; día en curso ausente; reintento del mismo día; pendiente recuperable mientras la elaboración servida lo contenga y perdido en cuanto se publica la siguiente | RF-1, RF-6 |
| `test_forecast.py` · temperatura | media horaria con 24 valores; día de cambio de hora con 23 y con 25; sin horario → media de extremos; sin extremos → `NO_DISPONIBLE` | RF-7 |
| `test_forecast.py` · sol | solsticios en las latitudes de las cinco plantas; `sky_factor` de todos los códigos, incluidos los nocturnos; tramo vacío → `NO_DISPONIBLE`; resultado recortado a `[0, horas de luz]`; día cubierto → 0 (válido, no hueco) | RF-7 |
| `test_forecast.py` · medias móviles | ventana de 14 completa; 13 días → `NO_DISPONIBLE`; hueco interno → `NO_DISPONIBLE`; un solo día sin racha invalida la media de racha y no la de viento; la ventana no se acorta nunca | RF-8 |
| `test_forecast.py` · ventanas | ventanas sin solape con paso 7; entrenamiento siempre anterior a la prueba; menos de tres ventanas → sin decisión; última ventana incompleta descartada | RF-10 |
| `test_forecast.py` · criterio | mejora ≥2 % en más de la mitad → aceptada; mejora en la mitad exacta → rechazada; mejora del 1,9 % en todas → rechazada; empate → no cuenta; un solo fold peor → motivo correcto | RF-10 |
| `test_forecast.py` · cobertura | archivo vacío; archivo con huecos; ubicaciones caídas; antigüedad media; reproducibilidad (misma entrada, misma salida) | RF-9, RF-13 |
| `test_forecast_parity.py` | el módulo canónico y la copia del backend dan el mismo resultado sobre el fixture diario y el horario; la regla de elección coincide con la consulta del backend sobre una base en memoria | RF-2, RF-5, RF-7, RF-8 |
| `test_fechas.py` | retraso de 4: la ventana termina en `hoy−4`; con la BD al día devuelve `None` | RF-13 |

**Lo que la puerta no puede cubrir** (y cómo se verifica):

| Cambio | Verificación manual |
|---|---|
| Descarga real de los 12 municipios | Ejecutar el paso de captura dos días seguidos: el segundo día añade los días nuevos y 0 duplicados (T-06) |
| Elaboración que sirve la fuente a la hora del planificador | Ejecutar a esa hora y anotar la elaboración declarada y el horizonte: el día en curso debe venir (CA-1.2); si el archivo va una elaboración por detrás, decidir la segunda captura (D-3-3) |
| Límite de peticiones de AEMET | Cronometrar una captura completa y revisar que no aparecen 429 (T-05) |
| Calibración de `sol` | Comparar estimado y observado en el solape y dejar MAE y correlación en el informe (T-11) |
| Celdas del notebook | Ejecución completa y comparación de la tabla de ventanas con el informe |
| Actualización del modelo | Recarga del `.joblib`, lista de variables idéntica en notebook y backend, y `GET /api/prediction` respondiendo (T-14) |

**Criterio de parada:** si la puerta falla, no se avanza. Si el criterio rechaza la mejora, la fase de modelo se
cierra sin tocar producción y se documenta.

---

## 7. Cumplimiento de la constitución

| Principio | Cómo se cumple | Desviación |
|---|---|---|
| 1. Simplicidad y continuidad | Dos módulos nuevos en `src/pipeline` (lógica + tests), dos en el backend (cliente y persistencia), una línea en `init_db`, un paso más en la tarea diaria y dos celdas al final del notebook. Nada se reordena ni se renombra | La copia vendorizada de la lógica es duplicación consciente; se justifica en la decisión 5 y se vigila con la puerta |
| 2. La spec manda | Cada pieza de los apartados 1–3 referencia su RF y la matriz del apartado 8 no deja ninguno sin cubrir | Las dudas abiertas bloquean tareas concretas: se listan en el apartado 9 como P-2 a P-4 y no se decide por ellas. P-1 (RF-5 contra RF-6) quedó cerrado al fijar que la elaboración declarada por la fuente, y no la fecha de captura, es la identidad de la previsión |
| 3. Lógica separada, con `hoy` como parámetro | Toda la lógica vive en funciones puras sin red, sin disco y sin reloj; las cinco funciones que dependen del día actual lo reciben | Las transformaciones sin estado no reciben `hoy` (parámetro decorativo), igual que en el plan 002 |
| 4. Tests como puerta, sin paquetes | `node --test` ejecuta la suite de Python; la lógica nueva solo usa la biblioteca estándar | La captura real y el notebook requieren red y pandas: se verifican a mano, como en el plan 002 |
| 5. Los datos son sagrados | Copia de la base antes de la primera captura; la observación no se modifica nunca; el archivo no se purga; el modelo se escribe en temporal y se verifica antes de sustituir | El principio está redactado para `localStorage`; aquí se traduce a archivo irreversible y copias de seguridad |
| 6. Idioma | Identificadores en inglés y comentarios, mensajes y documentación en español, como `insolation_probe.mjs` | `fechas.py`, `solar.py` y `evaluacion.py` usan identificadores en español y no se renombran (mínimo cambio): quedan anotados en D-2-6 |

---

## 8. Matriz de cobertura de requisitos

| RF | Piezas | Se prueba en |
|---|---|---|
| RF-1 Captura diaria | `aemet_forecast.py`, `capture_targets`, paso nuevo del planificador | `test_forecast.py` (captura), T-05/T-06 |
| RF-2 Archivo separado | `forecast_db.py` (esquema), `forecast.py` (`parse_*`), guardado del parte original | `test_forecast_parity.py`, T-04 |
| RF-3 Cobertura de ubicaciones | catálogo de 12 en `aemet_forecast.py`, columna de uso | `test_forecast.py` (cobertura), T-02 |
| RF-4 Idempotencia | upsert por clave en `forecast_db.py` | `test_forecast.py` (identidad), T-06 (dos capturas, 0 duplicados) |
| RF-5 Anti-fuga | `choose_forecast`, `forecast_age_days`, consulta equivalente del backend | `test_forecast.py` (mapa), `test_forecast_parity.py` |
| RF-6 Recuperación | `capture_targets`, `pending_days`, reintento del planificador | `test_forecast.py` (captura), T-07 |
| RF-7 Temperatura y sol | `mean_temperature`, `daylight_hours`, `sky_factor`, `estimate_sun`, calibración | `test_forecast.py` (temperatura y sol), T-10/T-11 |
| RF-8 Viento, racha y medias | `parse_hourly_parte`, `forecast_national_series`, `moving_average` | `test_forecast.py` (medias), T-09 |
| RF-9 Integración paralela | celdas nuevas del notebook, `coverage_summary` | Ejecución del notebook, T-12 |
| RF-10 Comparación y criterio | `evaluation_windows`, `decide_improvement`, `truthfulness_report` | `test_forecast.py` (ventanas y criterio), T-13 |
| RF-11 Actualización condicionada | guardado en temporal, recarga verificada, `model_loader.py` y copias | Verificación manual, T-14 |
| RF-12 Frescura de generación | bloque de lags en el notebook, lectura de REE sin recorte | Verificación manual, T-15 (independiente) |
| RF-13 Trazabilidad | estado de captura, resumen del planificador, informe JSON, `MEMORY.md`, retraso a 4 | `test_fechas.py`, `test_forecast.py` (cobertura), T-16 |
| RNF-1 … RNF-11 | Único archivo en la base del servicio; sin mezcla de orígenes; puerta; idioma | Matriz de tests del apartado 6 |

---

## 9. Riesgos y puntos de parada

1. **[CERRADO 2026-11-01] P-1 · RF-5 contra RF-6.** Recuperar un parte de ayer ya no inventa una elaboración
   de hoy: la elaboración es la que el parte declara. Como el horizonte de un parte empieza en su propia
   elaboración, un día solo puede recuperarse desde una elaboración que lo contenga, y `E ≤ D` se cumple
   siempre por construcción. La recuperación termina cuando la fuente publica la elaboración siguiente; a partir
   de ahí el día es hueco. No queda nada que decidir: RF-5 y RF-6 ya no se contradicen.
2. **P-2 · D-3-1 (bloqueante para T-02).** Los cinco municipios solares no están fijados. Sin ellos el catálogo
   no tiene 12 entradas y la cobertura de RF-3 no se puede cumplir.
3. **P-3 · D-3-3 (no bloqueante; se mide al operar T-05).** A las 3:00 la fuente probablemente sirve la
   elaboración de la tarde anterior. El día en curso llega y es válido, así que CA-1.2 se cumple; lo que no se
   guarda nunca es la elaboración del mismo día. Si la serie debe usar la elaboración más fresca, hace falta
   una segunda captura por la mañana y hay que medir qué elaboración se sirve a cada hora.
4. **P-4 · D-3-2 (bloqueante para T-13).** Con dos meses de archivo, entrenar solo con días de previsión deja
   una muestra minúscula; entrenar con observación mantiene el desajuste. Sin decisión, el veredicto no es
   interpretable.
5. **El `join` se desplaza un día** entre la serie de previsión y la observada → la mejora medida sería falsa.
   Parada en T-12 hasta verificarlo a mano con un día de verano y otro de invierno.
6. **La ventana de 14 días nunca se completa** por rachas ausentes (CE-7) → las tres medias de racha no existen
   y la variante con previsión no es comparable. Se informa y no se decide.
7. **El proxy de `sol` no correlaciona** → se descarta y el modelo se queda solo con `tmed` (CA-7.7). La
   comparación se repite sin `sol` y se documenta.
8. **AEMET limita o corta la captura** (429, 24 partes diarios + 24 horarios) → reintento del mismo día y
   recuperación marcada; si se acumulan días sin captura, el archivo no sirve para decidir y se informa.
9. **El modelo actualizado no recarga** → se restaura la copia previa (CE-18) y no se toca producción.
10. **D-3-5 y D-3-6 abiertas** → afectan a cómo se tratan los huecos en las ventanas y a si se añade un mínimo
    absoluto de mejora. Se implementa lo que fija la spec (2 %, mayoría, descartar filas incompletas) y se
    anota la respuesta cuando llegue.
11. **La fuente reelabora un día pasado** (no ocurre hoy, pero podría ocurrir con otro proveedor o con un
    reanálisis) → esas filas se guardan y **no son elegibles** por CA-5.3. Es la única prueba de que la regla
    anti-fuga sirve para algo más que documentar: si algún día aparece una elaboración posterior a su objetivo,
    el archivo la contiene y el mapa la ignora.

---

## 10. Orden de ejecución

| Tarea | Contenido | RF | Depende de |
|---|---|---|---|
| T-01 | Fixtures reales de los dos partes (diario y horario) | RF-2 | — |
| T-02 | Catálogo de 12 ubicaciones con su uso | RF-3 | P-2 |
| T-03 | `parse_daily_parte` / `parse_hourly_parte` + tests | RF-1, RF-7, RF-8 | T-01 |
| T-04 | Esquema del archivo + upsert + tests en base en memoria | RF-2, RF-4 | T-02 |
| T-05 | `aemet_forecast.py` y paso de captura en el planificador | RF-1, RF-3, RF-6, RF-13 | T-03, T-04 |
| T-06 | Verificar dos capturas seguidas: días nuevos y 0 duplicados | RF-4 | T-05 |
| T-07 | `capture_targets` / `pending_days` + reintento y recuperación acotada al horizonte | RF-6 | T-05 |
| T-08 | `choose_forecast` + paridad con la consulta del backend | RF-5 | T-04 |
| T-09 | `mean_temperature`, `daylight_hours`, `sky_factor`, `estimate_sun` | RF-7 | T-03 |
| T-10 | `moving_average` y serie nacional de previsión | RF-8 | T-09 |
| T-11 | Calibración de `sol` contra la observación (correlación y sesgo) | RF-7 | T-09 |
| T-12 | Celdas nuevas del notebook: cobertura y variables en paralelo | RF-9 | T-08, T-10 |
| T-13 | `evaluation_windows`, `decide_improvement` y tabla de veredicto | RF-10 | T-12, P-4 |
| T-14 | Actualización condicionada del modelo y verificación de recarga | RF-11 | T-13 |
| T-15 | Frescura de generación (independiente del archivo) | RF-12 | — |
| T-16 | Informe, `MEMORY.md` y cierre de dudas | RF-13 | T-14 |

Orden por fases: **capturar** (T-01–T-07), **derivar** (T-08–T-11), **comparar** (T-12–T-13), **decidir**
(T-14) y **transversal** (T-15–T-16). Las fases no se solapan en el tiempo: un archivo con huecos no sirve para
decidir, y decidir sin calibración es apostar.
