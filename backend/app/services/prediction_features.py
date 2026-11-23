"""Lógica pura para construir el vector LR-19 y declarar cada origen."""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import forecast_logic

FEATURE_COLS = (
    "velmedia", "racha", "mes", "dia_semana", "dia_año",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14",
    "eolica_ma7", "sol_lag1", "tmed_lag1", "eolica_prev",
)

ORIGINS = frozenset(("observacion", "prevision", "mixta", "estimada"))
MAX_REE_FORECAST_MWH = 720_000.0
REE_ANOMALY_RATIO = 0.60
REE_CONTEXT_DAYS = 7
REE_MIN_CONTEXT_VALUES = 5
MADRID = ZoneInfo("Europe/Madrid")


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _instant(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        instante = value
    elif isinstance(value, date):
        instante = datetime.combine(value, datetime.min.time())
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            instante = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=MADRID)
    return instante.astimezone(MADRID)


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _entry(value, origin, **details) -> dict:
    number = _number(value)
    if number is None or origin not in ORIGINS:
        return {"valor": None, "origen": None}
    return {"valor": number, "origen": origin, **details}


def _normalized_series(series) -> dict[date, float]:
    result = {}
    for raw_day, raw_value in (series or {}).items():
        value = _number(raw_value)
        if value is not None:
            result[_date(raw_day)] = value
    return result


def _eligible_aemet(rows, objetivo, ubicacion: str, hoy,
                    uso: str | None = None) -> dict | None:
    candidates = _aemet_candidates(rows, objetivo, ubicacion, hoy, uso=uso)
    return dict(candidates[0]) if candidates else None


def _eligible_aemet_values(rows, objetivo, ubicacion: str, hoy, uso: str,
                           names) -> dict | None:
    """Último valor no nulo de cada variable entre las elaboraciones elegibles.

    Un parte capturado de noche ya no trae el cielo de las horas de luz del
    día en curso y deja `sol` en null; en ese caso se conserva el valor de la
    elaboración anterior en vez de perder la variable.
    """
    candidates = _aemet_candidates(rows, objetivo, ubicacion, hoy, uso=uso)
    if not candidates:
        return None
    values = {}
    for name in names:
        values[name] = next(
            (
                _number(row.get(name)) for row in candidates
                if _number(row.get(name)) is not None
            ),
            None,
        )
    return values


def _aemet_candidates(rows, objetivo, ubicacion: str, hoy,
                      uso: str | None = None) -> list[dict]:
    """Elaboraciones elegibles de una ubicación/día, de la más nueva a la más vieja."""
    objetivo = _date(objetivo)
    cutoff = min(objetivo, _date(hoy))
    candidates = []
    for row in rows or []:
        if row.get("fuente", "aemet") != "aemet":
            continue
        if row.get("ubicacion") != ubicacion:
            continue
        if uso is not None and row.get("uso") != uso:
            continue
        if _date(row["objetivo"]) != objetivo:
            continue
        elaborado = _instant(row.get("elaborado"))
        if elaborado is None or elaborado.date() > cutoff:
            continue
        capturado = _instant(row.get("capturado_en")) or elaborado
        candidates.append((elaborado, capturado, row))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _, _, row in candidates]


def select_aemet_forecast(rows, objetivo, ubicacion: str, hoy,
                          uso: str | None = None) -> dict | None:
    """Elige la última elaboración AEMET elegible para una ubicación/día."""
    return _eligible_aemet(rows, objetivo, ubicacion, hoy, uso=uso)


def aggregate_observations(rows, station_ids, variable: str, hoy) -> dict[str, float]:
    """Media por fecha de las estaciones pedidas, sin duplicados ni días futuros."""
    hoy = _date(hoy)
    stations = set(station_ids)
    values_by_day: dict[date, list[float]] = {}
    seen = set()
    for row in rows or []:
        day = _date(row["fecha"])
        station = row.get("indicativo")
        if day > hoy or station not in stations or (day, station) in seen:
            continue
        value = _number(row.get(variable))
        if value is None:
            continue
        seen.add((day, station))
        values_by_day.setdefault(day, []).append(value)
    return {
        day.isoformat(): sum(values) / len(values)
        for day, values in sorted(values_by_day.items())
        if values
    }


