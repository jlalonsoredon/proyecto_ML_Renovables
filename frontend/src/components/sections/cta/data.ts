import svg1 from "./assets/green-1.svg?raw";
import svg2 from "./assets/green-2.svg?raw";
import svg3 from "./assets/green-3.svg?raw";
import svg4 from "./assets/green-4.svg?raw";

export const getInvolvedSection = {
  title: "Resultados del Modelo",
  subheading1_1: "Únete ",
  subheading1_2: "en Construcción de un Futuro Sostenible",
  initiatives: [
    {
      title: "Precisión del Modelo",
      description:
        "Nuestro modelo Linear Regression alcanza un R² de 0.579, explicando el 57.9% de la varianza en la producción eólica.",
      visual: svg2,
    },
    {
      title: "Datos Históricos",
      description:
        "Analizamos más de 4 años de datos de generación eléctrica y meteorológicos para entrenar nuestros modelos predictivos.",
      visual: svg4,
    },
    {
      title: "Predicción en Tiempo Real",
      description:
        "El sistema genera predicciones diarias actualizadas automáticamente cada noche basándose en el forecast de AEMET.",
      visual: svg3,
    },
  ],
  visual: "get-involved-section-image.jpg",
  callToAction: "Actúa Hoy para un Futuro más Verde",
  button: "Ver Predicciones",
};