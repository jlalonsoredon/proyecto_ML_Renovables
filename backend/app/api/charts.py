from fastapi import APIRouter
from typing import List
from datetime import date, datetime, timedelta, timezone
import logging
import json
import math
import os
from zoneinfo import ZoneInfo
import numpy as np
from fastapi import HTTPException

from ..services import db_ree
from ..services.model_loader import model_service
from ..services.redaction import redact_secrets

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

METRICS_PATH = os.environ.get(
    "METRICS_PATH", "modelos/familia_como_modelo.json"
)
MADRID = ZoneInfo("Europe/Madrid")


@router.get("/historical")
def get_historical(days: int = 30):
    from ..services.ree_client import ensure_recent_data

    # Actualizar BD con datos de REE si hay días sin cubrir
    try:
        updated, msg = ensure_recent_data(days=max(days, 30))
        if updated:
            logger.info(f"Datos REE actualizados: {msg}")
    except Exception as e:
        logger.warning(
            "No se pudo actualizar datos REE: %s",
            redact_secrets(e),
        )

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
    historicos = [
        {"modelo": "Linear Regression",  "rmse": 60432.9, "r2": 0.579,  "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Lasso",              "rmse": 60433.1, "r2": 0.579,  "mape": 41.73, "accuracy": 42.6},
        {"modelo": "Random Forest",      "rmse": 60437.6, "r2": 0.5789, "mape": 44.30, "accuracy": 36.3},
        {"modelo": "Ridge",              "rmse": 60498.1, "r2": 0.5781, "mape": 41.95, "accuracy": 42.0},
        {"modelo": "LightGBM",           "rmse": 61872.5, "r2": 0.5587, "mape": 44.46, "accuracy": 37.2},
        {"modelo": "XGBoost",            "rmse": 63346.3, "r2": 0.5374, "mape": 45.87, "accuracy": 36.6},
        {"modelo": "Red Neuronal (MLP)", "rmse": 63909.6, "r2": 0.5291, "mape": 43.22, "accuracy": 37.5},
    ]
    historicos = [
        {**fila, "n_variables": 16, "historico": True}
        for fila in historicos
    ]
    try:
        with open(METRICS_PATH, encoding="utf-8") as f:
            acta = json.load(f)
        metricas = acta["metricas_globales"]
        folds = acta["folds"]
        modelo = acta["modelo"]
        if modelo.get("features_produccion") != model_service.features:
            raise ValueError("las métricas no corresponden al artefacto cargado")

        filas_actuales = []
        for tipo, nombre, rol, decision in (
            ("base", "Linear Regression (19 variables)", "produccion", "vigente"),
            ("variante", "LightGBM (19 variables)", "candidata_rechazada", "rechazado"),
        ):
            globales = metricas[tipo]
            filas_actuales.append({
                "modelo": nombre,
                "rmse": globales["rmse"],
                "mae": globales["mae"],
                "r2": globales["r2"],
                "mape": None,
                "accuracy": None,
                "n": globales["n"],
                "n_variables": 19,
                "historico": False,
                "rol": rol,
                "decision": decision,
                "motivo": acta.get("criterio", {}).get("motivo", ""),
                "folds": [
                    {
                        "año": fold["año"],
                        "rmse": fold[tipo]["rmse"],
                        "mae": fold[tipo]["mae"],
                        "r2": fold[tipo]["r2"],
                    }
                    for fold in folds
                    if not fold.get("omitido") and fold.get(tipo)
                ],
            })
        return historicos + filas_actuales
    except Exception as error:
        logger.error("No se pudo leer el acta del modelo: %s", error)
        raise HTTPException(
            status_code=503,
            detail="El informe de comparación del modelo no está disponible",
        ) from error


