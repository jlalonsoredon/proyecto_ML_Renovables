# Spec 010 — Cachear las gráficas: un snapshot diario en el repositorio

- **Estado:** propuesta cerrada con las seis decisiones del 2026-11-16; plan redactado, pendiente de implementación.
- **Fecha:** 2026-11-16.
- **Depende de:** la spec 008 liberada en producción (contrato de 19 variables) y la spec 009 (frontend actual).
- **Autorización expresa:** el usuario pidió el 2026-11-16 resolver la espera del arranque en frío de Render y respondió a las seis preguntas de alcance recogidas en la sección 1.3. Queda registrado aquí para cumplir el principio 1 de la constitución.

## 1. Contexto

### 1.1 El problema

El backend `api_ML` de Render es un servicio **free**, sin disco y con una sola instancia en Frankfurt. Eso produce cuatro efectos que se suman:

| Hecho verificado | Consecuencia |
|---|---|
| Render duerme el servicio tras 15 minutos sin tráfico entrante. | La primera visita tras el letargo espera unos 51 s de arranque. |
| El sistema de archivos es efímero. | La SQLite (`backend/data/ree_generacion.db`) se reconstruye desde cero en cada arranque. |
| El APScheduler de las 03:00 vive dentro del proceso. | Si el servicio está dormido a esa hora, la tarea diaria no se ejecuta. |
| El navegador hace tres peticiones directas a Render. | La portada, la página de resultados y la gráfica de predicción pagan el arranque en frío. |

Las tres peticiones del navegador son:

| Punto de llamada | Endpoint | Payload |
|---|---|---|
| `frontend/src/utils/live-prediction.mjs` | `GET /api/prediction` | Tarjeta «Producción eólica prevista». |
| `frontend/src/components/charts/PredictionChart.astro` | `GET /api/historical?days=45` | Serie real de los últimos 45 días. |
| `frontend/src/components/charts/PredictionChart.astro` | `GET /api/prediction-chart` | Gráfica de 30 días, predicciones emitidas y viento. |

Además, el cron que debía mantener esto ya está muerto: `frontend/cron.js` está en la raíz del proyecto de Vercel, no en `frontend/api/`, así que la ruta `/api/cron` que declara `frontend/vercel.json` no existe. Y aunque existiera, solo llamaba a `/api/prediction/refresh`, que **recalcula con las previsiones ya guardadas**; no descarga AEMET ni REE.

### 1.2 Lo que ya funciona y no se toca

- El contrato de 19 variables de la spec 008 y la lógica de `prediction_service`.
- Los modelos, los cálculos y el artefacto `modelos/lr_eolica.joblib`.
- La web de la spec 009: recorrido, comparación de métricas y textos visibles.
- La captura de AEMET y REE, que ya resuelve la tarea diaria completa.

### 1.3 Las seis respuestas que cierran el alcance

| # | Pregunta | Respuesta del usuario | Consecuencia |
|---|---|---|---|
| 1 | ¿Qué datos se cachean? | Solo los tres payloads de eólica; más adelante se puede ampliar. | El snapshot contiene `prediccion`, `historico` y `grafico`. No hay demanda ni precios. |
| 2 | ¿Un archivo o tres? | Un solo `previsiones.json` consolidado. | Una versión = un archivo. Atomicidad real y dos peticiones menos. |
| 3 | ¿Dónde se guarda? | Commit diario en el repositorio. | Sin Supabase ni Vercel Blob. El propio commit es la versión y el puntero. |
| 4 | ¿Se retira el scheduler de las 03:00? | Se mantiene como respaldo. | El endpoint debe ser idempotente y el scheduler pasa a usar el mismo camino de generación. |
| 5 | ¿Runtime o build-time? ¿Antigüedad? | Build-time. Mostrar la última fecha disponible y avisar si no es la previsión para mañana. | Cero peticiones a Render desde el navegador. La frescura se mide por `fecha_objetivo`: `pendiente` de madrugada y `caducado` si la publicación ha fallado. |
| 6 | ¿GitHub Actions o Vercel Cron? | GitHub Actions a las **05:00**. | Workflow diario con `timezone: Europe/Madrid` y ejecución manual. |

## 2. Objetivo y alcance

**Objetivo:** que la generación de la previsión ocurra una vez al día, fuera de la ruta del visitante, y que la web la lea de su propio repositorio. El navegador no debe llamar a Render en ninguna circunstancia.

**Dentro del alcance:**

- Un endpoint interno autenticado que ejecuta la tarea diaria completa y devuelve un snapshot validado.
- Un workflow de GitHub Actions a las 05:00 que lo invoca, valida el resultado y lo publica como commit.
- Un único JSON versionado en `frontend/src/data/forecast-snapshot.json`.
- La sustitución de las tres llamadas a Render por la lectura de ese JSON en tiempo de build.
- La eliminación del cron muerto de Vercel.
- El aviso de antigüedad basado en la fecha objetivo.
- Las pruebas de la lógica nueva y de la integridad del snapshot.

**Fuera del alcance:** modelos, cálculos, métricas, diseño visual, nuevas dependencias, Supabase, Vercel Blob, Render Starter y cualquier cambio de contrato en los endpoints públicos existentes, que se conservan intactos para administración.

## 3. Decisiones aprobadas

