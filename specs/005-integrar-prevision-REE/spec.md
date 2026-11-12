# Spec 005 — La previsión de REE del día objetivo como variable del modelo

- **Estado:** borrador para revisión
- **Fecha:** 2026-11-11
- **Depende de:** spec 004 (archivo de previsiones y origen declarado) y spec 002
  (puerta de aceptación walk-forward).
- **Sustituye a:** nada. La spec 004 sigue vigente: esta añade un uso nuevo de la
  previsión de REE, no cambia el que ya existe.

## 1. Contexto

El proyecto predice la generación eólica **diaria peninsular** del día siguiente. El
modelo vigente del notebook usa 18 variables: calendario, viento y racha del día
objetivo, seis medias móviles de viento y racha, cuatro retardos de la generación, una
media de 7 días de la generación y dos variables solares del día anterior.

Desde la spec 004 se archiva la **previsión diaria D+1 de generación eólica peninsular**
que publica REE, con su elaboración declarada. Esa previsión es, por sí sola, un
predictor del día objetivo: en el histórico medido tiene **MAE 13.194 MWh y RMSE
19.969 MWh**, mejor que el modelo actual (**MAE 29.950 y RMSE 39.703** en su test).

Sin embargo, hoy esa previsión **solo se usa para tapar huecos** de los retardos y de la
media de 7 días cuando falta la observación. Cuando la observación existe, el modelo
nunca ve la previsión, aunque sea la mejor información disponible sobre el día que se
quiere predecir.

## 2. Problema

El modelo desaprovecha la mejor señal disponible sobre el día objetivo. Además, la
previsión entra hoy de forma indirecta y parcial: solo cuando la observación falta y
solo a través de variables construidas con días anteriores. El modelo no puede aprender
a corregir la previsión con el resto de variables ni a compensar su sesgo conocido
(sobreestima en 2026 en unos 13.000 MWh).

## 3. Objetivo

Incorporar al vector de entrada **una variable nueva: la previsión de generación eólica
peninsular de REE para el día objetivo**, de modo que el modelo prediga ese mismo día
conociendo la previsión oficial de ese mismo día.

La variable debe:

1. Ser siempre la previsión **elegible**: publicada antes de que empiece el día objetivo.
2. Declarar su origen, distinguiendo una previsión real de un relleno.
3. No perder filas del histórico por huecos, salvo cuando no exista ningún valor
   honesto con el que rellenar.
4. Someterse a la misma puerta de aceptación que cualquier variable nueva del proyecto:
   solo se queda si mejora de forma estricta y repetida.

## 4. Fuera de alcance

Queda fuera de esta versión:

- Cambiar la captura o el archivo de previsiones: ya existen y no se tocan.
- El backend y el frontend, incluido el modelo que sirve la web.
- Otros indicadores de REE (fotovoltaica, intradiarios) y otros horizontes distintos de
  D+1.
- Previsiones revisadas durante el propio día objetivo o después.
- Usar la previsión de REE como sustituto del objetivo: el objetivo sigue siendo la
  generación observada.
- Rellenar las tablas de observación con previsión, en cualquier forma.
- Cambiar las variables actuales del modelo o el criterio de entrenamiento.
- Reentrenar o copiar el modelo a producción sin autorización expresa.

## 5. Definiciones

- **Previsión del día objetivo:** generación eólica peninsular prevista para un día
  natural, en MWh, tal como la publica REE.
- **Previsión elegible:** la previsión del día objetivo cuya elaboración declarada es
  **anterior o igual al día anterior** al objetivo. Nunca una elaboración del propio
  día objetivo ni posterior.
- **Hueco de previsión:** día para el que no existe previsión elegible.
- **Relleno:** valor que sustituye a un hueco: la media de las previsiones elegibles
  reales de los **7 días naturales inmediatamente anteriores** al hueco. Si en esos 7
  días hay menos de 7 previsiones reales, se usa la media de las que haya. Un relleno
  nunca se construye con otro relleno.
- **Origen `prevision`:** el valor procede de una previsión elegible real.
- **Origen `estimada`:** el valor procede de un relleno.

## 6. Requisitos funcionales

### RF-1 — La variable nueva

El vector de mañana incorpora la previsión de REE del día objetivo, en MWh, como una
variable más del modelo.

- **CA-1.1** La variable representa el día objetivo completo (no una media ni un
  retardo): es la previsión de generación de ese mismo día.
- **CA-1.2** Solo se admite una previsión elegible. Una elaboración del propio día
  objetivo o posterior se considera no elegible y nunca se usa, aunque sea la única
  disponible.
- **CA-1.3** Si para un mismo día hay varias previsiones elegibles, se usa la de
  elaboración más reciente que siga cumpliendo la regla de elegibilidad.
- **CA-1.4** La variable se declara con su origen (`prevision` o `estimada`) y su valor
  se guarda junto a la predicción emitida, igual que el resto del vector.
