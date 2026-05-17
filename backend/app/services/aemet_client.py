import requests
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import os
import time
import numpy as np

logger = logging.getLogger(__name__)

AEMET_API_KEY = os.environ.get("AEMET_API_KEY", "")
AEMET_BASE_URL = "https://opendata.aemet.es/opendata/api"

HEADERS = {"Accept": "application/json"}

ESTACIONES_EOLICAS = [
    "4589X",  # ALOSNO, THARSIS (Huelva)
    "8175",   # ALBACETE BASE AÉREA
    "3013",   # MOLINA DE ARAGÓN (Guadalajara)
    "6001",   # TARIFA (Cádiz)
    "9299X",  # TARAZONA (Zaragoza)
    "9031C",  # BRIVIESCA (Burgos)
]

# Códigos INE de municipios próximos a los parques eólicos (igual que en api.ipynb)
MUNICIPIOS_EOLICOS = {
    "Gecama (Cuenca)":       "16078",
    "Maranchón (Guadalaj.)": "19169",
    "Borja (Zaragoza)":      "50053",
    "Tarifa (Cádiz)":        "11033",
    "Briviesca (Burgos)":    "09059",
    "La Muela (Zaragoza)":   "50157",
    "El Andévalo (Huelva)":  "21041",
}


def get_daily_forecast(municipio_id: str, nombre: str) -> Optional[Dict]:
    """
    Consulta la predicción diaria de un municipio AEMET.
    Devuelve (velmedia_ms, racha_ms) para mañana en m/s, o None si falla.
    """
    if not AEMET_API_KEY:
        logger.warning("AEMET_API_KEY no configurada")
        return None

    manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"{AEMET_BASE_URL}/prediccion/especifica/municipio/diaria/{municipio_id}"

    try:
        r1 = requests.get(url, params={"api_key": AEMET_API_KEY}, headers=HEADERS, timeout=15)
        if r1.status_code != 200:
            logger.warning(f"AEMET [{nombre}] HTTP {r1.status_code}")
            return None

        data_url = r1.json().get("datos")
        if not data_url:
            return None

        time.sleep(0.5)
        r2 = requests.get(data_url, headers=HEADERS, timeout=15)
        if r2.status_code != 200:
            return None

        pred = r2.json()
        if not isinstance(pred, list) or not pred:
            return None

        dias = pred[0].get("prediccion", {}).get("dia", [])
        for dia in dias:
            if str(dia.get("fecha", "")).startswith(manana):
                vientos = dia.get("viento", [])
                rachas  = dia.get("rachaMax", [])

                velocidades = [
                    float(v["velocidad"]) for v in vientos
                    if v.get("velocidad") not in (None, "")
                ]
                rachas_val = [
                    float(r["value"]) for r in rachas
                    if r.get("value") not in (None, "")
                ]

                vel_media = float(np.mean(velocidades)) if velocidades else None
                racha_max = float(np.max(rachas_val))   if rachas_val  else None

                if vel_media is None:
                    return None

                # AEMET devuelve km/h → convertir a m/s (igual que en el notebook)
                return {
                    "velmedia": round(vel_media / 3.6, 3),
                    "racha":    round(racha_max / 3.6, 3) if racha_max else 0.0,
                }

        logger.debug(f"No se encontró predicción para mañana en municipio {municipio_id}")
        return None

    except Exception as e:
        logger.error(f"Error consultando AEMET [{nombre}]: {e}")
        return None


