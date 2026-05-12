from fastapi import APIRouter
from typing import List
from datetime import datetime
import logging

from ..services import db_ree

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["charts"])


@router.get("/historical")
def get_historical(days: int = 30):
    data = db_ree.get_historical_data(days)
    if not data:
        data = generate_mock_historical(days)
    return data


@router.get("/energy-mix")
def get_energy_mix():
    mix = db_ree.get_energy_mix()
    if not mix["tecnologias"]:
        mix = get_mock_energy_mix()
    return mix


@router.get("/model-comparison")
def get_model_comparison():
    return [
        {"modelo": "Linear Regression", "rmse": 60432.9, "r2": 0.579, "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Lasso", "rmse": 60433.1, "r2": 0.579, "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Random Forest", "rmse": 60437.6, "r2": 0.5789, "mape": 44.3, "accuracy": 36.3},
        {"modelo": "Ridge", "rmse": 60498.1, "r2": 0.5781, "mape": 41.95, "accuracy": 42.0},
        {"modelo": "LightGBM", "rmse": 61872.5, "r2": 0.5587, "mape": 44.46, "accuracy": 37.2},
        {"modelo": "XGBoost", "rmse": 63346.3, "r2": 0.5374, "mape": 45.87, "accuracy": 36.6},
        {"modelo": "Red Neuronal (MLP)", "rmse": 63909.6, "r2": 0.5291, "mape": 43.22, "accuracy": 37.5},
    ]


@router.get("/feature-importance")
def get_feature_importance():
    return [
        {"feature": "velmedia", "importance": 0.35},
        {"feature": "racha", "importance": 0.25},
        {"feature": "eolica_lag1", "importance": 0.15},
        {"feature": "eolica_lag7", "importance": 0.10},
        {"feature": "vel_ma7", "importance": 0.08},
        {"feature": "mes", "importance": 0.04},
        {"feature": "dia_semana", "importance": 0.03},
    ]


@router.get("/wind-parks")
def get_wind_parks():
    return [
        {"nombre": "El Andévalo (Huelva)", "id": "4589X", "lat": 37.26418296737997, "lng": -6.944856396315273, "estacion": "ALOSNO, THARSIS"},
        {"nombre": "Gecama (Cuenca)", "id": "8175", "lat": 39.40848408319995, "lng": -2.2192737751771614, "estacion": "ALBACETE"},
        {"nombre": "Maranchón (Guadalajara)", "id": "3013", "lat": 41.06356588209968, "lng": -2.206160824662825, "estacion": "MOLINA DE ARAGÓN"},
        {"nombre": "Borja (Zaragoza)", "id": "9299X", "lat": 41.877046928697204, "lng": -1.5630303402886618, "estacion": "TARAZONA"},
        {"nombre": "Tarifa (Cádiz)", "id": "6001", "lat": 36.037373555997895, "lng": -5.570950423574283, "estacion": "TARIFA"},
        {"nombre": "Briviesca (Burgos)", "id": "9031C", "lat": 42.52921710077489, "lng": -3.408352539310985, "estacion": "BRIVIESCA"},
        {"nombre": "La Muela (Zaragoza)", "id": "9299X", "lat": 41.5924449830392, "lng": -1.1575020732335635, "estacion": "TARAZONA"},
    ]


def generate_mock_historical(days: int) -> List[dict]:
    result = []
    for i in range(days, 0, -1):
        date = datetime.now().timestamp() - (i * 86400)
        result.append({
            "fecha": datetime.fromtimestamp(date).strftime("%Y-%m-%d"),
            "eolica": 100000 + (i * 1000) + (hash(str(i)) % 50000),
            "solar": 150000 + (i * 500) + (hash(str(i)) % 30000),
            "hidraulica": 50000 + (i * 300) + (hash(str(i)) % 20000)
        })
    return result


def get_mock_energy_mix():
    return {
        "renovable": 58.33,
        "noRenovable": 41.67,
        "tecnologias": {
            "Eólica": 23.41,
            "Solar fotovoltaica": 19.83,
            "Hidráulica": 11.64,
            "Solar térmica": 1.62,
            "Otras renovables": 1.55,
            "Residuos renovables": 0.28
        }
    }