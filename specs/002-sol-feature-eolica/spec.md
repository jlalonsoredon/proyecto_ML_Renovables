# Spec 002 — La insolación como variable del modelo eólico

## 1. Contexto y objetivo

El objetivo del proyecto es predecir la **generación eólica diaria peninsular del día siguiente**. La
spec 001 se desvió: fijó como objetivo entrenar un **modelo solar autónomo** (RF-6 y HU-4) y, para no
alterar el modelo eólico (RF-7), lo construyó como un bloque independiente al final del notebook
(celdas 85–90). Ese bloque funciona, pero **no aporta nada al objetivo**: un modelo que predice
fotovoltaica no mejora un modelo que predice viento.

Esta spec corrige el rumbo. La insolación no entra como objetivo, sino como **variable explicativa** del
modelo eólico: el cielo despejado es un indicador de situación anticiclónica y, por tanto, de viento
flojo. La relación existe y está medida: **r(eólica diaria, solar diaria) = −0,434**; quitando el
efecto del mes, **−0,351**.

**Objetivo:** incorporar `sol` y `tmed` del día anterior (`sol_lag1`, `tmed_lag1`) al conjunto de
variables del modelo eólico y decidir, con una validación walk-forward de cuatro folds, si la mejora
justifica reentrenar el modelo de producción.

**Por qué esta forma y no otra** (ver anexo A para las medidas):

- **No se usa la generación solar (MWh) como variable.** Su escala se ha multiplicado por 2,3 en cuatro
  años por instalación de capacidad (74.823 → 173.321 MWh/día), no por meteorología: cualquier
  coeficiente aprendido queda obsoleto. `sol` y `tmed` son invariantes a la capacidad instalada.
- **No se usa la insolación del mismo día.** No está disponible al predecir el día siguiente; usarla
  sería fuga de datos. El día anterior sí lo está.
- **No se encadena un modelo solar con el eólico.** Para dar la insolación de mañana el modelo solar
  necesitaría el pronóstico de insolación, que AEMET no publica (el pronóstico municipal trae viento,
  temperatura y estado del cielo). La cadena no resuelve el problema que aparentemente resuelve y añade
  un modelo, error propagado y riesgo de fuga en el apilado.
- **Sin medias móviles.** Medidas: añadirlas no mejora nada (0,7788 con y sin ellas) y multiplican las
  columnas.

## 2. Estado de partida

| Elemento | Valor |
|---|---|
| Modelo de producción | LinearRegression + StandardScaler, 16 variables |
| Línea base (notebook, celda 82) | RMSE **39.980,3** MWh · MAE 29.626,4 · **R² 0,7981** · MAPE 24,4 % |
| Test | 351 días, 2025-11-09 → 2026-10-25 |
| Datos | `generacion` 10.572 filas hasta 2026-10-27; `aemet_diario` 30.376 hasta 2026-10-25 |
| Insolación | 5 estaciones, 1.759 días, cobertura 93,6 %–99,9 % (puerta en verde) |
| Bloque solar autónomo | **retirado del notebook** el 2026-10-31 (celdas 85–90). Quedan `lr_solar.joblib` y `solar_metrics.json` como artefactos sueltos (D-2-1) |

Dos defectos conocidos que deben resolverse **antes** de medir, porque falsearían la comparación:

1. **La descarga AEMET de la celda 21 está desactivada** (`#descargar_aemet(...)`): al reejecutar, el
   notebook no refresca meteorología y trabaja con lo que haya en la BD, sin avisar.
2. **Hay dos criterios de fecha distintos**: la serie eólica convierte los timestamps UTC a
   `Europe/Madrid` (celda 52) y el bloque solar los corta con `SUBSTR(datetime, 1, 10)` en UTC
   (celda 86). En invierno, `23:00Z` pertenece al día siguiente en Madrid; al unir ambas series hay
   días desplazados y el error es silencioso.

## 3. Usuarios

- **U1 — Analista (autor del proyecto).** Ejecuta el notebook y necesita saber, con una regla explícita,
  si las variables solares mejoran el modelo eólico.
- **U2 — Evaluador técnico (tutor, revisor).** Necesita poder auditar la decisión: qué se probó, con qué
  folds, con qué métricas y por qué se aceptó o se rechazó.
