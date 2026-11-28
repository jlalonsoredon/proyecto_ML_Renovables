---
name: AeroPredictor
description: Predicción diaria de la generación eólica peninsular con Machine Learning
colors:
  night-ground: "#0A120E"
  night-surface: "#101A15"
  night-surface-raised: "#16231C"
  night-ink: "#E9F3ED"
  night-muted: "#9DB5A8"
  wind-green: "#5BE08B"
  wind-green-ink: "#052012"
  day-ground: "#F3F7F4"
  day-surface: "#FFFFFF"
  day-surface-raised: "#E8F0EB"
  day-ink: "#0C1A13"
  day-muted: "#465B50"
  wind-green-day: "#14783A"
  sun-amber: "#F2B84B"
  sun-amber-day: "#8A5200"
  sky-blue: "#6CB8FF"
  sky-blue-day: "#1565C0"
  coral: "#FF8A6B"
  coral-day: "#B4411F"
  violet: "#B79CFF"
  violet-day: "#5B3FB5"
typography:
  display:
    fontFamily: "Space Grotesk, Inter, system-ui, sans-serif"
    fontSize: "clamp(40px, 5.6vw, 76px)"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Space Grotesk, Inter, system-ui, sans-serif"
    fontSize: "clamp(26px, 3.2vw, 40px)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Space Grotesk, Inter, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  lead:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  control: "999px"
  card-small: "16px"
  card: "20px"
  feature: "28px"
spacing:
  section: "104px"
  section-mobile: "64px"
  gutter: "clamp(20px, 5vw, 72px)"
  container: "1240px"
components:
  button-primary:
    backgroundColor: "{colors.wind-green}"
    textColor: "{colors.wind-green-ink}"
    rounded: "{rounded.control}"
    padding: "0 24px"
    height: "48px"
  button-ghost:
    textColor: "{colors.night-ink}"
    rounded: "{rounded.control}"
    padding: "0 24px"
    height: "48px"
  card:
    backgroundColor: "{colors.night-surface}"
    rounded: "{rounded.card}"
    padding: "28px"
  card-small:
    backgroundColor: "{colors.night-surface-raised}"
    rounded: "{rounded.card-small}"
    padding: "16px"
  theme-toggle:
    textColor: "{colors.night-ink}"
    rounded: "{rounded.control}"
    height: "40px"
---

# Design System: AeroPredictor

## Overview

**Creative North Star: «Un parte meteorológico de datos»**

Una web de lectura y exploración, no un panel de control. La cifra de mañana manda en Inicio; el resto de páginas explican de dónde sale. Fondo casi negro con un verde de aerogenerador como único acento fuerte, superficies apenas elevadas y tipografía geométrica en los títulos. Densidad media: mucho aire entre secciones y gráficas a ancho completo.

Fuente de verdad: `frontend/src/styles/aero.css` (variables CSS) y `frontend/tailwind.config.mjs`. Lo que aquí se describe refleja la web tras la spec 012 y la propuesta del lienzo del 26/11/2026.

**Key Characteristics:**
- Tema oscuro por defecto; claro con el selector de la cabecera, guardado en `localStorage` (`aero-tema`).
- Un acento (verde) y cuatro colores de serie (ámbar, azul, coral, violeta) reservados a las gráficas.
- Gráficas de Chart.js con los colores de los tokens; siguen el tema sin recargar.

## Colors

Paleta de noche verdosa con un verde eléctrico; cada color tiene su pareja para el tema claro con contraste AA.