| Id | Decisión | Justificación | Alternativa descartada |
|---|---|---|---|
| D-10-1 | Un único `forecast-snapshot.json` por ejecución. | Atomicidad: no puede existir una versión con la predicción nueva y el histórico viejo. | Tres archivos: multiplican las peticiones y permiten versiones a medias. |
| D-10-2 | La publicación es un commit en `frontend/src/data/`. | Cero servicios nuevos, cero claves, cero coste. El historial de git es el registro de versiones y el `git revert` es el botón de deshacer. | Supabase Storage o Vercel Blob: una cuenta y una dependencia más para guardar 50 KB al día. |
| D-10-3 | El disparador es GitHub Actions a las 05:00 con `timezone: Europe/Madrid`. | Tiene permiso de escritura con `GITHUB_TOKEN`, historial de ejecuciones y botón manual. Se espera que el commit diario cuente como actividad y evite la desactivación a los 60 días. | Vercel Cron: necesitaría un PAT para hacer el commit y no aporta nada aquí. |
| D-10-4 | El scheduler de las 03:00 se mantiene, pero pasa a llamar al mismo camino de generación que el endpoint. | Si el servicio está despierto a las 03:00, el trabajo queda hecho y cacheado en memoria. Si está dormido, el endpoint de las 05:00 lo repite. | Retirarlo: el usuario pidió conservarlo como red de seguridad. |
| D-10-5 | El frontend lee el snapshot en **build**, no en runtime. | Elimina por completo la red: no hay fetch, no hay CORS, no hay caché que invalidar, no hay arranque en frío. | Runtime contra un almacén externo: obliga a mantener manifiesto y políticas de caché. |
| D-10-6 | La frescura se mide por `fecha_objetivo`, no por horas, con dos estados distintos: `pendiente` y `caducado`. | «Previsión para mañana» es una condición semántica, no un intervalo. Un snapshot de hace 8 h puede ser correcto; uno de hace 2 h puede estar caducado. Y no es lo mismo «todavía no se ha publicado» que «la publicación ha fallado». | Umbral de 36 h: miente en ambos sentidos. Un solo estado de error: avisa cada madrugada de algo normal. |
| D-10-7 | El endpoint ejecuta `scheduler_service.run_daily_task`, no `refresh_prediction`. | Solo recalcular con las previsiones guardadas usaría datos viejos. La tarea completa captura AEMET, captura REE, descarga REE, descarga AEMET, concilia y predice. | Llamar a `/api/prediction/refresh`: publicaría una previsión construida con previsiones caducadas. |
| D-10-8 | La validación es explícita y ejecutable, no una intención. | Un snapshot inválido no debe llegar nunca al repositorio. Ver la sección 6.5. | «Comprobar que los datos son correctos»: no es verificable. |
| D-10-9 | El histórico se obtiene de `db_ree`, nunca de `/api/historical`. | Ese endpoint cae en `generate_mock_historical` si la BD está vacía. Publicar un mock como dato real sería el peor fallo posible. | Reutilizar el endpoint HTTP: arrastra el fallback silencioso. |
| D-10-10 | El token se compara con `secrets.compare_digest` y el endpoint falla cerrado si falta la variable. | Sin `REFRESH_TOKEN` configurado, el endpoint responde 503 y no ejecuta nada. | Comparación con `==` o arrancar sin token: abre la ejecución a cualquiera. |
| D-10-11 | Render ignora los cambios en `frontend/**`. | El commit diario no debe provocar un despliegue del backend. | Dejar que Render redeploye cada día: un minuto de build y un reinicio innecesarios. |
| D-10-12 | El workflow reintenta a las 08:00 solo si el snapshot no es el de mañana o tiene avisos. | Red de seguridad real a coste cero: si la ejecución de las 05:00 falla o sale degradada, la de las 08:00 publica una limpia. | Reintentar siempre: duplica trabajo y commits. |
| D-10-13 | Se retiran `frontend/cron.js` y el cron de `frontend/vercel.json`. | Nunca funcionaron y confunden sobre quién actualiza los datos. | Conservarlos: dejan una segunda vía muerta. |
| D-10-14 | El rollback es `git revert` del commit de datos o del commit de frontend. | Ambas cosas están versionadas y se reconstruyen solas. | Bandera `PUBLIC_DATA_SOURCE`: obliga a mantener dos caminos vivos. |
| D-10-15 | Sin dependencias nuevas. | El backend no habla con ningún almacén: devuelve JSON. El workflow usa `curl`, `git` y `node`, ya presentes en el runner. | SDK de Supabase, `@vercel/blob`, cliente HTTP nuevo. |
| D-10-16 | Código en inglés; campos del JSON, textos y documentación en español. | Constitución, principio 7. | Mezclar idiomas en identificadores. |
| D-10-17 | El snapshot declara `schema_version`. | Permite cambiar la forma sin romper builds antiguos. | Sin versión: cualquier cambio es una rotura silenciosa. |
| D-10-18 | La comparación con «mañana» se hace en el navegador, no en el build. | Un sitio estático no recalcula el día: sin esto, un build de anteayer seguiría diciendo «previsión para mañana». | Reconstruir el sitio cada hora: imposible en el plan gratuito y absurdo para un dato diario. |
| D-10-19 | Cadena de tiempos: espera de backfill 10 min < `curl` 20 min < job 30 min. | Cada capa corta antes que la siguiente, así el error aparece en el sitio correcto y no como un timeout genérico. | Tres topes independientes: el backend esperaría más de lo que aguanta `curl`. |
| D-10-20 | El endpoint registra los intentos fallidos y limita a 5 por minuto y por IP. | Un token estático en un servicio público merece al menos traza y freno. | Solo el token: un fallo de configuración pasa desapercibido. |

## 4. Arquitectura

### 4.1 Escritura (una vez al día)

```
GitHub Actions (05:00 Europe/Madrid)
        │  POST /api/internal/forecast/refresh   Authorization: Bearer <token>
        ▼
Render · FastAPI
        │  1. espera a que termine el backfill AEMET del arranque
        │  2. scheduler_service.run_daily_task(hoy)
        │  3. construye el snapshot con las funciones internas
        │  4. valida; si no pasa, responde error y no devuelve snapshot
        ▼
GitHub Actions
        │  valida otra vez con el mismo módulo del frontend
        │  git add frontend/src/data/forecast-snapshot.json
        │  commit + push solo si el contenido cambió
        ▼
Vercel · rebuild (~1 min)
        ▼
Sitio estático actualizado
```

