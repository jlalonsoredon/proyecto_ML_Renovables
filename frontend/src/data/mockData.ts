export interface ModelResult {
  modelo: string;
  rmse: number;
  mae: number;
  r2: number;
  mape: number;
  accuracy: number;
}

export interface EnergyMix {
  renovable: number;
  noRenovable: number;
  tecnologias: {
    [key: string]: number;
  };
}

export interface WindPark {
  nombre: string;
  id: string;
  lat: number;
  lng: number;
  estacion: string;
}

export interface HistoricalData {
  fecha: string;
  eolica: number;
  solar: number;
  hidraulica: number;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface CurrentPrediction {
  fecha: string;
  prediccionMWh: number;
  modelo: string;
  features: {
    velmedia: number;
    racha: number;
    mes: number;
    dia_semana: number;
  };
}

export const modelResults: ModelResult[] = [
  { modelo: "Linear Regression", rmse: 60432.9, mae: 47681.1, r2: 0.579, mape: 41.73, accuracy: 42.6 },
  { modelo: "Lasso", rmse: 60433.1, mae: 47681.1, r2: 0.579, mape: 41.73, accuracy: 42.6 },
  { modelo: "Random Forest", rmse: 60437.6, mae: 48187.7, r2: 0.5789, mape: 44.3, accuracy: 36.3 },
  { modelo: "Ridge", rmse: 60498.1, mae: 47741.2, r2: 0.5781, mape: 41.95, accuracy: 42.0 },
  { modelo: "LightGBM", rmse: 61872.5, mae: 49296.7, r2: 0.5587, mape: 44.46, accuracy: 37.2 },
  { modelo: "XGBoost", rmse: 63346.3, mae: 50137.9, r2: 0.5374, mape: 45.87, accuracy: 36.6 },
  { modelo: "Red Neuronal (MLP)", rmse: 63909.6, mae: 50309.5, r2: 0.5291, mape: 43.22, accuracy: 37.5 },
  { modelo: "SARIMAX", rmse: 91347.5, mae: 68304.1, r2: 0.038, mape: 43.51, accuracy: 28.1 },
];

export const energyMix: EnergyMix = {
  renovable: 58.33,
  noRenovable: 41.67,
  tecnologias: {
    "Eólica": 23.41,
    "Solar fotovoltaica": 19.83,
    "Hidráulica": 11.64,
    "Solar térmica": 1.62,
    "Otras renovables": 1.55,
    "Residuos renovables": 0.26
  }
};

export const windParks: WindPark[] = [
  { nombre: "El Andévalo (Huelva)", id: "4589X", lat: 37.26418296737997, lng: -6.944856396315273, estacion: "ALOSNO, THARSIS" },
  { nombre: "Gecama (Cuenca)", id: "8175", lat: 39.40848408319995, lng: -2.2192737751771614, estacion: "ALBACETE BASE AÉREA" },
  { nombre: "Maranchón (Guadalajara)", id: "3013", lat: 41.06356588209968, lng: -2.206160824662825, estacion: "MOLINA DE ARAGÓN" },
  { nombre: "Borja (Zaragoza)", id: "9299X", lat: 41.877046928697204, lng: -1.5630303402886618, estacion: "TARAZONA" },
  { nombre: "Tarifa (Cádiz)", id: "6001", lat: 36.037373555997895, lng: -5.570950423574283, estacion: "TARIFA" },
  { nombre: "Briviesca (Burgos)", id: "9031C", lat: 42.52921710077489, lng: -3.408352539310985, estacion: "BRIVIESCA" },
  { nombre: "La Muela (Zaragoza)", id: "9299X", lat: 41.5924449830392, lng: -1.1575020732335635, estacion: "TARAZONA" },
];

export const featureImportance: FeatureImportance[] = [
  { feature: "velmedia", importance: 0.35 },
  { feature: "racha", importance: 0.25 },
  { feature: "eolica_lag1", importance: 0.15 },
  { feature: "eolica_lag7", importance: 0.10 },
  { feature: "vel_ma7", importance: 0.08 },
  { feature: "mes", importance: 0.04 },
  { feature: "dia_semana", importance: 0.03 },
];

export const currentPrediction: CurrentPrediction = {
  fecha: "2026-05-14",
  prediccionMWh: 207354,
  modelo: "Linear Regression",
  features: {
    velmedia: 3.77,
    racha: 9.2,
    mes: 5,
    dia_semana: 3
  }
};

function generateHistoricalData(): HistoricalData[] {
  const data: HistoricalData[] = [];
  const baseDate = new Date("2026-05-10");

  for (let i = 29; i >= 0; i--) {
    const date = new Date(baseDate);
    date.setDate(date.getDate() - i);

    const eolica = 100000 + Math.random() * 200000;
    const solar = 150000 + Math.random() * 150000;
    const hidraulica = 50000 + Math.random() * 80000;

    data.push({
      fecha: date.toISOString().split("T")[0],
      eolica: Math.round(eolica),
      solar: Math.round(solar),
      hidraulica: Math.round(hidraulica)
    });
  }

  return data;
}

export const historicalData: HistoricalData[] = generateHistoricalData();

export function getPredictionForTomorrow(): CurrentPrediction {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);

  return {
    fecha: tomorrow.toISOString().split("T")[0],
    prediccionMWh: Math.round(180000 + Math.random() * 60000),
    modelo: "Linear Regression",
    features: {
      velmedia: Math.round((3 + Math.random() * 3) * 100) / 100,
      racha: Math.round((7 + Math.random() * 5) * 100) / 100,
      mes: tomorrow.getMonth() + 1,
      dia_semana: tomorrow.getDay()
    }
  };
}