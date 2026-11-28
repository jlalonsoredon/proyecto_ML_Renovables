# Spec 019 — Esperar a la previsión de REE antes de dar la predicción por buena

Estado: implementada (28/11/2026). Pendiente CA-5: comprobar tras desplegar que la ejecución de las 12:17 usa la previsión real de REE.

## Contexto

Entre el 17 y el 25/11/2026 la predicción falló mucho en algunos días (+23 % el 21/11, +147 % el 23/11, −32 % el 25/11). Al revisar el snapshot publicado (`frontend/src/data/forecast-snapshot.json`) día a día se ve la causa:

| Día | Real (GWh) | Predicción (GWh) | Error | Previsión de REE usada |
|---|---|---|---|---|
| 13/11 | 219,4 | 219,1 | 0 % | real |
| 16/11 | 299,1 | 278,5 | −7 % | real |
| 21/11 | 220,3 | 271,4 | +23 % | estimada |
| 23/11 | 110,8 | 274,2 | +147 % | estimada |
| 24/11 | 251,4 | 260,6 | +4 % | real |
| 25/11 | 380,5 | 260,3 | −32 % | estimada |
| 26/11 | 253,3 | 234,0 | −8 % | real |

- La variable de más peso del modelo es `eolica_prev`, la previsión eólica de REE para el día objetivo (69 % del peso relativo de los coeficientes).
- REE elabora esa previsión hacia las **10:50 (Madrid)**: `elaborado` ≈ 09:50 UTC en `archivo_previsiones.ree`.
- El workflow `forecast-refresh.yml` se ejecuta a las **05:17 y 08:17 (Madrid)** y GitHub lo arranca unos 20 minutos tarde. Las dos ejecuciones llegan antes de que exista la previsión de REE.
- Sin ella, `resolve_eolica_prev` (`backend/app/services/prediction_features.py`) usa la **media de las 7 previsiones anteriores** y la marca como `estimada`. El modelo devuelve entonces algo cercano a la media de la semana: valores casi planos (260-280 GWh) que fallan en los días atípicos.
- Con la previsión real de REE el error medio de esos días es de un 6 %. Los días que acertaron fue porque alguna ejecución de esa tarde (manual) ya tuvo el dato.
- **Dos piezas impiden que el sistema se corrija solo:**
  - `AVISOS_ESPERADOS` (en `frontend/src/utils/forecast.mjs` y `backend/app/services/forecast_cache.py`) trata «Paso capture_ree_forecast: fallo» como esperado. La guarda del workflow considera «limpio» un snapshot con la previsión de REE estimada y no reintenta.
  - La caché del backend (`forecast_cache.refresh`), sin `force`, reutiliza el snapshot del mismo objetivo si no tiene avisos bloqueantes.
- Ejemplo vigente: la predicción publicada el 28/11 para el 29/11 (183.860 MWh) se emitió a las 07:39 con `eolica_prev` estimada y el aviso «Paso capture_ree_forecast: fallo».

## Decisiones

- **D-19-1 — Provisional.** Una predicción es **provisional** si `prediccion.origenes.eolica_prev` no es `prevision` (es `estimada` o falta). Lo decide una función pura, `isProvisional(snapshot)` en `forecast.mjs`, con su espejo en `forecast_cache.py`.
- **D-19-2 — Ejecuciones después de REE.** El workflow añade dos crons en Europe/Madrid, **12:17** y **15:17**, por si REE se retrasa. Se mantienen las de 05:17 y 08:17: dan una cifra temprana, marcada como provisional, para que la web nunca se quede sin predicción por la mañana.
- **D-19-3 — La guarda reintenta las provisionales.** El workflow solo omite la ejecución si el snapshot es el de mañana, no tiene avisos bloqueantes **y no es provisional**. «Paso capture_ree_forecast: fallo» sigue siendo esperado por la mañana, pero ya no hace que una predicción provisional cuente como terminada.
- **D-19-4 — La caché no retiene provisionales.** `forecast_cache.refresh` no reutiliza un snapshot provisional aunque no tenga avisos bloqueantes: recalcula para recoger la previsión de REE en cuanto exista.
- **D-19-5 — La tarjeta lo dice.** Si la predicción vigente es provisional, la tarjeta mantiene su estado (vigente o pendiente) pero muestra el distintivo **«Provisional»** y el texto: «Calculada sin la previsión eólica de REE para mañana, que se publica hacia las 10:50. Se actualizará a lo largo del día.» No se oculta la cifra ni se rellena con otro dato. El contrato del snapshot no cambia: `origenes` ya se publica.
- **D-19-6 — Sin cambios en el modelo ni en el notebook.** Es un problema de la operación diaria, no del modelo. No se toca `FEATURE_COLS`, el `.joblib` ni `main.ipynb`. El scheduler propio del backend en Render (03:00 y 09:00) no cambia: el que publica es el workflow.
- **D-19-7 — Histórico honesto.** Las predicciones ya registradas (incluidas las estimadas del 17-25/11) no se reescriben. A partir de la implementación, el histórico guarda la última predicción emitida para cada día, que normalmente será la que ya usa la previsión real de REE.

## Criterios de aceptación

- **CA-1** `isProvisional` es `true` con `eolica_prev` estimada o ausente y `false` con `prevision`, en el frontend y en el backend (pruebas en `node --test` y en `backend/tests`).
- **CA-2** La guarda no omite un snapshot provisional del día de mañana y sí omite uno con la previsión real de REE y sin avisos bloqueantes (prueba sobre la función que usa la guarda).
- **CA-3** `forecast_cache.refresh` sin `force` recalcula si el snapshot en caché es provisional y lo reutiliza si no lo es.
- **CA-4** La tarjeta muestra «Provisional» y el texto de D-19-5 solo cuando corresponde, en Inicio y en Resultados.
- **CA-5** Tras desplegar, en un día normal la ejecución de las 12:17 publica una predicción con `origenes.eolica_prev = "prevision"`, y la tarjeta deja de mostrarse como provisional.
- **CA-6** `node --test`, `npm run build` y las pruebas del backend pasan.

## Riesgos

- REE puede publicar más tarde de las 12:17; queda el reintento de las 15:17. Si aún no existe, la cifra sigue siendo provisional y la tarjeta lo dice.
- Hasta cuatro commits diarios del bot significan hasta cuatro despliegues en Vercel.
- Render (plan gratuito) puede tardar en despertar; el workflow ya espera hasta 20 minutos.
- Mientras no se implemente, cada mañana se publica una predicción con la previsión de REE estimada. Relanzar el workflow a mano después de las 10:50 la corrige ese día.