### 4.2 Lectura (cada visita)

```
Usuario → Vercel (HTML + JS ya construidos) → gráficas
```

No hay petición al backend. Ni en la portada, ni en resultados, ni en la gráfica.

### 4.3 Por qué no las otras opciones

| Opción | Motivo del descarte |
|---|---|
| Render Starter (7 $/mes) | Resuelve el problema, pero el usuario eligió coste cero. Queda documentada como salida si algún día se acepta el gasto. |
| Supabase Storage | La arquitectura original era correcta, pero añade cuenta, bucket, claves, tabla de heartbeat y pausa por inactividad. El commit da lo mismo con menos piezas. |
| Vercel Blob | Igual que Supabase, con dependencia nueva en el frontend. |
| Keep-alive cada 10 min | Consume 744 de las 750 h del workspace y pone en riesgo los otros servicios free. No arregla la pérdida de SQLite. |
| Proxy con caché de CDN | El primer visitante tras cada despliegue sigue esperando, y el resto de páginas sigue dependiendo de Render. |

## 5. Contrato del snapshot

### 5.1 Archivo

`frontend/src/data/forecast-snapshot.json`. Un solo objeto, sin manifiesto: el commit es el puntero atómico y la versión. El nombre de archivo no cambia nunca; lo que cambia es su contenido y su commit.

El usuario llamó a este archivo «previsiones.json». Se adopta `forecast-snapshot.json` porque los artefactos de código van en inglés (constitución, principio 7); los campos del JSON y los textos visibles siguen en español.

### 5.2 Forma

```json
{
  "schema_version": 1,
  "version": "2026-11-16T050213Z",
  "fecha_generacion": "2026-11-16T05:02:13+01:00",
  "fecha_objetivo": "2026-11-17",
  "fecha_emision": "2026-11-16",
  "fecha_observacion": "2026-11-15",
  "prediccion": {
    "fecha": "2026-11-17",
    "prediccionMWh": 278461,
    "modelo": "Linear Regression",
    "features": { "velmedia": 3.17, "racha": 6.4 },
    "n_variables": 19,
    "vector_entrada": { "…": "19 entradas" },
    "origenes": { "…": "origen de cada entrada" },
    "fecha_emision": "2026-11-16",
    "emitida_en": "2026-11-16T05:01:44+01:00"
  },
  "historico": [
    { "fecha": "2026-10-17", "eolica": 123456.7 }
  ],
  "grafico": {
    "fechas_hist": ["…"],
    "real_gwh": [1.23],
    "pred_gwh": [1.24],
    "vel_norm": [0.31],
    "racha_norm": [-0.42],
    "vel_ms": [3.1],
    "racha_ms": [6.4],
    "manana": { "fecha": "2026-11-17", "pred_gwh": 278.46, "prediccion_mwh": 278461.37 },
    "predicciones_propias": [],
    "avisos": []
  },
  "avisos": []
}
```

### 5.3 Reglas del contrato

1. `prediccion` y `grafico` son **exactamente** los payloads que hoy devuelven `/api/prediction` y `/api/prediction-chart`, sin renombrar ni transformar campos. `historico` es la serie `{fecha, eolica}` de 45 días que ya consume la gráfica, obtenida de `get_historico_eolica`; no se usa `/api/historical` porque mezcla formatos de fecha y cae en datos simulados cuando la BD está vacía. Así la tarjeta y la gráfica no cambian de contrato.
2. `fecha_objetivo`, `fecha_emision` y `fecha_observacion` se repiten en la raíz para que la portada no tenga que leer tres objetos anidados.
3. `fecha_observacion` es la fecha del último punto de `historico`, no la de generación.
4. `version` es el instante UTC de la generación, con formato `YYYY-MM-DDTHHMMSSZ`. Se usa en el mensaje de commit y en los logs.
5. Los `avisos` de la raíz acumulan los pasos fallidos de la tarea diaria que no impidieron predecir. Se publican: son información, no ruido.
6. No hay campos opcionales sin motivo: si un dato no está, el snapshot no se publica.

## 6. Backend

### 6.1 Módulo nuevo

`backend/app/services/forecast_cache.py`. Responsabilidades:

- `build_snapshot(hoy) -> dict`: llama a `scheduler_service.run_daily_task(hoy)` y compone el snapshot reutilizando las funciones internas.
- `validate_snapshot(snapshot, hoy) -> list[str]`: devuelve la lista de problemas; vacía significa válido.
- `refresh(force=False) -> dict`: orquesta, aplica el bloqueo y guarda el resultado en memoria.
- `cached() -> dict | None`: metadatos del snapshot en memoria, para el endpoint de estado.

No se duplica ninguna función de cálculo: el histórico sale de `charts.get_historico_eolica` (ver 6.2) y la gráfica de `charts.build_prediction_chart_payload`.

### 6.2 Refactor mínimo en `charts.py`

- `_get_historico_eolica` pasa a llamarse `get_historico_eolica` (pública) y se actualizan sus dos usos.
- El cuerpo de `get_prediction_chart()` se extrae a `build_current_chart(hoy) -> dict`, que el endpoint sigue devolviendo tal cual y que `forecast_cache` reutiliza.

Sin cambios de comportamiento en `/api/historical` ni en `/api/prediction-chart`.

### 6.3 Endpoint interno

`POST /api/internal/forecast/refresh` (`backend/app/api/internal.py`, router con prefijo `/api/internal`).

