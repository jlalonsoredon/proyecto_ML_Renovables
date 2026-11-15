# MEMORY.md — Aero Predictor

Memoria del proyecto entre sesiones; mantenerla en torno a 50 líneas.

## Estado actual
- Specs 001–007 portan el análisis a `src/`; la spec activa 008 integra ese comportamiento en el backend sin modificar `src/` ni frontend.
- Spec 008 está implementada y probada localmente. El volumen vivo de Render no se ha pausado ni actualizado; ver `specs/008-integracion-backend-render/tasks.md`.
- Artefacto backend: Linear Regression + StandardScaler, 19 variables, `usa_scaler=True`; SHA-256 `e915381e2c24fcfbc2a81ab6eca2fdede7c7729f1abe2f79e58491cf9647c702`.
- Acta `backend/modelos/familia_como_modelo.json`: SHA-256 `a9413d313b36ee0f8868baac3a82eb52e8580a8f3d36e613a52de6e6b901cff0`.
- BD local instalada desde `src/data/ree_generacion.db`: 10.669 `generacion`, 30.544 `aemet_diario`, 2.900 `prediccion_diaria`, 8 `prediccion_propia`; `PRAGMA integrity_check=ok`.
- Manifiesto de datos: tablas `generacion=374a4766…`, `aemet_diario=6af3c63f…`, `prediccion_diaria=0eba7fd5…`, `prediccion_propia=c2d30409…`; las huellas completas están en `backup-008/final-backend/manifest.json`.
- Backups externos conservados en `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-008/`: estado previo (incluye LR-16 y sidecars) y `final-backend/` (BD previa a la sustitución, LR-19/acta y manifiesto). No borrar sin autorización.
- `render.yaml` usa rutas persistentes absolutas y `/health`; no se ejecutó migración al arrancar ni se hizo deploy.
- API: sin fallback de predicción; falta de datos/modelo produce 503. Gráfica de solo lectura, alineada a emisiones guardadas y sin valor de relleno.
- Suite dirigida backend: 33/33 tests pasan. Smoke HTTP local: health 200; prediction/refresh 503 con BD vacía; forecast/chart/comparison 200.
- `node --test` global: 48/49 pasan; falla el gate Python preexistente de `src/pipeline/tests/gate.test.mjs` (`ENOBUFS`). Se mantuvo `src/notebooks/main.ipynb` intacto; una clave AEMET en salidas requiere rotación/limpieza autorizada aparte.
- El artefacto avisa que se serializó con scikit-learn 1.8 frente al pin 1.5.0 de `backend/requirements.txt`; cargó en pruebas locales, pero confirmar compatibilidad antes del release. No se cambió ninguna dependencia.
- No se reentrenó el modelo ni se modificó `src/`, frontend o `backend/requirements.txt`.

## Contrato de dominio
- Objetivo: generación eólica diaria peninsular (MWh), predicción D+1. Orden LR-19 en `backend/app/services/model_loader.py` y `prediction_features.py`.
- Scheduler: captura y emisión a las 03:00; reintento AEMET a las 09:00, `Europe/Madrid`; nunca reentrena.
- ESIOS 1777: `REE_API_KEY`, `x-api-key`, objetivo local y `values_updated_at` declarado; no reconstruir histórico en la tarea diaria.
- AEMET: API de dos pasos y reintento 429; viento de previsión en km/h se convierte a m/s. Observación REE se agrega por fecha de `Europe/Madrid`.
- Borja y La Muela comparten `9299X`; no añadir `9299` (indicativo inválido) ni duplicar Tarazona.
- Evitar `get_historical_data()` para construir series diarias mezcladas; usar `get_generation_series()`.

## Próximos pasos
- Con autorización operativa, pausar escritores de Render, ejecutar migrador con backup externo, verificar hashes/health/API y conservar backup hasta confirmar rollback.
- Resolver con el usuario la compatibilidad de scikit-learn antes de desplegar; no actualizar dependencias por cuenta propia.
- Rotar la clave AEMET y retirar cualquier salida sensible en una tarea autorizada; no editar `main.ipynb` sin permiso.
