# Spec 001 — Incorporar la fotovoltaica al pipeline

> **Sustituida por `specs/002-sol-feature-eolica/spec.md` (2026-10-29).** El objetivo de esta spec
> (RF-6, HU-4: entrenar un modelo solar autónomo) no responde al objetivo del proyecto. Se mantiene como
> antecedente: el catálogo de estaciones, la descarga y la lógica pura de `src/pipeline/solar.py` siguen
> siendo válidos y los reutiliza la spec 002.

## 1. Contexto y objetivo

El proyecto predice la generación eólica diaria peninsular combinando datos de producción de REE con
datos meteorológicos de AEMET. En una fase anterior se descartó la energía solar fotovoltaica porque las
cinco estaciones meteorológicas elegidas para las mayores plantas fotovoltaicas de España no publicaban
insolación de forma aprovechable.

La investigación posterior identificó, para cada planta, una estación alternativa de la red primaria de
AEMET que sí dispone de serie de insolación:

| Planta | Provincia | Estación sustitutiva | Indicativo | Distancia |
|---|---|---|---|---|
| Francisco Pizarro | Cáceres | CÁCERES | 3469A | 56 km |
| Núñez de Balboa | Badajoz | BADAJOZ/TALAVERA LA REAL | 4452 | 70 km |
| Mula | Murcia | MURCIA/ALCANTARILLA | 7228 | 16 km |
| Don Rodrigo | Sevilla | SEVILLA/SAN PABLO | 5783 | 22 km |
| Chiprana-Samper | Zaragoza | ZARAGOZA/AEROPUERTO | 9434 | 82 km |

**Objetivo:** incorporar al proceso de creación del pipeline la obtención de datos de esas estaciones,
la construcción de las variables fotovoltaicas y el entrenamiento de un modelo de generación solar
diaria peninsular, **sin alterar el funcionamiento ni los resultados del modelo eólico**.

**Por qué ahora:** la limitación que motivó el descarte (ausencia de insolación) ya no existe para las
cinco plantas, y la serie de generación solar peninsular disponible está completa para todo el periodo
de estudio.

**Por qué importa:** el sistema pasa de explicar una sola tecnología renovable a explicar dos, y la
complementariedad eólico–solar es relevante para el análisis del mix.

## 2. Usuarios

- **U1 — Analista (autor del proyecto).** Ejecuta el proceso de creación del pipeline y necesita que
  produzca un modelo solar válido y comparable con el eólico.
- **U2 — Evaluador técnico (tutor, revisor del repositorio).** Necesita poder comprobar la metodología:
  qué estaciones se usaron, por qué, qué cobertura tienen y qué métricas alcanza el modelo.
- **U3 — Visitante de la web.** *No es usuario de esta versión*: no se expone nada nuevo en la interfaz.

## 3. Historias de usuario

- **HU-1.** Como U1, quiero que el proceso descargue automáticamente los datos meteorológicos de las
  cinco estaciones asociadas a las plantas fotovoltaicas, para no tener que gestionarlas a mano.
- **HU-2.** Como U1, quiero que el proceso me avise de forma inequívoca si una estación no publica
  insolación, para no entrenar un modelo con datos que no existen.
- **HU-3.** Como U1, quiero un conjunto de variables fotovoltaicas análogo al eólico, para poder
  comparar ambos modelos con el mismo criterio.
- **HU-4.** Como U1, quiero un modelo solar entrenado, evaluado y guardado junto al eólico, para
  disponer de las dos predicciones con el mismo proceso.
- **HU-5.** Como U2, quiero que quede registrado qué estación se asignó a cada planta y con qué
  cobertura, para poder auditar la decisión metodológica.

## 4. Requisitos funcionales

### RF-1 — Catálogo de plantas y estaciones
El sistema debe mantener un catálogo de las cinco plantas fotovoltaicas, cada una con sus coordenadas y
su estación meteorológica asignada según la tabla del apartado 1.

- **CA-1.1** CUANDO se inicia el proceso, el sistema debe disponer de exactamente cinco pares
  planta–estación, sin duplicados de indicativo.
