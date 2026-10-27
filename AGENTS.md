# AGENTS.md — Aero Predictor

Proyecto de captación y análisis de datos de **REE** y **AEMET** (fuentes oficiales) para predecir la **generación eólica diaria peninsular del día siguiente**. Incluye notebook de ML, backend FastAPI (Render) y frontend Astro (Vercel).

## Stack y estructura

- **Datos y modelo:** Python 3.11 + Jupyter. Notebook principal `src/notebooks/main.ipynb` (81 celdas).
- **Backend:** FastAPI + APScheduler, Python 3.11.9 (`backend/runtime.txt`), desplegado en **Render** (`render.yaml`).
- **Frontend:** Astro 5 + Tailwind 3 + Chart.js + Leaflet, TypeScript, Node 20.11.0, desplegado en **Vercel** (`frontend/vercel.json`).
- **Persistencia:** SQLite (`backend/data/ree_generacion.db`).
- **Modelo:** `joblib` en `modelos/lr_eolica.joblib`.

```
.
├── src/
│   ├── notebooks/main.ipynb   # descarga, EDA, interpolación, features, entrenamiento y serialización
│   ├── memoria.ipynb          # memoria del proyecto
│   ├── data/                  # BD de análisis, JSONs de gráficos, ERA5 .nc, copia del modelo
│   └── model/production/      # copia del modelo
├── backend/
│   ├── app/main.py            # FastAPI + lifespan + scheduler (3:00 Europe/Madrid)
│   ├── app/api/               # prediction.py, charts.py
│   ├── app/services/          # ree_client, aemet_client, db_ree, model_loader
│   ├── app/tasks/scheduler.py # tarea diaria (sin reentrenamiento)
│   ├── data/ree_generacion.db # BD usada por el backend (DB_PATH)
│   ├── modelos/               # copia del modelo
│   ├── run_scheduler.py       # scheduler en proceso aparte
│   └── requirements.txt
├── frontend/
│   ├── src/pages/             # index, resultados, proceso, mejoras
│   ├── src/components/        # charts, shared, sections
│   ├── src/utils/api.ts       # cliente de la API
│   ├── cron.js                # cron de Vercel → POST /api/prediction/refresh
│   └── package.json
├── modelos/lr_eolica.joblib
├── render.yaml
└── .env
```

## Comandos

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000
python run_scheduler.py                # scheduler standalone
curl http://localhost:8000/health
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # astro dev --host
npm run build      # astro check && astro build (falla si hay errores de tipos)
npm run preview
```

### Notebook
```bash
jupyter notebook src/notebooks/main.ipynb
# Ejecutar de arriba a abajo: descarga datos, entrena y escribe el .joblib
```

> No hay tests automatizados ni linter configurados. La verificación es levantar el backend, compilar el frontend y, si se toca el modelo, ejecutar el notebook.

## API (backend)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | info + lista de endpoints |
| GET | `/health` | healthcheck |
| GET | `/api/prediction` | predicción de mañana (reutiliza la guardada si es de mañana) |
| POST | `/api/prediction/refresh` | recalcula y guarda la predicción |
| GET | `/api/forecast` | forecast agregado de AEMET |
| GET | `/api/historical?days=30` | histórico eólica/solar/hidráulica |
| GET | `/api/energy-mix` | mix del día |
| GET | `/api/model-comparison` | métricas de modelos |
| GET | `/api/feature-importance` | importancia de features |
| GET | `/api/wind-parks` | parques + estaciones |
| GET | `/api/prediction-chart` | serie real + predicción + viento normalizado |

## Configuración

- Backend: `AEMET_API_KEY`, `REE_API_KEY`, `DB_PATH` (`data/ree_generacion.db`), `MODEL_PATH` (`modelos/lr_eolica.joblib`). Ver `backend/.env.example`.
- Frontend: `PUBLIC_API_URL` (por defecto `http://localhost:8000`). Ver `frontend/.env.example`.
- Nunca commitear `.env` ni claves.

## Convenciones

- Textos de interfaz y comentarios en **español**.
- Código simple, nombres descriptivos, comentarios solo donde aporten.
- Diseño limpio y responsive; toda pantalla nueva debe verse bien en móvil.
- Mantener el estilo de los archivos existentes (`backend/app/services/*.py`, `frontend/src/pages/*.astro`).
- Fechas en SQLite: `generacion.datetime` en ISO (`YYYY-MM-DDTHH:MM:SSZ`); `aemet_diario.fecha` en `YYYY-MM-DD`.

