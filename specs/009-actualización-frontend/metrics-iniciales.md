# Línea base — lo que la web muestra antes de la spec 009

- **Fecha de captura:** 2026-11-15.
- **Método:** navegación de las cuatro páginas en local, lectura de la API del
  backend y revisión de los datos incrustados en el frontend.
- **Propósito:** dejar constancia inmutable de las cifras que el visitante ve
  hoy. No se actualiza después; es la referencia contra la que la spec 009
  contrasta el estado nuevo.

> Este registro captura lo que se muestra, no lo que sería correcto. Varias
> cifras están desfasadas respecto al modelo en producción; precisamente por eso
> existe la spec 009.

---

## 1. Predicción destacada (`/resultados`)

La página se genera con un valor de ejemplo y lo sustituye al responder la API.

| Momento | Fecha | Producción | Modelo | Viento | Ráfagas |
|---|---|---|---|---|---|
| Antes de cargar | 2026-05-14 | 207.354 MWh | Linear Regression | 3,77 m/s | 9,2 m/s |
| Tras cargar | 2026-11-16 | 278.461 MWh | Linear Regression | 3,1746 m/s | 8,6507 m/s |

El valor de ejemplo se declara con 4 variables, mientras que el modelo real usa
19. La etiqueta del modelo no indica el número de variables.

## 2. Tabla de modelos (`/proceso`)

Escrita a mano en el contenido de la página. Siete filas, todas de 16 variables.

| Modelo | RMSE (MWh) | R² | MAPE (%) |
|---|---|---|---|
| Linear Regression | 60.433 | 0,579 | 41,73 |
| Lasso | 60.433 | 0,579 | 41,73 |
| Random Forest | 60.438 | 0,579 | 44,30 |
| Ridge | 60.498 | 0,578 | 41,95 |
| LightGBM | 61.873 | 0,559 | 44,46 |
| XGBoost | 63.346 | 0,537 | 45,87 |
| Red Neuronal (MLP) | 63.910 | 0,529 | 43,22 |

Texto asociado: *«Modelo seleccionado: Linear Regression por obtener el mejor
equilibrio entre R² (0.579) y menor RMSE»*.

## 3. Gráfica de comparación de modelos (`/proceso` y `/resultados`)

Ocho series semanales fijas, del 2025-06-29 al 2026-05-10 (46 semanas). No
consulta la API.

| Modelo | RMSE (MWh) | R² | MAPE (%) |
|---|---|---|---|
| Linear Regression ⭐ | 60.418 | 0,5779 | 41,6 |
| Lasso | 60.419 | 0,5779 | 41,6 |
| Ridge | 60.484 | 0,5769 | 41,8 |
| Random Forest | 60.544 | 0,5761 | 44,3 |
| LightGBM | 61.625 | 0,5608 | 44,1 |
| XGBoost | 62.182 | 0,5529 | 44,6 |
| Red Neuronal (MLP) | 62.424 | 0,5494 | 44,0 |
| SARIMAX | 91.679 | 0,0280 | 43,3 |

Ninguna fila de 19 variables aparece en la web, aunque la API ya las devuelve.

## 4. Textos con cifras

| Dónde | Texto | Cifra |
|---|---|---|
| `/resultados` | «Linear Regression obtiene el mejor resultado general» | R² = 0.579 |
| `/proceso` | «aproximadamente el … de la generación es renovable» | 58,33 % |
| `/proceso` | «siendo la energía eólica la tecnología más representativa» | 23,41 % |
| `/proceso` | «seguida de la solar fotovoltaica» | 19,83 % |
| `/proceso` | «y la hidráulica» | 11,64 % |
| `/proceso` | «Proporciona datos climáticos de … estaciones» | 14 estaciones |
| `/proceso` | «Ubicación geográfica de los … parques» | 7 parques |
| `/proceso` | «Período: Enero 2022 - Actualidad» | — |

La lista de estaciones que acompaña al texto nombra nueve ciudades, mientras que
el modelo usa siete ubicaciones eólicas y cinco solares.

## 5. Mix energético (gráfica de `/proceso`)

Valores fijos, sin consultar la API.

| Tecnología | % del total |
|---|---|
| Renovable | 58,33 |
| No renovable | 41,67 |
| Eólica | 23,41 |
| Solar fotovoltaica | 19,83 |
| Hidráulica | 11,64 |
| Solar térmica | 1,62 |
| Otras renovables | 1,55 |
| Residuos renovables | 0,26 |

## 6. Serie de generación renovable (`/proceso`)