- Autenticación `Authorization: Bearer <REFRESH_TOKEN>`, comparada con `secrets.compare_digest`.
- Si `REFRESH_TOKEN` no está configurada: `503` y log de error. No se ejecuta nada.
- Token ausente o incorrecto: `401` con `WWW-Authenticate: Bearer`, una línea de log con la IP real (6.9), hora y motivo, y contador de fallos. A partir de 5 fallos por minuto y por IP: `429` durante un minuto.
- `?force=true` ignora la caché en memoria.
- El router se registra con `include_in_schema=False`.
- Respuesta `200`:

```json
{
  "estado": "actualizado",
  "run_id": "2026-11-16T050213Z",
  "duracion_s": 143.2,
  "pasos": { "capture_aemet_forecast": "ok", "run_prediction": "ok" },
  "avisos": [],
  "snapshot": { "…": "objeto de la sección 5" }
}
```

- `estado` vale `actualizado` o `already_done`. En ambos casos incluye `snapshot`.
- Si la validación falla: `502` con `{"detail": "snapshot_invalido", "problemas": [...]}`. Nunca se devuelve un snapshot inválido.
- `GET /api/internal/forecast/status` exige el mismo token y devuelve `{"cache": {"version", "fecha_objetivo", "generado_en"} | null}`; `GET /health` sigue siendo público.

### 6.4 Idempotencia y concurrencia

- **Bloqueo:** `threading.Lock` no bloqueante. Si hay una ejecución en curso, `409 {"detail": "run_in_progress"}`.
- **Caché en memoria:** solo se guarda si la ejecución terminó **sin avisos**. Sin `force`, una segunda llamada para la misma fecha objetivo devuelve `already_done` con el mismo snapshot y no vuelve a ejecutar la tarea. Si hubo avisos, la siguiente llamada recalcula: un reintento no debe heredar una ejecución degradada.
- **Por qué en memoria y no en disco:** el disco de Render es efímero; persistir sería mentira. La memoria cubre el caso real: el scheduler de las 03:00 y la llamada de las 05:00 dentro del mismo contenedor despierto.
- **Idempotencia de publicación:** el workflow compara el hash del snapshot con el archivo del repositorio. Si coincide, no hace commit. Sin commit no hay rebuild ni versión nueva.

### 6.5 Validación (lista cerrada)

El snapshot se rechaza si cualquiera de estas condiciones falla:

| # | Comprobación |
|---|---|
| V1 | `schema_version` es `1` y `version` tiene formato UTC. |
| V2 | `prediccion.fecha == fecha_objetivo == hoy + 1 día` en `Europe/Madrid`. |
| V3 | `prediccion.fecha_emision == hoy` y `fecha_emision` en la raíz coincide. |
| V4 | `prediccion.modelo` no está vacío y `n_variables == 19`. |
| V5 | `prediccion.prediccionMWh` es finito y mayor que cero. |
| V6 | `vector_entrada` tiene las 19 claves de `FEATURE_COLS`, todas finitas, y `origenes` usa solo `observacion`, `prevision`, `mixta` o `estimada`. |
| V7 | `historico` no está vacío, está ordenado y su última fecha es `fecha_observacion`, con `fecha_observacion >= hoy - 2`. |
| V8 | `grafico.fechas_hist`, `real_gwh`, `pred_gwh`, `vel_norm`, `racha_norm`, `vel_ms` y `racha_ms` tienen la misma longitud. |
| V9 | `grafico.manana.fecha == fecha_objetivo` y `grafico.manana.prediccion_mwh` difiere de `prediccion.prediccionMWh` en menos de 1 MWh, con ambos valores finitos. El campo ya existe en el payload de `/api/prediction-chart`; la tolerancia es necesaria porque `prediccionMWh` se redondea a entero y el gráfico conserva el valor de la BD. |
| V10 | `grafico.avisos` no contiene avisos de datos simulados ni de series no leídas. |
| V11 | No hay `NaN`, `Infinity` ni `None` donde el contrato exige número. |
| V12 | `historico` procede de `db_ree.get_generation_series`; el número de puntos es mayor o igual que 30. |

### 6.6 Espera al backfill del arranque

`main.py` lanza `backfill_aemet_diario(days=35)` en un hilo al arrancar. Con el disco efímero, **cada arranque empieza con la BD vacía**: sin ese backfill no hay observaciones para `vel_ma3/7/14` ni `racha_ma3/7/14`, y la predicción no se puede construir.

Por eso:

- `scheduler_service` expone un `threading.Event` `backfill_done`.
- `main.py` lo activa al terminar el backfill, haya ido bien o mal (`finally`).
- `forecast_cache.refresh()` espera al evento con un máximo de 10 minutos antes de ejecutar la tarea diaria. Si expira, sigue igualmente y lo anota en `avisos`.
- Con `run_background_tasks=False` (pruebas) el evento nace activado.

### 6.7 Pasos críticos

`run_daily_task` devuelve un diccionario con el resultado de cada paso y no lanza excepción si uno falla. La publicación **no** se decide por ese diccionario, sino por V1–V12: si el snapshot es válido, se publica aunque un paso opcional haya fallado, y el fallo queda en `avisos`. Si la validación falla, no se publica nada y el endpoint responde `502`.

Ejemplo: si `capture_aemet_forecast` falla pero las previsiones archivadas siguen cubriendo el objetivo, `run_prediction` termina y el snapshot es válido. Si la descarga de REE falla, `fecha_observacion` se queda vieja y V7 lo rechaza. La validación, no el diccionario, es la que decide.

### 6.8 Logs

Cada ejecución registra `run_id`, duración, pasos fallidos y resultado de la validación. Cada intento rechazado registra IP, hora y motivo, nunca el token recibido. `redact_secrets` ya cubre `token` como parámetro; los mensajes del endpoint lo pasan explícitamente como valor a redactar.

