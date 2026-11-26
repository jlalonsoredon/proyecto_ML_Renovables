# Product

## Platform

web

## Stack

Astro 5 + Tailwind 3 + Chart.js + Leaflet (TypeScript), desplegado en Vercel. Backend FastAPI en Render. Datos y modelo en Python 3.11 con Jupyter (`src/notebooks/main.ipynb`).

## Users

Público principal: evaluadores y reclutadores que revisan el proyecto final del bootcamp de Data Science de KeepCoding como portfolio (confirmado por el autor el 26/11/2026). Llegan a la web para juzgar en pocos minutos el método, los datos y la calidad del resultado. Leen en escritorio y en móvil.

## Product Purpose

Mostrar cada día la predicción de la generación eólica peninsular del día siguiente, en MWh, y explicar cómo se obtiene: datos oficiales de REE y AEMET, análisis exploratorio, variables, comparación de modelos y evolución del proyecto por specs (SDD).

## Positioning

Proyecto de Machine Learning de extremo a extremo y honesto con sus límites: cifras con su protocolo de medida, estados explícitos cuando no hay predicción y nada de datos inventados para rellenar.

## Operating Context

Visita breve de evaluación. Las páginas son Inicio, Resultados, Proceso y Mejoras. La predicción se publica una vez al día desde un snapshot versionado (spec 010); si falta un dato, la tarjeta muestra «no disponible» y no se publica ninguna cifra.

## Capabilities and Constraints

- Las cifras de la web salen del notebook o de los JSON versionados del frontend; nunca se escriben a mano.
- Las métricas se muestran con el periodo y el número de variables con que se midieron; experimentos distintos no se restan.
- Constitución del proyecto (`docs/constitution.md`): desarrollo primero en `src/`, la spec activa manda, lógica pura probada con `node --test` e interfaz en español.

## Brand Commitments

Confirmado por el autor el 26/11/2026: se mantiene el estilo actual. Tema oscuro por defecto con selector claro persistente, verde como acento, Space Grotesk para títulos e Inter para el texto. Detalle en `DESIGN.md`.

## Evidence on Hand

- Métricas del modelo vigente (Linear Regression, 19 variables): R² 0,9308 y RMSE 23.108,4 MWh en un test de 354 días.
- Datos de REE y AEMET desde enero de 2022; snapshot diario de la previsión en `frontend/src/data/forecast-snapshot.json`.
- Diez specs documentadas (`specs/`), con su línea de tiempo en `frontend/src/data/spec-timeline.json`.

## Product Principles

1. La cifra de mañana primero; el método, a un clic.
2. Didáctico para quien no es técnico, riguroso para quien lo es: cada término técnico se explica.
3. Ninguna cifra sin fuente ni protocolo; ningún hueco relleno con datos simulados.
4. Las gráficas se exploran: series que se ocultan, valores bajo el cursor y tabla de datos.

## Accessibility & Inclusion

Contraste AA (≥ 4,5:1) en los dos temas, objetivos táctiles de 44 px, gráficas con tabla de datos y alternativa textual, foco visible, respeto de `prefers-reduced-motion` y composición sin desplazamiento horizontal desde 375 px.
