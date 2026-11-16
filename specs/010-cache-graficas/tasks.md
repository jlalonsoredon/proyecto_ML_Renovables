# Tareas 010 — Cachear las gráficas con un snapshot diario

Derivan de `spec.md` y `plan.md`. Estado: pendientes a 2026-11-16.

> **Bloqueante:** la 008 debe estar liberada en `main`. Mientras el contrato siga
> en 16 variables, V4 rechaza cualquier snapshot y no hay nada que sembrar.
> El workflow programado tampoco corre hasta que `SDD` esté fusionada.

## Bloque A — Requisitos previos

- [ ] **T-10-01 — Liberar la 008 en `main`** (CA-10.1)
  - Desplegar el contrato de 19 variables con `fecha_emision` y `n_variables`.
  - Hecho cuando: `/api/prediction` devuelve `n_variables: 19`, `fecha_emision`
    y el vector completo; `/health` responde 200.

- [ ] **T-10-02 — Fusionar `SDD` y filtrar Render** (D-10-11; CA-10.14)
  - Merge de `SDD` en `main` para que existan el workflow y el backend nuevos.
  - Build Filters del servicio `api_ML`: incluir `backend/**`, excluir
    `frontend/**`. Declarar `buildFilter` en `render.yaml` como documentación.
  - Hecho cuando: el workflow aparece en la rama por defecto y un commit que
    solo toca `frontend/**` no genera deploy en Render.

## Bloque B — Backend

- [x] **T-10-03 — Refactor de `charts.py`** (PD-10-2, PD-10-3; 6.2)
  - `_get_historico_eolica` pasa a `get_historico_eolica` y se actualiza su
    único uso (`build_current_chart`).
  - Extraer el cuerpo de `get_prediction_chart()` a `build_current_chart(hoy)`.
  - Hecho cuando: `/api/prediction-chart` y `/api/historical` responden lo mismo
    que antes, salvo el orden de claves.

- [x] **T-10-04 — `forecast_cache.py`** (V1–V12; D-10-7, D-10-9)
  - `build_snapshot(hoy)`: llama a `scheduler_service.run_daily_task(hoy)` y
    compone el snapshot con `get_historico_eolica` y
    `build_prediction_chart_payload`. Sin duplicar cálculos.
  - `validate_snapshot(snapshot, hoy)`: V1–V12, con V6 solo en Python.
  - `refresh(force=False)` y `cached()` con el lock y la caché de la sección 6.4.
  - Hecho cuando: un snapshot real pasa la validación y los bloques
    `prediccion`, `historico` y `grafico` coinciden con los endpoints públicos.

- [x] **T-10-05 — Endpoint interno** (CA-10.1–10.3, 10.5, 10.17; D-10-10, D-10-20)
  - `POST /api/internal/forecast/refresh` con `Authorization: Bearer` y
    `secrets.compare_digest`; `503` sin variable, `401` con traza, `429` a partir
    de 5 fallos/minuto/IP, `409` si hay una ejecución en curso, `502` si el
    snapshot no valida. `force` ignora la caché.
  - `GET /api/internal/forecast/status`. Router con `include_in_schema=False`.
  - Start command con `--proxy-headers --forwarded-allow-ips="*"` en
    `render.yaml` y en el dashboard, para que la IP del rate limit no sea la del
    proxy.
  - Hecho cuando: P-10-1 a P-10-8 pasan en local y P-10-18 contra uvicorn con
    proxy headers, con dos IPs distintas.
  - Pendiente manual: el start command del servicio real en el dashboard de
    Render (solo `render.yaml` está actualizado) y crear `REFRESH_TOKEN` allí.

- [x] **T-10-06 — Espera al backfill** (6.6; RNF-4)
  - `scheduler_service.backfill_done` (`threading.Event`), activado en `finally`
    desde `main.py`; con `run_background_tasks=False` nace activado.
  - `refresh()` espera 10 minutos como máximo y anota el timeout en `avisos`.
  - Hecho cuando: un arranque local con backfill lento no bloquea más de 10
    minutos y uno normal no espera de más.

- [x] **T-10-07 — Job de las 03:00** (D-10-4)
  - El scheduler llama a `forecast_cache.refresh()` en vez de a
    `run_daily_task`, sin reentrenar y con el mismo camino que el endpoint.
  - Hecho cuando: dos ejecuciones del mismo día devuelven `already_done` y los
    logs incluyen `run_id`, duración y avisos.

- [x] **T-10-08 — Matriz local con `curl`** (P-10-1 a P-10-8)
  - Sin token, token malo, sin `REFRESH_TOKEN`, llamada correcta, repetición,
    `force`, dos simultáneas y fallo forzado de REE.
  - Hecho cuando: los códigos y cuerpos coinciden con la tabla de pruebas.
  - Resultado: P-10-1, 2, 3, 5, 6, 7 y 8 pasan en local. P-10-4 (servicio
    dormido, menos de 20 min) solo se puede medir contra Render: queda para T-10-09.

## Bloque C — Sembrado

- [ ] **T-10-09 — Desplegar y sembrar** (5.1; 17.2)
  - Configurar `REFRESH_TOKEN` y el start command con proxy headers en Render,
    desplegar el backend y llamar una vez a
    `POST /api/internal/forecast/refresh?force=true`.
  - Guardar `.snapshot` como `frontend/src/data/forecast-snapshot.json` y
    commitearlo.
  - Hecho cuando: `jq .` lo muestra válido, `schema_version` es 1,
    `n_variables` es 19, `avisos` está vacío y `historico` tiene al menos 30
    puntos.

