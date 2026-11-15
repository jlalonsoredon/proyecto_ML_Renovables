from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.prediction_service import PredictionUnavailable, prediction_service

router = APIRouter(prefix="/api", tags=["prediction"])


def _no_disponible(error: PredictionUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content=error.response())


@router.get("/prediction")
def get_prediction():
    try:
        return prediction_service.get_prediction()
    except PredictionUnavailable as error:
        return _no_disponible(error)


@router.post("/prediction/refresh")
def refresh_prediction():
    try:
        return prediction_service.refresh_prediction()
    except PredictionUnavailable as error:
        return _no_disponible(error)


@router.get("/forecast")
def get_forecast():
    return prediction_service.forecast_payload()
