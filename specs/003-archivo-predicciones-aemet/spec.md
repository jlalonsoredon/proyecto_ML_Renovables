# Spec 003 — Archivo de previsiones meteorológicas para el modelo eólico

## 1. Contexto y objetivo

El objetivo del proyecto es predecir la **generación eólica diaria peninsular del día siguiente**. Hoy
el modelo se alimenta de dos fuentes con latencias muy distintas: la generación de REE (1–2 días) y la
observación meteorológica de AEMET (**4 días**). Como la segunda manda en el emparejamiento por fecha,
**13 de las 18 variables** que entran al modelo salen de una foto de hace cuatro días: los retardos de
generación (`eolica_lag1/2/3/7`), las medias móviles de viento y racha (`vel_ma3/7/14`,
`racha_ma3/7/14`), la media de generación (`eolica_ma7`) y las dos variables de la spec 002
(`sol_lag1`, `tmed_lag1`).

Solo cinco variables van frescas: el viento previsto del día objetivo (`velmedia`, `racha`) y las tres
de calendario. Dicho de otro modo: el modelo aprendió «mañana con datos de ayer» y en producción
recibe «mañana con datos de hace cuatro días». Es un desajuste entre entrenamiento y servicio, y es
**constante**, no ruido: el retraso no crece, se queda fijo.

Lo medido (anexo A):

- AEMET publica la observación diaria con **4 días** de retraso, de forma rodante y en todas las
  estaciones consultadas.
- AEMET **no publica archivo de previsiones**: sus consultas de predicción no aceptan fecha. Solo
  devuelve la previsión vigente. Lo que no se guarde, se pierde para siempre.
- La previsión vigente **sí incluye el día en curso**, con viento, temperatura, estado del cielo y
  probabilidad de precipitación. **No incluye horas de insolación**, y el campo de racha máxima del
  parte diario llega **vacío**.
- El parte **declara su propia elaboración** (`elaborado`, p. ej. `2026-11-01T08:59:08`) y su horizonte
  **empieza en el día de elaboración**: nunca devuelve días pasados. Esa marca, y no la fecha en que
  descargamos, es lo que identifica una elaboración.

**Objetivo:** conservar cada día la previsión vigente de las ubicaciones que usa el modelo, de modo que
exista un **archivo propio de previsiones** —que AEMET no ofrece— capaz de cubrir el hueco de cuatro
días que deja la observación; y decidir, con datos del propio archivo, si alimentar el modelo con esa
previsión mejora la predicción de mañana lo suficiente como para sustituir el modelo de producción.

**Por qué un archivo y no otra cosa:**

- **No se interpola.** Rellenar un hueco con los extremos es inventar el dato: en producción es mentir
  sobre lo que se sabe y en la reconstrucción histórica es usar información del futuro.
- **La observación y la previsión no se mezclan en la misma serie.** Son dos orígenes con error
  distinto; si se funden en una sola columna, en cinco días la serie cambia de fuente sin dejar rastro.
  Se mantienen como dos series paralelas y comparables.
- **Solo vale la previsión que existía en su momento, y eso lo dice la fuente.** Cada parte declara su
  elaboración. Para reconstruir qué sabía el sistema el día `D` hay que usar una previsión **elaborada el
  día `D` o antes**, y la fecha de descarga no cuenta: descargar mañana un parte elaborado ayer no lo
  convierte en información de mañana.
- **El archivo no se puede fabricar hacia atrás.** Empieza el día de la primera captura y crece hacia
  delante; los días anteriores no se recuperan con ninguna fuente oficial.

## 2. Usuarios

- **U1 — Analista (autor del proyecto).** Necesita saber, con una regla explícita, si la previsión
  archivada mejora el modelo, y con cuánta antigüedad llegó cada dato.
- **U2 — Evaluador técnico (tutor, revisor).** Necesita poder auditar la decisión: qué se archivó, con
  qué regla se eligió cada previsión, qué se midió y por qué se aceptó o se rechazó.