- [ ] **T-10-10 — Contrato en el repositorio** (V1–V12; RNF-3)
  - Revisar que `fecha_objetivo` es mañana, `fecha_observacion >= hoy - 2` y el
    archivo no supera 120 KB.
  - Hecho cuando: el snapshot es el estado inicial del build y no hay campos
    opcionales ni datos simulados.

## Bloque D — Lógica del frontend

- [ ] **T-10-11 — `forecast.mjs`** (8.1)
  - `todayInMadrid(now)`, `tomorrowInMadrid(today)`,
    `validateSnapshot(snapshot, today)`, `snapshotStatus(snapshot, today)`,
    `generationLabel(snapshot)` y `staleMessage(snapshot)`.
  - Sin DOM, sin red y sin reloj oculto: `todayInMadrid(now)` recibe el instante
    como parámetro opcional y el resto recibe la fecha ya resuelta.
  - Hecho cuando: los cuatro estados y los textos de la tabla 8.4 salen de
    estas funciones.

- [ ] **T-10-12 — Pruebas de la lógica** (8.1, 8.4; CA-10.10, 10.15)
  - `frontend/tests/forecast.test.mjs` con los 15 casos del plan: calendario,
    snapshot válido, faltantes, ayer/hoy, 16 variables, `NaN`, longitudes,
    husos, snapshot real, `pendiente`/`caducado`, build viejo, determinismo y
    datos simulados.
  - Retirar de `evolution.test.mjs` las pruebas de `predictionStatus`.
  - Hecho cuando: `node --test frontend/tests` está en verde.

## Bloque E — Automatización

- [ ] **T-10-13 — Workflow** (7.1–7.3; CA-10.4)
  - Crons `0 5` y `0 8` con `timezone: Europe/Madrid`, `workflow_dispatch` con
    `force`, `permissions: contents: write`, `concurrency` y
    `timeout-minutes: 30`.
  - Guardia por estado del archivo (objetivo mañana y `avisos` vacío), no por
    el texto del cron. Validación con `validateSnapshot` y la fecha de Madrid.
  - Publicación con `jq`, comparación de hash y resumen en
    `$GITHUB_STEP_SUMMARY`.
  - Hecho cuando: `workflow_dispatch` con y sin `force` funciona y una segunda
    ejecución sin cambios no crea commit.

- [ ] **T-10-14 — Secretos y primer commit automático** (7.3; CA-10.4, 10.14)
  - Cargar `BACKEND_URL` y `REFRESH_TOKEN` en GitHub Actions; ejecutar el
    workflow como si fuera la ventana de las 05:00.
  - Hecho cuando: el bot commitea, Vercel reconstruye, Render no despliega y la
    ejecución de las 08:00 se salta si el snapshot ya es el de mañana y está
    limpio.

## Bloque F — Integración del frontend

- [ ] **T-10-15 — Tarjeta y `live-prediction.mjs`** (8.2; CA-10.6, 10.7; RNF-9)
  - Renderizar la tarjeta en build desde el snapshot: valor, fechas, familia,
    variables y estado con la fecha del build.
  - `live-prediction.mjs` solo recalcula el estado con `todayInMadrid()` y
    actualiza el texto. Fuera `API_BASE_URL`, `TIMEOUT_MS`, `fetchJson` y
    `loading`.
  - Hecho cuando: sin JavaScript se ve el estado del build; con JavaScript se
    actualiza; todo funciona con Render bloqueado y sin `fetch`.

- [ ] **T-10-16 — `PredictionChart.astro`** (8.2, 8.4; CA-10.6–10.10)
  - Importar el snapshot en el `<script>`, dibujar con `fechas_hist`,
    `real_gwh`, `pred_gwh`, `vel_norm`, `racha_norm` y `manana`, y añadir la
    nota de frescura.
  - Hecho cuando: la gráfica funciona sin red y muestra `ok`, `pendiente`,
    `caducado` o `no_disponible` según la fecha del navegador.

- [ ] **T-10-17 — Textos y estado** (8.3, 8.4; RNF-11)
  - `LivePredictionStatus.astro`, `index.astro` y `resultados.astro`: copia de
    «publicado», sin «en vivo», sin «Cargando…» y sin el aviso de un minuto.
  - La hora sale de `generationLabel(snapshot)`; ningún texto fija las 05:00.
  - Hecho cuando: los textos coinciden con la tabla 8.4, se ven bien en móvil y
    sin JavaScript muestran el estado del build.

- [ ] **T-10-18 — Retirar el cron muerto** (D-10-13; CA-10.13)
  - Eliminar `frontend/cron.js`, quitar `crons` de `frontend/vercel.json` y
    retirar `predictionStatus` de `evolution.mjs`.
  - Hecho cuando: no quedan referencias al cron ni a `predictionStatus` y
    `node --test` sigue en verde.

## Bloque G — Verificación y cierre

- [ ] **T-10-19 — Extremo a extremo** (P-10-9 a P-10-20; RNF-1 a RNF-11)
  - `npm run build` con 0 errores de `astro check`, `node --test`, `grep -r
    onrender frontend/dist`, navegación con Render bloqueado, navegación sin
    JavaScript, `git revert` del commit de datos y revisión de logs/bundle sin
    token.
  - Hecho cuando: P-10-9 a P-10-20 pasan y el sitio se reconstruye sin
    intervención.

- [ ] **T-10-20 — Cierre documental**
  - Actualizar `MEMORY.md` con estado, secretos, filtro de Render, primer
    commit y forma de revertir.
  - Hecho cuando: el estado de la 010 queda escrito y los pendientes ajenos
    (008 en producción, rotación AEMET, scikit-learn) siguen listados.
