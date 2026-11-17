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
    `n_variables` es 19, no hay avisos bloqueantes y `historico` tiene al menos
    30 puntos.
  - Estado: **parcial**. El archivo existe (sembrado por el workflow con
    `force=true`, no a mano) y cumple: `historico` con 45 puntos, `n_variables`
    19 y solo los dos avisos esperables (REE sin D+1 y AEMET sin el diario de
    ayer), que no bloquean. Queda pendiente el start command con
    `--proxy-headers` en Render: `render.yaml` lo declara, pero el servicio
    `api_ML` conserva el antiguo y no está gestionado por blueprint.

- [ ] **T-10-10 — Contrato en el repositorio** (V1–V12; RNF-3)
  - Revisar que `fecha_objetivo` es mañana, `fecha_observacion >= hoy - 2` y el
    archivo no supera 120 KB.
  - Hecho cuando: el snapshot es el estado inicial del build, no tiene avisos
    bloqueantes y no hay campos opcionales ni datos simulados.

## Bloque D — Lógica del frontend

- [x] **T-10-11 — `forecast.mjs`** (8.1)
  - `todayInMadrid(now)`, `tomorrowInMadrid(today)`,
    `validateSnapshot(snapshot, today)`, `snapshotStatus(snapshot, today)`,
    `generationLabel(snapshot)` y `staleMessage(snapshot, today)`.
  - Sin DOM, sin red y sin reloj oculto: `todayInMadrid(now)` recibe el instante
    como parámetro opcional y el resto recibe la fecha ya resuelta.
  - Hecho cuando: los cuatro estados y los textos de la tabla 8.4 salen de
    estas funciones.

- [x] **T-10-12 — Pruebas de la lógica** (8.1, 8.4; CA-10.10, 10.15)
  - `frontend/tests/forecast.test.mjs` con los 15 casos del plan: calendario,
    snapshot válido, faltantes, ayer/hoy, 16 variables, `NaN`, longitudes,
    husos, snapshot real, `pendiente`/`caducado`, build viejo, determinismo y
    datos simulados.
  - Retirar de `evolution.test.mjs` las pruebas de `predictionStatus`.
  - Hecho cuando: `node --test frontend/tests` está en verde.
  - Resultado: 37 pasan, 0 fallan y 1 se omite con motivo explícito: el caso
    «snapshot real» espera a `frontend/src/data/forecast-snapshot.json`
    (T-10-09). Cuando exista, se ejecuta y la omisión desaparece.

## Bloque E — Automatización

- [x] **T-10-13 — Workflow** (7.1–7.3; CA-10.4)
  - Crons `0 5` y `0 8` con `timezone: Europe/Madrid`, `workflow_dispatch` con
    `force`, `permissions: contents: write`, `concurrency` y
    `timeout-minutes: 30`.
  - Guardia por estado del archivo (objetivo mañana y `avisos` vacío), no por
    el texto del cron. Validación con `validateSnapshot` y la fecha de Madrid.
  - Publicación con `jq`, comparación de hash y resumen en
    `$GITHUB_STEP_SUMMARY`.
  - Hecho cuando: `workflow_dispatch` con y sin `force` funciona y una segunda
    ejecución sin cambios no crea commit.
  - Resultado: `.github/workflows/forecast-refresh.yml`. Probado en local
    ejecutando los `run:` reales del YAML contra un servidor de pruebas y un
    remoto git `bare`: dispatch sin y con `force`, segunda ejecución sin commit,
    guardia en `schedule` (omite, ejecuta con objetivo de ayer, con avisos y con
    archivo corrupto) y fallos (401, 502, sin secretos, backend caído, snapshot
    rechazado por `forecast.mjs`). No comprobable fuera de GitHub: soporte real
    de `timezone` en `schedule`, `jq` y Node en el runner, permisos de push y
    reconstrucción de Vercel. Eso es T-10-14.

