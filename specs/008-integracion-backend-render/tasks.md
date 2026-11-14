# Tareas 008 — Integrar el pipeline de producción en Render

Derivadas de `spec.md` y `plan.md`. **Todas están pendientes**; esta spec no ha
implementado ni desplegado cambios.

## Bloque A — Pruebas primero

- [ ] **T-01 — Contrato del modelo** (RF-1; CA-1.1–1.5)
  - Verificar el artefacto, familia, escalador, hash y lista ordenada de 19
    variables.
  - Probar que una carga incompatible no usa fallback y `/health` responde 503.

- [ ] **T-02 — Esquema, snapshot y rollback** (RF-2; CA-2.1–2.8)
  - Probar esquema canónico, migración/activación controlada, integridad y
    restauración ante error.
  - Generar el manifiesto SHA/esquema/recuentos desde la instantánea y comparar
    la BD local y la copia Render con ese manifiesto.
  - Verificar que no se crean ni consultan las tablas heredadas.

- [ ] **T-03 — Capturas AEMET y REE** (RF-3; CA-3.1–3.9)
  - Simular respuestas AEMET/ESIOS, `429`, fallos parciales y recapturas.
  - Comprobar estaciones, columnas, elaboración, unidad, claves idempotentes y
    que REE no reconstruye su histórico en cada ejecución programada.

## Bloque B — Construcción y persistencia

- [ ] **T-04 — Vector de 19 variables y orígenes** (RF-4; CA-4.1–4.8)
  - Probar reglas temporales, datos mixtos, previsión REE, generación completa
    y ausencia de valores, incluida la alineación diaria en `Europe/Madrid`.
  - Comparar resultados con fixtures derivados del comportamiento vigente en
    `src/pipeline/`; no modificar `src/`.

- [ ] **T-05 — Predicción propia y reales** (RF-5; CA-5.1–5.4)
  - Probar upsert por objetivo/día, retención del real, signo del error y
    rechazo de generación incompleta.

- [ ] **T-06 — Scheduler** (RF-3/RF-5; CA-3.7–3.9, 5.1–5.4)
  - Verificar orden a las 03:00, reintento a las 09:00, reemisión idempotente
    y logs ante fallos.

## Bloque C — API y Render

- [ ] **T-07 — API de predicción** (RF-6; CA-6.1–6.8)
  - Mantener los contratos acordados; probar el 503 estructurado, conservar la
    fila previa ante un refresh fallido y añadir vector/orígenes/REE.
  - Verificar las filas históricas y actuales de `/api/model-comparison` y la
    alineación de `pred_gwh` con todas las emisiones trazables. Versionar la
    copia del acta `familia_como_modelo.json` junto al artefacto.

- [ ] **T-08 — Configuración y release** (RF-7; CA-7.1–7.5)
  - Corregir rutas persistentes y `healthCheckPath`; pausar escritores,
    respaldar BD y modelo fuera
    de las rutas activas, validar e instalar la instantánea con activación
    atómica. Conservar los respaldos hasta autorización explícita de borrado.
  - No ejecutar la migración en cada startup.

- [ ] **T-09 — Puertas y smoke tests** (RNF-1–RNF-10; criterios 1–9)
  - `node --test backend/tests/` y `node --test` completo del repositorio.
  - Comprobar integridad, hashes, backups y API local; health/API de Render
    solo después de autorizar el release y confirmar el rollback.

- [ ] **T-10 — Cierre documental**
  - Actualizar `MEMORY.md`, documentar huellas y resultado de la migración.
  - Confirmar que no hay cambios en `src/` ni frontend y que no se añadieron
    dependencias ni se reentrenó.