### Primary
- **Verde aerogenerador** (#5BE08B; claro #14783A): acción principal, enlaces, la serie del modelo vigente y la producción eólica. Texto sobre él en #052012 (oscuro) o #FFFFFF (claro).

### Secondary
- **Ámbar sol** (#F2B84B; claro #8A5200): racha, sol y estados pendientes.
- **Azul cielo** (#6CB8FF; claro #1565C0): viento medio y serie real en las comparativas.
- **Coral** (#FF8A6B; claro #B4411F): temperatura, variante de 16 variables y estados caducados o no disponibles.
- **Violeta** (#B79CFF; claro #5B3FB5): la predicción de mañana en la gráfica de 30 días.

### Neutral
- **Suelo** (#0A120E; claro #F3F7F4): fondo de página.
- **Superficie** (#101A15; claro #FFFFFF): tarjetas.
- **Superficie elevada** (#16231C; claro #E8F0EB): tarjetas pequeñas, recuadros de nota y resaltado de gráficas.
- **Tinta** (#E9F3ED; claro #0C1A13) y **tinta suave** (#9DB5A8; claro #465B50): texto principal y secundario.
- **Línea** (rgba(190,235,210,0.13); claro rgba(10,40,25,0.13)) y **rejilla** (opacidad 0,10): bordes y rejillas de gráficas.

### Named Rules
**La regla del acento único.** El verde marca la acción y el dato principal; los demás colores solo aparecen como series de gráfica o como estado.

**La regla de los dos temas.** Todo color se usa por su variable CSS (`var(--accent)`, `var(--muted)`…), nunca en hexadecimal en un componente; así los dos temas siguen pasando AA.

## Typography

**Display Font:** Space Grotesk (con Inter y system-ui)
**Body Font:** Inter (con system-ui)

**Character:** Títulos geométricos y apretados frente a un texto neutro y muy legible; las cifras usan numerales tabulares (`.num`).

### Hierarchy
- **Display** (600, clamp(40px, 5.6vw, 76px), 0,98): el título de cada página.
- **Headline** (600, clamp(26px, 3.2vw, 40px), 1,1): títulos de sección.
- **Title** (600, 20–24px, 1,2): subapartados y títulos de tarjeta.
- **Lead** (400, 18px, 1,6): entradilla bajo el título, máx. 62ch.
- **Body** (400, 16px, 1,6): texto corrido, 65–75ch.

### Named Rules
**La regla del título sin etiqueta.** Ningún título lleva encima una etiqueta en mayúsculas ni un número de sección. Excepciones: una secuencia cuyo orden importa (los pasos del proceso de Inicio) y el título de la tarjeta de predicción («Predicción para mañana»). Toda la web la cumple desde la spec 014.

## Layout

Contenedor de 1.240 px de contenido con márgenes de clamp(20 px, 5vw, 72 px), como el lienzo de diseño. Secciones separadas unos 104 px (64 px en móvil). Rejillas `auto-fit` con `minmax(min(Npx, 100%), 1fr)` para que nada desborde. La navegación se pega arriba y en móvil pasa los enlaces a una segunda fila desplazable.

## Elevation & Depth

Plano por defecto: la profundidad la dan las superficies tonales (suelo → superficie → superficie elevada) y un borde de 1 px con la línea. Solo la tarjeta de predicción lleva una sombra amplia y suave (`0 40px 90px -60px rgba(0,0,0,0.65)`).

## Shapes

Controles en píldora (999 px). Tarjetas a 20 px (las de los modelos a 24 px) y la tarjeta de predicción a 28 px; tarjetas pequeñas y notas a 16 px. Bordes de 1 px, nunca de color grueso a un lado.

## Components

### Buttons
- **Shape:** píldora (999 px), 48 px de alto.
- **Primary:** fondo verde, texto oscuro; se eleva 1 px al pasar el cursor.
- **Ghost:** transparente con borde de línea y texto en tinta.
- **Focus:** contorno de 2 px en el verde, separado 3 px.

### Cards / Containers
- **Corner Style:** 24 px (16 px las pequeñas).
- **Background:** superficie; las pequeñas y las notas, superficie elevada.
- **Border:** 1 px con la línea.
- **Internal Padding:** 28 px (16 px las pequeñas).

### Navigation
- Cabecera fija sobre el suelo, logo (rotor de tres palas + «AERO»«Predictor»), enlaces en píldora (el activo con `aria-current` y superficie elevada) y selector de tema de dos botones, Oscuro y Claro, con el activo en el acento; en móvil los enlaces pasan a una segunda fila y el selector solo muestra los iconos.

### Logo y favicon
- Rotor de tres palas en el acento con el centro en tinta (`src/components/shared/Logo.astro`). El favicon es el mismo rotor sobre el suelo, en un cuadrado redondeado.

### Gráficas (componente propio)
Criterios comunes de todas las gráficas:
- **Ancho fluido:** nunca desplazamiento horizontal; en la web, Chart.js responsive; en el lienzo, caja con relación de aspecto y etiquetas de eje en HTML.
- **Series:** botones o leyenda para mostrar y ocultar cuando hay más de una.
- **Lectura:** valores bajo el cursor o al tocar (tooltip de Chart.js en la web; lectura con botones anterior/siguiente en el lienzo).
- **Tabla de datos:** desplegable «Ver los datos en tabla» (`details.a-tabla`); en las nubes de puntos, resumen por tramos.
- **Color:** texto, rejilla y series desde los tokens (`src/utils/charts-tema.ts`, `public/js/chart-tema.js`).

### Tarjeta de predicción (componente propio)
Cuatro estados reales de la previsión publicada: vigente (verde), pendiente (ámbar), caducada (coral) y no disponible (coral, sin cifra). El estado se recalcula en el navegador con la fecha de hoy. Si la cifra se calculó sin la previsión real de REE (spec 019), se añade el distintivo «Provisional» en ámbar con borde discontinuo y una línea que lo explica.

## Do's and Don'ts

- **Do:** usar las variables CSS del tema en todo componente nuevo.
- **Do:** dar a cada gráfica su tabla de datos y su texto alternativo.
- **Do:** escribir las cifras con su fuente y su periodo.
- **Don't:** poner etiquetas en mayúsculas encima de los títulos ni numerar secciones sin motivo.
- **Don't:** usar el patrón de cifra grande con etiqueta pequeña y estadísticas de apoyo como estructura de sección, ni minigráficas decorativas sin ejes ni datos.
- **Don't:** degradados en el texto, cristal decorativo ni bordes gruesos de color a un lado de las tarjetas.
- **Don't:** dejar que una gráfica obligue a desplazar la página en horizontal.