- [ ] **T-10-14 — Secretos y primer commit automático** (7.3; CA-10.4, 10.14)
  - Cargar `BACKEND_URL` y `REFRESH_TOKEN` en GitHub Actions; ejecutar el
    workflow como si fuera la ventana de las 05:00.
  - Hecho cuando: el bot commitea, Vercel reconstruye, Render no despliega y la
    ejecución de las 08:00 se salta si el snapshot ya es el de mañana y está
    limpio.
  - Estado de la reconstrucción: **cumplido**. La GitHub App de Vercel no estaba
    instalada en `jlalonsoredon` (única causa de que ningún push desplegara). Una
    vez instalada, el commit `0e73ad2` generó despliegue de producción `READY`
    sin intervención, y un push a la rama `test/vercel-push` generó su preview.
    Queda por verificar en real solo la ejecución programada de las 08:00.
  - Estado: **abierta**. Medido en GitHub (secretos `BACKEND_URL` y
    `REFRESH_TOKEN` cargados): `force=true` (run `43969457872`) → éxito, commit
    `b01d40a` del bot; 2.ª ejecución sin `force` (run `43970160531`) → éxito pero
    **commit `b39bb24`** en lugar de `already_done`. Causa: el snapshot lleva
    avisos (`capture_aemet_forecast: parcial`, `download_aemet_data: parcial`),
    el backend no cachea con avisos y recalcula (401.623 → 403.125 MWh; cambia
    `velmedia`). Por la misma causa la guardia de las 08:00 no se saltará.
    Render no desplegó tras los commits del bot (eventos sin cambios desde las
    21:56; `rootDir=backend`). Pendiente: Vercel (403 de scope; hay que autorizar
    el equipo), build filter del dashboard y decidir qué hacer con los avisos de
    AEMET. El token se pegó en el chat: conviene rotarlo en Render y GitHub.
  - Actualización 17/11 (00:10): con la `AEMET_API_KEY` nueva en Render la
    captura pasó de 1/12 a 12/12 ubicaciones sin errores (el código no tenía
    fallo: desde local daba 23/24). Run `43975927336` → éxito, commit `30ff829`
    (objetivo 18/11, 19 variables). Siguen dos avisos estructurales, no
    transitorios: `capture_ree_forecast` (ESIOS no publica el D+1 de mañana a
    las 00:00–05:00) y `download_aemet_data` (AEMET no tiene aún el diario de
    ayer: 15/11 y 16/11 sin datos). Con ellos el backend no cachea y la 2.ª
    ejecución recalcula. Además: forzar la ejecución a las 23:5x falla con
    `faltan=['sol_lag1']` porque la elaboración AEMET de las 22:05 deja vacío el
    cielo del día en curso. Decisión pendiente: qué avisos impiden cachear.

## Bloque F — Integración del frontend

- [x] **T-10-15 — Tarjeta y `live-prediction.mjs`** (8.2; CA-10.6, 10.7; RNF-9)
  - Renderizar la tarjeta en build desde el snapshot: valor, fechas, familia,
    variables y estado con la fecha del build.
  - `live-prediction.mjs` solo recalcula el estado con `todayInMadrid()` y
    actualiza el texto. Fuera `API_BASE_URL`, `TIMEOUT_MS`, `fetchJson` y
    `loading`.
  - Hecho cuando: sin JavaScript se ve el estado del build; con JavaScript se
    actualiza; todo funciona con Render bloqueado y sin `fetch`.
  - Resultado: `cardView(snapshot, today)` (pura, con pruebas) genera los
    textos; las tres tarjetas (`index`, `resultados`, `LivePredictionStatus`)
    se renderizan en build y `initLivePrediction(snapshot)` solo recalcula el
    estado. `todayInMadrid` ya no está duplicada. Se retiraron los `noscript`
    de las tarjetas porque decían «dato en vivo». Comprobado en navegador con
    la fecha adelantada: `ok`, `pendiente`, `caducado` y `no_disponible`; 0
    peticiones a Render o `/api` en `/`, `/resultados` y `/proceso`; `dist/`
    sin `fetch` ni URL de Render. Límite: en `no_disponible` por fecha del
    navegador (objetivo posterior a mañana) el script no borra las cifras del
    build; solo cambia el mensaje (la spec no pide más).

- [x] **T-10-16 — `PredictionChart.astro`** (8.2, 8.4; CA-10.6–10.10)
  - Importar el snapshot en el `<script>`, dibujar con `fechas_hist`,
    `real_gwh`, `pred_gwh`, `vel_norm`, `racha_norm` y `manana`, y añadir la
    nota de frescura.
  - Hecho cuando: la gráfica funciona sin red y muestra `ok`, `pendiente`,
    `caducado` o `no_disponible` según la fecha del navegador.
  - Resultado: la gráfica importa el snapshot, no llama a la red y la nota de
    frescura se renderiza en build y se recalcula en el navegador. El punto de
    la previsión se etiqueta «mañana», «hoy» (pendiente) o «caducado» y no se
    dibuja en `no_disponible`. Comprobado en navegador (4 estados, sin
    desbordamiento horizontal en móvil). Adelanto de T-10-17: se retiró
    «Cargando datos…» y el aviso de un minuto de la gráfica.

- [x] **T-10-17 — Textos y estado** (8.3, 8.4; RNF-11)
  - `LivePredictionStatus.astro`, `index.astro` y `resultados.astro`: copia de
    «publicado», sin «en vivo», sin «Cargando…» y sin el aviso de un minuto.
  - La hora sale de `generationLabel(snapshot)`; ningún texto fija las 05:00.
  - Hecho cuando: los textos coinciden con la tabla 8.4, se ven bien en móvil y
    sin JavaScript muestran el estado del build.
  - Resultado: sin «en vivo», «Cargando…» ni aviso de un minuto en `index`,
    `resultados`, `proceso` ni la gráfica. Textos comprobados contra la tabla
    8.4 (`ok`, `pendiente`, `caducado`, `no_disponible`). La hora sale de
    `generationLabel`. Sin JavaScript: el HTML del build trae el estado
    (comprobado en `dist/`). En `no_disponible` el script también sustituye las
    cifras por «no disponible» (antes quedaban visibles; corregido). Móvil
    comprobado en `resultados`; la portada no se pudo capturar en móvil por el
    estado de la ventana del navegador.

