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


# ---------------------------------------------------------------------------
# Helpers para features del modelo (lags y medias móviles)
# ---------------------------------------------------------------------------

# Indicativos de estaciones AEMET en zonas eólicas (igual que en api.ipynb)
_ESTACIONES_EOLICAS = ("4589X", "8175", "3013", "9299X", "6001", "9031C", "9299")


def get_eolica_recent(days: int = 14) -> list:
    """
    Devuelve lista de generación diaria eólica total (MWh) de los últimos `days` días,
    ordenada de más antiguo a más reciente.
    """
    query = f"""
        SELECT DATE(datetime) AS fecha, SUM(valor_MWh) AS valor
        FROM {TABLE_NAME}
        WHERE tecnologia = 'Eólica'
          AND DATE(datetime) >= DATE('now', ? || ' days')
        GROUP BY DATE(datetime)
        ORDER BY fecha ASC
    """
    with _get_conn() as conn:
        rows = conn.execute(query, (f"-{days}",)).fetchall()
    return [float(r[1]) for r in rows if r[1] is not None]


def get_wind_recent(days: int = 14) -> dict:
    """
    Devuelve historial de velmedia y racha promedio de los últimos `days` días
    desde la tabla `aemet_diario` (estaciones eólicas) o `aemet_daily` si no existe.
    Listas ordenadas de más antiguo a más reciente.
    """
    with _get_conn() as conn:
        # Intentar tabla del notebook (contiene datos por estación eólica)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "aemet_diario" in tables:
            placeholders = ",".join("?" * len(_ESTACIONES_EOLICAS))
            query = f"""
                SELECT fecha, AVG(velmedia) AS velmedia, AVG(racha) AS racha
                FROM aemet_diario
                WHERE indicativo IN ({placeholders})
                  AND fecha >= DATE('now', ? || ' days')
                GROUP BY fecha
                ORDER BY fecha ASC
            """
            rows = conn.execute(query, (*_ESTACIONES_EOLICAS, f"-{days}")).fetchall()
            return {
                "velmedia": [float(r[1]) for r in rows if r[1] is not None],
                "racha":    [float(r[2]) for r in rows if r[2] is not None],
            }

        if "aemet_daily" in tables:
            query = f"""
                SELECT fecha, vel_media, rachas_max
                FROM aemet_daily
                WHERE fecha >= DATE('now', ? || ' days')
                ORDER BY fecha ASC
            """
            rows = conn.execute(query, (f"-{days}",)).fetchall()
            return {
                "velmedia": [float(r[1]) for r in rows if r[1] is not None],
                "racha":    [float(r[2]) for r in rows if r[2] is not None],
            }

    return {"velmedia": [], "racha": []}