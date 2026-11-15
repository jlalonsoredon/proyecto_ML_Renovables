"""Orquestación de predicción, persistencia y reconciliación de reales."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import db_ree, forecast_db
from .forecast_logic import generation_lags
from .model_loader import FEATURE_COLS, model_service
from .prediction_features import build_prediction_map

logger = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")


class PredictionUnavailable(RuntimeError):
    """No hay un vector LR-19 completo y honesto para el objetivo."""

    def __init__(self, fecha: str, faltan=None, avisos=None, detail=None):
        self.fecha = fecha
        self.faltan = list(faltan or [])
        self.avisos = list(avisos or [])
        self.detail = detail or "Predicción no disponible"
        super().__init__(self.detail)

    def response(self) -> dict:
        return {
            "detail": self.detail,
            "fecha": self.fecha,
            "faltan": self.faltan,
            "avisos": self.avisos,
        }


def today_in_madrid() -> date:
    """Único límite de reloj de la aplicación; la lógica recibe la fecha."""
    return datetime.now(MADRID).date()


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.astimezone(MADRID).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _valid_cached_prediction(row: dict | None) -> bool:
    if not row:
        return False
    if row.get("modelo") != model_service.family or row.get("n_variables") != 19:
        return False
    vector = row.get("vector_entrada") or {}
    origins = row.get("origenes") or {}
    if tuple(vector) != tuple(FEATURE_COLS) or tuple(origins) != tuple(FEATURE_COLS):
        return False
    if any(not isinstance(value, (int, float)) or not math.isfinite(float(value))
           for value in vector.values()):
        return False
    valid_origins = {"observacion", "prevision", "mixta", "estimada"}
    return all(origin in valid_origins for origin in origins.values())


class PredictionService:
    def __init__(self, model=None, data_store=None, clock=None):
        self.model = model or model_service
        self.data_store = data_store or db_ree
        self.clock = clock or today_in_madrid

    def _load_inputs(self, hoy: date) -> tuple[dict, dict, dict, list, list]:
        objetivo = hoy + timedelta(days=1)
        observations_wind = self.data_store.get_wind_observations(hoy, days=35)
        observations_solar = self.data_store.get_solar_observations(hoy, days=35)
        observations_generation = self.data_store.get_generation_series(hoy=hoy)
        desde = objetivo - timedelta(days=14)
        with self.data_store._get_conn() as conn:
            forecast_rows = forecast_db.rows_between(conn, desde, objetivo)
        aemet_rows = [row for row in forecast_rows if row.get("fuente") == "aemet"]
        ree_rows = [row for row in forecast_rows if row.get("fuente") == "ree"]
        return (
            observations_wind,
            observations_solar,
            observations_generation,
            aemet_rows,
            ree_rows,
        )

    def build_prediction(self, hoy=None) -> dict:
        hoy_local = _as_date(hoy or self.clock())
        objetivo = hoy_local + timedelta(days=1)
        if not self.model.ready:
            raise PredictionUnavailable(
                objetivo.isoformat(),
                avisos=[f"Modelo de producción no disponible: {self.model.load_error}"],
            )

        (obs_meteo, obs_solar, obs_gen, aemet_rows, ree_rows) = self._load_inputs(hoy_local)
        resolved = build_prediction_map(
            obs_meteo,
            obs_solar,
            obs_gen,
            aemet_rows,
            ree_rows,
            hoy_local,
        )
        if resolved["faltan"]:
            raise PredictionUnavailable(
                objetivo.isoformat(),
                faltan=resolved["faltan"],
                avisos=[
                    "No se emite predicción porque faltan entradas obligatorias.",
                    *([resolved["aviso_generacion"]] if resolved.get("aviso_generacion") else []),
                ],
            )

        vector = resolved["vector_entrada"]
        try:
            prediction = self.model.predict_vector(vector)
        except Exception as error:
            logger.exception("No se pudo aplicar el artefacto LR-19")
            raise PredictionUnavailable(
                objetivo.isoformat(),
                avisos=[f"Error al aplicar el modelo: {type(error).__name__}"],
            ) from error

        emitida_en = datetime.now(MADRID)
        record = {
            "fecha_objetivo": objetivo,
            "fecha_emision": hoy_local,
            "emitida_en": emitida_en.isoformat(),
            "prediccion_mwh": float(prediction),
            "modelo": self.model.family,
            "n_variables": len(FEATURE_COLS),
            "vector_entrada": vector,
            "origenes": resolved["origenes"],
            "real_mwh": None,
            "error_mwh": None,
        }
        self.data_store.save_own_prediction(record)
        return self._api_prediction(record)

    @staticmethod
    def _api_prediction(record: dict) -> dict:
        vector = record.get("vector_entrada") or {}
        return {
            "fecha": _as_date(record["fecha_objetivo"]).isoformat(),
            "prediccionMWh": round(float(record["prediccion_mwh"]), 0),
            "modelo": record["modelo"],
            "features": {
                "velmedia": vector.get("velmedia"),
                "racha": vector.get("racha"),
            },
            "n_variables": int(record.get("n_variables") or 0),
            "vector_entrada": vector,
            "origenes": record.get("origenes") or {},
            "fecha_emision": _as_date(record["fecha_emision"]).isoformat(),
            "emitida_en": record.get("emitida_en"),
        }

    def get_prediction(self, hoy=None) -> dict:
        hoy_local = _as_date(hoy or self.clock())
        objetivo = hoy_local + timedelta(days=1)
        if self.model.ready:
            cached = self.data_store.get_own_prediction(objetivo)
            if _valid_cached_prediction(cached):
                return self._api_prediction(cached)
        return self.build_prediction(hoy_local)

    def refresh_prediction(self, hoy=None) -> dict:
        return self.build_prediction(hoy)

    def reconcile_reals(self, hoy=None) -> int:
        hoy_local = _as_date(hoy or self.clock())
        generation = self.data_store.get_generation_series(hoy=hoy_local)
        if not generation:
            return 0
        diagnostic = generation_lags(generation, hoy_local)
        discarded = {
            _as_date(row["fecha"])
            for row in diagnostic["frescura"].get("descartados", [])
        }
        updates = 0
        for prediction in self.data_store.predictions_without_real(hoy_local):
            target = _as_date(prediction["fecha_objetivo"])
            real = generation.get(target)
            if target > hoy_local or target in discarded or real is None:
                continue
            updates += self.data_store.update_own_prediction_real(target, real)
        return updates

    def forecast_payload(self, hoy=None) -> dict:
        hoy_local = _as_date(hoy or self.clock())
        objetivo = hoy_local + timedelta(days=1)
        desde = objetivo - timedelta(days=14)
        with self.data_store._get_conn() as conn:
            rows = forecast_db.rows_between(conn, desde, objetivo)
        aemet_rows = [row for row in rows if row.get("fuente") == "aemet"]
        ree_rows = [row for row in rows if row.get("fuente") == "ree"]
        aemet = build_prediction_map(
            {}, {}, {}, aemet_rows, [], hoy_local
        )
        from .prediction_features import select_aemet_forecast

        locations = sorted({
            row["ubicacion"] for row in aemet_rows
            if row.get("objetivo") == objetivo and row.get("uso") == "eolica"
        })
        wind_rows = {}
        for location in locations:
            selected = select_aemet_forecast(
                aemet_rows, objetivo, location, hoy_local, uso="eolica"
            )
            if selected is not None:
                wind_rows[location] = selected
        ree_payload = None
        from .prediction_features import resolve_eolica_prev

        ree_value = resolve_eolica_prev(ree_rows, objetivo, hoy_local)
        if ree_value is not None:
            ree_payload = {
                "fecha": objetivo.isoformat(),
                "eolica_mwh": ree_value["valor"],
                "elaborado": ree_value.get("elaborado"),
                "origen": ree_value["origen"],
            }
            if ree_value["origen"] == "estimada":
                ree_payload["dias_media"] = ree_value["dias_media"]
        wind = aemet.get("mapa", {})
        avisos = []
        if wind.get("velmedia", {}).get("valor") is None:
            avisos.append("No hay previsión AEMET archivada para el objetivo.")
        if ree_payload is None:
            avisos.append("No hay previsión REE elegible para el objetivo.")
        return {
            "fecha": objetivo.isoformat(),
            "velmedia": wind.get("velmedia", {}).get("valor"),
            "racha": wind.get("racha", {}).get("valor"),
            "estaciones": {
                name: {
                    "velmedia": row.get("viento_ms"),
                    "racha": row.get("racha_ms"),
                }
                for name, row in wind_rows.items()
            },
            "ree": ree_payload,
            "avisos": avisos,
        }


prediction_service = PredictionService()
