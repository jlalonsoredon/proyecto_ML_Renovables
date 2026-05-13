import joblib
import os
import numpy as np
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "modelos/lr_eolica.joblib")

# Debe coincidir exactamente con FEATURE_COLS del notebook api.ipynb
FEATURE_COLS = [
    "velmedia", "racha", "mes", "dia_semana", "dia_año",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14",
    "eolica_ma7",
]


class ModelService:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.features = None
        self._load_model()

    def _load_model(self):
        try:
            pipeline = joblib.load(MODEL_PATH)
            # El notebook guarda la clave como "modelo", no "model"
            self.model = pipeline.get("modelo")
            self.scaler = pipeline.get("scaler")
            self.features = pipeline.get("features", FEATURE_COLS)
            logger.info(f"Modelo cargado: {MODEL_PATH} | features={len(self.features)}")
        except FileNotFoundError:
            logger.warning(f"Modelo no encontrado: {MODEL_PATH}. Usando predicción por defecto.")
            self.model = None
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            self.model = None

    def _get_eolica_lags(self) -> Dict[str, float]:
        """Devuelve los últimos 7 valores diarios de generación eólica de la BD."""
        from app.services.db_ree import get_eolica_recent
        try:
            valores = get_eolica_recent(days=7)  # lista ordenada de más antiguo a más reciente
            n = len(valores)
            fallback = 150000.0

            def lag(i):
                idx = n - i
                return float(valores[idx]) if idx >= 0 else fallback

            return {
                "eolica_lag1": lag(1),
                "eolica_lag2": lag(2),
                "eolica_lag3": lag(3),
                "eolica_lag7": lag(7),
                "eolica_ma7": float(np.mean(valores[-7:])) if n >= 7 else fallback,
            }
        except Exception as e:
            logger.warning(f"No se pudieron obtener lags eólicos: {e}")
            fallback = 150000.0
            return {
                "eolica_lag1": fallback,
                "eolica_lag2": fallback,
                "eolica_lag3": fallback,
                "eolica_lag7": fallback,
                "eolica_ma7": fallback,
            }

    def _get_wind_history(self, days: int = 14) -> Dict[str, list]:
        """Devuelve listas de velmedia y racha históricos de las estaciones eólicas."""
        from app.services.db_ree import get_wind_recent
        try:
            return get_wind_recent(days=days)
        except Exception as e:
            logger.warning(f"No se pudo obtener historial de viento: {e}")
            return {"velmedia": [], "racha": []}

    def _create_features(self, velmedia: float, racha: float) -> np.ndarray:
        manana = datetime.now() + timedelta(days=1)
        mes = manana.month
        dia_semana = manana.weekday()
        dia_año = manana.timetuple().tm_yday

        eolica_lags = self._get_eolica_lags()
        wind_hist = self._get_wind_history(days=14)

        vel_hist = np.array(wind_hist["velmedia"], dtype=float)
        racha_hist = np.array(wind_hist["racha"], dtype=float)

        def rolling_mean(hist, n):
            window = np.append(hist[-(n - 1):], velmedia) if len(hist) >= n - 1 else np.append(hist, velmedia)
            return float(np.mean(window))

        def rolling_mean_racha(hist, n):
            window = np.append(hist[-(n - 1):], racha) if len(hist) >= n - 1 else np.append(hist, racha)
            return float(np.mean(window))

        features = {
            "velmedia":     velmedia,
            "racha":        racha,
            "mes":          mes,
            "dia_semana":   dia_semana,
            "dia_año":      dia_año,
            **eolica_lags,
            "vel_ma3":      rolling_mean(vel_hist, 3),
            "vel_ma7":      rolling_mean(vel_hist, 7),
            "vel_ma14":     rolling_mean(vel_hist, 14),
            "racha_ma3":    rolling_mean_racha(racha_hist, 3),
            "racha_ma7":    rolling_mean_racha(racha_hist, 7),
            "racha_ma14":   rolling_mean_racha(racha_hist, 14),
        }

        col_order = self.features if self.features else FEATURE_COLS
        return np.array([features[c] for c in col_order]).reshape(1, -1)

    def predict(self, velmedia: float, racha: float) -> Optional[Dict]:
        fecha_manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        if self.model is None or self.scaler is None:
            logger.warning("Modelo no disponible, retornando predicción por defecto")
            lags = self._get_eolica_lags()
            base_pred = lags["eolica_ma7"]
            return {
                "prediccionMWh": round(base_pred * (1 + velmedia / 20), 0),
                "modelo": "Linear Regression (sin modelo cargado)",
                "fecha": fecha_manana,
                "features": {"velmedia": round(velmedia, 2), "racha": round(racha, 2)},
            }

        try:
            features = self._create_features(velmedia, racha)
            features_scaled = self.scaler.transform(features)
            prediction = self.model.predict(features_scaled)[0]

            return {
                "prediccionMWh": round(float(prediction), 0),
                "modelo": "Linear Regression",
                "fecha": fecha_manana,
                "features": {"velmedia": round(velmedia, 2), "racha": round(racha, 2)},
            }
        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            lags = self._get_eolica_lags()
            return {
                "prediccionMWh": round(lags["eolica_ma7"], 0),
                "modelo": "Linear Regression (fallback)",
                "fecha": fecha_manana,
                "features": {"velmedia": round(velmedia, 2), "racha": round(racha, 2)},
            }


model_service = ModelService()