- **U3 — Operación del servicio.** Necesita enterarse de que la captura diaria ha fallado sin tener que
  mirar la base de datos, y saber si el archivo tiene huecos y de qué días.
- **U4 — Visitante de la web.** *No es usuario de esta versión*: no se expone nada nuevo en la
  interfaz ni en la API.

## 3. Historias de usuario

- **HU-1.** Como U1, quiero que la previsión vigente se guarde todos los días automáticamente, para no
  depender de acordarme de ejecutar nada y no perder días irreemplazables.
- **HU-2.** Como U1, quiero que cada previsión guardada recuerde **cuándo la elaboró la fuente y para qué
  día valía**, para poder reconstruir qué sabía el sistema en un momento dado sin ambigüedad.
- **HU-3.** Como U1, quiero conservar el parte original además de los valores ya derivados, para poder
  recalcular un indicador dentro de seis meses sin volver a descargarlo (AEMET ya no lo tendrá).
- **HU-4.** Como U1, quiero cubrir con previsión **todas** las variables que hoy envejecen —sol,
  temperatura, viento y racha, incluidas sus medias móviles—, para que el modelo no siga mezclando
  datos frescos con datos de hace cuatro días.
- **HU-5.** Como U1, quiero que un fallo de captura no se convierta en un hueco definitivo, para no
  perder la única fuente que existe.
- **HU-6.** Como U2, quiero que la regla de elección de previsión sea única, explícita y comprobable,
  para que la reconstrucción histórica no dependa de mi criterio del día.
- **HU-7.** Como U1, quiero comparar el modelo actual con el alimentado por previsiones sobre las
  mismas fechas, para no confundir una mejora real con el ruido de un mes.
- **HU-8.** Como U3, quiero un resumen diario de la captura (qué se guardó, qué falló y qué quedó
  pendiente), para enterarme de un problema antes de que se acumulen huecos.
- **HU-9.** Como U2, quiero que la decisión quede registrada con sus números y su fecha, para poder
  reproducirla o revertirla.

## 4. Requisitos funcionales

### RF-1 — Captura diaria de la previsión vigente

El sistema debe capturar automáticamente, una vez al día y sin intervención manual, la previsión
meteorológica vigente de cada ubicación del modelo, incluido el día en curso.

- **CA-1.1** CUANDO llega la hora diaria de captura, el sistema debe solicitar la previsión de todas
  las ubicaciones del catálogo y guardar, para cada una, todos los días que la fuente publique.
- **CA-1.2** La captura debe incluir el **día en curso** entre los días objetivo; si la fuente no lo
  devuelve para alguna ubicación, debe registrarse esa ausencia como incidencia.
- **CA-1.3** La captura debe guardar también los días siguientes que la fuente publique, con un mínimo
  esperado de seis; si devuelve menos, debe informarse del horizonte real obtenido.
- **CA-1.4** La captura debe completarse sin intervención humana y sin depender de que alguien ejecute
  el análisis.
- **CA-1.5** SI la captura no puede ejecutarse a su hora, ENTONCES el sistema debe reintentarla el
  mismo día antes de darla por perdida.

### RF-2 — Archivo separado de la observación

El sistema debe conservar las previsiones en un archivo propio, distinguible de la observación
meteorológica, con la elaboración del parte y el día objetivo como parte de su identidad.

- **CA-2.1** Cada previsión guardada debe quedar identificada por **la elaboración que declara el parte,
  el día objetivo y la ubicación**; no puede existir más de un registro para esa combinación.
- **CA-2.2** La observación meteorológica no debe modificarse ni rellenarse con previsiones en ningún
  caso; el archivo es un origen distinto y así debe poder distinguirse.
- **CA-2.3** El archivo debe conservar indefinidamente las previsiones pasadas; no se purgan al llegar
  la observación del día. Una nueva elaboración del mismo día objetivo es una previsión **distinta** y se
  conserva junto a la anterior, sin sustituirla.
- **CA-2.4** Cada registro debe conservar el parte original recibido, además de los valores derivados,
  para permitir recalcular indicadores sin volver a la fuente.