- **U3 — Visitante de la web.** *No es usuario de esta versión*: no se expone nada nuevo en la interfaz.

## 4. Historias de usuario

- **HU-1.** Como U1, quiero que el notebook refresque la meteorología en cada ejecución, para no
  entrenar con una BD congelada sin darme cuenta.
- **HU-2.** Como U1, quiero que la serie eólica y la solar usen el mismo criterio de fecha, para que la
  unión por día no desplace registros en invierno.
- **HU-3.** Como U1, quiero dos variables solares del día anterior en el modelo eólico, para aprovechar
  la información sinóptica sin fuga de datos.
- **HU-4.** Como U1, quiero comparar el modelo con y sin esas variables sobre los mismos cuatro folds,
  para no confundir una mejora real con el ruido de un único año.
- **HU-5.** Como U1, quiero que el modelo de producción solo cambie si la mejora se repite, para no
  empeorar el servicio por una casualidad estadística.
- **HU-6.** Como U2, quiero un registro con las métricas de cada fold y la decisión tomada, para poder
  reproducir el análisis.

## 5. Requisitos funcionales

### RF-1 — Descarga meteorológica operativa
El sistema debe refrescar el histórico de AEMET en cada ejecución del notebook, respetando el límite de
seis meses por petición de la fuente.

- **CA-1.1** CUANDO se ejecuta la celda de descarga, el sistema debe solicitar únicamente los días que
  faltan en la base de datos.
- **CA-1.2** La descarga debe trocearse en ventanas de como máximo 150 días.
- **CA-1.3** SI una ventana falla, ENTONCES el sistema debe informar del tramo y del error, y no
  continuar como si el histórico estuviera completo.
- **CA-1.4** CUANDO se ejecuta por segunda vez sin días nuevos, el sistema no debe realizar ninguna
  petición y debe informarlo.
- **CA-1.5** La descarga no debe duplicar filas en `aemet_diario`.

### RF-2 — Criterio único de fecha
El sistema debe convertir los timestamps UTC de REE a fecha peninsular con una única función, usada
tanto por la serie eólica como por la solar.

- **CA-2.1** La conversión debe aplicar horario de verano europeo: UTC+2 desde el último domingo de
  marzo a las 01:00 UTC hasta el último domingo de octubre a las 01:00 UTC, y UTC+1 el resto del año.
- **CA-2.2** `2026-01-15T23:00:00Z` debe resolverse como `2026-01-16`.
- **CA-2.3** `2026-07-15T22:00:00Z` debe resolverse como `2026-07-16`.
- **CA-2.4** La función debe ser pura —recibe el timestamp y devuelve el día— y probarse sin depender de
  la zona horaria del sistema operativo.
- **CA-2.5** Las dos series deben construirse con la misma función; ninguna debe cortar la fecha con
  `SUBSTR` sobre UTC.

### RF-3 — Serie diaria de insolación y temperatura
El sistema debe disponer de una serie diaria nacional de `sol` y `tmed` para todo el periodo de la serie
eólica.

- **CA-3.1** La serie debe ser la media de las estaciones con dato de cada día (misma lógica que
  `solar.daily_national_series`).
- **CA-3.2** SI un día no tiene ninguna estación con dato, ENTONCES el sistema debe detenerse con un
  error que indique la fecha; no se interpola.
- **CA-3.3** La media debe calcularse sobre días naturales consecutivos, sin que un hueco desplace los
  valores.

### RF-4 — Variables solares del día anterior
El sistema debe añadir exactamente dos variables al modelo eólico: `sol_lag1` y `tmed_lag1`.

- **CA-4.1** Cada variable debe tomar el valor del **día natural inmediatamente anterior**, no el del
  último día con dato.
- **CA-4.2** SI el día anterior no tiene dato, ENTONCES la fila debe descartarse del entrenamiento y
  contarse en el informe; no se rellena con otro valor.
- **CA-4.3** No debe añadirse ninguna media móvil, retardo adicional ni la generación solar como
  variable.
- **CA-4.4** El primer día de la serie no debe tener valor en esas variables.

### RF-5 — Validación walk-forward de cuatro folds
El sistema debe comparar el modelo base (16 variables) con el ampliado (18 variables) sobre los mismos
cuatro folds cronológicos.

