const API_BASE_URL = import.meta.env.PUBLIC_API_URL || "http://localhost:8000";

export interface Prediction {
  fecha: string;
  prediccionMWh: number;
  modelo: string;
  features: {
    velmedia: number;
    racha: number;
  };
}

export interface HistoricalData {
  fecha: string;
  eolica: number;
  solar: number;
  hidraulica: number;
}

export interface EnergyMix {
  renovable: number;
  noRenovable: number;
  tecnologias: Record<string, number>;
}

export interface ModelResult {
  modelo: string;
  rmse: number;
  r2: number;
  mape: number;
  accuracy: number;
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface WindPark {
  nombre: string;
  id: string;
  lat: number;
  lng: number;
  estacion: string;
}

async function fetchAPI<T>(endpoint: string): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`);
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Error fetching ${endpoint}:`, error);
    throw error;
  }
}

export const api = {
  getPrediction: () => fetchAPI<Prediction>("/api/prediction"),
  getHistorical: (days: number = 30) => fetchAPI<HistoricalData[]>(`/api/historical?days=${days}`),
  getEnergyMix: () => fetchAPI<EnergyMix>("/api/energy-mix"),
  getModelComparison: () => fetchAPI<ModelResult[]>("/api/model-comparison"),
  getFeatureImportance: () => fetchAPI<FeatureImportance[]>("/api/feature-importance"),
  getWindParks: () => fetchAPI<WindPark[]>("/api/wind-parks"),
};