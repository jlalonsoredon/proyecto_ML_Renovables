import json
import logging
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "data/ree_generacion.db")
TABLE_NAME = "generacion"
ZONA_MADRID = ZoneInfo("Europe/Madrid")

ESTACIONES_EOLICAS = ("4589X", "8175", "3013", "6001", "9299X", "9031C")
ESTACIONES_SOLARES = ("3469A", "4452", "7228", "5783", "9434")

RENOVABLES = {
    "Eólica", "Solar fotovoltaica", "Solar térmica", "Hidráulica",
    "Hidroeólica", "Otras renovables", "Residuos renovables",
}

ESQUEMA_PREDICCION_PROPIA = """
CREATE TABLE IF NOT EXISTS prediccion_propia (
    fecha_objetivo TEXT NOT NULL,
    fecha_emision TEXT NOT NULL,
    emitida_en TEXT NOT NULL,
    prediccion_mwh REAL NOT NULL,
    modelo TEXT NOT NULL,
    n_variables INTEGER NOT NULL,
    vector_entrada TEXT,
    origenes TEXT,
    real_mwh REAL,
    error_mwh REAL,
    PRIMARY KEY (fecha_objetivo, fecha_emision)
)
"""

COLUMNAS_PROPIAS = (
    "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
    "modelo", "n_variables", "vector_entrada", "origenes", "real_mwh",
    "error_mwh",
)


def _get_conn() -> sqlite3.Connection:
    carpeta = os.path.dirname(DB_PATH)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _connection(conn=None):
    propia = conn is None
    conexion = _get_conn() if propia else conn
    try:
        yield conexion
        if propia:
            conexion.commit()
    finally:
        if propia:
            conexion.close()


def init_db(conn=None) -> None:
    """Inicializa los esquemas canónicos sin crear tablas de predicción legadas."""
    with _connection(conn) as conexion:
        conexion.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                datetime TEXT NOT NULL,
                tecnologia TEXT NOT NULL,
                tipo TEXT,
                valor_MWh REAL,
                porcentaje REAL,
                PRIMARY KEY (datetime, tecnologia)
            )
        """)
        conexion.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_datetime "
            f"ON {TABLE_NAME} (datetime)"
        )
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS aemet_diario (
                fecha TEXT NOT NULL,
                indicativo TEXT NOT NULL,
                nombre TEXT,
                provincia TEXT,
                tmed REAL,
                tmin REAL,
                tmax REAL,
                velmedia REAL,
                racha REAL,
                prec REAL,
                sol REAL,
                PRIMARY KEY (fecha, indicativo)
            )
        """)
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_aemet_fecha ON aemet_diario (fecha)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_aemet_ind ON aemet_diario (indicativo)"
        )
        conexion.execute(ESQUEMA_PREDICCION_PROPIA)
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_prediccion_propia_objetivo "
            "ON prediccion_propia (fecha_objetivo)"
        )
        from .forecast_db import init_forecast_db
        init_forecast_db(conexion)
    logger.info("BD canónica inicializada: %s", DB_PATH)


def health_check() -> None:
    """Lanza si la BD no es íntegra o carece de las tablas de producción."""
    required = {
        "generacion",
        "aemet_diario",
        "prediccion_diaria",
        "prediccion_propia",
    }
    with _connection() as conn:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"PRAGMA quick_check: {integrity}")
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = sorted(required - tables)
    if missing:
        raise sqlite3.DatabaseError(
            f"faltan tablas canónicas: {', '.join(missing)}"
        )


def _as_date(value) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(ZONA_MADRID).date()
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    instante = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(ZONA_MADRID).date()


def _local_datetime(value) -> datetime:
    if isinstance(value, datetime):
        instante = value
    else:
        instante = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(ZONA_MADRID)


def _hoy_madrid() -> date:
    return datetime.now(ZONA_MADRID).date()