Seis series semanales fijas, del 2022-01-02 al 2026-05-17, en GWh: eólica,
solar fotovoltaica, hidráulica, solar térmica, otras renovables y residuos. No
consulta la API.

## 7. Importancia de variables

Existe una visualización con siete valores fijos —`velmedia` 0,35, `racha` 0,25,
`eolica_lag1` 0,15, `eolica_lag7` 0,10, `vel_ma7` 0,08, `mes` 0,04 y
`dia_semana` 0,03— que **no está montada en ninguna página**. La API ya devuelve
las 19 variables reales.

## 8. Predicción frente a real (`/resultados`)

Consulta la API: últimos 30 días reales más la predicción de mañana. Funciona,
pero emite un error de consola por un bloque de script duplicado. La serie
incluye el día en curso, que aún está incompleto.

## 9. Mapa de parques (`/proceso`)

Siete parques fijos. Borja y La Muela comparten la estación `9299X`
(TARAZONA), por lo que la estación aparece dos veces.

## 10. Estado actual del backend (referencia de contraste)

Capturado a la misma hora, para poder comparar:

| Dato | Valor |
|---|---|
| Predicción de mañana | 278.461 MWh · 2026-11-16 · 19 variables |
| Linear Regression (19 variables) | RMSE 23.108,4 · MAE 15.588,2 · R² 0,9308 · n = 354 |
| LightGBM (19 variables) | RMSE 20.246,4 · MAE 14.447,0 · R² 0,9468 · n = 354 · rechazado |
| Ventana de evaluación | 2025-11-22 → 2026-11-10 |
| Importancia de variables | 19 filas; `eolica_prev` 0,6909 |
| Mix energético | 100 % solar fotovoltaica (día en curso, incompleto) |
| Último día de la serie | 2026-11-15, con eólica 0 e hidráulica 0 (incompleto) |

Las siete filas históricas de 16 variables siguen disponibles y marcadas como
tales. Las dos filas de 19 variables declaran `mape` y `accuracy` como no
disponibles, porque el acta de evaluación no las incluye.

## 11. Contradicciones detectadas

1. **Tres métricas distintas para Linear Regression** conviven en la web:
   60.433 / 0,579 en la tabla, 60.418 / 0,5779 en la gráfica y 60.432,9 / 0,579
   en datos que ya no se muestran. Ninguna coincide con la API.
2. **La gráfica de modelos ignora las filas actuales**: el backend ya publica 19
   variables y la web sigue dibujando solo las ocho antiguas.
3. **Valor de ejemplo visible**: antes de que responda la API se lee una
   predicción del 14 de mayo de 2026.
4. **Gráficas congeladas en mayo de 2026**: mix y serie renovable no reflejan el
   estado actual.
5. **«14 estaciones»** no coincide con las 12 ubicaciones que usa el modelo.
6. **«trimestre»** aparece como variable creada y no forma parte del modelo.
7. **Datos generados al azar** en una serie histórica que ninguna página usa.
8. **Error de consola** en la gráfica de predicción frente a real.
9. **Codificación**: la predicción devuelve `dia_aÃ±o` con doble codificación,
   mientras que la gráfica devuelve `dia_año` correctamente.

## 12. Qué NO captura este registro

- No fija el aspecto visual ni el diseño; solo contenido y cifras.
- No incluye el estado del volumen de Render, solo el backend local.
- No juzga si las cifras antiguas fueron correctas en su momento; solo
  documenta que son las que el visitante ve hoy.

---

## Anotaciones posteriores

Este registro no se reescribe. Las anotaciones se añaden aquí, fechadas.

### 2026-11-15 — Revisión QA de la spec

- **Spec que usa este registro:** la spec 009 de esta misma carpeta.
- **Cifra elegida como línea base:** la tabla de modelos de la sección 2,
  RMSE 60.433 MWh · R² 0,579 · MAPE 41,73 %, con 16 variables y ventana no
  documentada.
- **Entorno publicado, capturado el mismo día:** la sección 10 recoge el
  backend local. El entorno publicado respondía distinto:

| Dato | Entorno publicado |
|---|---|
| Predicción para 2026-11-16 | 106.432 MWh |
| Variables declaradas | no las declara |
| Ráfagas | 0,0 m/s |
| Fecha de emisión | no la devuelve |
| Filas de modelos | 7, sin número de variables ni estado histórico |
| Primera respuesta | más de 45 s (arranque en frío) |

La diferencia se debe a que la spec 008 no está liberada en el entorno
publicado.
