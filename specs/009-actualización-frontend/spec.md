# Spec 009 — Actualizar el frontend: el recorrido de las specs y las métricas reales

- **Estado:** spec cerrada tras revisión QA; pendiente de plan e implementación.
- **Fecha:** 2026-11-15.
- **Depende del comportamiento establecido en:** specs 001 a 008.
- **Línea base registrada en:** el registro de métricas iniciales de esta misma
  carpeta.
- **Autorización expresa:** el usuario pidió el 2026-11-15 actuar sobre el
  frontend sin un cambio previo en el análisis. Queda registrado aquí para
  cumplir el principio 1 de la constitución.

## 1. Contexto

La web se construyó cuando el modelo tenía 16 variables y sus métricas rondaban
los 60.400 MWh de error. Desde entonces el proyecto ha pasado por ocho specs y
la web no ha cambiado: sus tablas, sus textos y sus gráficas siguen mostrando el
estado de mayo de 2026.

La web cuenta una historia que ya terminó y, además, se contradice:

- La tabla de modelos afirma un error de 60.433 MWh y un R² de 0,579.
- La gráfica de comparación afirma 60.418 MWh y 0,5779.
- Los datos internos que ya no se muestran dicen 60.432,9 y 0,579.
- El sistema de referencia publica 23.108,4 MWh y 0,9308 sobre 354 días.

Son cuatro cifras para el mismo modelo, y ninguna permite al visitante entender
qué se ha conseguido.

La spec 008 dejó escrito que la gráfica de comparación seguiría con sus datos
antiguos «hasta una futura spec de frontend». Esta es esa spec.

### 1.1 Dos entornos durante la transición

Al cerrar esta spec conviven dos versiones del servicio:

| Entorno | Predicción para 2026-11-16 | Variables | Filas de modelos |
|---|---|---|---|
| Referencia (integración de la spec 008) | 278.461 MWh | 19 | 9 |
| Publicado (sin liberar la spec 008) | 106.432 MWh | 16 | 7 |

La web se sirve contra el entorno publicado, pero el contenido de esta spec se
escribe contra la referencia. La sección 3 define cómo convive la web con esa
diferencia mientras no se libere la spec 008.

### 1.2 Lo que se quiere contar

| Spec | Tema | Categoría |
|---|---|---|
| 001 | Incorporar la fotovoltaica al pipeline | Datos |
| 002 | La insolación como variable del modelo eólico | Modelo |
| 003 | Archivo de previsiones meteorológicas | Datos |
| 004 | Previsión de fuentes y predicción propia en el análisis | Datos, modelo |
| 005 | La previsión de REE del día objetivo como variable | Modelo |
| 006 | EDA de variables nuevas y elección de familia | Modelo |
| 007 | Consistencia de la familia elegida y trazabilidad | Modelo |
| 008 | Integración del pipeline en el backend | Producción |
| 009 | Esta actualización del frontend | Interfaz |

Las categorías son orientativas; el plan las confirmará con el contenido de cada
spec.

## 2. Objetivo y alcance

**Objetivo:** que la web explique qué cambió en cada spec y qué resultado dejó,
con métricas honestas y con todos sus datos coherentes con el sistema de
referencia.

**Dentro del alcance:**

- La sección nueva del recorrido de las specs.
- La comparación de métricas con la línea base.
- El bloque de estado actual.
- La corrección de toda cifra visible que contradiga a la referencia, en las
  cuatro páginas.
- La puesta al día de los datos de las gráficas.
- La eliminación del error de consola de la página de resultados, porque impide
  verificar que los datos se muestran sin fallos.
- Las pruebas de la lógica de selección y formato.
- El registro de la línea base.

**Fuera del alcance:** rediseño visual, backend, modelo, datos de observación,
páginas nuevas, cambios en el menú y dependencias nuevas.

## 3. Decisiones aprobadas

### 3.1 Contenido

- **D-9-1 — Recorrido completo.** Se documentan las nueve specs, una ficha por
  spec, incluidas las que no movieron ninguna métrica. Ninguna se agrupa ni se
  omite.
- **D-9-2 — Formato.** Las fichas forman una línea de tiempo vertical. Cada hito
  muestra, sin interactuar, número, título, categoría y resultado en una frase.
  La situación de partida, el cambio y el detalle técnico se despliegan.
- **D-9-3 — Categorías.** Cuatro categorías cerradas: datos, modelo, producción
  e interfaz. Un hito puede llevar varias.