@router.get("/feature-importance")
def get_feature_importance():
    if not model_service.ready or not model_service.features:
        raise HTTPException(status_code=503, detail="Modelo de producción no disponible")
    try:
        coefs = np.abs(np.asarray(model_service.model.coef_, dtype=float)).reshape(-1)
        if len(coefs) != len(model_service.features):
            raise ValueError("coeficientes no alineados con las features")
        total = float(coefs.sum())
        if not np.isfinite(total) or total <= 0:
            raise ValueError("el modelo no tiene coeficientes utilizables")
        return [
            {"feature": feat, "importance": round(float(value / total), 4)}
            for feat, value in sorted(
                zip(model_service.features, coefs),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
    except Exception as error:
        logger.error("No se pudo calcular la importancia del modelo: %s", error)
        raise HTTPException(
            status_code=503, detail="La importancia del modelo no está disponible"
        ) from error


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


def get_historico_eolica(days: int, hoy=None) -> List[dict]:
    """
    Devuelve [{"fecha": "YYYY-MM-DD", "eolica": float}, ...] de los últimos `days`
    días disponibles en la tabla `generacion`.

    `db_ree.get_generation_series` convierte primero el timestamp UTC al día
    natural de Europe/Madrid antes de agregar.
    """
    if hoy is None:
        from ..services.prediction_service import today_in_madrid

        hoy = today_in_madrid()
    series = db_ree.get_generation_series(hoy=hoy)
    fechas = sorted(series)[-int(days):]
    return [
        {"fecha": fecha.isoformat(), "eolica": float(series[fecha])}
        for fecha in fechas
    ]


def _chart_date(value) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(MADRID).date()
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _chart_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _chart_json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _chart_emission_time(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=MADRID)
    return stamp.astimezone(timezone.utc)


def _chart_prediction_key(row):
    return (
        _chart_date(row.get("fecha_emision")),
        _chart_emission_time(row.get("emitida_en")),
    )


def _chart_api_prediction(row) -> dict:
    """Copia una fila canónica sin cambiar unidades ni perder trazabilidad."""
    return {
        "fecha_objetivo": _chart_date(row["fecha_objetivo"]).isoformat(),
        "fecha_emision": _chart_date(row["fecha_emision"]).isoformat(),
        "emitida_en": row.get("emitida_en"),
        "prediccion_mwh": _chart_number(row.get("prediccion_mwh")),
        "modelo": row.get("modelo"),
        "n_variables": row.get("n_variables"),
        "vector_entrada": _chart_json_object(row.get("vector_entrada")),
        "origenes": _chart_json_object(row.get("origenes")),
        "real_mwh": _chart_number(row.get("real_mwh")),
        "error_mwh": _chart_number(row.get("error_mwh")),
    }


def build_prediction_chart_payload(
    historico, viento, predicciones_propias, hoy, avisos=None
) -> dict:
    """Forma la respuesta con observaciones y emisiones guardadas, sin predicción nueva."""
    hoy = _chart_date(hoy)
    normalizado = []
    for row in historico or []:
        try:
            fecha = _chart_date(row["fecha"])
        except (KeyError, TypeError, ValueError):
            continue
        valor = _chart_number(row.get("eolica", row.get("eolica_mwh")))
        if valor is not None:
            normalizado.append({"fecha": fecha, "eolica": valor})
    normalizado.sort(key=lambda row: row["fecha"])
    normalizado = normalizado[-30:]

    fechas = [row["fecha"].isoformat() for row in normalizado]
    fechas_set = set(fechas)
    viento = viento or {}
    vel_hist = [
        _chart_number((viento.get(fecha) or {}).get("velmedia"))
        for fecha in fechas
    ]
    racha_hist = [
        _chart_number((viento.get(fecha) or {}).get("racha"))
        for fecha in fechas
    ]

    emisiones = []
    for row in predicciones_propias or []:
        try:
            emisiones.append(_chart_api_prediction(row))
        except (KeyError, TypeError, ValueError):
            continue
    emisiones.sort(
        key=lambda row: (
            row["fecha_objetivo"],
            row["fecha_emision"],
            _chart_emission_time(row["emitida_en"]),
        )
    )
    emisiones_historicas = [
        row for row in emisiones if row["fecha_objetivo"] in fechas_set
    ]

    ultima_por_objetivo = {}
    for row in emisiones:
        target = row["fecha_objetivo"]
        previous = ultima_por_objetivo.get(target)
        if previous is None or _chart_prediction_key(row) > _chart_prediction_key(previous):
            ultima_por_objetivo[target] = row

    pred_gwh = [
        (
            round(ultima_por_objetivo[fecha]["prediccion_mwh"] / 1000, 2)
            if fecha in ultima_por_objetivo
            and ultima_por_objetivo[fecha]["prediccion_mwh"] is not None
            else None
        )
        for fecha in fechas
    ]

    vel_validos = [value for value in vel_hist if value is not None]
    racha_validas = [value for value in racha_hist if value is not None]
    suficientes_vel = len(vel_validos) >= 2
    suficientes_racha = len(racha_validas) >= 2
    vel_mean = float(np.mean(vel_validos)) if vel_validos else 0.0
    vel_std = max(float(np.std(vel_validos)), 0.001) if vel_validos else 1.0
    racha_mean = float(np.mean(racha_validas)) if racha_validas else 0.0
    racha_std = max(float(np.std(racha_validas)), 0.001) if racha_validas else 1.0

    def znorm(value, mean, std, sufficient):
        if value is None or not sufficient:
            return None
        return round((float(value) - mean) / std, 3)

    target_manana = (hoy + timedelta(days=1)).isoformat()
    prediction = ultima_por_objetivo.get(target_manana)
    vector = prediction["vector_entrada"] if prediction else {}
    origenes = prediction["origenes"] if prediction else {}
    vel_manana = _chart_number(vector.get("velmedia"))
    racha_manana = _chart_number(vector.get("racha"))
    prediction_mwh = prediction["prediccion_mwh"] if prediction else None
    avisos_finales = list(avisos or [])
    if not normalizado:
        avisos_finales.append("Sin datos históricos disponibles en la BD")
    if prediction_mwh is None:
        avisos_finales.append(
            "No hay una predicción propia disponible para mañana; no se ha aplicado fallback."
        )

    return {
        "fechas_hist": fechas,
        "real_gwh": [round(row["eolica"] / 1000, 2) for row in normalizado],
        "pred_gwh": pred_gwh,
        "vel_norm": [
            znorm(value, vel_mean, vel_std, suficientes_vel)
            for value in vel_hist
        ],
        "racha_norm": [
            znorm(value, racha_mean, racha_std, suficientes_racha)
            for value in racha_hist
        ],
        "vel_ms": [
            round(value, 2) if value is not None else None
            for value in vel_hist
        ],
        "racha_ms": [
            round(value, 2) if value is not None else None
            for value in racha_hist
        ],
        "manana": {
            "fecha": target_manana,
            "pred_gwh": (
                round(prediction_mwh / 1000, 2)
                if prediction_mwh is not None else None
            ),
            "es_fallback": False,
            "estado": "disponible" if prediction_mwh is not None else "no_disponible",
            "vel_norm": znorm(vel_manana, vel_mean, vel_std, suficientes_vel),
            "racha_norm": znorm(racha_manana, racha_mean, racha_std, suficientes_racha),
            "velmedia": round(vel_manana, 1) if vel_manana is not None else None,
            "racha": round(racha_manana, 1) if racha_manana is not None else None,
            "prediccion_mwh": prediction_mwh,
            "modelo": prediction.get("modelo") if prediction else None,
            "n_variables": prediction.get("n_variables") if prediction else None,
            "vector_entrada": vector if prediction else None,
            "origenes": origenes if prediction else None,
            "fecha_emision": prediction.get("fecha_emision") if prediction else None,
            "emitida_en": prediction.get("emitida_en") if prediction else None,
        },
        "predicciones_propias": emisiones_historicas,
        "avisos": list(dict.fromkeys(avisos_finales)),
    }


def build_current_chart(hoy) -> dict:
    """Lee el histórico y las emisiones persistidas para `hoy`; no consulta fuentes."""
    manana = hoy + timedelta(days=1)
    avisos = []
    try:
        historico = get_historico_eolica(30, hoy=hoy)
    except Exception as error:
        logger.error("Error obteniendo datos históricos para el gráfico: %s", error)
        historico = []
        avisos.append("No se pudieron leer datos históricos de generación")

    fechas = [row["fecha"] for row in historico]
    try:
        viento = db_ree.get_wind_for_dates(fechas)
    except Exception as error:
        logger.warning("No se pudieron leer observaciones de viento: %s", error)
        viento = {}
        avisos.append("No se pudieron leer datos de viento históricos")

    try:
        emisiones = db_ree.get_own_predictions(
            desde=fechas[0] if fechas else manana,
            hasta=manana,
        )
    except Exception as error:
        logger.warning("No se pudieron leer predicciones propias: %s", error)
        emisiones = []
        avisos.append("No se pudieron leer predicciones propias guardadas")

    return build_prediction_chart_payload(
        historico,
        viento,
        emisiones,
        hoy,
        avisos,
    )


@router.get("/prediction-chart")
def get_prediction_chart():
    """Devuelve el histórico y las emisiones persistidas; no consulta fuentes."""
    from ..services.prediction_service import today_in_madrid

    return build_current_chart(today_in_madrid())