- **CA-5.1** Los folds deben ser los años 2023, 2024, 2025 y 2026; en cada uno, el entrenamiento debe
  usar exclusivamente los días anteriores al 1 de enero del año evaluado.
- **CA-5.2** La comparación debe usar las mismas fechas de entrenamiento y de prueba en las dos
  variantes, y solo diferir en las dos variables nuevas.
- **CA-5.3** El escalado debe ajustarse únicamente con el entrenamiento de cada fold.
- **CA-5.4** SI un fold no dispone de al menos 200 días de entrenamiento y 100 de prueba, ENTONCES debe
  omitirse e informarse.
- **CA-5.5** El informe debe mostrar, por fold, RMSE y R² de las dos variantes.

### RF-6 — Criterio de aceptación
La mejora debe considerarse real solo si se repite en la mayoría de los folds.

- **CA-6.1** La variante con variables solares se acepta si su RMSE es estrictamente menor en **al menos
  3 de los 4 folds**.
- **CA-6.2** SI el criterio no se cumple, ENTONCES el modelo de producción no se modifica y la decisión
  queda registrada con las métricas que la motivaron.
- **CA-6.3** El criterio no debe evaluarse sobre el resultado agregado ni sobre un único split.

### RF-7 — Reentrenamiento y persistencia condicionados
Solo si se cumple RF-6, el sistema debe reentrenar y actualizar el modelo de producción.

- **CA-7.1** El conjunto de variables del notebook y el de `backend/app/services/model_loader.py` deben
  coincidir exactamente (18 elementos).
- **CA-7.2** El modelo guardado debe contener `modelo`, `scaler` y `features`, con `features` idéntico al
  usado al entrenar, y debe poder recargarse y reproducir las métricas del test.
- **CA-7.3** Las copias del `.joblib` que apunta `MODEL_PATH` en cada entorno deben quedar sincronizadas;
  el informe debe indicar qué rutas se actualizaron.
- **CA-7.4** SI el criterio no se cumple, el `.joblib` de producción no debe sobrescribirse.

### RF-8 — El bloque solar autónomo se retira del notebook
El modelo solar de las celdas 85–90 deja de ser un objetivo del proyecto y desaparece del proceso.

- **CA-8.1** Las celdas del bloque solar (85 a 90) se eliminan; el notebook termina en el bloque eólico
  y queda con 85 celdas.
- **CA-8.2** Las celdas anteriores —catálogo, descarga, puerta de cobertura y todo el bloque eólico— deben
  quedar idénticas, sin reordenar ni renumerar.
- **CA-8.3** `src/pipeline/solar.py` se conserva: la serie diaria de `sol`/`tmed` que exige RF-3 se apoya
  en ella. Lo que se retira es el modelo solar, no la lógica de datos.
- **CA-8.4** Los artefactos del modelo solar (`lr_solar.joblib`, `solar_metrics.json`) no forman parte del
  pipeline y su retirada del árbol se decide aparte (D-2-1).

### RF-9 — Trazabilidad de la decisión
El sistema debe dejar un registro reproducible de la comparación.

- **CA-9.1** Debe quedar un informe con fecha de ejecución, métricas por fold de las dos variantes, el
  resultado del criterio y la decisión tomada.
- **CA-9.2** El informe debe registrar la cobertura de las estaciones solares usadas.
- **CA-9.3** `MEMORY.md` debe recoger la decisión y las métricas de referencia.

### RF-10 — Visibilidad del fallback de racha
El sistema debe informar cuando la variable `racha` de la predicción no proviene del pronóstico.

- **CA-10.1** CUANDO AEMET no devuelve `rachaMax`, el sistema debe indicarlo y decir cuántos días de
  histórico se usaron para estimarla.
- **CA-10.2** El aviso debe quedar en la salida del notebook; no se cambia el contrato de la API.
- **CA-10.3** Esta spec no corrige el fallback: solo lo hace visible y deja la corrección como duda
  abierta (D-2-5).

## 6. Requisitos no funcionales

- **RNF-1 — Continuidad de la estructura.** El cambio se hace dentro del pipeline existente: no se
  reordena el notebook, no se renombran las celdas del bloque eólico ni se reestructura el backend.
- **RNF-2 — Cambio mínimo.** Dos variables, un criterio de fecha y una descarga. Todo lo demás del
  modelo eólico permanece igual.