- **CA-2.5** Cada registro debe guardar la fecha y hora real de captura, distinta de la elaboración que
  declara el parte.
- **CA-2.6** La elaboración debe tomarse del propio parte. La fecha de captura nunca puede hacer las
  veces de elaboración.
- **CA-2.7** SI un parte no declara su elaboración, ENTONCES el registro debe guardarse marcado como sin
  elaboración conocida y no debe ser elegible para reconstruir ningún día.

### RF-3 — Cobertura de ubicaciones

El sistema debe cubrir todas las ubicaciones cuyas variables alimentan el modelo: las de los parques
eólicos y las de las plantas solares.

- **CA-3.1** El catálogo de ubicaciones de la captura debe contener las 7 ubicaciones eólicas ya usadas
  en la predicción y las 5 ubicaciones solares que alimentan `sol` y `tmed`.
- **CA-3.2** Cada ubicación del catálogo debe declarar para qué se usa (eólica o solar), para poder
  agregarlas por separado.
- **CA-3.3** SI una ubicación del catálogo no devuelve previsión, ENTONCES debe quedar registrada como
  incidencia y el resto de ubicaciones debe capturarse igualmente.
- **CA-3.4** Añadir o retirar una ubicación no debe alterar las previsiones ya archivadas.

### RF-4 — Idempotencia y corrección

El sistema debe poder repetir la captura del mismo día sin duplicar ni corromper el archivo.

- **CA-4.1** CUANDO se ejecuta la captura dos veces sobre la misma elaboración, el número de registros
  no debe aumentar por duplicación.
- **CA-4.2** SI la fuente ha publicado una nueva elaboración del mismo día objetivo, ENTONCES debe
  guardarse como registro distinto y conservarse el anterior; nunca debe pisarse una elaboración con otra.
- **CA-4.3** La sustitución solo puede afectar a la misma elaboración recapturada, y nunca a
  elaboraciones anteriores ni a días objetivo distintos.
- **CA-4.4** Una captura interrumpida a mitad no debe dejar el archivo en un estado parcial que impida
  la siguiente captura.

### RF-5 — Regla única de elección de previsión (anti-fuga)

El sistema debe poder responder, para un día objetivo y una ubicación, qué previsión era la válida en
un momento dado, con una regla única.

- **CA-5.1** Para un día objetivo `D`, solo son elegibles las previsiones cuya **elaboración declarada**
  sea anterior o igual a `D`.
- **CA-5.2** Si hay varias elegibles, debe usarse la de elaboración **más reciente**.
- **CA-5.3** Una previsión elaborada después de su día objetivo nunca debe usarse, ni siquiera si es la
  única disponible.
- **CA-5.4** SI no existe ninguna previsión elegible, ENTONCES el sistema debe devolver «no disponible»
  y no un valor por defecto.
- **CA-5.5** La antigüedad de la previsión usada, en días, debe quedar disponible junto al valor para
  poder informarla y analizarla.
- **CA-5.6** La elegibilidad debe calcularse siempre con la elaboración declarada por la fuente. La fecha
  de captura no es una elaboración y no puede usarse para decidir si un dato vale.
- **CA-5.7** Una previsión sin elaboración declarada no es elegible, aunque sea la única del archivo.

### RF-6 — Recuperación de capturas fallidas

El sistema debe recuperar un día objetivo mientras la fuente siga sirviendo alguna elaboración que lo
contenga, y debe declararlo perdido en cuanto deje de hacerlo.

- **CA-6.1** CUANDO una captura falla total o parcialmente, el sistema debe reintentarla el mismo día.
- **CA-6.2** SI el fallo persiste, ENTONCES el sistema debe reintentar en capturas posteriores mientras el
  día objetivo siga apareciendo en el horizonte de una elaboración servida.
- **CA-6.3** Un día objetivo solo puede recuperarse de una elaboración que lo contenga, y —medido— una
  elaboración nunca contiene días anteriores a su propia fecha. La recuperación debe terminar, por tanto,
  antes de que la fuente publique la primera elaboración posterior a ese día.
