import logging
import math
import os
from typing import Sequence

import joblib
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "modelos/lr_eolica.joblib")

# Orden exacto guardado en el artefacto LR-19.
FEATURE_COLS = [
    "velmedia", "racha", "mes", "dia_semana", "dia_año",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14",
    "eolica_ma7",
    "sol_lag1", "tmed_lag1", "eolica_prev",
]

FAMILIA_PRODUCCION = "Linear Regression"


class ModelUnavailable(RuntimeError):
    """El artefacto no satisface el contrato de producción."""


class ModelService:
    def __init__(self, model_path: str | None = None,
                 expected_features: Sequence[str] | None = None):
        self.model_path = model_path or MODEL_PATH
        self.expected_features = tuple(expected_features or FEATURE_COLS)
        self.model = None
        self.scaler = None
        self.features: list[str] = []
        self.family = ""
        self.uses_scaler = False
        self.load_error: str | None = None
        self._load_model()

    @property
    def ready(self) -> bool:
        return self.model is not None and self.load_error is None

    def _load_model(self) -> None:
        try:
            artifact = joblib.load(self.model_path)
            if not isinstance(artifact, dict):
                raise ValueError("el artefacto no es un diccionario")
            required = {"modelo", "scaler", "features", "familia", "usa_scaler"}
            missing = sorted(required - artifact.keys())
            if missing:
                raise ValueError(f"faltan claves del artefacto: {', '.join(missing)}")

            features = tuple(artifact["features"])
            if features != self.expected_features:
                raise ValueError("el orden de features no coincide con LR-19")
            if artifact["familia"] != FAMILIA_PRODUCCION:
                raise ValueError(
                    f"familia incompatible: {artifact['familia']!r}"
                )
            if not isinstance(artifact["usa_scaler"], bool):
                raise ValueError("usa_scaler debe ser booleano")

            model = artifact["modelo"]
            scaler = artifact["scaler"]
            if model is None or getattr(model, "n_features_in_", None) != len(features):
                raise ValueError("el modelo no declara las 19 features esperadas")
            uses_scaler = artifact["usa_scaler"]
            if uses_scaler and (
                scaler is None
                or getattr(scaler, "n_features_in_", None) != len(features)
            ):
                raise ValueError("el scaler no coincide con las 19 features")
            if not uses_scaler and scaler is not None:
                logger.warning("El artefacto contiene scaler pero declara usa_scaler=False")

            self.model = model
            self.scaler = scaler
            self.features = list(features)
            self.family = artifact["familia"]
            self.uses_scaler = uses_scaler
            logger.info(
                "Modelo cargado: %s | familia=%s | features=%d",
                self.model_path,
                self.family,
                len(self.features),
            )
        except Exception as error:
            self.model = None
            self.scaler = None
            self.features = []
            self.family = ""
            self.uses_scaler = False
            self.load_error = str(error)
            logger.error("No se pudo cargar el modelo de producción: %s", error)

    def predict_vector(self, vector: dict[str, float]) -> float:
        if not self.ready:
            raise ModelUnavailable(self.load_error or "modelo no disponible")
        if tuple(vector.keys()) != self.expected_features:
            raise ValueError("el vector no conserva el orden de las 19 features")
        values = [float(vector[name]) for name in self.features]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("el vector contiene valores no finitos")
        frame = pd.DataFrame([values], columns=self.features)
        model_input = self.scaler.transform(frame) if self.uses_scaler else frame
        prediction = float(self.model.predict(model_input)[0])
        if not math.isfinite(prediction):
            raise ValueError("el modelo produjo una predicción no finita")
        return prediction


model_service = ModelService()
