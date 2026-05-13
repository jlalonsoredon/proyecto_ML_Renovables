from fastapi import APIRouter
from typing import List
from datetime import datetime
import logging
import json
import os
import numpy as np

from ..services import db_ree
from ..services.model_loader import model_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["charts"])

# Parques eólicos con coordenadas reales y su indicativo AEMET asociado
# (mismos datos que en api.ipynb → parques_eolicos / estaciones_meteorologicas_eolicas)
_WIND_PARKS = [
    {"nombre": "El Andévalo (Huelva)",       "indicativo": "4589X", "estacion": "ALOSNO, THARSIS",    "lat": 37.26418296737997,  "lng": -6.944856396315273},
    {"nombre": "Gecama (Cuenca)",             "indicativo": "8175",  "estacion": "ALBACETE BASE AÉREA", "lat": 39.40848408319995,  "lng": -2.2192737751771614},
    {"nombre": "Maranchón (Guadalajara)",     "indicativo": "3013",  "estacion": "MOLINA DE ARAGÓN",    "lat": 41.06356588209968,  "lng": -2.206160824662825},
    {"nombre": "Borja (Zaragoza)",            "indicativo": "9299X", "estacion": "TARAZONA",            "lat": 41.877046928697204, "lng": -1.5630303402886618},
    {"nombre": "Tarifa (Cádiz)",              "indicativo": "6001",  "estacion": "TARIFA",              "lat": 36.037373555997895, "lng": -5.570950423574283},
    {"nombre": "Briviesca (Burgos)",          "indicativo": "9031C", "estacion": "BRIVIESCA",           "lat": 42.52921710077489,  "lng": -3.408352539310985},
    {"nombre": "La Muela (Zaragoza)",         "indicativo": "9299X", "estacion": "TARAZONA",            "lat": 41.592444983039200, "lng": -1.157502073233564},
]

METRICS_PATH = os.environ.get("METRICS_PATH", "modelos/metrics.json")


@router.get("/historical")
def get_historical(days: int = 30):
    from ..services.ree_client import ensure_recent_data

    # Actualizar BD con datos de REE si hay días sin cubrir
    try:
        updated, msg = ensure_recent_data(days=max(days, 30))
        if updated:
            logger.info(f"Datos REE actualizados: {msg}")
    except Exception as e:
        logger.warning(f"No se pudo actualizar datos REE: {e}")

    data = db_ree.get_historical_data(days)
    if not data:
        logger.warning("Sin datos en BD — devolviendo mock histórico")
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
    # Intentar leer métricas guardadas junto al modelo (modelos/metrics.json)
    try:
        with open(METRICS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Error leyendo {METRICS_PATH}: {e}")

    # Valores reales del entrenamiento en api.ipynb (df_resultados)
    return [
        {"modelo": "Linear Regression",  "rmse": 60432.9, "r2": 0.579,  "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Lasso",              "rmse": 60433.1, "r2": 0.579,  "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Random Forest",      "rmse": 60437.6, "r2": 0.5789, "mape": 44.30, "accuracy": 36.3},
        {"modelo": "Ridge",              "rmse": 60498.1, "r2": 0.5781, "mape": 41.95, "accuracy": 42.0},
        {"modelo": "LightGBM",           "rmse": 61872.5, "r2": 0.5587, "mape": 44.46, "accuracy": 37.2},
        {"modelo": "XGBoost",            "rmse": 63346.3, "r2": 0.5374, "mape": 45.87, "accuracy": 36.6},
        {"modelo": "Red Neuronal (MLP)", "rmse": 63909.6, "r2": 0.5291, "mape": 43.22, "accuracy": 37.5},
    ]


@router.get("/feature-importance")
def get_feature_importance():
    # Calcular desde los coeficientes del modelo LinearRegression cargado
    if model_service.model is not None and model_service.features:
        try:
            coefs = np.abs(model_service.model.coef_)
            total = float(coefs.sum()) or 1.0
            return [
                {"feature": feat, "importance": round(float(c / total), 4)}
                for feat, c in sorted(
                    zip(model_service.features, coefs),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ]
        except Exception as e:
            logger.warning(f"Error calculando feature importance desde el modelo: {e}")

    # Fallback: importancias aproximadas basadas en el análisis del notebook
    return [
        {"feature": "eolica_lag1",  "importance": 0.18},
        {"feature": "eolica_ma7",   "importance": 0.14},
        {"feature": "eolica_lag7",  "importance": 0.12},
        {"feature": "eolica_lag2",  "importance": 0.11},
        {"feature": "eolica_lag3",  "importance": 0.10},
        {"feature": "vel_ma14",     "importance": 0.08},
        {"feature": "racha_ma14",   "importance": 0.07},
        {"feature": "vel_ma7",      "importance": 0.06},
        {"feature": "racha_ma7",    "importance": 0.05},
        {"feature": "velmedia",     "importance": 0.04},
        {"feature": "racha",        "importance": 0.03},
        {"feature": "mes",          "importance": 0.01},
        {"feature": "dia_semana",   "importance": 0.01},
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