- **D-9-4 — Nivel del texto.** El hito plegado se entiende sin conocimientos
  técnicos. El detalle desplegado usa términos y cifras. Un glosario explica R²,
  RMSE, MAE, MAPE, retardo, media móvil, walk-forward y variable.
- **D-9-5 — Identificadores.** Los nombres internos de variables solo aparecen en
  el detalle técnico, acompañados de su descripción en español.

### 3.2 Métricas

- **D-9-6 — Sistema de referencia.** La referencia es el modelo de 19 variables
  integrado en la spec 008: Linear Regression con RMSE 23.108,4 MWh, MAE 15.588,2
  MWh y R² 0,9308, sobre 354 días entre el 2025-11-22 y el 2026-11-10. Toda
  cifra fija de la web debe coincidir con ella.
- **D-9-7 — Línea base.** Es la cifra de la tabla de modelos de la página de
  proceso: RMSE 60.433 MWh, R² 0,579 y MAPE 41,73 %, con 16 variables. Su
  ventana de evaluación no está documentada y así se declara.
- **D-9-8 — Comparabilidad.** Dos cifras son comparables si comparten número de
  variables, ventana y días. Entre cifras comparables se puede mostrar la
  diferencia. Entre cifras no comparables no se muestra ningún porcentaje,
  diferencia ni factor; se presentan una junto a otra con su protocolo.
- **D-9-9 — Cifras de cada spec.** Una ficha puede citar la mejora que midió su
  propia spec, porque esa medición se hizo con un único protocolo. La cita
  incluye siempre su protocolo.
- **D-9-10 — Referencia histórica.** Las siete filas de 16 variables se
  conservan con la etiqueta «histórico». No se borran ni se mezclan con las
  vigentes.
- **D-9-11 — Una cifra por concepto.** Cuando la web muestra dos cifras distintas
  para el mismo modelo y el mismo protocolo, se conserva la de la línea base y la
  otra desaparece. Cuando el protocolo difiere, ambas pueden quedar, cada una con
  el suyo.

### 3.3 Datos y estados

- **D-9-12 — Origen de los datos.** El recorrido, la comparación y las gráficas
  de referencia usan cifras cerradas y versionadas. Solo el bloque de estado
  actual consulta el servicio.
- **D-9-13 — Día completo.** Se hereda la regla de la spec 008: un día es
  completo si su generación eólica alcanza al menos el 60 % de la mediana de los
  siete días anteriores, con un mínimo de cinco valores de entorno.
- **D-9-14 — Ventana de 30 días.** Las series muestran siempre 30 días
  completos. Si el último no lo es, se retrocede hasta reunir 30. Nunca se
  representa un día incompleto como cero ni se interpola.
- **D-9-15 — Vocabulario de estados.** Cada fila o dato lleva su estado escrito:
  «vigente», «histórico», «no disponible» o «caducado». El color y el estilo
  acompañan, nunca sustituyen al texto.
- **D-9-16 — Bloque en vivo.** Se muestra lo que devuelva el servicio, con la
  versión que el propio servicio declara: familia y número de variables. Un
  campo que no llegue se marca «no disponible». Nunca se completa con datos del
  registro.
- **D-9-17 — Caducidad.** Un dato está caducado si su fecha objetivo es anterior
  al día actual peninsular. Se marca como tal y se sigue mostrando.
- **D-9-18 — Sin predicción.** Si no hay predicción, se declara el estado. Nunca
  se rellena con un valor de ejemplo, el último real ni un cero.

### 3.4 Ubicación y calidad

- **D-9-19 — Ubicación.** La sección va en la página de proceso, después de los
  parques monitorizados y antes de la llamada a la acción final. Se numera como
  paso 6 y se accede desde un enlace de anclaje en la cabecera de la página. No
  se toca el menú.
- **D-9-20 — Coherencia.** Se corrige cualquier cifra visible que contradiga la
  referencia, en las cuatro páginas. El diseño actual se mantiene.
- **D-9-21 — Pruebas.** La lógica de selección y formato se separa de la
  interfaz, recibe la fecha de referencia como parámetro y se prueba con la
  herramienta de pruebas del proyecto. No se avanza con pruebas en rojo.
- **D-9-22 — Responsive.** Las cuatro páginas se revisan a 360 px. Un defecto
  introducido por esta spec bloquea la entrega. Un defecto anterior se registra
  y no se corrige aquí.

## 4. Requisitos funcionales

### RF-1 — Contar el recorrido de las nueve specs