### 6.9 IP real detrás del proxy de Render

Render termina TLS en su proxy. Sin configuración adicional, `request.client.host` sería la IP del proxy y los intentos de todos los visitantes contarían como uno solo: el rate limit de D-10-20 pasaría en local y no frenaría nada en producción.

El start command de uvicorn añade `--proxy-headers --forwarded-allow-ips="*"`, tanto en `render.yaml` como en el servicio real del dashboard. Con eso, `request.client.host` es la IP que Render pone en `X-Forwarded-For`.

Se confía en todas las IPs porque el contenedor no es accesible desde fuera de Render; el único camino es su proxy. Si algún día se expone el puerto, hay que restringir `forwarded-allow-ips` a la red de Render. La cabecera es falsificable por el cliente: el rate limit encarece la fuerza bruta, pero la barrera principal sigue siendo el token y la IP no autoriza nada por sí sola.

Verificación: P-10-18 se ejecuta contra uvicorn con proxy headers o contra el servicio publicado, enviando `X-Forwarded-For` distintos. Con `TestClient` no se ejerce el middleware de uvicorn; ahí se inyecta `client` en la petición.

## 7. Automatización

### 7.1 Workflow

`.github/workflows/forecast-refresh.yml`:

```yaml
on:
  schedule:
    - cron: "0 5 * * *"
      timezone: "Europe/Madrid"
    - cron: "0 8 * * *"
      timezone: "Europe/Madrid"
  workflow_dispatch:
    inputs:
      force:
        description: "Ignorar la caché del backend y recalcular"
        type: boolean
        default: false
```

- `permissions: contents: write`.
- `concurrency: { group: forecast-refresh, cancel-in-progress: false }`.
- `timeout-minutes: 30`.
- Secretos: `BACKEND_URL` y `REFRESH_TOKEN`.

### 7.2 Pasos

1. **Checkout** del repositorio.
2. **Guardia de frescura** (solo para ejecuciones programadas): lee `frontend/src/data/forecast-snapshot.json`, calcula si `fecha_objetivo` es mañana en `Europe/Madrid` **y** si `avisos` está vacío, y escribe `skip=true|false` en `$GITHUB_OUTPUT`. Los pasos siguientes llevan `if: steps.guard.outputs.skip != 'true'`. No se compara con el texto del cron: la condición depende del estado del archivo, no de qué expresión lo disparó.
3. **Petición**: `curl --fail-with-body --max-time 1200 -X POST "$BACKEND_URL/api/internal/forecast/refresh"` con el token, guardando la respuesta en `/tmp/refresh.json` y el código HTTP en un archivo.
4. **Diagnóstico**: si el código no es 200, imprime el cuerpo redactado y termina con error.
5. **Validación**: extrae `.snapshot` con `jq` y lo valida con el módulo del frontend:

   ```bash
   node --input-type=module -e "
     import { readFileSync } from 'node:fs';
     import { validateSnapshot } from './frontend/src/utils/forecast.mjs';
     const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid' }).format(new Date());
     const problemas = validateSnapshot(JSON.parse(readFileSync('/tmp/snapshot.json', 'utf8')), hoy);
     if (problemas.length) { console.error(problemas); process.exit(1); }
   "
   ```

   `validateSnapshot` es el mismo módulo que usa la web: una sola definición de «snapshot válido».
6. **Publicación**: copia a `frontend/src/data/forecast-snapshot.json`, `git add`, y hace commit solo si `git diff --cached --quiet` es falso. Mensaje: `data: snapshot de previsión para 2026-11-17`. Autor: `github-actions[bot]`. Push a la rama por defecto.
7. **Resumen**: escribe en `$GITHUB_STEP_SUMMARY` versión, fecha objetivo, duración, avisos y si hubo commit.

### 7.3 Reintento de las 08:00

Existe solo para el caso de que la ejecución de las 05:00 falle o termine con avisos. No crea una segunda versión: la guardia lo detiene si el snapshot ya es el de mañana y está limpio, y la comparación de hash detiene el commit si el contenido es idéntico.

### 7.4 Filtro de compilación de Render

El commit diario toca `frontend/**`. Para que Render no redeploye:

- En el dashboard del servicio `api_ML`: *Settings → Build & Deploy → Build Filters*, incluir `backend/**` y excluir `frontend/**`.
- En `render.yaml`, dejar constancia con `buildFilter.paths: [backend/**]` para que la definición versionada diga la verdad, aunque el servicio actual no esté sincronizado con el blueprint.

Verificación: tras el primer commit automático, el evento de Render no debe registrar un deploy.

## 8. Frontend

### 8.1 Módulo nuevo `frontend/src/utils/forecast.mjs`

Módulo puro, sin DOM y sin red, para que `node --test` lo importe sin transpilar:

| Función | Responsabilidad |
|---|---|
| `todayInMadrid(now = new Date())` | Fecha `YYYY-MM-DD` en `Europe/Madrid` para el instante dado. Es la única función que lee el reloj; las pruebas le pasan un instante fijo. |
| `tomorrowInMadrid(today)` | Suma un día a una fecha `YYYY-MM-DD` sin cruzar husos. |
| `validateSnapshot(snapshot, today)` | Implementa V1–V5 y V7–V12; devuelve `string[]`. V6 queda solo en el backend porque la lista de las 19 variables vive allí. `today` entra como parámetro porque V2, V3 y V7 comparan con la fecha actual. De V12, el frontend comprueba el recuento y el orden; la procedencia real la garantiza el backend. |
| `snapshotStatus(snapshot, today)` | Cuatro estados: `ok` si el objetivo es mañana; `pendiente` si el objetivo es hoy (aún no se ha publicado la de mañana); `caducado` si el objetivo ya pasó; `no_disponible` si el snapshot es ilegible, está incompleto o `n_variables != 19`. Devuelve `motivo`. |
| `generationLabel(snapshot)` | «Datos del 16/11/2026 a las 05:02», en español. |
| `staleMessage(snapshot)` | Texto del aviso cuando el objetivo no es mañana. |

