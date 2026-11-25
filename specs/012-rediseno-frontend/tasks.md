# Tareas — Spec 012

- [x] **T-12-1 — Spec.** `spec.md` con decisiones, criterios y riesgos.
- [x] **T-12-2 — Tokens y tema.** Variables CSS, selector en cabecera, persistencia y script anti-parpadeo.
  - Hecho cuando: CA-2 y CA-5.
- [x] **T-12-3 — Navegación, pie y base.** Cabecera responsive con selector, pie con web/GitHub/LinkedIn, imagen OG.
- [x] **T-12-4 — Inicio.** Hero con tarjeta de estados (D-12-5), bloques de resultados y proceso.
- [x] **T-12-5 — Resultados.** Gráfica interactiva de 30 días y tarjetas de modelos a ancho completo, con Chart.js.
  - Hecho cuando: CA-3 y CA-6.
- [x] **T-12-6 — Proceso.** EDA didáctico, importancia de variables, mapa de referencia, SDD y specs en acordeón.
- [x] **T-12-7 — Mejoras.** Hoja de ruta con specs relacionadas (D-12-8).
- [x] **T-12-8 — Verificación.** Tres anchos, ambos temas, `node --test`, `npm run build`.
- [x] **T-12-9 — Cierre.** Revisar la tarjeta de Mejoras (D-12-9), `MEMORY.md`.
  - Resultado: la tarjeta de Mejoras enlaza a la spec 012 y dice «gráficas interactivas con Chart.js». `MEMORY.md` actualizado.

## Resultado de la verificación (25/11/2026)

- `node --test`: 47/47. `npm run build` (incluye `astro check`): 0 errores.
- Revisión en navegador: Inicio, Resultados, Proceso y Mejoras en oscuro y claro; sin desbordamiento horizontal a 375 px.
- Sin comprobar: ancho de tableta (~820 px) y despliegue en Vercel.
- `og:image` es una ruta relativa (`/og.png`): hasta corregir `site` en `astro.config.mjs`, algunas redes no la resolverán.