- **CA-6.4** Cuando ese momento llega y el día sigue sin capturar, debe registrarse como hueco definitivo y
  contarse entre los días esperados.
- **CA-6.5** El sistema nunca debe reconstruir un hueco con la observación del día ni con una interpolación.
- **CA-6.6** El resumen diario debe indicar cuántos días quedan pendientes de recuperar y desde cuándo.
- **CA-6.7** La recuperación no puede alterar RF-5: si la fuente sirviera alguna vez un día pasado dentro de
  una elaboración nueva, el registro se guardaría y no sería elegible.

### RF-7 — Temperatura y sol previstos

El sistema debe derivar, para cada ubicación y día objetivo, una temperatura media y una estimación de
horas de insolación a partir de la previsión, y debe declarar cuál es estimada.

- **CA-7.1** La temperatura media debe derivarse de la previsión; cuando el parte ofrezca temperatura
  hora a hora, debe usarse la media de las horas del día; en su defecto, la media de máxima y mínima.
- **CA-7.2** La insolación **no** viene en la previsión: debe estimarse a partir de las horas de luz
  astronómicas del día y el estado del cielo previsto, y ese valor debe quedar marcado como estimado.
- **CA-7.3** Las horas de luz deben calcularse a partir de la latitud de la ubicación y el día del año,
  sin depender de una tabla fija por fecha.
- **CA-7.4** Cada código de estado del cielo de la fuente debe tener asignado un factor de insolación
  entre 0 y 1, incluidos los códigos nocturnos.
- **CA-7.5** La insolación estimada nunca debe superar las horas de luz del día ni ser negativa.
- **CA-7.6** SI el parte no trae estado del cielo para un tramo del día, ENTONCES la insolación de ese
  día debe marcarse como no disponible, no estimarse a ciegas.
- **CA-7.7** Antes de usar la insolación estimada como variable del modelo, debe medirse su error frente
  a la insolación observada en los días con ambas; si su correlación es inferior a 0,7, debe
  descartarse y quedarse solo la temperatura.

### RF-8 — Viento y racha previstos, con sus medias móviles

El sistema debe poder construir las medias móviles de viento y racha **íntegramente** a partir de la
previsión, sin mezclar valores observados dentro de la misma ventana.

- **CA-8.1** El viento y la racha de un día deben tomarse de la previsión elegida según RF-5, aplicando
  su conversión de unidades a la que usa el modelo.
- **CA-8.2** SI el parte diario no trae racha máxima, ENTONCES la racha debe obtenerse del parte
  horario; si tampoco la trae, la racha de ese día queda no disponible.
- **CA-8.3** Las medias móviles de 3, 7 y 14 días deben calcularse sobre días naturales consecutivos de
  la serie de previsión, sin que un hueco desplace los valores.
- **CA-8.4** Una media móvil de `n` días solo está disponible cuando existen las `n` previsions
  consecutivas; hasta entonces debe devolverse «no disponible», no un valor parcial calculado con los
  días que haya.
- **CA-8.5** Una ventana de media móvil nunca debe combinar, para el mismo día, un valor observado y
  uno previsto.
- **CA-8.6** La serie de previsión y la serie de observación deben mantenerse en paralelo y comparables
  día a día, compartiendo el mismo criterio de fecha.

### RF-9 — Integración en el modelo sin sustituir lo existente

El sistema debe construir las variables de previsión **junto a** las observadas, sin reemplazarlas
mientras no se decida el cambio.

- **CA-9.1** Las variables derivadas de previsión deben construirse en paralelo a las actuales, con
  nombres que las distingan, y sin modificar el conjunto de variables del modelo de producción.
- **CA-9.2** El modelo de producción debe seguir funcionando con las variables actuales durante toda la
  fase de comparación.
- **CA-9.3** La cobertura del archivo, la antigüedad media de los datos usados y el número de filas
  descartadas por falta de previsión deben informarse en cada ejecución del análisis.