def get_aggregated_forecast() -> Optional[Dict]:
    """
    Consulta todos los municipios eólicos y devuelve la media de velmedia y racha.
    """
    if not AEMET_API_KEY:
        logger.warning("AEMET_API_KEY no configurada — forecast no disponible")
        return None

    resultados = []
    for nombre, mun_id in MUNICIPIOS_EOLICOS.items():
        forecast = get_daily_forecast(mun_id, nombre)
        if forecast:
            resultados.append(forecast)
            logger.info(f"  ✅ {nombre}: velmedia={forecast['velmedia']} m/s, racha={forecast['racha']} m/s")
        else:
            logger.warning(f"  ⚠️  Sin datos para {nombre} ({mun_id})")
        time.sleep(0.5)

    if not resultados:
        logger.error("No se obtuvieron datos de ninguna estación eólica")
        return None

    velmedia_media = float(np.mean([r["velmedia"] for r in resultados]))
    racha_media    = float(np.mean([r["racha"]    for r in resultados]))

    return {
        "fecha":    (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "velmedia": round(velmedia_media, 3),
        "racha":    round(racha_media, 3),
        "estaciones": {str(i): r for i, r in enumerate(resultados)},
    }


def download_aemet_diario(fecha: str) -> list:
    """
    Descarga mediciones climatológicas diarias para las 6 estaciones eólicas.
    Usa la API histórica de AEMET (dos pasos: meta-URL → datos).
    Retorna lista de dicts [{fecha, indicativo, velmedia, racha}, ...].
    """
    if not AEMET_API_KEY:
        logger.warning("AEMET_API_KEY no configurada — omitiendo descarga histórica")
        return []

    fecha_ini_iso = f"{fecha}T00:00:00UTC"
    fecha_fin_iso = f"{fecha}T23:59:59UTC"
    resultados = []

    for station_id in ESTACIONES_EOLICAS:
        url = (
            f"{AEMET_BASE_URL}/valores/climatologicos/diarios/datos"
            f"/fechaini/{fecha_ini_iso}"
            f"/fechafin/{fecha_fin_iso}"
            f"/estacion/{station_id}"
        )

        # Paso 1: obtener URL de datos (con un reintento en timeout)
        r1 = None
        for attempt in range(2):
            try:
                r1 = requests.get(url, params={"api_key": AEMET_API_KEY},
                                  headers=HEADERS, timeout=15)
                break
            except requests.exceptions.Timeout:
                if attempt == 0:
                    logger.warning(f"AEMET timeout [{station_id}] — reintentando en 3s")
                    time.sleep(3)
                else:
                    logger.error(f"AEMET timeout definitivo [{station_id}]")
            except requests.exceptions.RequestException as e:
                logger.error(f"AEMET error de red [{station_id}]: {e}")
                break

        if r1 is None:
            time.sleep(0.5)
            continue

        if r1.status_code == 429:
            logger.warning("AEMET rate limit (429) — esperando 60s")
            time.sleep(60)
            try:
                r1 = requests.get(url, params={"api_key": AEMET_API_KEY},
                                  headers=HEADERS, timeout=15)
            except Exception as e:
                logger.error(f"AEMET fallo tras rate limit [{station_id}]: {e}")
                time.sleep(0.5)
                continue

        if r1.status_code != 200:
            logger.warning(f"AEMET [{station_id}] paso 1 HTTP {r1.status_code}")
            time.sleep(0.5)
            continue

        try:
            datos_url = r1.json().get("datos")
        except Exception as e:
            logger.error(f"AEMET [{station_id}] JSON inválido paso 1: {e}")
            time.sleep(0.5)
            continue

        if not datos_url:
            logger.warning(f"AEMET [{station_id}] sin URL de datos para {fecha}")
            time.sleep(0.5)
            continue

        # Paso 2: descargar registros
        time.sleep(0.5)
        try:
            r2 = requests.get(datos_url, headers=HEADERS, timeout=15)
        except requests.exceptions.RequestException as e:
            logger.error(f"AEMET [{station_id}] error descargando datos: {e}")
            time.sleep(0.5)
            continue

        if r2.status_code != 200:
            logger.warning(f"AEMET [{station_id}] paso 2 HTTP {r2.status_code}")
            time.sleep(0.5)
            continue

        try:
            registros = r2.json()
        except Exception as e:
            logger.error(f"AEMET [{station_id}] JSON inválido paso 2: {e}")
            time.sleep(0.5)
            continue

        if not isinstance(registros, list) or not registros:
            logger.warning(f"AEMET [{station_id}] sin registros para {fecha}")
            time.sleep(0.5)
            continue

        for rec in registros:
            vel_raw   = rec.get("velmedia")
            racha_raw = rec.get("racha")
            if not vel_raw or not racha_raw:
                continue
            try:
                velmedia = float(str(vel_raw).replace(",", "."))
                racha    = float(str(racha_raw).replace(",", "."))
            except (ValueError, TypeError):
                continue
            resultados.append({
                "fecha":      rec.get("fecha", fecha),
                "indicativo": rec.get("indicativo", station_id),
                "velmedia":   velmedia,
                "racha":      racha,
            })

        time.sleep(0.5)

    logger.info(
        f"download_aemet_diario({fecha}): {len(resultados)} registros "
        f"de {len(ESTACIONES_EOLICAS)} estaciones"
    )
    return resultados