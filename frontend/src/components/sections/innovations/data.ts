import imgGrid from "./assets/inno-grid.webp";
import imgSolar from "./assets/inno-panel.webp";
import imgWind from "./assets/inno-wind.webp";
import imgHydro from "./assets/central-hidraulica.png";

export const innovationsSection = {
  title: "Latest Innovations",
  subheading1_1: "Discover Our Cutting-edge",
  subheading1_2: " Green Energy Technologies",
  innovations: [
    {
      title: "Visión general de sistema energético",
      description:
        "España supera ya el 55% de producción eléctrica renovable, pero aún queda un largo camino por recorrer. En 2024, la media de la UE se situó en el 47,4%, sin embargo países como Dinamarca (88,8%), Portugal (87,4%) o Croacia (73,8%) demuestran que el techo está mucho más arriba. A nivel europeo, la eólica y la hidroeléctrica concentran más de dos tercios de toda la generación renovable. Conocer y predecir con precisión cuánta energía eólica se va a producir es clave para acelerar esta transición.",
      visual: imgGrid,
    },
    {
      title: "Energía fotovoltaica",
      description:
        "Con apenas un 20% de la producción eléctrica proveniente de fuentes solares, España aún tiene un gran potencial para expandir su capacidad fotovoltaica y aprovechar al máximo la energía del sol.",
      visual: imgSolar,
    },
    {
      title: "Energía eólica",
      description:
        "España cuenta con un gran potencial eólico, especialmente en regiones como Galicia, Castilla y León y Andalucía. La energía eólica es una fuente clave para alcanzar los objetivos de energía renovable y reducir las emisiones de carbono.",
      visual: imgWind,
    },
  ],
  visual: "innovations-section-image.jpg",
  callToAction: "Explore the Future of Green Energy with [Company Name]",
  button: "Learn More",
};

export const innovationsSectionProceso = {
  title: "Latest Innovations",
  innovations: [
    {
      title: "Visión general de sistema energético",
      description:
        "España supera ya el 55% de producción eléctrica renovable, pero aún queda un largo camino por recorrer. En 2024, la media de la UE se situó en el 47,4%, sin embargo países como Dinamarca (88,8%), Portugal (87,4%) o Croacia (73,8%) demuestran que el techo está mucho más arriba. A nivel europeo, la eólica y la hidroeléctrica concentran más de dos tercios de toda la generación renovable. Conocer y predecir con precisión cuánta energía eólica se va a producir es clave para acelerar esta transición.",
      visual: imgGrid,
    },
    {
      title: "Energía hidroeléctrica",
      description:
        "Fluye con la naturaleza. Nuestros sistemas hidroeléctricos aprovechan la energía del agua en movimiento, proporcionando electricidad confiable y ecológica.",
      visual: imgHydro,
    },
    {
      title: "Energía fotovoltaica",
      description:
        "Con apenas un 20% de la producción eléctrica proveniente de fuentes solares, España aún tiene un gran potencial para expandir su capacidad fotovoltaica y aprovechar al máximo la energía del sol.",
      visual: imgSolar,
    },
    {
      title: "Energía eólica",
      description:
        "España cuenta con un gran potencial eólico, especialmente en regiones como Galicia, Castilla y León y Andalucía. La energía eólica es una fuente clave para alcanzar los objetivos de energía renovable y reducir las emisiones de carbono.",
      visual: imgWind,
    },
  ],
};