def aemet_national_series(rows, uso: str, hoy) -> dict[str, dict]:
    """Medias diarias de las ubicaciones AEMET elegibles del uso solicitado.

    Las filas `nacional` son un agregado durable que solo se usa cuando no hay
    ninguna fila por ubicación para ese día. Así el bootstrap del snapshot no
    se promedia con las ubicaciones ni duplica el valor.
    """
    rows = list(rows or [])
    locations = sorted({
        row.get("ubicacion") for row in rows
        if row.get("fuente", "aemet") == "aemet"
        and row.get("uso") == uso
        and row.get("ubicacion")
        and row.get("ubicacion") != "nacional"
    })
    targets = sorted({
        _date(row["objetivo"]) for row in rows
        if row.get("fuente", "aemet") == "aemet" and row.get("uso") == uso
    })
    names = ("viento_ms", "racha_ms", "sol", "tmed")
    result = {}
    for target in targets:
        day_values = {name: [] for name in names}
        for location in locations:
            values = _eligible_aemet_values(
                rows, target, location, hoy, uso, names
            )
            if values is None:
                continue
            for name in names:
                if values[name] is not None:
                    day_values[name].append(values[name])
        if not any(day_values.values()):
            national = _eligible_aemet_values(
                rows, target, "nacional", hoy, uso, names
            )
            if national is None:
                continue
            result[target] = national
            continue
        result[target] = {
            name: sum(values) / len(values) if values else None
            for name, values in day_values.items()
        }
    return {
        target.isoformat(): values
        for target, values in sorted(result.items())
    }


def resolve_window(observaciones, previsiones, objetivo, dias: int, hoy) -> dict:
    """Media exacta de días naturales con prioridad observación/previsión."""
    if dias <= 0:
        raise ValueError(f"la ventana debe ser positiva: {dias}")
    objetivo = _date(objetivo)
    hoy = _date(hoy)
    obs = _normalized_series(observaciones)
    prev = _normalized_series(previsiones)
    dates = [objetivo - timedelta(days=offset) for offset in range(dias - 1, -1, -1)]
    values = []
    missing = []
    n_observed = n_forecast = 0
    for day in dates:
        if day <= hoy and day in obs:
            values.append(obs[day])
            n_observed += 1
        elif day in prev:
            values.append(prev[day])
            n_forecast += 1
        else:
            missing.append(day.isoformat())
    if missing:
        return {
            "valor": None,
            "origen": None,
            "dias_observados": n_observed,
            "dias_previstos": n_forecast,
            "faltantes": missing,
        }
    origin = (
        "observacion" if n_forecast == 0
        else "prevision" if n_observed == 0
        else "mixta"
    )
    return {
        "valor": sum(values) / len(values),
        "origen": origin,
        "dias_observados": n_observed,
        "dias_previstos": n_forecast,
        "faltantes": [],
    }


def latest_complete_generation(series, hoy) -> dict:
    """Descarta el último día REE si queda por debajo de su entorno de 7 días."""
    hoy = _date(hoy)
    values = {
        day: value for day, value in _normalized_series(series).items()
        if day <= hoy
    }
    discarded = []
    while values:
        latest = max(values)
        context = [
            values[latest - timedelta(days=offset)]
            for offset in range(1, REE_CONTEXT_DAYS + 1)
            if latest - timedelta(days=offset) in values
        ]
        if len(context) < REE_MIN_CONTEXT_VALUES:
            break
        median = float(statistics.median(context))
        if median <= 0 or values[latest] >= REE_ANOMALY_RATIO * median:
            break
        discarded.append(latest.isoformat())
        del values[latest]
    anchor = max(values) if values else None
    return {
        "ancla": anchor.isoformat() if anchor else None,
        "descartados": discarded,
        "aviso": (
            f"se descartan {len(discarded)} día(s) REE incompletos"
            if discarded else None
        ),
    }