- **CA-1.5** El valor nunca se interpola ni se copia de la generación observada del
  propio día objetivo.

### RF-2 — Entrenamiento

Todas las filas del histórico de entrenamiento llevan la variable nueva.

- **CA-2.1** Los huecos de previsión se rellenan con la regla de relleno; no se elimina
  ninguna fila por falta de previsión, salvo las que no tienen **ninguna** previsión
  real en su ventana de 7 días (CE-1), que es el caso de arranque.
- **CA-2.2** El relleno de cada día usa solo información anterior a ese día. El
  entrenamiento no puede ver previsiones de días posteriores al que rellena.
- **CA-2.3** El resto de variables y el objetivo no cambian: la variable nueva se añade,
  no sustituye a ninguna.
- **CA-2.4** Una previsión con valor cero es un dato válido y no se trata como hueco.

### RF-3 — Predicción del día siguiente

La predicción de mañana usa la previsión elegible de mañana.

- **CA-3.1** Se usa la previsión elegible más reciente publicada antes del día objetivo.
- **CA-3.2** Si mañana no tiene previsión elegible, se rellena con la regla de relleno y
  se marca `estimada`; la predicción **no se detiene** por este motivo.
- **CA-3.3** Si tampoco existe ninguna previsión real en los 7 días anteriores, no hay
  relleno honesto: la predicción se detiene y se declara el motivo. La parada aplica
  **cuando `eolica_prev` forma parte del modelo**; si la comparación la rechaza, la
  predicción sigue con las 18 variables y el origen se declara igualmente.
- **CA-3.4** El origen de la variable aparece en el mapa de orígenes de la ejecución y
  en la predicción guardada.
- **CA-3.5** El relleno de esta variable no altera el relleno de retardos y medias que
  ya define la spec 004: son usos distintos de la misma previsión (pasado frente a día
  objetivo) y conviven.

### RF-4 — Comparación y adopción

La variable solo entra en el modelo si mejora de forma estricta y repetida.

- **CA-4.1** Se compara la variante con la variable nueva contra el modelo vigente de
  18 variables, con el mismo objetivo, el mismo resto del vector y el mismo corte de
  test.
- **CA-4.2** La comparación es walk-forward, con las mismas cuatro ventanas que usa el
  proyecto para aceptar variables (precedente de la spec 002).
- **CA-4.3** Se adopta solo si el RMSE mejora **de forma estricta en al menos 3 de las 4
  ventanas**. Una mejora global con ventanas en contra no basta.
- **CA-4.4** Si no se adopta, el modelo vigente queda intacto, la variable no se guarda
  como parte del modelo y el resultado se documenta como rechazo.
- **CA-4.5** El informe declara, por ventana y en conjunto: RMSE, MAE y R² de la
  variante y del modelo vigente, la decisión y su motivo.
- **CA-4.6** El informe incluye como referencia el error de la previsión de REE sola,
  para saber si el modelo aporta algo sobre copiarla.

### RF-5 — Trazabilidad

La ejecución deja constancia de cómo se construyó la variable.

- **CA-5.1** Se informa de cuántos días usaron previsión real, cuántos relleno y cuántos
  no se pudieron usar.
- **CA-5.2** Cada hueco relleno queda identificado por su fecha y por el número de
  previsiones reales que aportaron a su media.
- **CA-5.3** El informe de comparación queda escrito y es legible sin volver a ejecutar
  el análisis.
- **CA-5.4** Las tablas de observación no reciben ninguna fila nueva ni modificada: se
  verifica por recuento y huella.

## 7. Requisitos no funcionales

- **RNF-1 — Honestidad.** Lo relleno se declara como `estimada`; lo no elegible no se
  usa; el valor real nunca se sustituye por una previsión ni al revés.
- **RNF-2 — Sin fuga de información.** Ningún valor de una fila puede depender de datos
  posteriores a su fecha, ni al entrenar ni al predecir.
- **RNF-3 — Determinismo.** Dos ejecuciones con la misma entrada dan el mismo resultado.
  La fecha de referencia entra siempre como parámetro; nada depende del reloj.
- **RNF-4 — Simplicidad.** Se añade lo mínimo: una variable, una regla de relleno y su
  comparación. Sin dependencias nuevas y sin cambios estructurales.
- **RNF-5 — Ámbito.** Todo el desarrollo vive en el directorio de análisis. No se toca
  el backend ni el frontend sin autorización expresa.
- **RNF-6 — Idioma.** Documentación, mensajes y comentarios en español.

## 8. Casos límite y errores

- **CE-1 — Arranque sin historia.** Los primeros días del histórico pueden no tener
  ninguna previsión real anterior con la que rellenar. Esas filas no se usan y se
  cuentan; no se inventa un valor.
- **CE-2 — Dos elaboraciones elegibles del mismo día.** Gana la más reciente; queda una
  sola fila por día.
- **CE-3 — Elaboración del propio día objetivo.** No es elegible: se descarta y se
  informa, porque usaría información que no existía al predecir.