- [x] **T-10-18 — Retirar el cron muerto** (D-10-13; CA-10.13)
  - Eliminar `frontend/cron.js`, quitar `crons` de `frontend/vercel.json` y
    retirar `predictionStatus` de `evolution.mjs`.
  - Hecho cuando: no quedan referencias al cron ni a `predictionStatus` y
    `node --test` sigue en verde.
  - Resultado: `frontend/cron.js` eliminado; `frontend/vercel.json` queda en
    `{}`; `predictionStatus` retirada de `evolution.mjs`. Sin referencias en
    `frontend/src`, `frontend/tests` ni `vercel.json`. Quedan menciones en
    `AGENTS.md`, `README.md` y specs anteriores: son documentación histórica o
    del proyecto y no se han tocado sin pedirlo. `node --test frontend/tests`:
    42/42.

## Bloque G — Verificación y cierre

- [ ] **T-10-19 — Extremo a extremo** (P-10-9 a P-10-20; RNF-1 a RNF-11)
  - `npm run build` con 0 errores de `astro check`, `node --test`, `grep -r
    onrender frontend/dist`, navegación con Render bloqueado, navegación sin
    JavaScript, `git revert` del commit de datos y revisión de logs/bundle sin
    token.
  - Hecho cuando: P-10-9 a P-10-20 pasan y el sitio se reconstruye sin
    intervención.
  - Resultado (parcial, ver `MEMORY.md`):
    - P-10-11 cumplida: `grep onrender dist` sin resultados; ni token ni clave
      en `dist/` ni en los logs de Render.
    - P-10-12 cumplida: `/`, `/resultados` y `/proceso` sin peticiones a
      Render ni a `/api` (con el preview del build).
    - P-10-13 y P-10-17 cumplidas: con la fecha del navegador adelantada, el
      snapshot del 18/11 pasa a `pendiente` (18/11) y a `caducado` (19/11, un
      build de dos días).
    - P-10-14 cumplida: revertir el commit de datos deja el blob del snapshot
      anterior (`f17d98d6`).
    - P-10-16 cumplida: ningún deploy de Render tras los commits del bot.
    - P-10-18 cumplida en local con uvicorn: 401 × 5, 429 en el sexto; con otra
      IP (`X-Forwarded-For`) sigue 401.
    - P-10-19 cumplida con la regla nueva (opción A): con un aviso bloqueante
      la segunda llamada recalcula; con solo los esperables (REE y AEMET diario)
      devuelve `already_done`. Verificado con pasos simulados y en producción.
      La formulación original de P-10-19 («cualquier aviso recalcula») ya no
      aplica.
    - P-10-9 cumplida del todo: ejecución manual → commit (`4da4894`) y build de
      Vercel; tras instalar la GitHub App, cualquier push despliega solo
      (`0e73ad2` en producción, `36bffa4` en preview, ambos `READY`).
    - P-10-10 cumplida tras la opción A: la primera ejecución sin `force`
      publica `4da4894` y la segunda responde `already_done` sin commit (logs de
      Render: «Snapshot ya generado»).
    - **Hallazgo (resuelto):** Vercel no creó ningún despliegue automático desde
      `47578bb` porque la GitHub App de Vercel no estaba instalada en
      `jlalonsoredon` (`create_git_project` devolvía «you need to install the
      GitHub integration first»). Los builds manuales funcionaban porque el repo
      es público. Tras instalarla, los push despliegan solos.
    - P-10-20 no verificable fuera de GitHub.
    - Pendiente para cerrar T-10-19: el despliegue automático de Vercel por
      push (ver hallazgo). P-10-20 se queda como no verificable.
    - Sin JavaScript: comprobado en el HTML del build; no se ha probado en un
      navegador con JS desactivado.

- [x] **T-10-20 — Cierre documental**
  - Actualizar `MEMORY.md` con estado, secretos, filtro de Render, primer
    commit y forma de revertir.
  - Hecho cuando: el estado de la 010 queda escrito y los pendientes ajenos
    (008 en producción, rotación AEMET, scikit-learn) siguen listados.
  - Resultado: `MEMORY.md` recoge estado, secretos, commits del bot, forma de
    revertir y los pendientes ajenos (008 en producción, rotación de la clave
    AEMET y de `REFRESH_TOKEN`, compatibilidad de scikit-learn). El filtro de
    build de Render y `healthCheckPath` siguen siendo manuales en el dashboard.