- **CA-1.1** Existe un hito por cada spec, de la 001 a la 009, en orden.
- **CA-1.2** Plegado, cada hito muestra número, título, categorías y una frase de
  resultado comprensible sin conocimientos técnicos.
- **CA-1.3** Desplegado, cada hito declara situación de partida, cambio
  introducido, resultado y detalle técnico.
- **CA-1.4** Si una spec no produjo métrica, el resultado se describe sin cifras
  y se dice explícitamente que no hubo cambio medible.
- **CA-1.5** Toda cifra citada incluye su protocolo y procede de una medición
  registrada en esa spec.
- **CA-1.6** El hito de la 009 se presenta como la spec que produce esta sección.
  No se marca «en curso» ni lleva fecha de cierre.
- **CA-1.7** Los hitos se despliegan y pliegan con ratón, teclado y tacto, y su
  estado es perceptible para lectores de pantalla.
- **CA-1.8** Con el código del navegador desactivado, todos los hitos se
  muestran desplegados.
- **CA-1.9** Existe un glosario accesible desde el detalle técnico.

### RF-2 — Comparar las métricas con la línea base

- **CA-2.1** La comparación principal enfrenta la línea base (D-9-7) y la
  referencia (D-9-6).
- **CA-2.2** Cada fila declara número de variables, ventana de evaluación, días y
  estado. Una ventana desconocida se escribe «no documentada».
- **CA-2.3** Entre filas no comparables no aparece ningún porcentaje, diferencia
  ni factor.
- **CA-2.4** Un aviso breve explica, en lenguaje llano, por qué la línea base y la
  referencia no se pueden restar.
- **CA-2.5** La comparación incluye LightGBM de 19 variables con el estado
  «histórico», su decisión de rechazo y el motivo: mejoró en 1 de 4 ventanas y se
  exigían 3.
- **CA-2.6** Entre Linear Regression y LightGBM de 19 variables, que comparten
  protocolo, se puede mostrar la diferencia.
- **CA-2.7** Una métrica que no existe se muestra «no disponible», nunca como
  cero, copiada de otra fila ni estimada.
- **CA-2.8** La comparación está disponible también como tabla con encabezados.

### RF-3 — Mostrar el estado actual

- **CA-3.1** El bloque muestra fecha objetivo, producción, familia, número de
  variables y fecha de emisión, cuando el servicio los devuelve.
- **CA-3.2** La familia y el número de variables se toman de la respuesta. Si no
  llegan, se marcan «no disponible».
- **CA-3.3** Si la fecha objetivo es anterior a hoy, el dato se marca «caducado».
- **CA-3.4** Si no hay predicción, el bloque dice «no disponible». No aparece una
  cifra de ejemplo, el último real ni un cero.
- **CA-3.5** Si el servicio no responde, el bloque muestra un aviso y el resto de
  la sección sigue legible.
- **CA-3.6** Mientras el servicio responde, el bloque muestra un estado de carga
  sin cifras.
- **CA-3.7** Si el servicio supera el tiempo de espera que fije el plan, el
  bloque pasa al aviso de fallo. El tiempo debe tolerar el arranque en frío del
  servicio.
- **CA-3.8** Con el código del navegador desactivado, el bloque explica que el
  dato en vivo no está disponible.
- **CA-3.9** El dato se carga una vez por visita; no hay refresco periódico.

### RF-4 — Dejar la web sin contradicciones

- **CA-4.1** Ninguna cifra fija de la web contradice la referencia.
- **CA-4.2** Desaparece la predicción de ejemplo que se ve en la portada y en
  resultados antes de que llegue el dato real.
- **CA-4.3** La tabla de modelos y la gráfica de comparación muestran las mismas
  cifras para el mismo modelo, en las dos páginas donde aparecen.
- **CA-4.4** Todo texto que cite un R², un error o un porcentaje lo hace con su
  protocolo.
- **CA-4.5** Se corrigen el número de estaciones y la lista de variables, que hoy
  incluye una que no pertenece al modelo.
- **CA-4.6** Los textos del mix y de la serie renovable citan su periodo y cifras
  de días completos.
- **CA-4.7** Ninguna de las cuatro páginas produce errores en la consola del
  navegador.

### RF-5 — Poner al día los datos de las gráficas

- **CA-5.1** La comparación de modelos muestra nueve filas: siete históricas de
  16 variables y dos de 19, con la de producción marcada «vigente».
- **CA-5.2** Las series semanales antiguas, si se conservan, declaran su propia
  ventana y no se presentan como métricas del modelo vigente.