def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    with _connection() as conn:
        row = conn.execute(
            f"SELECT MIN(datetime), MAX(datetime) FROM {TABLE_NAME}"
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def save_generation_data(df: pd.DataFrame, conn=None,
                         replace_existing_dates=None) -> int:
    if df is None or df.empty:
        return 0
    expected = ("datetime", "tecnologia", "tipo", "valor_MWh", "porcentaje")
    if any(column not in df.columns for column in expected):
        raise ValueError("DataFrame REE incompleto")
    rows = df.loc[:, expected].to_dict("records")
    replace_dates = {_as_date(day) for day in (replace_existing_dates or ())}
    insert_rows = []
    replace_rows = []
    for row in rows:
        (replace_rows if _as_date(row["datetime"]) in replace_dates else insert_rows).append(row)
    with _connection(conn) as connection:
        if insert_rows:
            connection.executemany(
                f"""INSERT OR IGNORE INTO {TABLE_NAME}
                    (datetime, tecnologia, tipo, valor_MWh, porcentaje)
                    VALUES (:datetime, :tecnologia, :tipo, :valor_MWh, :porcentaje)""",
                insert_rows,
            )
        if replace_rows:
            connection.executemany(
                f"""INSERT INTO {TABLE_NAME}
                    (datetime, tecnologia, tipo, valor_MWh, porcentaje)
                    VALUES (:datetime, :tecnologia, :tipo, :valor_MWh, :porcentaje)
                    ON CONFLICT (datetime, tecnologia) DO UPDATE SET
                        tipo = excluded.tipo,
                        valor_MWh = excluded.valor_MWh,
                        porcentaje = excluded.porcentaje""",
                replace_rows,
            )
    if replace_rows:
        logger.info(
            "REE: actualizadas explícitamente %d filas de días incompletos",
            len(replace_rows),
        )
    return len(rows)


def get_generation_data(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    with _connection() as conn:
        rows = conn.execute(
            f"""SELECT datetime, tecnologia, valor_MWh
                FROM {TABLE_NAME}
                WHERE datetime >= ? AND datetime <= ?
                ORDER BY datetime""",
            (fecha_inicio, fecha_fin),
        ).fetchall()
    result = pd.DataFrame([dict(row) for row in rows])
    if not result.empty:
        result["datetime"] = pd.to_datetime(result["datetime"], utc=True)
    return result


def get_generation_series(hoy=None, desde=None) -> dict[date, float]:
    """Agrupa Eólica por día natural de Madrid, no por la fecha UTC."""
    hoy = _as_date(hoy or _hoy_madrid())
    desde = _as_date(desde) if desde is not None else None
    with _connection() as conn:
        rows = conn.execute(
            f"SELECT datetime, valor_MWh FROM {TABLE_NAME} "
            "WHERE tecnologia = 'Eólica' AND valor_MWh IS NOT NULL "
            "ORDER BY datetime"
        ).fetchall()
    series = {}
    for row in rows:
        day = _as_date(row["datetime"])
        if day > hoy or (desde is not None and day < desde):
            continue
        series[day] = series.get(day, 0.0) + float(row["valor_MWh"])
    return series


def get_generation_days(desde: date, hasta: date) -> set[date]:
    series = get_generation_series(hoy=hasta, desde=desde)
    return set(series)


def get_eolica_recent(days: int = 14, hoy=None) -> list[float]:
    hoy = _as_date(hoy or _hoy_madrid())
    desde = hoy - timedelta(days=days - 1)
    series = get_generation_series(hoy=hoy, desde=desde)
    return [series[day] for day in sorted(series)]


def _mean_by_day(rows, estaciones, hoy, days, fields) -> dict[date, dict]:
    hoy = _as_date(hoy)
    desde = hoy - timedelta(days=days - 1)
    estaciones = set(estaciones)
    acumulados = {}
    with _connection() as conn:
        placeholders = ",".join("?" for _ in estaciones)
        query = (
            f"SELECT fecha, indicativo, {', '.join(fields)} FROM aemet_diario "
            f"WHERE indicativo IN ({placeholders}) AND fecha >= ? AND fecha <= ? "
            "ORDER BY fecha, indicativo"
        )
        data = conn.execute(
            query,
            (*sorted(estaciones), desde.isoformat(), hoy.isoformat()),
        ).fetchall()
    for row in data:
        day = _as_date(row["fecha"])
        values = acumulados.setdefault(day, {field: [] for field in fields})
        for field in fields:
            value = row[field]
            if value is not None:
                values[field].append(float(value))
    return {
        day: {
            field: (
                sum(values[field]) / len(values[field])
                if values[field] else None
            )
            for field in fields
        }
        for day, values in acumulados.items()
    }


def get_wind_observations(hoy, days: int = 35) -> dict[date, dict]:
    return _mean_by_day(
        [], ESTACIONES_EOLICAS, hoy, days, ("velmedia", "racha")
    )


def get_solar_observations(hoy, days: int = 35) -> dict[date, dict]:
    return _mean_by_day(
        [], ESTACIONES_SOLARES, hoy, days, ("sol", "tmed")
    )


def get_wind_recent(days: int = 14, hoy=None) -> dict[str, list[float]]:
    hoy = _as_date(hoy or _hoy_madrid())
    series = get_wind_observations(hoy, days)
    return {
        "velmedia": [
            row["velmedia"] for _, row in sorted(series.items())
            if row["velmedia"] is not None
        ],
        "racha": [
            row["racha"] for _, row in sorted(series.items())
            if row["racha"] is not None
        ],
    }


def save_aemet_diario(records: list[dict]) -> int:
    if not records:
        return 0
    columns = (
        "fecha", "indicativo", "nombre", "provincia", "tmed", "tmin", "tmax",
        "velmedia", "racha", "prec", "sol",
    )
    normalized = []
    for record in records:
        if not record.get("fecha") or not record.get("indicativo"):
            continue
        normalized.append({column: record.get(column) for column in columns})
    if not normalized:
        return 0
    placeholders = ", ".join(f":{column}" for column in columns)
    with _connection() as conn:
        conn.executemany(
            f"""INSERT OR IGNORE INTO aemet_diario ({', '.join(columns)})
                VALUES ({placeholders})""",
            normalized,
        )
    logger.info("aemet_diario: %d filas recibidas (solo faltantes insertadas)", len(normalized))
    return len(normalized)


def get_own_predictions(fecha_objetivo=None, desde=None, hasta=None,
                        conn=None) -> list[dict]:
    conditions = []
    values = []
    if fecha_objetivo is not None:
        conditions.append("fecha_objetivo = ?")
        values.append(_as_date(fecha_objetivo).isoformat())
    if desde is not None:
        conditions.append("fecha_objetivo >= ?")
        values.append(_as_date(desde).isoformat())
    if hasta is not None:
        conditions.append("fecha_objetivo <= ?")
        values.append(_as_date(hasta).isoformat())
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _connection(conn) as connection:
        rows = connection.execute(
            f"""SELECT {', '.join(COLUMNAS_PROPIAS)}
                FROM prediccion_propia {where}
                ORDER BY fecha_objetivo, fecha_emision, emitida_en""",
            values,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["vector_entrada"] = json.loads(item["vector_entrada"]) if item["vector_entrada"] else {}
        item["origenes"] = json.loads(item["origenes"]) if item["origenes"] else {}
        item["fecha_objetivo"] = _as_date(item["fecha_objetivo"]).isoformat()
        item["fecha_emision"] = _as_date(item["fecha_emision"]).isoformat()
        result.append(item)
    return result


def get_own_prediction(fecha_objetivo, conn=None) -> dict | None:
    rows = get_own_predictions(fecha_objetivo=fecha_objetivo, conn=conn)
    return max(rows, key=lambda row: (row["fecha_emision"], row["emitida_en"] or "")) if rows else None


def save_own_prediction(record: dict, conn=None) -> None:
    required = (
        "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
        "modelo", "n_variables",
    )
    missing = [name for name in required if record.get(name) is None]
    if missing:
        raise ValueError(f"faltan campos de prediccion_propia: {', '.join(missing)}")
    fecha_objetivo = _as_date(record["fecha_objetivo"]).isoformat()
    fecha_emision = _as_date(record["fecha_emision"]).isoformat()
    vector_json = json.dumps(record.get("vector_entrada"), ensure_ascii=False)
    origenes_json = json.dumps(record.get("origenes"), ensure_ascii=False)
    with _connection(conn) as connection:
        connection.execute(
            """INSERT INTO prediccion_propia (
                   fecha_objetivo, fecha_emision, emitida_en, prediccion_mwh,
                   modelo, n_variables, vector_entrada, origenes, real_mwh, error_mwh
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (fecha_objetivo, fecha_emision) DO UPDATE SET
                   emitida_en = excluded.emitida_en,
                   prediccion_mwh = excluded.prediccion_mwh,
                   modelo = excluded.modelo,
                   n_variables = excluded.n_variables,
                   vector_entrada = excluded.vector_entrada,
                   origenes = excluded.origenes,
                   error_mwh = CASE
                       WHEN prediccion_propia.real_mwh IS NULL THEN NULL
                       ELSE prediccion_propia.real_mwh - excluded.prediccion_mwh
                   END""",
            (
                fecha_objetivo,
                fecha_emision,
                str(record["emitida_en"]),
                float(record["prediccion_mwh"]),
                str(record["modelo"]),
                int(record["n_variables"]),
                vector_json,
                origenes_json,
                record.get("real_mwh"),
                record.get("error_mwh"),
            ),
        )


def restore_own_predictions(records: list[dict]) -> int:
    """Inserta emisiones históricas que falten sin sobrescribir las guardadas.

    Se usa al inicio de cada refresh para recuperar las predicciones que la
    SQLite efímera de Render perdió en un reinicio. El snapshot anterior es el
    archivo durable; aquí solo se rellena lo que no exista ya.
    """
    inserts = []
    for record in records or []:
        try:
            objetivo = _as_date(record.get("fecha_objetivo"))
            emision = _as_date(record.get("fecha_emision"))
            mwh = float(record.get("prediccion_mwh"))
            n_variables = int(record.get("n_variables"))
        except (TypeError, ValueError):
            continue
        modelo = str(record.get("modelo") or "").strip()
        if (
            objetivo is None
            or emision is None
            or not modelo
            or n_variables <= 0
            or not math.isfinite(mwh)
            or mwh <= 0
        ):
            continue
        emitida_en = str(record.get("emitida_en") or f"{emision.isoformat()}T00:00:00")
        inserts.append((
            objetivo.isoformat(),
            emision.isoformat(),
            emitida_en,
            mwh,
            modelo,
            n_variables,
            json.dumps(record.get("vector_entrada") or {}, ensure_ascii=False),
            json.dumps(record.get("origenes") or {}, ensure_ascii=False),
            record.get("real_mwh"),
            record.get("error_mwh"),
        ))

    restauradas = 0
    with _connection() as connection:
        for values in inserts:
            cursor = connection.execute(
                """INSERT INTO prediccion_propia (
                       fecha_objetivo, fecha_emision, emitida_en, prediccion_mwh,
                       modelo, n_variables, vector_entrada, origenes, real_mwh, error_mwh
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (fecha_objetivo, fecha_emision) DO NOTHING""",
                values,
            )
            restauradas += max(cursor.rowcount, 0)
    return restauradas


def update_own_prediction_real(fecha_objetivo, real_mwh, conn=None) -> int:
    if real_mwh is None:
        return 0
    with _connection(conn) as connection:
        cursor = connection.execute(
            """UPDATE prediccion_propia
               SET real_mwh = ?, error_mwh = ? - prediccion_mwh
               WHERE fecha_objetivo = ?""",
            (
                float(real_mwh),
                float(real_mwh),
                _as_date(fecha_objetivo).isoformat(),
            ),
        )
    return cursor.rowcount


def predictions_without_real(hoy, conn=None) -> list[dict]:
    with _connection(conn) as connection:
        rows = connection.execute(
            f"""SELECT {', '.join(COLUMNAS_PROPIAS)}
                FROM prediccion_propia
                WHERE real_mwh IS NULL AND fecha_objetivo <= ?
                ORDER BY fecha_objetivo, fecha_emision""",
            (_as_date(hoy).isoformat(),),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["vector_entrada"] = json.loads(item["vector_entrada"]) if item["vector_entrada"] else {}
        item["origenes"] = json.loads(item["origenes"]) if item["origenes"] else {}
        result.append(item)
    return result


def get_historical_data(days: int = 30, hoy=None) -> list[dict]:
    hoy = _as_date(hoy or _hoy_madrid())
    since = hoy - timedelta(days=days - 1)
    with _connection() as conn:
        rows = conn.execute(
            f"SELECT datetime, tecnologia, valor_MWh FROM {TABLE_NAME} "
            "WHERE valor_MWh IS NOT NULL ORDER BY datetime"
        ).fetchall()
    grouped = {}
    for row in rows:
        day = _as_date(row["datetime"])
        if day < since or day > hoy:
            continue
        grouped.setdefault(day, {}).setdefault(row["tecnologia"], 0.0)
        grouped[day][row["tecnologia"]] += float(row["valor_MWh"])
    return [
        {
            "fecha": day.isoformat(),
            "eolica": round(values.get("Eólica", 0.0), 0),
            "solar": round(values.get("Solar fotovoltaica", 0.0), 0),
            "hidraulica": round(values.get("Hidráulica", 0.0), 0),
        }
        for day, values in sorted(grouped.items())
    ]


def get_energy_mix(fecha: str | None = None) -> dict:
    objetivo = _as_date(fecha or _hoy_madrid())
    with _connection() as conn:
        rows = conn.execute(
            f"SELECT datetime, tecnologia, valor_MWh FROM {TABLE_NAME} "
            "WHERE valor_MWh IS NOT NULL"
        ).fetchall()
    totals = {}
    for row in rows:
        if _as_date(row["datetime"]) == objetivo:
            totals[row["tecnologia"]] = totals.get(row["tecnologia"], 0.0) + float(row["valor_MWh"])
    total = sum(totals.values())
    renewable = sum(value for name, value in totals.items() if name in RENOVABLES)
    return {
        "renovable": round(renewable / total * 100, 2) if total else 0,
        "noRenovable": round((total - renewable) / total * 100, 2) if total else 0,
        "tecnologias": {
            name: round(value / total * 100, 2) for name, value in totals.items()
        } if total else {},
    }


def get_generation_for_dates(fechas: list[str]) -> dict[str, float]:
    if not fechas:
        return {}
    wanted = {_as_date(fecha) for fecha in fechas}
    series = get_generation_series(hoy=max(wanted), desde=min(wanted))
    return {day.isoformat(): value for day, value in series.items() if day in wanted}


def _observations_for_dates(fechas: list[str], estaciones, fields) -> dict[str, dict]:
    """Media por fecha de las estaciones pedidas, restringida a las fechas dadas."""
    if not fechas:
        return {}
    wanted = {_as_date(fecha) for fecha in fechas}
    with _connection() as conn:
        placeholders = ",".join("?" for _ in estaciones)
        rows = conn.execute(
            f"""SELECT fecha, indicativo, {', '.join(fields)} FROM aemet_diario
                WHERE indicativo IN ({placeholders})""",
            estaciones,
        ).fetchall()
    accum = {}
    for row in rows:
        day = _as_date(row["fecha"])
        if day not in wanted:
            continue
        values = accum.setdefault(day, {field: [] for field in fields})
        for field in fields:
            if row[field] is not None:
                values[field].append(float(row[field]))
    return {
        day.isoformat(): {
            field: (sum(values[field]) / len(values[field]) if values[field] else None)
            for field in fields
        }
        for day, values in accum.items()
    }


def get_wind_for_dates(fechas: list[str]) -> dict[str, dict]:
    return _observations_for_dates(fechas, ESTACIONES_EOLICAS, ("velmedia", "racha"))


def get_solar_for_dates(fechas: list[str]) -> dict[str, dict]:
    return _observations_for_dates(fechas, ESTACIONES_SOLARES, ("sol", "tmed"))


def get_predictions_for_dates(fechas: list[str]) -> dict[str, float]:
    if not fechas:
        return {}
    wanted = {_as_date(fecha).isoformat() for fecha in fechas}
    placeholders = ",".join("?" for _ in wanted)
    with _connection() as conn:
        rows = conn.execute(
            f"""SELECT fecha_objetivo, prediccion_mwh, fecha_emision, emitida_en
                FROM prediccion_propia
                WHERE fecha_objetivo IN ({placeholders})
                ORDER BY fecha_objetivo, fecha_emision DESC, emitida_en DESC""",
            sorted(wanted),
        ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["fecha_objetivo"], float(row["prediccion_mwh"]))
    return result


def get_own_predictions_for_dates(fechas: list[str]) -> list[dict]:
    if not fechas:
        return []
    return get_own_predictions(desde=min(fechas), hasta=max(fechas))
