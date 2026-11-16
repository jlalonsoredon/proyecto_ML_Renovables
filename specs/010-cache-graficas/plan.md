# Plan 010 — Cachear las gráficas con un snapshot diario

Deriva de `spec.md`. No modifica modelos, cálculos ni dependencias. Sustituye
tres peticiones del navegador por un archivo versionado que se construye una vez
al día.

## 1. Decisiones de diseño

`PD-10-x` identifica una decisión de este plan; `P-10-x` es una prueba de
aceptación de la spec.

| Id | Decisión | Cubre |
|---|---|---|
| PD-10-1 | `forecast_cache.py` compone el snapshot llamando a funciones internas, nunca a los endpoints HTTP del propio servicio. | D-10-7, D-10-9, RNF-1 |
| PD-10-2 | El cuerpo de `get_prediction_chart()` se extrae a `build_current_chart(hoy)` en `charts.py`. El endpoint y el snapshot usan la misma función. | D-10-7, CA-10.1 |
| PD-10-3 | `_get_historico_eolica` se renombra a `get_historico_eolica` y pasa a ser pública. | D-10-9 |
| PD-10-4 | Bloqueo con `threading.Lock` no bloqueante (`409`) y caché en memoria por `fecha_objetivo`, solo si la ejecución no dejó avisos. | D-10-4, CA-10.5, CA-10.17 |
| PD-10-5 | El job de las 03:00 llama a `forecast_cache.refresh()` en vez de a `run_daily_task`. Mismo camino, misma caché. | D-10-4 |
| PD-10-6 | La espera al backfill AEMET del arranque es un `threading.Event` con tope de 10 minutos. | 6.6, RNF-4 |
| PD-10-7 | Doble validación: Python antes de responder y el mismo `forecast.mjs` en el workflow antes de commitear. V6 solo en Python. | D-10-8, CA-10.3 |
| PD-10-8 | El workflow extrae `.snapshot` con `jq`, valida con `node` y hace commit solo si el archivo cambia. | D-10-12, 7.2 |
| PD-10-9 | La guardia se aplica a toda ejecución programada y decide por estado del archivo (objetivo y avisos), nunca comparando el texto del cron. El disparo manual ejecuta siempre y `force` pasa `?force=true`. | D-10-12 |
| PD-10-10 | El JSON se importa en el `<script>` de la gráfica; no se sirve desde `public/`. Evita fetch, caché y cabeceras. | D-10-5, RNF-1 |
| PD-10-11 | La tarjeta se renderiza en build desde el snapshot; `live-prediction.mjs` solo recalcula el estado en el cliente. Pierde `API_BASE_URL`, `TIMEOUT_MS`, `fetchJson` y `loading`. | D-10-5, 8.2, RNF-9 |
| PD-10-12 | `snapshotStatus` sustituye a `predictionStatus`. Se retiran la función y sus pruebas de `evolution.mjs`. | D-10-6, 8.4 |
| PD-10-13 | Los textos nuevos están en español y no cambian estructura, clases ni jerarquía visual. | RNF-11 |
| PD-10-14 | `frontend/src/utils/api.ts` no se toca: no lo importa nadie. | 8.3 |
| PD-10-15 | `render.yaml` documenta el filtro de compilación, pero el servicio real se configura en el dashboard. | D-10-11 |
| PD-10-16 | Cadena de tiempos 10 < 20 < 30 minutos: espera de backfill, `curl` y `timeout-minutes`. | D-10-19, RNF-4 |
| PD-10-17 | `snapshotStatus` tiene cuatro estados; `pendiente` usa tono informativo. | D-10-6, 8.4 |
| PD-10-18 | La comparación de fechas corre en el cliente; el build solo aporta los datos. El HTML trae el estado del build como valor por defecto. | D-10-18, CA-10.15, RNF-9 |
| PD-10-19 | uvicorn arranca con `--proxy-headers --forwarded-allow-ips="*"` en `render.yaml` y en el dashboard. | D-10-20, 6.9 |
| PD-10-20 | Ningún texto fija la hora de publicación: sale de `generationLabel`, que lee `fecha_generacion`. | 8.4 |

### Justificación y alternativas descartadas

