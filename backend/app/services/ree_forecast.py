"""Captura de la previsión D+1 del indicador ESIOS 1777."""

import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from . import forecast_db
from .ree_forecast_logic import parse_ree_d1

logger = logging.getLogger(__name__)

ESIOS_URL = "https://api.esios.ree.es/indicators/1777"
ESIOS_TIMEOUT = 60
GEO_PENINSULA = 8741
MADRID = ZoneInfo("Europe/Madrid")


def _hoy(value=None) -> date:
    if value is None:
        return datetime.now(MADRID).date()
    if isinstance(value, datetime):
        return value.astimezone(MADRID).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def capture_ree_forecast(hoy=None, session=requests, api_key=None,
                         captured_at=None, conn=None) -> dict:
    """Descarga y archiva solo el D+1; no reconstruye el histórico."""
    hoy_local = _hoy(hoy)
    objetivo = hoy_local + timedelta(days=1)
    token = api_key if api_key is not None else os.environ.get("REE_API_KEY", "")
    capturado = captured_at or datetime.now(MADRID)
    if not token:
        motivo = "falta REE_API_KEY en el entorno"
        logger.error("Captura REE omitida: %s", motivo)
        return {
            "estado": "fallo",
            "objetivo": objetivo.isoformat(),
            "filas_guardadas": 0,
            "errores": [motivo],
        }

    dia = objetivo.isoformat()
    params = {
        "start_date": f"{dia}T00:00",
        "end_date": f"{dia}T23:59",
        "time_trunc": "day",
        "geo_ids[]": GEO_PENINSULA,
    }
    headers = {"x-api-key": token, "Accept": "application/json"}
    try:
        response = session.get(ESIOS_URL, params=params, headers=headers, timeout=ESIOS_TIMEOUT)
    except requests.exceptions.RequestException as error:
        motivo = f"fallo de red ESIOS: {error}"
        logger.error("Captura REE: %s", motivo)
        return {
            "estado": "fallo",
            "objetivo": dia,
            "filas_guardadas": 0,
            "errores": [motivo],
        }

    if response.status_code != 200:
        motivo = (
            f"credencial ESIOS rechazada (HTTP {response.status_code})"
            if response.status_code in (401, 403)
            else f"ESIOS HTTP {response.status_code}"
        )
        logger.error("Captura REE: %s", motivo)
        return {
            "estado": "fallo",
            "objetivo": dia,
            "filas_guardadas": 0,
            "errores": [motivo],
        }
    try:
        payload = response.json()
    except ValueError:
        motivo = "respuesta ESIOS no es JSON"
        logger.error("Captura REE: %s", motivo)
        return {
            "estado": "fallo",
            "objetivo": dia,
            "filas_guardadas": 0,
            "errores": [motivo],
        }

    parsed = parse_ree_d1(payload, objetivo, hoy_local, capturado)
    filas_guardadas = 0
    if parsed["fila"] is not None:
        fila = dict(parsed["fila"])
        fila["capturado_en"] = capturado
        filas_guardadas = forecast_db.save_forecast_rows(
            conn, [fila], "ree", parte=payload
        )

    estado = "ok" if filas_guardadas else "fallo"
    resumen = {
        "estado": estado,
        "objetivo": dia,
        "filas_guardadas": filas_guardadas,
        "errores": parsed["motivos"],
    }
    logger.info(
        "Captura REE %s: %d filas; %d avisos",
        dia,
        filas_guardadas,
        len(parsed["motivos"]),
    )
    return resumen
