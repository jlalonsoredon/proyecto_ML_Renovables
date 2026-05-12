import img1 from "./assets/solar3.png";
import img2 from "./assets/wind.png";
import img3 from "./assets/hydro.png";
import img4 from "./assets/storage.png";
import img5 from "./assets/smart-grid.png";
import img6 from "./assets/green.png";

export const servicesSectionData = {
  title: "Discover Our Cutting-edge Green Energy Technologies",
  subheading: {
    text1_1: "Predicción de Generación Eólica con Machine Learning - ",
    text1_2: "Innovación y Sostenibilidad.",
    text2:
      "Combinamos datos de la Red Eléctrica de España con información meteorológica de AEMET para predecir la producción de energía eólica.",
  },
  services: [
    {
      title: "Datos de Generación Eléctrica",
      briefDescription:
        "Obtenemos datos históricos de producción de energía eólica, solar e hidráulica desde la API de Red Eléctrica de España.",
      visual: img2,
    },
    {
      title: "Datos Meteorológicos",
      briefDescription:
        "Recopilamos datos de velocidad del viento, ráfagas y temperatura de 14 estaciones de AEMET cercanas a parques eólicos.",
      visual: img1,
    },
    {
      title: "Machine Learning",
      briefDescription:
        "Entrenamos modelos predictivos utilizando Linear Regression, XGBoost y Random Forest para forecasting de generación eólica.",
      visual: img5,
    },
    {
      title: "Predicción Diaria",
      briefDescription:
        "Generamos predicciones diarias de producción eólica para el día siguiente basándonos en el forecast de AEMET.",
      visual: img4,
    },
    {
      title: "Visualización de Datos",
      briefDescription:
        "Presentamos gráficos interactivos con la evolución histórica, comparativa de modelos y predicción vs real.",
      visual: img6,
    },
    {
      title: "Actualización Automática",
      briefDescription:
        "El sistema se actualiza automáticamente cada noche a las 3:00 AM para proporcionar predicciones siempre actualizadas.",
      visual: img3,
    },
  ],
  callToAction:
    "Descubre el Futuro de la Predicción Energética. Explora Nuestro Proyecto Hoy!",
  buttonText: "Ver Resultados",
};