- **CA-9.4** Toda fila que no pueda construirse con previsión debe descartarse de la comparación y
  contarse; nunca completarse con la observación.

### RF-10 — Comparación y criterio de decisión

El sistema debe comparar el modelo actual con el alimentado por previsiones sobre las mismas fechas y
decidir con una regla explícita.

- **CA-10.1** La comparación debe usar las mismas fechas de entrenamiento y de prueba en las variantes
  comparadas, y diferir solo en el origen de las variables.
- **CA-10.2** La comparación debe hacerse en **ventanas móviles** de 21 días que avanzan de 7 en 7, no
  en los cuatro folds anuales de la spec 002, porque el archivo no llega a cuatro años.
- **CA-10.3** La variante con previsiones debe considerarse mejor solo si reduce el RMSE **al menos un
  2 %** en **más de la mitad** de las ventanas evaluadas.
- **CA-10.4** SI se evalúan menos de tres ventanas, ENTONCES no debe tomarse ninguna decisión y debe
  informarse de que la evidencia es insuficiente.
- **CA-10.5** SI el criterio no se cumple, ENTONCES el modelo de producción no debe modificarse y la
  decisión, con sus métricas, debe quedar registrada.
- **CA-10.6** La comparación debe informar también del error de la propia previsión frente a la
  observación, para separar «la previsión es mala» de «la previsión no aporta al modelo».

### RF-11 — Actualización condicionada del modelo de producción

Solo si se cumple RF-10, el sistema debe reentrenar y actualizar el modelo de producción con las
variables de previsión.

- **CA-11.1** El conjunto de variables del análisis y el que espera el servicio de predicción deben
  coincidir exactamente, en orden y en número.
- **CA-11.2** El modelo guardado debe poder recargarse y reproducir las métricas del conjunto de prueba.
- **CA-11.3** Todas las copias del modelo que usa cada entorno deben quedar sincronizadas, y el informe
  debe indicar cuáles se actualizaron.
- **CA-11.4** SI la recarga no reproduce las métricas, ENTONCES debe restaurarse la copia anterior y
  registrarse el fallo.
- **CA-11.5** SI el criterio no se cumple, el modelo de producción no debe sobrescribirse.

### RF-12 — Frescura de las variables de generación

El sistema debe dejar de arrastrar el retraso meteorológico en las variables que dependen de la
generación, porque esa fuente publica antes.

- **CA-12.1** Los retardos de generación y su media móvil deben construirse con la última generación
  disponible, sin recortarse a la última fecha meteorológica.
- **CA-12.2** SI la generación de los últimos días parece incompleta (un día muy por debajo de su
  entorno), ENTONCES debe señalarse antes de usarla, en lugar de incorporarla en silencio.
- **CA-12.3** Este requisito no depende del archivo de previsiones y puede cerrarse por separado.
- **CA-12.4** El cambio no debe alterar el resto de variables ni las métricas de referencia sin
  documentarlo.

### RF-13 — Trazabilidad y avisos

El sistema debe dejar constancia de lo capturado y de lo decidido.

- **CA-13.1** Cada ejecución de la captura debe producir un resumen con fecha, ubicaciones capturadas,
  días guardados, días pendientes, errores y su causa.
- **CA-13.2** SI no se capturó ninguna ubicación, ENTONCES la ejecución debe terminar en fallo visible,
  no en éxito silencioso.
- **CA-13.3** Debe quedar un informe con fecha, número de ventanas evaluadas, métricas de cada variante
  por ventana, resultado del criterio y decisión tomada.
- **CA-13.4** El informe debe registrar la cobertura del archivo y el error de la previsión frente a la
  observación en el solape disponible.
- **CA-13.5** La memoria del proyecto debe recoger la decisión y las métricas de referencia.

## 5. Requisitos no funcionales

- **RNF-1 — Una sola fuente de verdad del archivo.** Todo lo que escribe y todo lo que lee previsiones
  debe ver el mismo archivo; no puede haber copias divergentes entre el servicio y el análisis.
