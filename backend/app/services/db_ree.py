import sqlite3
import pandas as pd
from datetime import datetime
from typing import Optional, Tuple, List
import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "data/ree_generacion.db")
TABLE_NAME = "generacion"

RENOVABLES = {
    "Eólica", "Solar fotovoltaica", "Solar térmica",
    "Hidráulica", "Hidroeólica", "Otras renovables", "Residuos renovables"
}


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else "data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                datetime TEXT NOT NULL,
                tecnologia TEXT NOT NULL,
                tipo TEXT,
                valor_MWh REAL,
                porcentaje REAL,
                PRIMARY KEY (datetime, tecnologia)
            )
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_datetime
            ON {TABLE_NAME} (datetime)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                prediccion_mwh REAL,
                modelo TEXT,
                velmedia REAL,
                racha REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS aemet_daily (
                fecha TEXT PRIMARY KEY,
                temp_max REAL,
                temp_min REAL,
                vel_media REAL,
                rachas_max REAL,
                precipitacion REAL,
                sol REAL
            )
        """)
    logger.info(f"BD inicializada: {DB_PATH}")


def get_date_range() -> Tuple[Optional[str], Optional[str]]:
    with _get_conn() as conn:
        row = conn.execute(
            f"SELECT MIN(datetime), MAX(datetime) FROM {TABLE_NAME}"
        ).fetchone()
    return row if row else (None, None)


def save_generation_data(df: pd.DataFrame):
    if df.empty:
        return
    with _get_conn() as conn:
        df.to_sql("_tmp", conn, if_exists="replace", index=False)
        conn.execute(f"""
            INSERT OR IGNORE INTO {TABLE_NAME}
                (datetime, tecnologia, tipo, valor_MWh, porcentaje)
            SELECT datetime, tecnologia, tipo, valor_MWh, porcentaje
            FROM _tmp
        """)
        conn.execute("DROP TABLE _tmp")
    logger.info(f"Guardados {len(df)} registros de generación")


def get_generation_data(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    query = f"""
        SELECT datetime, tecnologia, valor_MWh
        FROM {TABLE_NAME}
        WHERE datetime >= ? AND datetime <= ?
        ORDER BY datetime
    """
    with _get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=[fecha_inicio, fecha_fin])
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def get_energy_mix(fecha: str = None) -> dict:
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT tecnologia, SUM(valor_MWh) as total
        FROM {TABLE_NAME}
        WHERE datetime LIKE ?
        GROUP BY tecnologia
    """
    with _get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=[f"{fecha}%"])

    total = df["total"].sum() if not df.empty else 1
    renovable = df[df["tecnologia"].isin(RENOVABLES)]["total"].sum()

    return {
        "renovable": round((renovable / total) * 100, 2) if total > 0 else 0,
        "noRenovable": round(((total - renovable) / total) * 100, 2) if total > 0 else 0,
        "tecnologias": {row["tecnologia"]: round((row["total"] / total) * 100, 2)
                       for _, row in df.iterrows()} if not df.empty else {}
    }


def save_prediction(fecha: str, prediccion_mwh: float, modelo: str, velmedia: float, racha: float):
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO predictions (fecha, prediccion_mwh, modelo, velmedia, racha)
            VALUES (?, ?, ?, ?, ?)
        """, (fecha, prediccion_mwh, modelo, velmedia, racha))
    logger.info(f"Predicción guardada: {fecha} -> {prediccion_mwh} MWh")


def get_latest_prediction() -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT fecha, prediccion_mwh, modelo, velmedia, racha
            FROM predictions
            ORDER BY created_at DESC
            LIMIT 1
        """).fetchone()
    if row:
        return {
            "fecha": row[0],
            "prediccionMWh": round(row[1], 0),
            "modelo": row[2],
            "features": {
                "velmedia": row[3],
                "racha": row[4]
            }
        }
    return None


def save_aemet_data(fecha: str, temp_max: float, temp_min: float, vel_media: float,
                    rachas_max: float, precipitacion: float, sol: float):
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO aemet_daily
            (fecha, temp_max, temp_min, vel_media, rachas_max, precipitacion, sol)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fecha, temp_max, temp_min, vel_media, rachas_max, precipitacion, sol))
    logger.info(f"Datos AEMET guardados: {fecha}")


def get_aemet_forecast() -> Optional[dict]:
    tomorrow = (datetime.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT fecha, vel_media, rachas_max
            FROM aemet_daily
            WHERE fecha = ?
        """, (tomorrow,)).fetchone()
    if row:
        return {
            "fecha": row[0],
            "velmedia": row[1],
            "racha": row[2]
        }
    return None


def get_historical_data(days: int = 30) -> List[dict]:
    desde = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"""
        SELECT datetime, tecnologia, valor_MWh
        FROM {TABLE_NAME}
        WHERE datetime >= ?
        ORDER BY datetime
    """
    with _get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=[desde])

    df["datetime"] = pd.to_datetime(df["datetime"])
    df["fecha"] = df["datetime"].dt.strftime("%Y-%m-%d")

    eolica = df[df["tecnologia"] == "Eólica"].groupby("fecha")["valor_MWh"].sum()
    solar = df[df["tecnologia"] == "Solar fotovoltaica"].groupby("fecha")["valor_MWh"].sum()
    hidraulica = df[df["tecnologia"] == "Hidráulica"].groupby("fecha")["valor_MWh"].sum()

    result = []
    for fecha in sorted(set(df["fecha"])):
        result.append({
            "fecha": fecha,
            "eolica": round(eolica.get(fecha, 0), 0),
            "solar": round(solar.get(fecha, 0), 0),
            "hidraulica": round(hidraulica.get(fecha, 0), 0)
        })
    return result