- **RNF-3 — Sin dependencias nuevas.** Se resuelve con lo ya disponible (`numpy`, `pandas`,
  `scikit-learn`, `joblib`, `sqlite3`).
- **RNF-4 — Reproducibilidad.** Dos ejecuciones con los mismos datos deben dar las mismas métricas.
- **RNF-5 — Honestidad del diagnóstico.** Un hueco de datos, una descarga fallida o una variable
  estimada nunca deben quedar ocultos tras un valor por defecto.
- **RNF-6 — Lógica pura y comprobable.** Las fechas y el criterio de aceptación se implementan como
  funciones puras en `src/pipeline/`, sin pandas, y se prueban con `node --test`.
- **RNF-7 — Puerta en verde.** `node --test "src/pipeline/tests/*.test.mjs"` debe pasar al cerrar cada
  tarea de lógica. Prohibido avanzar con la puerta en rojo.
- **RNF-8 — Idioma.** Comentarios, mensajes de salida y documentación en español.
- **RNF-9 — Respeto a la fuente.** La descarga debe respetar el límite de seis meses por petición y el
  rate limit de AEMET.

## 7. Casos límite

- **CE-1.** El día anterior a la predicción no tiene `sol` en ninguna estación: la fila se descarta y se
  cuenta.
- **CE-2.** `sol = 0` es un valor válido (día sin sol), no un dato ausente.
- **CE-3.** `sol > 24` es imposible: debe rechazarse antes de entrenar.
- **CE-4.** Cambio de hora: un día natural debe tener un único valor, sin duplicar ni perder registros.
- **CE-5.** La serie solar termina antes que la eólica: se recorta al tramo común y se informa.
- **CE-6.** La serie solar empieza después que la eólica: las primeras filas no tienen `lag1` y se
  descartan.
- **CE-7.** Un fold con menos de 200 días de entrenamiento.
- **CE-8.** Un fold cuyo año no está completo (2026): se evalúa con los días disponibles y se indica.
- **CE-9.** La descarga se interrumpe a mitad: al relanzar no debe duplicar ni perder datos.
- **CE-10.** Los dos años de entrenamiento de un fold producen un ajuste degenerado: se informa y no se
  usa ese fold para decidir.
- **CE-11.** Las variables solares empeoran el modelo: no se toca producción y se documenta.
- **CE-12.** El `.joblib` de producción no se puede recargar tras el reentrenamiento: se restaura la copia
  previa.

## 8. Fuera de alcance

- Mantener el modelo solar autónomo como objetivo de producción, exponerlo en la API o en la web, o
  conservar su bloque de celdas en el notebook.
- Encadenar una predicción solar como variable del modelo eólico.
- Cambiar el objetivo del modelo al residual (`demanda − solar − resto de renovables`).
- Añadir medias móviles de insolación o de temperatura.
- Usar la generación solar (MWh) como variable explicativa.
- Incorporar presión, nubosidad o radiación de ERA5.
- Corregir el fallback de `racha` con otra fuente (solo se documenta).
- Corregir la estación duplicada `9299X` del bloque eólico.
- Sincronizar las dos bases de datos del proyecto (`src/` y `backend/`).
- Añadir reentrenamiento automático en el scheduler o desplegar la nueva versión.

## 9. Criterios de finalización

La funcionalidad se considera terminada cuando:

1. La celda de descarga refresca AEMET por tramos, es idempotente y avisa de los fallos.
2. Existe una única función de fecha peninsular, con tests de los bordes de cambio de hora, y las series
   eólica y solar la usan.
3. El modelo ampliado usa exactamente 18 variables: las 16 actuales más `sol_lag1` y `tmed_lag1`.
4. Se han reportado RMSE y R² por fold de las dos variantes sobre los cuatro folds.
5. La decisión se ha tomado con el criterio de 3 de 4 folds y está registrada con sus métricas.
6. Si se aceptó: `FEATURE_COLS` coincide en notebook y backend, el `.joblib` recarga y reproduce las
   métricas, y las copias están sincronizadas. Si se rechazó: el modelo de producción está intacto.
7. El bloque solar está retirado del notebook (85 celdas), las celdas anteriores están intactas y
   `src/pipeline/solar.py` sigue disponible para la serie diaria.
8. `MEMORY.md` recoge la decisión, las métricas y las rutas actualizadas.