| Decisión | Justificación | Alternativa descartada |
|---|---|---|
| Funciones internas (PD-10-1) | Un HTTP contra sí mismo duplica red, serialización y errores, y arrastra los fallbacks de `/api/historical`. | Llamar a los endpoints públicos: más simple de escribir, peor de depurar. |
| `build_current_chart` (PD-10-2) | Garantiza que el snapshot y la gráfica no puedan divergir. | Copiar las cinco líneas del handler: dos definiciones del mismo payload. |
| Caché en memoria (PD-10-4) | El disco de Render es efímero; persistir sería una ilusión. La memoria cubre el caso real 03:00 → 05:00. | Escribir en SQLite: se pierde al dormir. Volver a ejecutar siempre: duplica AEMET y REE. |
| Espera al backfill (PD-10-6) | Sin observaciones AEMET no hay `vel_ma14` ni `racha_ma14`, y la predicción falla. | Predecir en cuanto arranca: falla la mitad de las mañanas. |
| Doble validación (PD-10-7) | El backend valida el contenido; el workflow valida lo que va a commitear, con el código que lo va a leer. | Confiar solo en el backend: un bug de serialización llegaría al repositorio. |
| Importar el JSON (PD-10-10) | Cero red, cero caché, cero CORS. El hash de Vite lo hace inmutable. | `public/data/*.json`: añade un fetch y cabeceras que mantener. |

## 2. Archivos que se crean o modifican

| Acción | Archivo | Responsabilidad |
|---|---|---|
| Crear | `backend/app/services/forecast_cache.py` | Composición, validación, caché y orquestación del snapshot. |
| Crear | `backend/app/api/internal.py` | Endpoints internos autenticados de refresco y estado. |
| Crear | `frontend/src/utils/forecast.mjs` | Lógica pura: validación, estado, etiquetas y fechas. |
| Crear | `frontend/src/data/forecast-snapshot.json` | Snapshot sembrado en la fase 1. |
| Crear | `frontend/tests/forecast.test.mjs` | Pruebas de la lógica pura y de integridad del snapshot. |
| Crear | `.github/workflows/forecast-refresh.yml` | Disparo diario, guardia, validación y commit. |
| Modificar | `backend/app/api/charts.py` | `get_historico_eolica` pública y `build_current_chart`. |
| Modificar | `backend/app/main.py` | Router interno, job de las 03:00 y evento de backfill. |
| Modificar | `backend/app/tasks/scheduler.py` | Atributo `backfill_done`. |
| Modificar | `backend/.env.example` | `REFRESH_TOKEN=`. |
| Modificar | `render.yaml` | `REFRESH_TOKEN`, `buildFilter` y start command con `--proxy-headers`. |
| Modificar | `frontend/src/utils/live-prediction.mjs` | Sin red; snapshot importado. |
| Modificar | `frontend/src/components/charts/PredictionChart.astro` | Sin red; nota de frescura. |
| Modificar | `frontend/src/components/evolution/LivePredictionStatus.astro` | Renderiza valores y estado en build; copia con `generationLabel`, no «en vivo». |
| Modificar | `frontend/src/pages/index.astro` | Quitar el aviso de un minuto. |
| Modificar | `frontend/src/pages/resultados.astro` | Ídem. |
| Modificar | `frontend/src/utils/evolution.mjs` | Retirar `predictionStatus`. |
| Modificar | `frontend/tests/evolution.test.mjs` | Retirar las pruebas de `predictionStatus`. |
| Eliminar | `frontend/cron.js` | Cron que nunca se desplegó. |
| Modificar | `frontend/vercel.json` | Quitar `crons`. |
| Modificar | `MEMORY.md` | Estado y próximos pasos al cerrar. |

## 3. Orden de trabajo

| Paso | Trabajo | Verificación |
|---|---|---|
| 0 | Liberar la 008 en `main`, fusionar `SDD` y configurar el filtro de compilación de Render. | `/api/prediction` devuelve `n_variables: 19` y `fecha_emision`. |
| 1 | `charts.py`: renombrar y extraer. | `/api/prediction-chart` responde idéntico byte a byte salvo orden de claves. |
| 2 | `forecast_cache.py` + `internal.py` + `main.py`. | Matriz de P-10-1 a P-10-8 y P-10-18 con `curl` en local o contra uvicorn con proxy headers. |
| 3 | Desplegar el backend y sembrar el snapshot con una llamada real a `force=true`. | `jq . frontend/src/data/forecast-snapshot.json` y revisión manual de los tres bloques. |
| 4 | `forecast.mjs` y sus pruebas. | `node --test frontend/tests`. |
| 5 | Workflow y secretos. | `workflow_dispatch` con `force` y sin él. |
| 6 | Sustituir las tres llamadas y retirar el cron muerto. | `npm run build` y navegación con Render bloqueado. |
| 7 | Extremo a extremo en producción. | Commit del workflow, rebuild de Vercel y Render sin desplegar. |

Cada paso se cierra antes de abrir el siguiente. La verificación de extremo a
extremo (paso 7) solo empieza cuando los anteriores están en verde.

## 4. Funciones puras de `forecast.mjs`