- **CA-5.3** La serie de los últimos días muestra 30 días completos (D-9-14).
- **CA-5.4** El mix energético corresponde a días completos y nunca muestra un
  reparto del 100 % de una sola tecnología por falta de datos.
- **CA-5.5** La importancia de variables muestra las 19 del modelo vigente.
- **CA-5.6** El mapa mantiene los siete parques y declara que dos comparten
  estación.
- **CA-5.7** Ninguna serie se genera al azar ni cambia entre recargas.
- **CA-5.8** Cada gráfica declara su periodo y su fuente, y tiene una descripción
  textual.

### RF-6 — Registrar la línea base

- **CA-6.1** Existe un registro versionado con lo que la web mostraba antes de
  esta spec.
- **CA-6.2** El registro incluye fecha de captura, método y fuente de cada cifra.
- **CA-6.3** El registro no se reescribe. Un error o un dato posterior se añade
  como anotación fechada.
- **CA-6.4** La spec y el registro se referencian mutuamente.

### RF-7 — Probar la lógica

- **CA-7.1** Se prueba la elección del último día completo, incluidos los casos
  con menos de cinco valores de entorno.
- **CA-7.2** Se prueba la ventana de 30 días cuando el último día es incompleto.
- **CA-7.3** Se prueba el formato de métricas y la representación «no
  disponible».
- **CA-7.4** Se prueba la asignación de estados: vigente, histórico, no
  disponible y caducado.
- **CA-7.5** Se prueba la detección de caducidad con fechas de referencia fijas,
  incluido el cambio de día.
- **CA-7.6** Se prueba que no se calcula diferencia entre filas no comparables.
- **CA-7.7** Las pruebas no dependen del reloj ni de la red.

## 5. Requisitos no funcionales

- **RNF-1 — Sin dependencias nuevas.** Se usa lo ya instalado.
- **RNF-2 — Diseño existente.** Se reutilizan tipografía, colores, espaciados y
  piezas visuales actuales. Componer una línea de tiempo, una tabla o un bloque
  de estado con esas piezas no es restyling. Crear un estilo visual nuevo, sí.
- **RNF-3 — Responsive.** A 360 px no hay desplazamiento horizontal de página.
  Las tablas anchas se desplazan dentro de su propio contenedor.
- **RNF-4 — Accesibilidad.** La información no depende solo del color. Las tablas
  tienen encabezados. Las gráficas tienen descripción textual. Todo lo
  interactivo se usa con teclado. El contenido se lee con zoom al 200 %.
- **RNF-5 — Tema.** Todo el contenido nuevo es legible en modo claro y oscuro.
- **RNF-6 — Formato.** Números con separador de miles de punto y decimal de coma.
  Fechas en formato largo en español. Fechas objetivo en hora peninsular.
- **RNF-7 — Honestidad.** Sin valores de relleno, sin diferencias entre
  protocolos distintos, sin métricas copiadas.
- **RNF-8 — Alcance.** No se modifica el backend, el modelo, los datos de
  observación ni la lógica de predicción.
- **RNF-9 — Degradación.** Sin servicio, el recorrido, la comparación y las
  gráficas de referencia siguen legibles.
- **RNF-10 — Trazabilidad.** Toda cifra publicada se puede rastrear a su spec o
  al registro de línea base.
- **RNF-11 — Impresión.** La sección imprime con los hitos desplegados y sin
  depender del color.
- **RNF-12 — Idioma.** Interfaz y textos en español. Los identificadores internos
  solo aparecen en el detalle técnico y explicados.

## 6. Casos límite

- **CE-1 — El servicio no responde.** El bloque actual muestra un aviso. El resto
  de la sección se mantiene.
- **CE-2 — Arranque en frío.** El bloque muestra el estado de carga hasta el
  tiempo de espera fijado y después el aviso.
- **CE-3 — El servicio responde con la versión anterior.** El bloque muestra 16
  variables, declara la versión y marca «no disponible» lo que no llegue.
- **CE-4 — Divergencia entre la cifra en vivo y la referencia.** Se muestran
  ambas, cada una con su origen. No se oculta ni se corrige la cifra en vivo.
- **CE-5 — No hay predicción.** Se declara «no disponible».
- **CE-6 — Fecha objetivo pasada.** El dato se marca «caducado».
- **CE-7 — Cambio de día durante la visita.** La caducidad se evalúa al cargar;
  no se recalcula en directo.
- **CE-8 — Día en curso incompleto.** Se excluye de la serie y del mix y la
  ventana retrocede.
- **CE-9 — Menos de cinco días de entorno para validar.** El día no se da por
  completo.
