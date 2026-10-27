# MEMORY.md — Aero Predictor

Memoria del proyecto entre sesiones. Máximo ~50 líneas: resume o elimina lo que ya no aporte.

## Estado actual
- Modelo de producción: **LinearRegression + StandardScaler** (`modelos/lr_eolica.joblib`, dict `{modelo, scaler, features}`).
- Test (2025-08-02 → 2026-06-23, 326 días): **RMSE 59.150,8 MWh · R² 0,5931 · MAPE 40,82 % · Accuracy 43,6 %**.
- Backend FastAPI en Render; frontend Astro en Vercel; scheduler diario a las 3:00 (Europe/Madrid).
- Datos: eólica diaria peninsular 2021-12-31 → 2026-06-24; AEMET 14 estaciones 2022-01-01 → 2026-06-23.
- El scheduler descarga datos y predice, pero **no reentrena** el modelo.

## Decisiones (y por qué)
- **Target diario** (no semanal): el notebook entrena con serie diaria; `src/memoria.ipynb` aún menciona "semanal" y debe corregirse.
- **LinearRegression** como modelo de producción por interpretabilidad; boosting y SARIMAX no mejoran.
- **Interpolación lineal** para huecos de viento (mejor RMSE en la mayoría de estaciones).
- **Solo eólica**: solar e hidráulica se descartaron por falta de datos fiables (insolación / caudal de cuenca).

## Aprendizajes y errores a evitar
- `9299X` está duplicado (Borja y La Muela) y `"9299"` es inválido → se duplica Tarazona en la media.
- `get_historical_data()` mezcla formatos de fecha; usar `SUBSTR(datetime, 1, 10)`.
- Métricas de `charts.py`/README desactualizadas frente a las reales; `metrics.json` no existe.
- Fallbacks/mock (150.000 MWh) pueden enmascarar fallos; revisar `avisos`.
- REE CCAA solo da **mensual/anual**; `time_trunc=day` con `geo_limit=ccaa` falla.
- AEMET: dos pasos + rate limit; viento en km/h.
- No tocar `FEATURE_COLS` sin reentrenar y sincronizar notebook/backend.

## Próximos pasos
- Unificar feature engineering notebook ↔ `model_loader` y añadir reentrenamiento programado.
- Corregir duplicado `9299X` y métricas hardcodeadas.
- Integrar previsiones ESIOS (541 eólica, 542/543/10034 solar, PBF 12/13, 460 demanda).
- Usar la eólica mensual por CCAA como pesos/estructura (no como target).
- Actualizar README y memoria; mover claves a `.env`.