- **RNF-2 — Sin mezcla de orígenes.** Observación y previsión no comparten columna, ni se rellenan
  mutuamente, ni se interpolan. Un valor estimado siempre se identifica como tal.
- **RNF-3 — Honestidad del diagnóstico.** Un hueco, un fallo de captura o un valor estimado nunca deben
  quedar ocultos tras un valor por defecto.
- **RNF-4 — Reproducibilidad.** Dos ejecuciones con el mismo archivo deben producir la misma decisión y
  las mismas métricas.
- **RNF-5 — Lógica pura y comprobable.** El cálculo de horas de luz, la traducción del estado del cielo,
  la estimación de insolación y la regla de elección de previsión deben probarse sin red y sin depender
  de la zona horaria de la máquina.
- **RNF-6 — Puerta en verde.** La batería de pruebas debe pasar antes de cerrar cualquier tarea; no se
  avanza con pruebas en rojo.
- **RNF-7 — Respeto a la fuente.** La captura debe respetar el límite de peticiones de AEMET, con
  pausas y reintentos, y tolerar sus errores de disponibilidad.
- **RNF-8 — Cambio mínimo.** No se reordena el análisis existente, no se renombran sus etapas y no se
  altera el contrato de la API ni la interfaz.
- **RNF-9 — Sin dependencias nuevas** más allá de las ya presentes en el proyecto.
- **RNF-10 — Idioma.** Comentarios, mensajes y documentación en español.
- **RNF-11 — Coste irrelevante.** El archivo debe crecer de forma despreciable (del orden de decenas de
  registros diarios) y no debe exigir mantenimiento manual.

## 6. Casos límite

- **CE-1.** Primer día de vida del archivo: no existe previsión elegible para ningún día anterior; las
  variables de previsión están no disponibles y las filas se descartan de la comparación.
- **CE-2.** Previsión elaborada el **mismo día** que su día objetivo (`E = D`): es válida y es la que debe
  usarse preferentemente.
- **CE-3.** Previsión **elaborada después** de su día objetivo: este proveedor no lo hace (su horizonte
  empieza en la elaboración), pero si llegara así se guarda y no se usa nunca para reconstruir ese día.
- **CE-4.** La fuente publica una nueva elaboración del mismo día objetivo dentro de la misma jornada: se
  guarda como registro distinto y se conserva el anterior; dos capturas de la misma elaboración no duplican.
- **CE-5.** Captura parcial: unas ubicaciones sí y otras no. Las que faltan quedan pendientes y se
  reintentan; no se rellenan con otra ubicación.
- **CE-6.** La fuente no devuelve el día en curso para una ubicación, solo días futuros: se registra la
  ausencia; ese día no se sustituye por el siguiente.
- **CE-7.** El parte diario llega sin racha máxima (situación ya observada): se usa el parte horario; si
  tampoco la trae, la racha de ese día queda no disponible y las medias de racha no se construyen.
- **CE-8.** El estado del cielo llega vacío en algún tramo: la insolación de ese día queda no disponible.
- **CE-9.** Día sin sol por niebla o cubierto total: `sol = 0` es un valor válido, no un dato ausente.
- **CE-10.** Insolación estimada superior a las horas de luz: debe rechazarse el valor y registrarse.
- **CE-11.** Archivo con menos de 14 días: las medias móviles de 14 días no se construyen; las de 3 y 7
  sí, cuando su ventana esté completa.
- **CE-12.** Hueco dentro de una ventana de media móvil: la ventana queda no disponible; no se acorta ni
  se rellena.
- **CE-13.** La previsión de un día se captura en una fecha posterior a su elaboración —caso normal: el
  parte elaborado ayer se descarga en la madrugada de hoy y todavía contiene ayer—: la elaboración sigue
  siendo la declarada por la fuente y la fila es válida para su día objetivo.
- **CE-14.** El servicio de captura se cae varios días seguidos: al volver, recupera los días que sigan
  dentro del horizonte de alguna elaboración servida y marca el resto como hueco definitivo.
