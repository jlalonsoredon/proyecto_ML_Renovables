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
        "Linear Regression con 19 variables alcanza un R² de 0,9308 en un test de 354 días (nov. 2025 – nov. 2026): explica el 93 % de la variación de la producción eólica.",
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
        "Cada día a las 03:00 se genera la predicción de mañana con la previsión meteorológica de AEMET y la previsión eólica de REE.",
      visual: svg3,
    },
  ],
  visual: "get-involved-section-image.jpg",
  callToAction: "Actúa Hoy para un Futuro más Verde",
  button: "Ver Predicciones",
};