`snapshotStatus` sustituye a `predictionStatus`, que se retira de `evolution.mjs` junto con sus pruebas: validaba la respuesta HTTP que deja de existir. La regla nueva es `fecha_objetivo === mañana`, no `fecha_objetivo >= hoy`.

### 8.2 Consumo del snapshot

- La tarjeta se renderiza en el build desde el snapshot: valor, fechas, familia, variables y estado calculado con la fecha del build. `live-prediction.mjs` solo recalcula el estado con `todayInMadrid()` y actualiza el texto; no rellena las cifras ni hace peticiones. Desaparecen `API_BASE_URL`, `TIMEOUT_MS`, `fetchJson` y el estado `loading`.
- `PredictionChart.astro` importa el JSON en su `<script>` y dibuja con los mismos campos que hoy (`fechas_hist`, `real_gwh`, `pred_gwh`, `vel_norm`, `racha_norm`, `manana`). La nota de frescura se renderiza en build y se recalcula con el mismo `snapshotStatus`.
- Ninguno de los dos hace `fetch`.
- El estado (`ok`, `pendiente`, `caducado`) se recalcula en el navegador con `todayInMadrid()` en cada visita. El HTML trae el estado del build como valor por defecto y el script lo sobrescribe. Sin JavaScript se ve el estado del build —puede estar caducado si el `dist/` es viejo, pero nunca queda un «Cargando…»—. Los datos vienen del build; la comparación de fechas, no. Así un `dist/` de hace tres días avisa sin necesidad de reconstruir.

### 8.3 Archivos que cambian

| Acción | Archivo | Cambio |
|---|---|---|
| Crear | `frontend/src/data/forecast-snapshot.json` | Snapshot inicial sembrado (fase 2). |
| Crear | `frontend/src/utils/forecast.mjs` | Lógica pura de la sección 8.1. |
| Crear | `frontend/tests/forecast.test.mjs` | Pruebas de validación, estado y formatos. |
| Modificar | `frontend/src/utils/live-prediction.mjs` | Solo recalcula el estado en cliente; sin red ni relleno de cifras. |
| Modificar | `frontend/src/components/charts/PredictionChart.astro` | Sin red; datos del snapshot; nota de frescura. |
| Modificar | `frontend/src/components/evolution/LivePredictionStatus.astro` | Renderiza valores y estado en build; copia con `generationLabel`, no «en vivo». |
| Modificar | `frontend/src/pages/index.astro` | Tarjeta renderizada en build; sin «Cargando…» ni aviso de un minuto. |
| Modificar | `frontend/src/pages/resultados.astro` | Ídem. |
| Modificar | `frontend/src/utils/evolution.mjs` | Retirar `predictionStatus`. |
| Modificar | `frontend/tests/evolution.test.mjs` | Retirar las pruebas de `predictionStatus`. |
| Eliminar | `frontend/cron.js` | Cron que nunca se desplegó. |
| Modificar | `frontend/vercel.json` | Sin `crons`. |

`frontend/src/utils/api.ts` no se toca: no lo importa nadie.

### 8.4 Estados y textos

| Situación | Estado | Texto |
|---|---|---|
| `fecha_objetivo` = mañana | `ok` | «Previsión para el 17/11/2026. Datos del 16/11/2026 a las 03:12.» |
| `fecha_objetivo` = hoy (madrugada) | `pendiente` | «La previsión de mañana todavía no se ha publicado. La última disponible es para hoy, 16/11.» Tono informativo, no de error. |
| `fecha_objetivo` anterior | `caducado` | «La previsión publicada es del 14/11 para el 15/11. No hay datos más recientes.» Tono de aviso. |
| Snapshot ilegible o incompleto | `no_disponible` | «No hay una previsión publicada válida. El resto de la página sigue siendo válido.» |

La hora de publicación nunca se escribe a mano: sale de `generationLabel(snapshot)`, que usa `fecha_generacion`. El scheduler de las 03:00 puede generar el snapshot y la llamada de las 05:00 devolverlo como `already_done`; fijar «05:00» en el texto mentiría sobre ese caso.

La tarjeta sigue mostrando valor, fecha objetivo, emisión, familia, variables y viento. La gráfica mantiene su ventana de 30 días completos.

### 8.5 La madrugada es un estado normal

Entre las 00:00 y la primera ejecución correcta del día —las 03:00 si el servicio está despierto, las 05:00 si estaba dormido—, el snapshot más reciente apunta al día en curso. No es un fallo: la previsión de mañana todavía no existe. Por eso ese caso es `pendiente`, con tono informativo y el texto de la tabla anterior. `caducado` queda reservado para cuando la fecha objetivo ya pasó, que sí implica que algo ha fallado.

La distinción evita el peor efecto de un estado único: normalizar un aviso de error que aparece todas las noches. La ventana no tiene una hora fija de fin: depende de cuándo arranca el servicio. Adelantar la ejecución a las 23:30 la reduciría a costa de predecir con previsiones menos frescas.

## 9. Continuidad y errores

### 9.1 La última versión válida siempre está disponible

El archivo del repositorio solo se sustituye cuando el snapshot pasa las validaciones. Si la generación falla, si AEMET cae, si Render no responde o si el workflow se cae a mitad, **el archivo anterior permanece** y la web sigue sirviendo la última previsión con su aviso de antigüedad. No hay estado intermedio posible: un archivo, un commit.

