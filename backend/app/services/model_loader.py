import joblib
import os
import numpy as np
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "modelos/lr_eolica.joblib")

FEATURE_COLS = [
    "velmedia", "racha", "mes", "dia_semana",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14", "racha_ma7", "eolica_ma7"
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
            self.model = pipeline.get("model")
            self.scaler = pipeline.get("scaler")
            self.features = pipeline.get("features", FEATURE_COLS)
            logger.info(f"Modelo cargado: {MODEL_PATH}")
        except FileNotFoundError:
            logger.warning(f"Modelo no encontrado: {MODEL_PATH}. Usando predicción por defecto.")
            self.model = None
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            self.model = None

    def _get_historical_average(self, days: int = 7) -> float:
        from app.services import db_ree
        try:
            fecha_inicio = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            df = db_ree.get_generation_data(fecha_inicio, datetime.now().strftime("%Y-%m-%d"))
            eolica_data = df[df["tecnologia"] == "Eólica"]["valor_MWh"]
            if not eolica_data.empty:
                return eolica_data.mean()
        except Exception:
            pass
        return 150000

    def _create_features(self, velmedia: float, racha: float) -> np.ndarray:
        from app.services import db_ree

        ahora = datetime.now()
        mes = ahora.month
        dia_semana = ahora.weekday()

        eolica_avg = self._get_historical_average()

        features = [
            velmedia,
            racha,
            mes,
            dia_semana,
            eolica_avg * 0.95,
            eolica_avg * 0.90,
            eolica_avg * 0.85,
            eolica_avg * 1.10,
            velmedia * 0.98,
            velmedia * 0.95,
            velmedia * 0.92,
            racha * 0.90,
            eolica_avg * 1.05
        ]

        return np.array(features).reshape(1, -1)

    def predict(self, velmedia: float, racha: float) -> Optional[Dict]:
        if self.model is None or self.scaler is None:
            logger.warning("Modelo no disponible, retornando predicción por defecto")
            base_pred = self._get_historical_average()
            return {
                "prediccion_mwh": round(base_pred * (1 + velmedia / 10), 0),
                "modelo": "Linear Regression (default)",
                "velmedia": velmedia,
                "racha": racha,
                "fecha": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            }

        try:
            features = self._create_features(velmedia, racha)
            features_scaled = self.scaler.transform(features)
            prediction = self.model.predict(features_scaled)[0]

            return {
                "prediccion_mwh": round(prediction, 0),
                "modelo": "Linear Regression",
                "velmedia": velmedia,
                "racha": racha,
                "fecha": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            }
        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            base_pred = self._get_historical_average()
            return {
                "prediccion_mwh": round(base_pred * (1 + velmedia / 10), 0),
                "modelo": "Linear Regression (fallback)",
                "velmedia": velmedia,
                "racha": racha,
                "fecha": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            }


model_service = ModelService()