def _valid_ree_value(value) -> float | None:
    number = _number(value)
    if number is None or number < 0 or number > MAX_REE_FORECAST_MWH:
        return None
    return number


def select_ree_forecast(rows, objetivo, hoy) -> dict | None:
    """Selecciona la última previsión REE emitida antes del día objetivo."""
    objetivo = _date(objetivo)
    cutoff = min(objetivo - timedelta(days=1), _date(hoy))
    candidates = []
    for row in rows or []:
        if row.get("fuente", "ree") != "ree":
            continue
        if row.get("ubicacion") != "peninsula":
            continue
        if _date(row["objetivo"]) != objetivo:
            continue
        elaborado = _instant(row.get("elaborado"))
        value = _valid_ree_value(row.get("eolica_mwh"))
        if elaborado is None or elaborado.date() > cutoff or value is None:
            continue
        captured = _instant(row.get("capturado_en")) or elaborado
        candidates.append((elaborado, captured, value, row))
    if not candidates:
        return None
    elaborado, capturado, value, row = max(
        candidates, key=lambda item: (item[0], item[1])
    )
    return {
        "valor": value,
        "elaborado": elaborado.isoformat(),
        "capturado_en": capturado.isoformat(),
        "fila": dict(row),
    }


def resolve_generation_features(observada, ree_forecasts, objetivo, hoy) -> dict:
    """Resuelve generación observada y previsión en los huecos, día a día."""
    hoy = _date(hoy)
    objetivo = _date(objetivo)
    observed = {
        day: value for day, value in _normalized_series(observada).items()
        if day <= hoy
    }
    diagnostico = forecast_logic.generation_lags(observed, objetivo)
    anchor = diagnostico["ancla"]
    entries = {}
    if anchor is None:
        for lag in (1, 2, 3, 7):
            entries[f"eolica_lag{lag}"] = {"valor": None, "origen": None}
        entries["eolica_ma7"] = {"valor": None, "origen": None}
        return {
            "entradas": entries,
            "ancla": None,
            "frescura": diagnostico["frescura"],
        }

    for lag in (1, 2, 3, 7):
        name = f"eolica_lag{lag}"
        day = anchor - timedelta(days=lag - 1)
        value = diagnostico["valores"].get(name)
        origin = "observacion" if value is not None else None
        if value is None:
            forecast = select_ree_forecast(ree_forecasts, day, hoy)
            if forecast is not None:
                value = forecast["valor"]
                origin = "prevision"
        entries[name] = _entry(value, origin)

    mean7 = diagnostico["eolica_ma7"]
    if mean7 is not None:
        entries["eolica_ma7"] = _entry(mean7, "observacion")
    else:
        forecast_series = {}
        for row in ree_forecasts or []:
            if row.get("fuente", "ree") != "ree" or row.get("ubicacion") != "peninsula":
                continue
            day = _date(row["objetivo"])
            forecast = select_ree_forecast(ree_forecasts, day, hoy)
            if forecast is not None:
                forecast_series[day.isoformat()] = forecast["valor"]
        window = resolve_window(
            {day.isoformat(): value for day, value in observed.items()},
            forecast_series,
            anchor,
            7,
            hoy,
        )
        details = {}
        if window["origen"] == "mixta":
            details = {
                "dias_observados": window["dias_observados"],
                "dias_previstos": window["dias_previstos"],
            }
        entries["eolica_ma7"] = _entry(
            window["valor"], window["origen"], **details
        )
    return {
        "entradas": entries,
        "ancla": anchor.isoformat(),
        "frescura": diagnostico["frescura"],
    }


