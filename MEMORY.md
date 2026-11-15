# MEMORY.md — Aero Predictor

Memoria del proyecto entre sesiones; mantenerla en torno a 50 líneas.

## Estado actual
- Specs 001–007 portan el análisis a `src/`; la spec activa 008 integra ese comportamiento en el backend sin modificar `src/` ni frontend.
- Spec 008 está implementada y probada localmente. El volumen vivo de Render no se ha pausado ni actualizado; ver `specs/008-integracion-backend-render/tasks.md`.
- Artefacto backend: Linear Regression + StandardScaler, 19 variables, `usa_scaler=True`; SHA-256 `e915381e2c24fcfbc2a81ab6eca2fdede7c7729f1abe2f79e58491cf9647c702`.
- Acta `backend/modelos/familia_como_modelo.json`: SHA-256 `a9413d313b36ee0f8868baac3a82eb52e8580a8f3d36e613a52de6e6b901cff0`.
- BD del backend sincronizada el 2026-11-15 desde una instantánea consistente de `src/data/ree_generacion.db`: 10.675 `generacion`, 30.554 `aemet_diario`, 2.985 `prediccion_diaria`, 9 `prediccion_propia`; `PRAGMA integrity_check=ok` y hashes idénticos al origen en las cuatro tablas.
- Manifiesto de la sincronización: tablas `generacion=3a25d373…`, `aemet_diario=6fb5c04b…`, `prediccion_diaria=85aea754…`, `prediccion_propia=3a595135…`; huellas completas y `target_before` en `backup-sync-20261115-115557/manifest.json`.
- Backups externos: `C:/Users/jlalo/AppData/Local/Temp/opencode/backup-sync-20261115-115557/` (BD previa del backend + instantánea de `src`) y `backup-008/` (estado previo y `final-backend/`). No borrar sin autorización.
- `render.yaml` usa rutas persistentes absolutas y `/health`; no se ejecutó migración al arrancar ni se hizo deploy.
- API: sin fallback de predicción; falta de datos/modelo produce 503. Gráfica de solo lectura, alineada a emisiones guardadas y sin valor de relleno.
- Suite dirigida backend: 32/33 tras la sincronización. El único fallo es `el artefacto backend coincide con LR-19…`, porque el kernel de Jupyter reentrenó `src/data/modelos/lr_eolica.joblib` (`cf7d9f65…`); el artefacto promovido (`e915381e…`) sigue intacto en `backend/modelos/` y en `src/data/modelos/lr_eolica-previo-20261115.joblib`. Los 32 tests de datos, contrato, persistencia y seguridad pasan.
- Smoke HTTP con `cwd=backend` y tareas de fondo desactivadas: `/health` 200; `/api/prediction` 200, pero recalcula en vez de reutilizar la fila de `src` porque `src` guarda `modelo='Linear Regression (19 variables)'` y el backend valida `'Linear Regression'`; al compartir PK (`fecha_objetivo`, `fecha_emision`) la sobrescribe. La fila se restauró desde la instantánea y los hashes vuelven a coincidir.
- `node --test` global: 48/49 pasan; falla el gate Python preexistente de `src/pipeline/tests/gate.test.mjs` (`ENOBUFS`).
- Seguridad: `backend/app/services/redaction.py` sanea claves en logs/errores AEMET/REE; la celda 98 del notebook ya no imprime la URL con `api_key` y sus 9 salidas filtradas se sustituyeron por `[REDACTADO]`. El test `test_las_salidas_del_notebook_no_exponen_claves_de_api` pasa.
- La clave AEMET antigua sigue en el historial Git (no en el árbol de trabajo); hay que rotarla y, con autorización, purgar el historial. `.render_api_key` está ignorado y no versionado.
- El artefacto avisa que se serializó con scikit-learn 1.8 frente al pin 1.5.0 de `backend/requirements.txt`; cargó en pruebas locales, pero confirmar compatibilidad antes del release. No se cambió ninguna dependencia.
- No se reentrenó el modelo ni se modificó frontend, `backend/requirements.txt` o la lógica de predicción. En `src/` solo se tocó la celda 98 del notebook para redactar la salida y sanear el mensaje de error.
- La celda temporal de exportación de predicciones para la spec 009 depende del estado creado por el split temporal y el ranking de PASO 5/6 (`test`, `y_test`, `COLUMNAS_MODELO`, `df_resultados`, `predicciones`); si el kernel se reinicia, hay que ejecutar las celdas anteriores en orden antes de exportar.
- Frontend local (2026-11-15): Node 26.13.1 LTS vía winget, `npm ci` (464 paquetes) y `frontend/.env` con `PUBLIC_API_URL=http://localhost:8000`; `npm run build` OK y las 4 páginas + 7 endpoints responden 200 con los gráficos dibujados. Persiste un `SyntaxError` de consola en `PredictionChart.astro` (`<script define:vars>` con `import`), que no rompe el gráfico; `/api/prediction` sobrescribe la fila de `src` por la etiqueta `modelo`.
- El backend arranca en modo WAL: `backend/data/ree_generacion.db` aparece como `M` y crea `-wal`/`-shm` aunque el contenido lógico de las cuatro tablas coincide con `src`; la instantánea exacta de HEAD está en `backup-sync-20261115-115557/`.

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
- Rotar la clave AEMET expuesta y, con autorización, purgar el historial Git; la redacción ya está aplicada, pero el notebook abierto en Jupyter puede sobrescribirla si se guarda desde el navegador.
- Coordinar el kernel de Jupyter que mantiene abierto `src/data/ree_generacion.db` (WAL/SHM modificados) y reentrena artefactos en `src/data/modelos` (`lr_eolica.joblib` nuevo y `lr_eolica-previo-20261115.joblib`); no revertir esos datos sin autorización.
- Decidir con el usuario si se unifica la etiqueta `modelo` de `src` con la del backend (`"Linear Regression"`) para que `/api/prediction` reutilice la predicción guardada en vez de recalcularla y sobrescribirla.
- Spec 009 (`specs/009-actualización-frontend/`) redactada el 2026-11-15: recorrido de las 9 specs al final de `/proceso`, comparación con protocolo visible y sin % de mejora entre experimentos, histórico congelado + estado actual en vivo, y puesta al día de los datos de las gráficas. Incluye `metrics-iniciales.md` con lo que mostraba la web antes. Tras revisión QA (52 hallazgos, 13 preguntas) quedó cerrada con 22 decisiones: referencia = LR-19 local (23.108,4 / 0,9308), línea base = tabla de `/proceso` (60.433 / 0,579), día completo heredado de la 008, 30 días retrocediendo, línea de tiempo desplegable, 4 categorías, bloque en vivo que declara la versión recibida (producción sigue en 16 variables: 106.432 MWh para 2026-11-16) y pruebas `node --test` de la lógica pura. Pendiente de plan.