- **CA-1.2** El sistema debe conservar para cada par las coordenadas de la planta y la distancia a su
  estación, de modo que la asignación sea auditable.

### RF-2 — Obtención del histórico meteorológico
El sistema debe obtener el histórico diario de las cinco estaciones para el mismo periodo que cubre la
serie eólica, incorporando al menos insolación, temperatura media, temperatura mínima y temperatura
máxima.

- **CA-2.1** CUANDO finaliza la obtención, el sistema debe disponer de una serie diaria por estación que
  cubra el periodo de estudio completo.
- **CA-2.2** SI una estación ya dispone de datos descargados para un día, ENTONCES el sistema debe
  omitir esa descarga y no duplicar registros.
- **CA-2.3** CUANDO se ejecuta el proceso por segunda vez, el sistema debe dejar el volumen de datos
  igual que tras la primera ejecución.

### RF-3 — Validación de la disponibilidad de insolación
El sistema debe comprobar, antes de construir variables, que cada una de las cinco estaciones publica
efectivamente insolación para el periodo de estudio.

- **CA-3.1** SI una estación no publica insolación en ningún día del periodo, ENTONCES el sistema debe
  detener la ejecución con un error que identifique la planta y el indicativo afectados.
- **CA-3.2** SI se detiene por este motivo, ENTONCES el sistema no debe generar el modelo solar.
- **CA-3.3** El mensaje de error debe indicar la causa y la acción esperada (revisar o sustituir la
  estación), no solo el fallo técnico.

### RF-4 — Diagnóstico de cobertura
El sistema debe informar, por estación y por variable, el porcentaje de valores ausentes y el bloque de
días consecutivos sin dato más largo.

- **CA-4.1** CUANDO finaliza el diagnóstico, el sistema debe mostrar los resultados de las cinco
  estaciones de forma legible en la salida del proceso.
- **CA-4.2** SI una estación supera el umbral de ausencia aceptado, ENTONCES el sistema debe señalarlo
  de forma destacada. *(Umbral pendiente: ver duda D-1.)*

### RF-5 — Construcción de variables fotovoltaicas
El sistema debe construir un conjunto de variables de entrada para el modelo solar estructuralmente
análogo al del modelo eólico, sustituyendo las variables de viento por variables de insolación y
temperatura.

- **CA-5.1** El conjunto debe contener, al menos: insolación diaria, temperatura media, mes, día de la
  semana, día del año, retardos de la generación solar de 1, 2, 3 y 7 días, medias móviles de
  insolación de 3, 7 y 14 días y media móvil de la generación solar de 7 días.
- **CA-5.2** CUANDO se construyen las variables, el sistema no debe usar información posterior al día
  predicho (sin fuga de datos).
- **CA-5.3** Las variables derivadas deben calcularse sobre días consecutivos reales, sin que un hueco
  de datos se traduzca en un retardo incorrecto.

### RF-6 — Objetivo del modelo solar
El sistema debe construir la serie objetivo con la generación solar fotovoltaica diaria peninsular.

- **CA-6.1** La serie objetivo debe cubrir el mismo periodo y tener un valor por día, sin duplicados.
- **CA-6.2** SI el periodo de la serie objetivo no cubre el de la serie eólica, ENTONCES el sistema debe
  informar del recorte aplicado antes de entrenar.

### RF-7 — Alineación con el pipeline existente
El sistema debe integrar el bloque fotovoltaico en el mismo proceso, respetando la estructura actual.

- **CA-7.1** CUANDO se ejecuta el proceso, el bloque eólico debe ejecutarse y producir el mismo resultado
  que antes de este cambio, con los mismos datos de entrada.
- **CA-7.2** El bloque fotovoltaico no debe modificar ni reordenar los datos que consume el bloque
  eólico.
- **CA-7.3** SI el bloque fotovoltaico falla, ENTONCES la ejecución completa debe detenerse con error.
  *(Decisión tomada: se acepta el impacto sobre el bloque eólico.)*

### RF-8 — Entrenamiento del modelo solar
El sistema debe entrenar un modelo de regresión para la generación solar diaria usando el mismo esquema
de partición temporal que el modelo eólico.