- **CE-15.** Cambio de hora: un día natural debe tener un único valor, sin duplicar ni perder horas en
  la media de temperatura.
- **CE-16.** Ventanas de comparación con menos de tres ventanas completas: no se decide y se informa.
- **CE-17.** La variante con previsiones empata o mejora por debajo del umbral: no se cambia el modelo.
- **CE-18.** La previsión mejora en el análisis pero el modelo actualizado no recarga o no reproduce sus
  métricas: se restaura la copia anterior.
- **CE-19.** La generación de los últimos días llega incompleta: debe señalarse antes de usarla en los
  retardos.
- **CE-20.** El archivo y la observación empiezan o terminan en fechas distintas: se recorta al tramo
  común y se informa del recorte.

## 7. Fuera de alcance

- **Exponer el archivo al visitante.** No hay consulta nueva, ni pantalla nueva, ni cambio de contrato
  en la API. El archivo es infraestructura interna del análisis y de la predicción.

Queda fuera de esta versión por decisión técnica, no por falta de interés, y se detalla en las dudas
abiertas: recuperar los días anteriores a la primera captura (imposible con fuentes oficiales),
incorporar un proveedor externo de previsión con archivo histórico, y decidir cómo se entrena el modelo
con cuatro años de observación y solo dos meses de previsión.

## 8. Criterios de finalización

La funcionalidad se considera terminada cuando:

1. La captura diaria se ejecuta sola, guarda el día en curso y los siguientes de las 12 ubicaciones, y
   su repetición no duplica registros.
2. Cada previsión archivada identifica la elaboración del parte, el día objetivo y la ubicación, conserva el
   parte original y no toca la observación.
3. Existe una regla única y probada para elegir la previsión válida de un día, con los casos de elaboración
   anterior, igual y posterior al objetivo cubiertos por pruebas.
4. Un fallo de captura se reintenta, se recupera mientras la fuente sirva una elaboración que contenga el día y,
   si no, queda registrado como hueco; en ningún caso se rellena con observación ni con interpolación.
5. La temperatura y la insolación previstas se derivan con las reglas de RF-7 y la insolación queda
   marcada como estimada; su error frente a la observación está medido en el solape disponible.
6. Las medias móviles de viento y racha se construyen íntegramente con previsión y solo cuando su
   ventana está completa.
7. Se han comparado las variantes sobre las mismas fechas, en ventanas móviles, con el umbral del 2 % y
   la regla de mayoría, y la decisión está registrada con sus métricas y la cobertura del archivo.
8. Si se aceptó: el modelo de producción usa el nuevo conjunto de variables, recarga y reproduce sus
   métricas, y todas las copias que usa cada entorno están sincronizadas. Si se rechazó: el modelo de
   producción está intacto y la decisión consta por escrito.
9. Las variables de generación ya no se recortan a la última fecha meteorológica y su frescura está
   informada.
10. El resumen de cada captura indica lo guardado, lo pendiente y los errores, y una captura sin
    resultados termina en fallo visible.
11. La memoria del proyecto recoge la decisión, las métricas y el estado del archivo.

## 9. Dudas abiertas

- **[NECESITA ACLARACIÓN] D-3-1 — Municipios de las cinco plantas solares.** El mapeo planta ↔ municipio
  de las ubicaciones solares no está fijado. ¿Se acepta el municipio más cercano a cada planta, como se
  hizo con los parques eólicos, o se prefiere el que ya se usa para la estación meteorológica?
- **[NECESITA ACLARACIÓN] D-3-2 — Entrenamiento con dos meses de previsión y cuatro años de
  observación.** Si el modelo final se entrena solo con los días que tienen previsión, la muestra es
  minúscula; si se entrena con observación y se predice con previsión, persiste el desajuste que esta
  spec quiere corregir; si se mezclan, se rompe RNF-2. ¿Cuál de los tres se acepta como mal menor?
