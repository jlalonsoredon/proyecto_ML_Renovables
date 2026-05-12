import requests
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import os
import time

logger = logging.getLogger(__name__)

AEMET_API_KEY = os.environ.get("AEMET_API_KEY", "")
AEMET_BASE_URL = "https://opendata.aemet.es/opendata/api"

HEADERS = {"Accept": "application/json"}

ESTACIONES = {
    "4589X": {"nombre": "Alosno, Tharsis", "municipio": "Alosno"},
    "8175": {"nombre": "Albacete", "municipio": "Albacete"},
    "3013": {"nombre": "Molina de Aragón", "municipio": "Molina de Aragon"},
    "9299X": {"nombre": "Tarazona", "municipio": "Tarazona"},
    "6001": {"nombre": "Tarifa", "municipio": "Tarifa"},
    "9031C": {"nombre": "Briviesca", "municipio": "Briviesca"},
}


def get_daily_forecast(municipio: str, fecha: str = None) -> Optional[Dict]:
    if not AEMET_API_KEY:
        logger.warning("AEMET_API_KEY no configurada")
        return None

    if fecha is None:
        fecha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    url = f"{AEMET_BASE_URL}/prediccion/especifica/municipio/diaria/{municipio}"

    params = {"api_key": AEMET_API_KEY}

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            logger.warning(f"AEMET error {response.status_code}: {response.text[:100]}")
            return None

        data_url = response.json().get("datos")
        if not data_url:
            return None

        time.sleep(1)
        data_response = requests.get(data_url, headers=HEADERS, timeout=30)
        forecast_data = data_response.json()

        for day in forecast_data.get("prediccion", {}).get("dia", []):
            if day.get("fecha") == fecha:
                day_data = day.get("datos", {})
                return {
                    "fecha": fecha,
                    "temp_max": float(day_data.get("tmax", [0])[0].get("value", 0)),
                    "temp_min": float(day_data.get("tmin", [0])[0].get("value", 0)),
                    "vel_media": float(day_data.get("viento", [{}])[0].get("velocidad", 0)),
                    "rachas_max": float(day_data.get("racha", [{}])[0].get("value", 0)),
                    "precipitacion": float(day_data.get("precipitacion", [{}])[0].get("value", 0)),
                    "sol": float(day_data.get("sol", [{}])[0].get("value", 0))
                }
        return None

    except Exception as e:
        logger.error(f"Error consultando AEMET: {e}")
        return None


def get_forecast_for_wind_parks() -> Dict:
    forecasts = {}

    for estacion_id, estacion_info in ESTACIONES.items():
        municipio = estacion_info["municipio"]
        forecast = get_daily_forecast(municipio)
        if forecast:
            forecasts[estacion_id] = forecast

    return forecasts


def get_aggregated_forecast() -> Optional[Dict]:
    forecasts = get_forecast_for_wind_parks()

    if not forecasts:
        return None

    vel_media_values = [f.get("vel_media", 0) for f in forecasts.values() if f.get("vel_media")]
    racha_values = [f.get("rachas_max", 0) for f in forecasts.values() if f.get("rachas_max")]

    if not vel_media_values:
        return None

    return {
        "fecha": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "velmedia": round(sum(vel_media_values) / len(vel_media_values), 2),
        "racha": round(max(racha_values), 2) if racha_values else 0,
        "estaciones": forecasts
    }