- **CE-4 — Previsión de valor cero.** Es un dato válido (poco viento previsto), no un
  hueco.
- **CE-5 — Previsión imposible.** Un valor negativo o fuera de rango se descarta y se
  informa; no se recorta a cero en silencio.
- **CE-6 — Cadena de huecos.** Cada hueco se rellena con previsiones reales anteriores a
  él; un relleno no alimenta a otro relleno.
- **CE-7 — Previsión de otra zona.** Solo vale la previsión peninsular del sistema
  eléctrico; cualquier otra zona se considera no elegible.
- **CE-8 — Día objetivo ya publicado.** Si el día objetivo ya tiene observación, la
  variable sigue siendo la previsión elegible que se usó al predecir; la observación no
  se cuela como variable. En el histórico de entrenamiento se usa la revisión elegible
  final (siempre anterior al objetivo, sin fuga); en el vector archivado de cada emisión
  se conserva el valor del momento de predecir. Son dos instantes distintos y ambos
  quedan declarados.
- **CE-9 — Sin previsión ni historia.** Si no hay previsión elegible ni previsiones
  anteriores, se declara y no se predice cuando la variable está en el modelo (CA-3.3).

## 9. Criterios de finalización

1. La variable nueva existe en el entrenamiento y en la predicción del día siguiente,
   con su origen declarado y guardado.
2. La regla de relleno está documentada, se aplica siempre y no usa información
   posterior al día que rellena.
3. La comparación walk-forward de 4 ventanas se ha ejecutado y la decisión está
   declarada con su motivo.
4. Si la decisión es aceptar, el modelo del análisis pasa a 19 variables y su artefacto
   es coherente con esa lista; si es rechazar, el modelo de 18 variables queda intacto.
5. Las tablas de observación siguen intactas (recuento y huella).
6. La puerta de tests está en verde.
7. El informe de comparación y la memoria del proyecto recogen la decisión, los números
   y el estado.

## 10. Decisiones tomadas

- **D-5-1 — Qué previsión entra como variable.** La del **día objetivo**, no los
  retardos de previsión ni una media de previsiones: el modelo debe conocer la
  previsión del día que predice (decisión del usuario, 2026-11-11).
- **D-5-2 — Elegibilidad.** Solo la previsión con elaboración **anterior o igual al día
  anterior** al objetivo. Evita la fuga de una revisión hecha con el día en marcha.
- **D-5-3 — Relleno antes que pérdida de filas.** Un hueco se rellena con la media de
  las previsiones reales de los 7 días anteriores, declarado `estimada`. Excepción: sin
  ninguna previsión anterior no hay relleno y la fila no se usa (CE-1).
- **D-5-4 — Adopción estricta.** Walk-forward de 4 ventanas y mejora del RMSE en al
  menos 3 de ellas; si no, la variable se rechaza y se documenta.
- **D-5-5 — Vocabulario de origen.** `prevision` para la previsión real y `estimada`
  para el relleno, reutilizando el vocabulario de la spec 004; no se inventa un origen
  nuevo.
- **D-5-6 — Convivencia con la spec 004.** El uso de la previsión para tapar huecos de
  retardos y de la media de 7 días sigue igual. La variable nueva es un uso adicional,
  no un reemplazo.
- **D-5-7 — Qué significa «mejor».** Se mide con el mismo error que el resto del
  proyecto (RMSE sobre el test común). El MAE de la previsión de REE sola se informa
  como referencia, pero no decide la adopción.

## 11. Dudas abiertas

- **D-5-8 — Modelo de destino.** El modelo de 18 variables aún no está en producción
  (pendiente de autorización). Si la variable se acepta, ¿se prepara el modelo de 19
  variables para sustituir al de la web en el mismo movimiento, o se mantiene como
  modelo del análisis hasta nueva autorización? Se propone lo segundo.
- **D-5-9 — Umbral de mejora.** «Mejora estricta» se interpreta como cualquier reducción
  del RMSE, sin mínimo porcentual, igual que en la spec 002. Si se quiere exigir un
  mínimo (por ejemplo 2 %), decirlo antes de ejecutar la comparación.

## Anexo A — Medición que motiva la spec

Referencia del archivo ya construido (spec 004, Anexo B) sobre `2022-01-01 → 2026-11-08`:

| Referencia | MAE (MWh) | RMSE (MWh) |
|---|---:|---:|
| Previsión de REE sola | 13.194 | 19.969 |
| Modelo de 18 variables (test) | 29.950 | 39.703 |

Además, el sesgo de la previsión de REE en 2026 es de unos +13.120 MWh (sobreestima).
Esa es la parte que el modelo puede aprender a corregir con el resto del vector: por eso
se somete a comparación y no se adopta por su cuenta.

**Riesgo declarado:** si la previsión domina al resto de variables, el modelo puede
limitarse a copiarla. El informe debe mostrar el error del modelo y el de la previsión
sola, para que esa situación quede visible y no se confunda con una mejora.