- **[NECESITA ACLARACIÓN] D-3-3 — Cuántas capturas al día y con qué elaboración.** El parte declara su
  elaboración (`elaborado`), que en la medición fue de las 08:59. Una captura única a las 3:00 tomaría la
  elaboración de la tarde anterior: es válida (cubre el día en curso), pero el archivo iría siempre una
  elaboración por detrás y nunca guardaría la del mismo día. ¿Una captura al día, o también una segunda
  pasada por la mañana? Hay que medir qué elaboración se sirve a cada hora antes de decidir.
- **[NECESITA ACLARACIÓN] D-3-4 — Fuente alternativa de insolación.** Ningún proveedor oficial publica
  horas de insolación previstas. ¿Se admite, en una versión posterior, un proveedor externo con archivo
  de predicciones (radiación y temperatura) o el proyecto se queda solo con AEMET?
- **[NECESITA ACLARACIÓN] D-3-5 — Qué se hace con los huecos definitivos.** Cuando un día quede perdido,
  ¿la comparación descarta la fila (perdiendo días de evaluación) o se acepta una ventana con huecos
  usando solo los días completos?
- **[NECESITA ACLARACIÓN] D-3-6 — Ventana y umbral de decisión.** Se fija en 21 días con avance de 7 y un
  umbral del 2 % en más de la mitad de las ventanas. ¿Se mantiene así o se prefiere exigir también un
  mínimo absoluto de mejora en MWh?
- **[NECESITA ACLARACIÓN] D-3-7 — Retirada de la vía de relleno masivo.** Existe una herramienta de
  relleno histórico de meteorología que ya no usa el análisis. ¿Se retira en esta iteración o se
  conserva como utilidad?

## Anexo A — Evidencia medida

**Retraso de publicación de la observación** (dos sondeos, tres estaciones cada uno):

| Fecha de consulta | Último día publicado | Retraso | Estaciones |
|---|---|---|---|
| 2026-10-31 | 2026-10-27 | 4 días | 3469A, 5783, 9434 |
| 2026-11-01 | 2026-10-28 | 4 días | 3469A, 5783, 9434 |

**Campos del parte previsto** (municipio de Cuenca, 2026-11-01):

```
Diario : cotaNieveProv, estadoCielo, fecha, humedadRelativa, probPrecipitacion,
         rachaMax, sensTermica, temperatura, uvMax, viento
Horario: estadoCielo, fecha, humedadRelativa, nieve, ocaso, orto, precipitacion,
         probNieve, probPrecipitacion, probTormenta, sensTermica, temperatura,
         vientoAndRachaMax
```

Dos ausencias que condicionan el diseño: **no hay horas de insolación** en ninguno de los dos partes, y
`rachaMax` del parte diario **llega vacío** en todos los tramos.

**El parte declara su elaboración y su horizonte** (consulta del 2026-11-01, municipio 16078):

```
elaborado : 2026-11-01T08:59:08     · version: 1.0
diaria    : 2026-11-01 … 2026-11-07   (7 días, empieza el día de elaboración)
horaria   : 2026-11-01 … 2026-11-03   (3 días)
```

De ahí salen las dos reglas que resuelven el conflicto entre RF-5 y RF-6: **la elaboración es la que declara
el parte**, y **una elaboración nunca contiene días anteriores a sí misma**, así que un día objetivo deja
de ser recuperable en cuanto la fuente publica la elaboración siguiente.

**Variables afectadas por el retraso** (13 de 18): `eolica_lag1`, `eolica_lag2`, `eolica_lag3`,
`eolica_lag7`, `vel_ma3`, `vel_ma7`, `vel_ma14`, `racha_ma3`, `racha_ma7`, `racha_ma14`, `eolica_ma7`,
`sol_lag1`, `tmed_lag1`.

**Cota superior muy floja del daño** (medición ya existente, desplazando la predicción un día): MAE
29.561 MWh alineada, 39.464 con −1 día, 49.738 con +1 día. No mide el efecto de envejecer solo la
historia —ahí se desalinea también el viento previsto—, pero acota el orden de magnitud del problema.