def resolve_eolica_prev(rows, objetivo, hoy) -> dict | None:
    """Previsión D+1 elegible o media de las siete previsiones reales previas."""
    objetivo = _date(objetivo)
    hoy = _date(hoy)
    cutoff = min(objetivo - timedelta(days=1), hoy)
    candidates = []
    for row in rows or []:
        if row.get("fuente", "ree") != "ree" or row.get("ubicacion") != "peninsula":
            continue
        if _date(row["objetivo"]) != objetivo:
            continue
        elaborado = _instant(row.get("elaborado"))
        value = _valid_ree_value(row.get("eolica_mwh"))
        if elaborado is None or elaborado.date() > cutoff or value is None:
            continue
        captured = _instant(row.get("capturado_en")) or elaborado
        candidates.append((elaborado, captured, value))
    if candidates:
        elaborado, _, value = max(candidates, key=lambda item: (item[0], item[1]))
        return {
            "valor": value,
            "origen": "prevision",
            "dias_media": 0,
            "elaborado": elaborado.isoformat(),
        }

    values = []
    for offset in range(6, -1, -1):
        day = cutoff - timedelta(days=offset)
        selected = select_ree_forecast(rows, day, hoy)
        if selected is not None:
            values.append(selected["valor"])
    if not values:
        return None
    return {
        "valor": sum(values) / len(values),
        "origen": "estimada",
        "dias_media": len(values),
        "desde": (cutoff - timedelta(days=6)).isoformat(),
        "hasta": cutoff.isoformat(),
    }


LAG1_ESTIMATE_DAYS = 7
LAG1_MIN_VALUES = 3


def _recent_observed_mean(observed, key: str, dia, hoy) -> dict | None:
    """Media observada de los siete días anteriores a `dia` (sin pasar de hoy)."""
    hasta = min(_date(dia) - timedelta(days=1), _date(hoy))
    desde = hasta - timedelta(days=LAG1_ESTIMATE_DAYS - 1)
    values = []
    for offset in range(LAG1_ESTIMATE_DAYS):
        value = _number((observed.get(desde + timedelta(days=offset)) or {}).get(key))
        if value is not None:
            values.append(value)
    if len(values) < LAG1_MIN_VALUES:
        return None
    return {
        "valor": sum(values) / len(values),
        "dias_media": len(values),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
    }


