from fastapi import APIRouter
from typing import Optional
from datetime import datetime
import logging

from ..services import db_ree
from ..services.aemet_client import get_aggregated_forecast
from ..services.model_loader import model_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["prediction"])


@router.get("/prediction")
def get_prediction():
    prediction = db_ree.get_latest_prediction()
    if prediction:
        return prediction

    forecast = get_aggregated_forecast()
    if forecast:
        result = model_service.predict(forecast["velmedia"], forecast["racha"])
        return result

    return {
        "fecha": (datetime.now().timestamp() + 86400),
        "prediccionMWh": 180000,
        "modelo": "Linear Regression",
        "features": {"velmedia": 3.5, "racha": 8.0}
    }


@router.post("/prediction/refresh")
def refresh_prediction():
    from ..services import aemet_client, db_ree as db

    forecast = aemet_client.get_aggregated_forecast()
    if not forecast:
        return {"error": "No se pudo obtener forecast de AEMET"}

    result = model_service.predict(forecast["velmedia"], forecast["racha"])

    db.save_prediction(
        fecha=result["fecha"],
        prediccion_mwh=result["prediccion_mwh"],
        modelo=result["modelo"],
        velmedia=result["velmedia"],
        racha=result["racha"]
    )

    return result


@router.get("/forecast")
def get_forecast():
    forecast = get_aggregated_forecast()
    if forecast:
        return forecast
    return {
        "fecha": (datetime.now().timestamp() + 86400),
        "velmedia": 3.5,
        "racha": 8.0,
        "estaciones": {}
    }