- **CE-10 — Menos de 30 días completos disponibles.** Se muestran los que haya y
  se declara el número.
- **CE-11 — Una métrica no existe.** Se muestra «no disponible».
- **CE-12 — Métrica implausible** (R² mayor que 1, error negativo o vacío). Se
  muestra «no disponible» y se registra como incidencia.
- **CE-13 — Una spec sin métrica.** El hito lo dice explícitamente.
- **CE-14 — Navegación sin código del navegador.** Hitos desplegados, tablas
  legibles y bloque en vivo con su explicación.
- **CE-15 — Nombres de variable mal codificados en el servicio.** La sección usa
  los nombres del registro, no los del servicio.
- **CE-16 — Línea base frente a fila histórica de Linear Regression.** Se
  presentan como la misma medición con distinto redondeo; no aparecen como dos
  modelos distintos.
- **CE-17 — Nueva spec después de la 009.** Añadir un hito no debe exigir cambiar
  los existentes.

## 7. Criterios de finalización

1. Los nueve hitos existen, están ordenados y cada uno declara partida, cambio y
   resultado.
2. La comparación declara protocolo y estado en cada fila y no contiene
   diferencias entre protocolos distintos.
3. Ninguna cifra fija de la web contradice la referencia.
4. Las gráficas muestran datos de días completos, declaran su periodo y no usan
   valores aleatorios ni de ejemplo.
5. El bloque en vivo declara la versión que recibe y marca lo que falta.
6. El registro de línea base existe, está versionado y coincide con lo que
   mostraba la web.
7. Sin servicio, la web avisa y sigue siendo legible.
8. La consola no muestra errores en ninguna de las cuatro páginas.
9. Las cuatro páginas se revisan a 360 px sin defectos nuevos; los anteriores
   quedan registrados.
10. Las pruebas de la lógica pasan sin depender del reloj ni de la red.
11. La sección es legible en modo claro y oscuro, con teclado y con zoom al 200 %.
12. No se han modificado backend, modelo, datos de observación ni dependencias.

## 8. Fuera de alcance

- Restyling visual, cambio de identidad o creación de un estilo nuevo.
- Añadir una página nueva o una entrada de menú.
- Cambiar el backend, sus contratos o su lógica de predicción.
- Liberar la spec 008 en el entorno publicado.
- Reentrenar, reevaluar o sustituir el modelo.
- Recalcular la línea base con otro protocolo.
- Corregir la codificación de los nombres de variable del servicio.
- Corregir defectos responsive anteriores a esta spec.
- Persistencia en el navegador: esta spec no guarda datos del visitante, por lo
  que el principio 6 de la constitución no aplica.
- Internacionalización, autenticación, analítica y buscadores.
- Modificar los datos históricos de observación.

## 9. Trazabilidad de la revisión QA

| Hallazgo | Resuelto en |
|---|---|
| Sistema de referencia no definido | D-9-6, sección 1.1 |
| Línea base ambigua | D-9-7, CE-16 |
| Día completo sin definir | D-9-13, CA-7.1 |
| Ventana de 30 días | D-9-14, CE-10 |
| Formato de las fichas | D-9-2, CA-1.2, CA-1.3 |
| Taxonomía incompleta | D-9-3 |
| Nivel del texto e identificadores | D-9-4, D-9-5, RNF-12 |
| Distinción visual y «no disponible» | D-9-15 |
| Caducidad sin regla | D-9-17, CE-6 |
| Producción sin los campos pedidos | D-9-16, CE-3 |
| Mix del 100 % frente a coherencia | CA-5.4, D-9-13 |
| Nueve filas sin tocar el backend | D-9-12 |
| Borrar frente a conservar históricos | D-9-10, D-9-11 |
| Porcentajes de las specs 002 y 005 | D-9-8, D-9-9 |
| Límite del restyling | RNF-2 |
| Responsive en cuatro páginas | D-9-22 |
| Error de consola fuera de «contenido» | Sección 2 |
| Posición y acceso | D-9-19 |
| Arranque en frío y tiempo de espera | CA-3.7, CE-2 |
| Modo oscuro, zoom, teclado, impresión | RNF-4, RNF-5, RNF-11 |
| Formato de números y fechas | RNF-6 |
| Principio 1: orden del procedimiento | Autorización en la cabecera |
| Principio 4: lógica separada | D-9-21 |
| Principio 5: tests como puerta | D-9-21, RF-7 |
| Principio 6: datos del usuario | Sección 8 |