def build_prediction_map(obs_meteo, obs_solar, obs_gen, aemet_rows, ree_rows, hoy) -> dict:
    """Construye el mapa LR-19, su vector ordenado y los faltantes."""
    hoy = _date(hoy)
    objetivo = hoy + timedelta(days=1)
    mapa = {
        "mes": _entry(objetivo.month, "observacion"),
        "dia_semana": _entry(objetivo.weekday(), "observacion"),
        "dia_año": _entry(objetivo.timetuple().tm_yday, "observacion"),
    }

    wind_series = aemet_national_series(aemet_rows, "eolica", hoy)
    solar_series = aemet_national_series(aemet_rows, "solar", hoy)
    wind_forecast = {
        _date(day): values["viento_ms"]
        for day, values in wind_series.items()
        if values["viento_ms"] is not None
    }
    gust_forecast = {
        _date(day): values["racha_ms"]
        for day, values in wind_series.items()
        if values["racha_ms"] is not None
    }
    target_weather = wind_series.get(objetivo.isoformat(), {})
    for name, key in (("velmedia", "viento_ms"), ("racha", "racha_ms")):
        value = _number(target_weather.get(key))
        mapa[name] = _entry(value, "prevision" if value is not None else None)

    observed_wind = {}
    observed_gust = {}
    for day, values in (obs_meteo or {}).items():
        local_day = _date(day)
        if local_day <= hoy:
            wind = _number(values.get("velmedia"))
            gust = _number(values.get("racha"))
            if wind is not None:
                observed_wind[local_day] = wind
            if gust is not None:
                observed_gust[local_day] = gust

    for name, observed, forecast_series, days in (
        ("vel_ma3", observed_wind, wind_forecast, 3),
        ("vel_ma7", observed_wind, wind_forecast, 7),
        ("vel_ma14", observed_wind, wind_forecast, 14),
        ("racha_ma3", observed_gust, gust_forecast, 3),
        ("racha_ma7", observed_gust, gust_forecast, 7),
        ("racha_ma14", observed_gust, gust_forecast, 14),
    ):
        window = resolve_window(observed, forecast_series, objetivo, days, hoy)
        details = {}
        if window["origen"] == "mixta":
            details = {
                "dias_observados": window["dias_observados"],
                "dias_previstos": window["dias_previstos"],
            }
        mapa[name] = _entry(window["valor"], window["origen"], **details)

    yesterday = objetivo - timedelta(days=1)
    observed_solar = {
        _date(day): values for day, values in (obs_solar or {}).items()
    }
    solar_observation = observed_solar.get(yesterday, {})
    solar_forecast = solar_series.get(yesterday.isoformat(), {})
    for name, key, forecast_origin in (
        ("sol_lag1", "sol", "estimada"),
        ("tmed_lag1", "tmed", "prevision"),
    ):
        observed_value = (
            _number(solar_observation.get(key)) if yesterday <= hoy else None
        )
        forecast_value = _number(solar_forecast.get(key))
        if observed_value is not None:
            mapa[name] = _entry(observed_value, "observacion")
        elif forecast_value is not None:
            mapa[name] = _entry(forecast_value, forecast_origin)
        else:
            # Sin observación ni previsión del día: media declarada de los
            # últimos días observados, como hace `eolica_prev` con REE.
            estimate = _recent_observed_mean(observed_solar, key, yesterday, hoy)
            mapa[name] = (
                _entry(estimate["valor"], "estimada",
                       dias_media=estimate["dias_media"],
                       desde=estimate["desde"], hasta=estimate["hasta"])
                if estimate is not None else {"valor": None, "origen": None}
            )

    generation = resolve_generation_features(obs_gen, ree_rows, objetivo, hoy)
    mapa.update(generation["entradas"])
    ree_target = resolve_eolica_prev(ree_rows, objetivo, hoy)
    mapa["eolica_prev"] = (
        _entry(
            ree_target["valor"],
            ree_target["origen"],
            **({"dias_media": ree_target["dias_media"]}
               if ree_target["origen"] == "estimada" else {}),
        )
        if ree_target is not None else {"valor": None, "origen": None}
    )

    missing = [
        name for name in FEATURE_COLS
        if _number(mapa.get(name, {}).get("valor")) is None
        or mapa.get(name, {}).get("origen") not in ORIGINS
    ]
    vector = (
        {name: mapa[name]["valor"] for name in FEATURE_COLS}
        if not missing else None
    )
    origins = {name: mapa[name]["origen"] for name in FEATURE_COLS}
    return {
        "fecha_objetivo": objetivo.isoformat(),
        "features": list(FEATURE_COLS),
        "mapa": mapa,
        "vector_entrada": vector,
        "origenes": origins,
        "faltan": missing,
        "ancla_generacion": generation["ancla"],
        "aviso_generacion": generation["frescura"].get("aviso"),
    }


def ordered_vector(mapa, model_features=FEATURE_COLS) -> dict:
    """Valida que el mapa pueda ordenarse exactamente como el artefacto."""
    features = tuple(model_features)
    if features != FEATURE_COLS:
        raise ValueError("el orden de features no coincide con LR-19")
    missing = [
        name for name in features
        if _number((mapa.get(name) or {}).get("valor")) is None
        or (mapa.get(name) or {}).get("origen") not in ORIGINS
    ]
    if missing:
        return {"vector_entrada": None, "faltan": missing}
    return {
        "vector_entrada": {name: float(mapa[name]["valor"]) for name in features},
        "faltan": [],
    }


def prediction_error(fecha_objetivo, real_mwh, prediccion_mwh, hoy):
    """Error real menos predicción; ignora reales ausentes o de objetivos futuros."""
    if _date(fecha_objetivo) > _date(hoy):
        return None
    real = _number(real_mwh)
    prediction = _number(prediccion_mwh)
    return real - prediction if real is not None and prediction is not None else None