## Comandos
- Tests: `node --test`

## Reglas
- Lee `docs/constitution.md` y la spec activa (`specs/NNN-*/`) antes de tocar código. 

## Reglas de dominio / trampas conocidas

- **Objetivo:** generación eólica **diaria peninsular** (MWh). Modelo de producción: **LinearRegression + StandardScaler**, guardado como dict `{modelo, scaler, features}`.
- **Features (16):** `velmedia`, `racha`, `mes`, `dia_semana`, `dia_año`, `eolica_lag1/2/3/7`, `vel_ma3/7/14`, `racha_ma3/7/14`, `eolica_ma7`. Deben coincidir entre el notebook y `model_loader.FEATURE_COLS`.
- **Estación duplicada:** Borja y La Muela usan el mismo indicativo `9299X` (TARAZONA) y `_ESTACIONES_EOLICAS` incluye además `"9299"` (inválido). La media nacional de viento duplica Tarazona.
- **Fechas mezcladas:** no usar `db_ree.get_historical_data()` para series diarias (mezcla ISO y `YYYY-MM-DD`). Usar `_get_historico_eolica()` o `SUBSTR(datetime, 1, 10)`.
- **Métricas reales** (test, Linear Regression): RMSE **59.150,8 MWh**, MAE 45.986,5, **R² 0,5931**, MAPE 40,82 %, Accuracy 43,6 %. Las de `charts.py` (60.432,9 / 0,579) y el README están desactualizadas; `METRICS_PATH` (`modelos/metrics.json`) no existe.
- **Fallbacks silenciosos:** `generate_mock_historical`, `get_mock_energy_mix`, `_fallback_prediction` y el valor 150.000 MWh pueden ocultar fallos. Revisar los `avisos` de `/api/prediction-chart`.
- **Modelo estático:** el scheduler diario descarga datos y predice, pero **no reentrena**. El `.joblib` está duplicado en 4 rutas; actualizar la copia que apunta `MODEL_PATH`.
- **AEMET:** viento en **km/h** → convertir a m/s. API de dos pasos (meta-URL → datos) y con rate limit (429).
- **REE:** `estructura-generacion` con `geo_limit=peninsular&geo_ids=8741` da **diario**. Con `geo_limit=ccaa` **solo** funciona `time_trunc=month`/`year`; `day` devuelve 500/502 y la API ancla a meses naturales.
- **Datos:** `generacion` (6 tecnologías renovables, 2021-12-31 → 2026-06-24) y `aemet_diario` (14 estaciones, 2022-01-01 → 2026-06-23). Las BD de `src/` y `backend/` **no están sincronizadas** (9.822 vs 9.684 filas).
- **CORS:** `allow_origins=["*"]` con credenciales; no asumir seguridad.
- **Frontend:** `astro.config.mjs` conserva el `site` del template y `cron.js` tiene la URL de Render hardcodeada.

## Forma de trabajar

- Cambios pequeños y verificables; explicar al terminar qué se tocó y cómo se probó.
- Planificar antes de tocar el pipeline o el esquema de datos.
- Preguntar antes de: añadir dependencias, crear archivos nuevos, cambiar el formato de datos/BD o el contrato de la API.
- Actualizar `MEMORY.md` al terminar cada tarea.

## Límites

- ✅ **Siempre:** leer el código antes de cambiarlo; mantener notebook y backend sincronizados; actualizar `MEMORY.md`.
- ⚠️ **Pregunta antes:** dependencias, archivos nuevos, cambios de esquema/contrato y reentrenamientos que sobrescriban el modelo de producción.
- 🚫 **Nunca:** commitear `.env` o claves; borrar/sobrescribir las BD versionadas sin copia; cambiar `FEATURE_COLS` sin reentrenar y actualizar el `.joblib`; exponer la API key en notebooks.

## Verificación

1. **Backend:** `uvicorn app.main:app --reload` y comprobar `/health`, `/api/prediction` y `/api/prediction-chart`.
2. **Frontend:** `npm run build` (incluye `astro check`) y `npm run dev`.
3. **Modelo:** ejecutar el notebook o las celdas afectadas y comprobar que el `.joblib` guarda `modelo`, `scaler` y `features` coherentes con `FEATURE_COLS`.