### 9.2 Fallo en el primer arranque

Si `forecast-snapshot.json` no existe, el build de Astro falla. Por eso la fase 2 lo siembra **antes** de que el frontend lo importe. Nunca se despliega código que espere un archivo inexistente.

### 9.3 Datos simulados

`generate_mock_historical` y `_fallback_prediction` no se usan en este camino. Si el histórico real no está, el snapshot no se publica. Es preferible una web con el dato de ayer que una web con un dato inventado.

### 9.4 Ejecuciones simultáneas

Tres barreras: el lock del backend (`409`), el `concurrency` del workflow y la comparación de hash antes del commit.

### 9.5 Render dormido a las 03:00

El scheduler no corre. No pasa nada: el workflow de las 05:00 despierta el servicio con su petición y espera lo que tarde. El visitante no espera nunca.

## 10. Requisitos no funcionales

| Id | Requisito |
|---|---|
| RNF-1 | El navegador no realiza ninguna petición a un dominio de Render. Verificable con `grep -r onrender frontend/dist`. |
| RNF-2 | La primera carga de las gráficas no depende de ningún servicio externo: HTML y JS vienen de Vercel. |
| RNF-3 | El snapshot completo no supera los 120 KB sin comprimir. |
| RNF-4 | El workflow termina en menos de 20 minutos en el caso normal y nunca supera los 30 del `timeout-minutes`. |
| RNF-5 | En el caso normal, la ejecución consume menos de 10 minutos de Actions. El `timeout-minutes: 30` es el corte de seguridad (RNF-4), no el consumo esperado. |
| RNF-6 | El coste mensual añadido es 0 €. |
| RNF-7 | `REFRESH_TOKEN` no aparece en el repositorio, ni en el bundle, ni en los logs. |
| RNF-8 | `include_in_schema=False`: el endpoint no aparece en `/docs` ni en `/openapi.json`, no se anuncia en `/` y no se documenta en la web. |
| RNF-9 | Sin JavaScript se ven los datos y el estado calculado en el build; solo la gráfica de Chart.js lo requiere. |
| RNF-10 | El repositorio crece 50–120 KB al día, es decir, ≤ 50 MB al año contando el histórico de snapshots. |
| RNF-11 | Los textos nuevos están en español y respetan el diseño existente en móvil. |

## 11. Variables de entorno y secretos

| Dónde | Variable | Uso |
|---|---|---|
| Render | `REFRESH_TOKEN` (`sync: false`) | Autentica el endpoint interno. |
| GitHub Actions | `BACKEND_URL` | URL pública del servicio. |
| GitHub Actions | `REFRESH_TOKEN` | Mismo valor que en Render. |
| Vercel | — | No se añade ninguna variable nueva. |

`PUBLIC_API_URL` deja de usarse en los dos puntos de llamada reales. Se conserva en Vercel durante la transición y se retira cuando el build no la referencie.

`backend/.env.example` incorpora `REFRESH_TOKEN=` con un valor vacío y un comentario.

## 12. Casos límite

| Caso | Comportamiento esperado |
|---|---|
| El workflow corre el 29 de febrero. | `tomorrowInMadrid` suma días con `Date.UTC`, no con aritmética de strings. |
| Cambio de hora (marzo y octubre). | `timezone: Europe/Madrid` en el cron; 05:00 y 08:00 no caen en la hora saltada. La validación compara fechas locales, no instantes. |
| GitHub retrasa el cron 20 minutos en hora punta. | El diseño lo tolera: no hay hora límite y el estado `pendiente` cubre la espera. |
| El servicio tarda 12 minutos en arrancar y terminar. | La cadena 10 < 20 < 30 minutos lo cubre; el visitante no lo nota. |
| El snapshot es idéntico al del día anterior. | No hay commit, no hay rebuild. |
| La primera ejecución termina con avisos. | No se cachea; el reintento de las 08:00 vuelve a generar. |
| El repositorio lleva 60 días sin actividad. | Se espera que el commit diario cuente como actividad y lo evite; si aun así se desactiva, el estado `caducado` lo delata. |
| El token se filtra en un log. | `redact_secrets` lo sustituye; los intentos fallidos se registran sin el valor recibido. |
| El JSON se corrompe en el commit. | `validateSnapshot` en el workflow lo impide; si aun así llega, el build falla y Vercel no publica. |

## 13. Criterios de finalización

| Id | Criterio |
|---|---|
| CA-10.1 | Existe `POST /api/internal/forecast/refresh`, protegido, que ejecuta la tarea diaria completa y devuelve el snapshot. |
| CA-10.2 | Sin token o con token incorrecto responde `401`; sin `REFRESH_TOKEN` configurada responde `503`. |
| CA-10.3 | Un snapshot inválido no se devuelve ni se publica. |
| CA-10.4 | El workflow diario publica el snapshot con un commit y Vercel reconstruye. |
| CA-10.5 | El workflow manual funciona y admite `force`. |
| CA-10.6 | La web no hace ninguna petición a Render. |
| CA-10.7 | Con Render dormido, la web carga las gráficas con normalidad. |
| CA-10.8 | Si la ejecución falla, la web conserva el snapshot anterior y lo señala como caducado. |
| CA-10.9 | La fecha de generación y la fecha objetivo se muestran siempre. |
| CA-10.10 | El estado distingue `pendiente` (objetivo = hoy) de `caducado` (objetivo ya pasado). |
| CA-10.11 | No se añaden dependencias ni servicios. |
| CA-10.12 | `npm run build` pasa con 0 errores y `node --test` en verde. |
| CA-10.13 | El cron muerto de Vercel ha desaparecido. |
| CA-10.14 | El commit diario no dispara un despliegue de Render. |
| CA-10.15 | El estado se recalcula en el navegador: un `dist/` viejo avisa sin reconstruir. |
| CA-10.16 | La cadena de tiempos es 10 < 20 < 30 minutos. |
| CA-10.17 | Una ejecución con avisos no se cachea y se reintenta. |