- **CA-8.1** La partición debe ser temporal y cronológica, con la misma proporción que el modelo eólico,
  sin mezclar días de entrenamiento y de prueba.
- **CA-8.2** Todo ajuste de escala o transformación debe calcularse solo con los datos de entrenamiento.
- **CA-8.3** CUANDO termina el entrenamiento, el sistema debe informar del número de días de
  entrenamiento y de prueba y de sus rangos de fechas.

### RF-9 — Evaluación del modelo solar
El sistema debe evaluar el modelo solar y reportar, como mínimo, las mismas métricas que el modelo
eólico.

- **CA-9.1** El informe debe incluir error cuadrático medio, error absoluto medio, coeficiente de
  determinación, error porcentual absoluto medio y la métrica de acierto por tramos.
- **CA-9.2** Las métricas deben calcularse exclusivamente sobre el conjunto de prueba.
- **CA-9.3** El sistema debe presentar el modelo solar junto a los modelos de referencia comparados,
  en el mismo formato que el eólico.

### RF-10 — Persistencia del modelo solar
El sistema debe guardar el modelo solar de forma independiente del modelo eólico.

- **CA-10.1** CUANDO finaliza el entrenamiento, el sistema debe dejar disponible el modelo solar con su
  transformación de escala y su lista de variables.
- **CA-10.2** El guardado del modelo solar no debe sobrescribir ni alterar el modelo eólico ya
  existente.
- **CA-10.3** El conjunto de variables guardado debe coincidir exactamente con el usado en el
  entrenamiento.

### RF-11 — Trazabilidad de la decisión
El sistema debe dejar constancia de las estaciones elegidas, su motivación y su cobertura.

- **CA-11.1** CUANDO se ejecuta el proceso, debe quedar registrado qué estación se asignó a cada planta
  y por qué se descartaron las anteriores.
- **CA-11.2** Las métricas obtenidas deben quedar registradas junto a la fecha de la ejecución.

## 5. Requisitos no funcionales

- **RNF-1 — Simplicidad y continuidad.** El bloque fotovoltaico se añade al proceso existente; no se
  reestructura ni se renombra el pipeline principal.
- **RNF-2 — Neutralidad sobre lo existente.** El modelo eólico en producción y sus variables no cambian
  como consecuencia de esta funcionalidad.
- **RNF-3 — Reproducibilidad.** Dos ejecuciones con los mismos datos de entrada deben producir los
  mismos resultados y las mismas métricas.
- **RNF-4 — Idempotencia.** Reejecutar la obtención de datos no debe duplicar registros ni corromper el
  histórico.
- **RNF-5 — Honestidad del diagnóstico.** Un fallo de datos nunca debe quedar oculto tras un valor por
  defecto o una serie simulada.
- **RNF-6 — Idioma.** Comentarios, mensajes de salida y documentación en español.
- **RNF-7 — Sin dependencias nuevas.** La funcionalidad se resuelve con lo ya disponible en el entorno.
- **RNF-8 — Respeto a la fuente de datos.** La obtención de datos debe respetar los límites de peticiones
  del proveedor y no bloquear ejecuciones posteriores.

## 6. Casos límite

- **CE-1.** Una estación publica la variable de insolación pero con huecos: cómo se trata. *(Ver D-1.)*
- **CE-2.** Una estación deja de medir a mitad de la serie histórica (caso real de CASPE, que dejó de
  publicar insolación en enero de 2024).
- **CE-3.** Insolación igual a cero: es un valor válido (día sin sol), no un dato ausente.
- **CE-4.** Insolación superior a las 24 horas del día: valor físicamente imposible, debe detectarse.
- **CE-5.** Días sin generación solar registrada en el objetivo.
- **CE-6.** Días festivos o con calendario atípico que alteren el patrón semanal.
- **CE-7.** Año bisiesto y cambio de hora: la serie diaria debe mantener un valor por día natural.
- **CE-8.** Desfase entre el final de la serie meteorológica y el de la serie de generación: el sistema
  debe recortar al tramo común e informar.
