from fastapi import APIRouter
from typing import Optional
from datetime import datetime, timedelta
import logging

from ..services import db_ree
from ..services.aemet_client import get_aggregated_forecast
from ..services.model_loader import model_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["prediction"])


def _fallback_prediction() -> dict:
    """Predicción de emergencia cuando no hay modelo ni AEMET disponibles."""
    fecha_manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        vals = db_ree.get_eolica_recent(days=7)
        base = round(float(sum(vals) / len(vals)), 0) if vals else 150000.0
    except Exception:
        base = 150000.0
    return {
        "fecha": fecha_manana,
        "prediccionMWh": base,
        "modelo": "Linear Regression (fallback histórico)",
        "features": {"velmedia": None, "racha": None},
    }


@router.get("/prediction")
def get_prediction():
    # 1. Intentar devolver la última predicción guardada en BD
    prediction = db_ree.get_latest_prediction()
    if prediction:
        return prediction

    # 2. Calcular nueva predicción con datos de AEMET + modelo
    forecast = get_aggregated_forecast()
    if forecast:
        result = model_service.predict(forecast["velmedia"], forecast["racha"])
        # Guardar en BD para próximas consultas
        try:
            db_ree.save_prediction(
                fecha=result["fecha"],
                prediccion_mwh=result["prediccionMWh"],
                modelo=result["modelo"],
                velmedia=result["features"]["velmedia"] or 0.0,
                racha=result["features"]["racha"] or 0.0,
            )
        except Exception as e:
            logger.warning(f"No se pudo guardar predicción en BD: {e}")
        return result

    # 3. Sin AEMET: usar media histórica
    return _fallback_prediction()


@router.post("/prediction/refresh")
def refresh_prediction():
    forecast = get_aggregated_forecast()
    if not forecast:
        return {"error": "No se pudo obtener forecast de AEMET"}

    result = model_service.predict(forecast["velmedia"], forecast["racha"])

    db_ree.save_prediction(
        fecha=result["fecha"],
        prediccion_mwh=result["prediccionMWh"],
        modelo=result["modelo"],
        velmedia=result["features"]["velmedia"] or 0.0,
        racha=result["features"]["racha"] or 0.0,
    )

    return result


@router.get("/forecast")
def get_forecast():
    forecast = get_aggregated_forecast()
    if forecast:
        return forecast
    return {
        "fecha": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "velmedia": None,
        "racha": None,
        "estaciones": {},
        "error": "AEMET no disponible",
    }