| Función | Entrada | Salida |
|---|---|---|
| `tomorrowInMadrid(today)` | `"2026-11-16"` | `"2026-11-17"` |
| `todayInMadrid(now)` | `Date` o nada | `"2026-11-16"` |
| `validateSnapshot(snapshot, today)` | objeto + fecha | `string[]` de problemas |
| `snapshotStatus(snapshot, today)` | objeto + fecha | `{ state, motivo, objetivo, valorMWh, familia, nVariables, emision, generacion }` |
| `generationLabel(snapshot)` | objeto | `"Datos del 16/11/2026 a las 05:02"` |
| `staleMessage(snapshot)` | objeto | Texto del aviso de la tabla 8.4 |

Sin DOM, sin `fetch` y sin reloj oculto: `todayInMadrid(now)` recibe el instante
como parámetro opcional y el resto de funciones recibe la fecha ya resuelta.

## 5. Estrategia de pruebas con `node --test`

`frontend/tests/forecast.test.mjs`:

1. `tomorrowInMadrid` cruza mes, año y 29 de febrero.
2. Snapshot válido evaluado con su fecha: `validateSnapshot` devuelve `[]`.
3. Falta `prediccion` o `grafico`: un problema por clave.
4. `fecha_objetivo` de ayer: `caducado` con el texto correcto.
5. `fecha_objetivo` de hoy: `pendiente` con el texto informativo de madrugada.
6. `n_variables` 16: `no_disponible`.
7. `NaN` en `prediccionMWh`: `no_disponible`.
8. Longitudes desalineadas en `grafico`: un problema por lista.
9. `generationLabel` en dos husos distintos da el mismo texto.
10. El snapshot real del repositorio pasa `validateSnapshot` y
    `snapshotStatus` con la fecha de su `fecha_emision`.
11. Un build de hace dos días, evaluado con la fecha de hoy, da `caducado`.
12. El estado no depende del reloj del build: misma entrada, misma salida.
13. `validateSnapshot` rechaza avisos con marcas de datos simulados.
14. `generationLabel` usa `fecha_generacion`: un snapshot de las 03:12 no
    muestra las 05:00.
15. `todayInMadrid` con un instante UTC fijo devuelve la fecha de Madrid en
    verano e invierno.

`frontend/tests/evolution.test.mjs`: se retiran las cuatro pruebas de
`predictionStatus`; el resto queda igual.

Backend: no se añade framework. La validación se prueba con los casos de la
matriz de `curl` y con la comprobación de que un snapshot manipulado responde
`502`.

## 6. Verificación manual

1. `npm run build` en `frontend/`: 0 errores de `astro check`.
2. `node --test frontend/tests`: todo en verde.
3. `grep -r onrender frontend/dist`: sin resultados.
4. Con Render dormido: portada, resultados y proceso cargan y dibujan.
5. `curl` sin token, con token malo y sin variable de entorno: `401`, `401`, `503`.
6. Seis intentos con token malo desde una IP: `429` en el sexto. Uno desde otra IP: `401`, no `429`.
7. `curl` correcto dos veces: `200` y `already_done`.
8. `curl` correcto con `force=true`: `actualizado`.
9. Ejecutar el workflow a mano: commit y rebuild de Vercel.
10. Ejecutarlo otra vez el mismo día: sin commit.
11. Revisar los eventos de Render: sin deploy por el commit de datos.
12. `git revert` del commit de datos: la web vuelve al snapshot anterior.
13. Con JavaScript desactivado: la tarjeta muestra valor y estado del build; la gráfica no se dibuja y el resto de la página sigue legible.

## 7. Riesgos del plan

| Riesgo | Mitigación |
|---|---|
| El merge de `SDD` toca `MEMORY.md` y el mismo bloque de próximos pasos. | Actualizar `MEMORY.md` después del merge, no antes. |
| El snapshot sembrado se toma de la producción de 16 variables. | El paso 0 es bloqueante: no se siembra hasta que la 008 esté liberada. |
| El backend tarda más de 20 min en el primer arranque tras el letargo. | `curl --max-time 1200`, `timeout-minutes: 30` y reintento a las 08:00. |
| `jq` no está en el runner. | Está en `ubuntu-latest`; si faltara, se sustituye por `node -e`. |
| El commit diario dispara Render. | Filtro de compilación antes del primer commit automático. |
| El build de Astro falla si el JSON no existe. | Sembrado en el paso 3, antes de importarlo en el paso 6. |
| El dashboard no actualiza el start command y el rate limit ve una sola IP. | `render.yaml` deja el comando escrito; P-10-18 lo comprueba desde dos IPs. |

## 8. Transición

- `PUBLIC_API_URL` se conserva en Vercel durante la transición aunque el
  frontend ya no la use; se retira en una limpieza posterior.
- `frontend/src/utils/api.ts` queda sin uso y no se toca en esta spec (PD-10-14).