- **CE-9.** Ejecución interrumpida a mitad de la descarga: al relanzar no debe duplicar ni perder datos.
- **CE-10.** Estación descatalogada o indicativo inexistente en la fuente.
- **CE-11.** El proceso se ejecuta sin conexión o la fuente devuelve error temporal: debe fallar de forma
  explícita, nunca continuar con datos incompletos.
- **CE-12.** Las cinco estaciones existen y publican insolación, pero la serie resultante es tan corta que
  no permite separar entrenamiento y prueba con garantías.

## 7. Fuera de alcance

- Exponer la predicción solar en la API o en la interfaz web.
- Modificar el scheduler o añadir reentrenamiento automático.
- Cambiar el modelo eólico, sus variables o sus métricas.
- Incorporar la energía hidráulica.
- Sustituir la insolación por datos de reanálisis (ERA5) cuando falte.
- Imputar o reconstruir la insolación ausente.
- Corregir el defecto conocido de estación duplicada en la red eólica.
- Reentrenar el modelo en producción o desplegar la nueva versión.
- Sincronizar las dos bases de datos del proyecto.

## 8. Criterios de finalización

La funcionalidad se considera terminada cuando:

1. Una única ejecución del proceso, partiendo del repositorio limpio, descarga las cinco estaciones,
   construye las variables y entrena y guarda el modelo solar.
2. El catálogo planta–estación coincide exactamente con la tabla del apartado 1.
3. El diagnóstico de cobertura se muestra para las cinco estaciones.
4. Se han reportado las métricas del modelo solar sobre el conjunto de prueba.
5. El modelo eólico se entrena y guarda igual que antes del cambio, con métricas idénticas a las
   registradas previamente.
6. Existe una comprobación explícita de que un fallo de insolación detiene la ejecución con un mensaje
   que identifica planta e indicativo.
7. La memoria del proyecto recoge la decisión, las estaciones y las métricas obtenidas.

## 9. Dudas abiertas

- **[NECESITA ACLARACIÓN] D-1 — Umbral de huecos.** Se decidió detener la ejecución si falta insolación,
  pero "huecos" no está cuantificado. Cobertura observada en el histórico disponible: Sevilla 94,6 %,
  Cáceres y Murcia sin medir aún. ¿Se tolera un porcentaje (por ejemplo hasta un 5 %), un número máximo
  de días consecutivos, o cualquier ausencia detiene el proceso?
- **[NECESITA ACLARACIÓN] D-2 — Alcance del fallo.** Aceptado que un fallo fotovoltaico aborta también el
  bloque eólico. ¿Se confirma que es deseable que un problema de una estación solar impida refrescar el
  modelo eólico, que hoy funciona?
- **[NECESITA ACLARACIÓN] D-3 — Temperaturas.** ¿Entran temperatura mínima y máxima como variables del
  modelo, o solo temperatura media, para mantener el paralelismo exacto con el esquema eólico (que usa
  dos variables meteorológicas)?
- **[NECESITA ACLARACIÓN] D-4 — Estaciones originales.** ¿Se eliminan del proceso las cinco estaciones
  originales (TRUJILLO, ZAFRA, CARTAGENA, SEVILLA AEROPUERTO, CASPE) o se mantienen documentadas como
  antecedente?
- **[NECESITA ACLARACIÓN] D-5 — Métrica de acierto.** El modelo eólico reporta un porcentaje de acierto
  calculado por tramos de quintiles. ¿Se reutiliza ese mismo criterio para el modelo solar?
- **[NECESITA ACLARACIÓN] D-6 — Constitución del proyecto.** `docs/constitution.md` está redactada para
  otro proyecto: menciona "Diario de Estudio", almacenamiento en el navegador y pruebas con `node --test`,
  y pide código en inglés, mientras que este proyecto es de análisis de datos y su AGENTS.md exige
  español. ¿Se adapta la constitución a este proyecto antes de planificar?
- **[NECESITA ACLARACIÓN] D-7 — Umbral de calidad.** ¿Existe un mínimo de coeficiente de determinación
  por debajo del cual el modelo solar no debe considerarse aceptable?