## 14. Pruebas de aceptación

| Id | Prueba | Resultado esperado |
|---|---|---|
| P-10-1 | `curl -X POST` sin cabecera | `401` |
| P-10-2 | `curl` con token incorrecto | `401` |
| P-10-3 | Arrancar sin `REFRESH_TOKEN` y llamar | `503`, sin ejecución |
| P-10-4 | Llamada correcta con el servicio dormido | `200` en menos de 20 min, snapshot válido |
| P-10-5 | Repetir la llamada sin `force` | `already_done` con el mismo snapshot |
| P-10-6 | Repetir con `force=true` | `actualizado` |
| P-10-7 | Dos llamadas simultáneas | Una `200` y una `409` |
| P-10-8 | Forzar un fallo de REE | `502`, sin snapshot |
| P-10-9 | Ejecutar el workflow manualmente | Commit y rebuild |
| P-10-10 | Ejecutar el workflow dos veces el mismo día | Un solo commit |
| P-10-11 | `grep -r onrender frontend/dist` | Sin resultados |
| P-10-12 | Bloquear Render y navegar | Las tres páginas cargan |
| P-10-13 | Retrasar el snapshot un día | Aviso de caducidad visible |
| P-10-14 | `git revert` del commit de datos | La web vuelve al snapshot anterior |
| P-10-15 | Revisar el bundle y los logs | Sin token, sin claves |
| P-10-16 | Commit automático | Render no despliega |
| P-10-17 | Abrir un `dist/` de hace dos días | El estado pasa a `caducado` sin reconstruir |
| P-10-18 | Seis intentos con token incorrecto en un minuto, desde la misma IP | `429` en el sexto; una séptima desde otra IP sigue dando `401` |
| P-10-19 | Ejecución con un aviso y llamada posterior | Recalcula en vez de `already_done` |
| P-10-20 | Cron de las 05:00 retrasado 20 minutos | Se ejecuta igual y publica |

## 15. Fuera de alcance

- Reentrenar el modelo o cambiar `FEATURE_COLS`.
- Añadir demanda, precios o cualquier payload que no exista hoy.
- Rediseñar la web de la spec 009.
- Sustituir SQLite por una base persistente.
- Pagar Render Starter.
- Mantener una segunda fuente de datos en paralelo.

## 16. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La spec 008 no está liberada y el contrato sigue en 16 variables. | V4 rechaza todos los snapshots y no hay publicación. | Requisito previo obligatorio: liberar la 008 en `main` antes de sembrar. |
| El backfill AEMET del arranque tarda más que la espera. | Predicción sin observaciones y fallo de validación. | Espera de 10 min, aviso en la respuesta y reintento a las 08:00. |
| AEMET limita por tasa (429). | Captura parcial o fallida. | Ya existe reintento en la tarea; si no basta, la validación impide publicar un dato incompleto. |
| Render tarda más de 20 min en frío. | El workflow falla. | Reintento a las 08:00 y `timeout-minutes: 30`. |
| El workflow se desactiva por inactividad. | Deja de actualizarse. | Se espera que el commit diario cuente como actividad. Si no basta, el `caducado` lo hace visible y se reactiva a mano. |
| El repositorio crece sin control. | Clon más lento con los años. | ≤ 50 MB/año (RNF-10); se puede podar el histórico de datos si algún día molesta. |
| Se publica una previsión con `origenes` estimados. | Calidad del dato. | Se muestran en `prediccion.origenes`; la web no los oculta. |
| El push del bot no dispara el build de Vercel. | El snapshot se commitea pero la web no se actualiza. | Comprobar el primer commit automático (CA-10.4); si Vercel ignora los pushes del bot, usar un PAT fine-grained solo para el push. |
| GitHub retrasa el cron en hora punta. | La publicación llega más tarde de las 05:00. | Sin hora límite y con `pendiente` cubriendo la espera. |
| El start command del dashboard no incorpora `--proxy-headers`. | El rate limit cuenta todos los intentos como una sola IP y no frena nada. | Comprobarlo con P-10-18 desde dos IPs en el primer despliegue; `render.yaml` deja el comando escrito. |

## 17. Requisitos previos y orden de implementación

**Requisitos previos (bloqueantes):**

1. Liberar la spec 008 en `main`: contrato de 19 variables con `fecha_emision` y `n_variables`.
2. Fusionar `SDD` en `main`: el workflow programado solo corre en la rama por defecto y Render despliega desde `main`.
3. Configurar el filtro de compilación de Render (7.4).

**Fases:**

1. **Backend.** `forecast_cache.py`, el refactor de `charts.py`, el endpoint interno, el evento de backfill y el cambio del job de las 03:00.
2. **Sembrar.** Desplegar el backend en `main`, llamar una vez a `POST /api/internal/forecast/refresh?force=true` y guardar el `.snapshot` devuelto como `frontend/src/data/forecast-snapshot.json`. Es el estado inicial y la prueba de que el contrato de 19 variables encaja en producción.
3. **Lógica del frontend.** `forecast.mjs` y sus pruebas. Va antes que el workflow porque la validación previa al commit usa el mismo módulo.
4. **Automatización.** Workflow, secretos, guardia de las 08:00 y primer commit automático.
5. **Integración del frontend.** Sustitución de las tres llamadas, textos de estado y retirada del cron muerto.
6. **Verificación.** P-10-1 a P-10-20, con Render dormido incluido.

Cada fase se verifica antes de pasar a la siguiente; ninguna se despliega si la anterior no está en verde.