## 10. Dudas abiertas

- **[RESUELTA 2026-10-31] D-2-1 — ¿Se retira el bloque solar del notebook?** Sí. Las celdas 85–90 se
  han eliminado y el notebook termina en el bloque eólico (85 celdas, celdas 0–84 verificadas
  idénticas). Queda por decidir el destino de `lr_solar.joblib` y `solar_metrics.json`.
- **[NECESITA ACLARACIÓN] D-2-2 — Magnitud mínima de la mejora.** El criterio exige mejorar en 3 de 4
  folds, pero no fija cuánto. Lo medido es una mejora de RMSE del 2–3 % (≈1.000 MWh). ¿Se exige un
  mínimo (por ejemplo, ≥0,5 % en cada fold que mejora) o basta el signo?
- **[NECESITA ACLARACIÓN] D-2-3 — Momento del reentrenamiento.** ¿Se actualiza el modelo de producción en
  esta misma iteración si el criterio se cumple, o se deja preparado y se despliega aparte?
- **[NECESITA ACLARACIÓN] D-2-4 — Variables de temperatura.** Solo entra `tmed`. ¿Se probarán `tmin` y
  `tmax` en una iteración posterior o quedan descartadas? (Viene de D-3 de la spec 001.)
- **[NECESITA ACLARACIÓN] D-2-5 — Fallback de `racha`.** El pronóstico municipal de AEMET no publica
  `rachaMax`, así que en producción `racha` sale de la media de los últimos 7 días y cinco de las
  dieciséis variables (todas las medias móviles de racha) pierden información espacial. ¿Se corrige con
  otra fuente (aviso de rachas por municipio, ESIOS) o se asume?
- **[NECESITA ACLARACIÓN] D-2-6 — Constitución del proyecto.** `docs/constitution.md` sigue redactada
  para otro proyecto ("Diario de Estudio", `localStorage`, `node --test`, código en inglés). Esta spec
  cumple el espíritu (lógica pura, tests como puerta) pero no la letra. ¿Se adapta antes de seguir?
- **[NECESITA ACLARACIÓN] D-2-7 — Métrica de acierto.** El modelo eólico reporta acierto por quintiles.
  ¿Se mantiene como métrica secundaria del walk-forward o basta RMSE y R²?

## Anexo A — Evidencia de la decisión

Medición realizada el 2026-10-29 con los datos del repositorio, reproducida del análisis previo a esta
spec.

**Relación entre tecnologías** (`generacion`, 1.762 días): r(eólica, solar) = **−0,434**; quitando la
media de cada mes, **−0,351**.

**Ablación** (Ridge, split cronológico del notebook, 1.401 días de entrenamiento y 351 de prueba). La
base reproduce 42.764 / 0,7690 frente a los 39.980 / 0,7981 del notebook porque no replica la
interpolación de estaciones; lo relevante son las diferencias:

| Variables | RMSE | R² | ΔR² |
|---|---|---|---|
| Base eólica (16) | 42.764 | 0,7690 | — |
| + `sol`, `tmed` del mismo día | 41.504 | 0,7824 | +0,013 |
| + `sol`, `tmed` del día anterior | 41.846 | 0,7788 | +0,010 |
| + día anterior y medias móviles de 7 días | 41.855 | 0,7788 | +0,010 |

Test pareado sobre errores cuadráticos: t = −2,08 (mismo día) y t = −1,60 (día anterior).

**Walk-forward** (R², entrenamiento con todo lo anterior a cada año):

| Año evaluado | Base | Mismo día | Día anterior |
|---|---|---|---|
| 2023 | 0,777 | 0,794 | 0,790 |
| 2024 | 0,749 | 0,754 | 0,750 |
| 2025 | 0,727 | 0,743 | 0,740 |
| 2026 | 0,763 | 0,775 | 0,771 |

Conclusiones que fija esta spec: la señal existe y es estable en el tiempo; el 75 % de la mejora se
conserva usando solo información del día anterior; las medias móviles no aportan; y predecir la solar
para encadenarla no aporta nada que no esté ya en el día anterior.

**Deriva de la generación solar** (media diaria anual): 74.823 (2022) → 100.681 (2023) → 119.391 (2024) →
134.747 (2025) → 173.321 (2026). Motivo por el que se descarta como variable explicativa.
