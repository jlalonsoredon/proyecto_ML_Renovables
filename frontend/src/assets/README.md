# Assets - Imágenes del Proyecto

Este directorio存放 imágenes estáticas para el proyecto AeroPredictor.

## Estructura

```
src/assets/
├── proceso/          # Imágenes del proceso ML
│   ├── data-collection.png
│   ├── model-training.png
│   └── prediction.png
└── README.md
```

## Cómo usar imágenes

### En componentes Astro

```astro
---
import { Image } from "astro:assets";
import miImagen from "../assets/proceso/data-collection.png";
---

<Image src={miImagen} alt="Descripción de la imagen" />
```

### Propiedades de Image

- `src` - ruta de la imagen importada
- `alt` - texto alternativo (obligatorio para accesibilidad)
- `width` / `height` - dimensiones (opcional, se infiere automáticamente)
- `format` - formato (webp, avif, png, jpg)
- `quality` - calidad (low, mid, high)

### Alternativa: ruta pública

Para imágenes que no necesitan optimización:

```astro
<img src="/images/imagen-publica.png" alt="Descripción" />
```

Colocar en: `public/images/`