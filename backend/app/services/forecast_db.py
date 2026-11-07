"""Persistencia del archivo de previsiones meteorológicas (spec 003, RF-2, RF-4, RF-13).

Una tabla propia, separada de la observación (`aemet_diario`) y con la
elaboración declarada por el parte dentro de la clave. Aquí solo hay E/S: la
derivación de las variables vive en `forecast_logic`, copia exacta de
`src/pipeline/forecast.py`.

La conexión se pide a `db_ree` para que todo el servicio lea y escriba el mismo
archivo (RNF-1). La importación es diferida porque `db_ree` arrastra pandas y
esta capa también se usa en la puerta de tests, sin dependencias instaladas.
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

TABLA = "prediccion_aemet"
TABLA_ESTADO = "captura_estado"

# Sin elaboración declarada el registro se guarda, pero no es elegible (CA-2.7).
# SQLite admite NULL en una PRIMARY KEY, así que la ausencia se marca con "".
SIN_ELABORACION = ""

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLA} (
    elaborado     TEXT NOT NULL,
    objetivo      TEXT NOT NULL,
    ubicacion     TEXT NOT NULL,
    uso           TEXT NOT NULL,
    viento_ms     REAL,
    racha_ms      REAL,
    tmax          REAL,
    tmin          REAL,
    tmed          REAL,
    sol           REAL,
    tramos_cielo  TEXT,
    orto          REAL,
    ocaso         REAL,
    uv_max        REAL,
    parte_json    TEXT,
    capturado_en  TEXT NOT NULL,
    PRIMARY KEY (elaborado, objetivo, ubicacion)
)
"""

ESQUEMA_ESTADO = f"""
CREATE TABLE IF NOT EXISTS {TABLA_ESTADO} (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecutada_en       TEXT NOT NULL,
    ubicaciones_ok     INTEGER NOT NULL DEFAULT 0,
    ubicaciones_error  INTEGER NOT NULL DEFAULT 0,
    filas_guardadas    INTEGER NOT NULL DEFAULT 0,
    dias_pendientes    INTEGER,
    desde_pendiente    TEXT,
    estado             TEXT NOT NULL,
    detalle            TEXT
)
"""

COLUMNAS = (
    "elaborado", "objetivo", "ubicacion", "uso", "viento_ms", "racha_ms",
    "tmax", "tmin", "tmed", "sol", "tramos_cielo", "orto", "ocaso",
    "uv_max", "parte_json", "capturado_en",
)


# ─────────────────────────────────────────────
# Conexión y esquema
# ─────────────────────────────────────────────

def connect(ruta: str = ":memory:") -> sqlite3.Connection:
    """Conexión propia para tests y herramientas; el servicio usa `db_ree`."""
    if ruta != ":memory:":
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
    return sqlite3.connect(ruta)


def _default_conn() -> sqlite3.Connection:
    from .db_ree import _get_conn
    return _get_conn()


@contextmanager
def _conexion(conn):
    """Usa la conexión recibida o abre la del servicio, y cierra solo la propia."""
    if conn is not None:
        yield conn
        return
    propia = _default_conn()
    try:
        yield propia
        propia.commit()
    finally:
        propia.close()


def ensure_schema(conn=None):
    """Crea las dos tablas. Es idempotente: se llama en cada arranque."""
    with _conexion(conn) as conexion:
        conexion.execute(ESQUEMA)
        conexion.execute(ESQUEMA_ESTADO)
        conexion.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLA}_objetivo ON {TABLA} (objetivo)"
        )
        conexion.commit()
    logger.info("Esquema del archivo de previsiones listo")


def init_forecast_db(conn=None):
    """Entrada única desde `db_ree.init_db()`; acepta su conexión abierta."""
    ensure_schema(conn)


# ─────────────────────────────────────────────
# Escritura
# ─────────────────────────────────────────────

def _texto_elaborado(valor) -> str:
    if valor is None:
        return SIN_ELABORACION
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


def _texto_objetivo(valor) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def _texto_json(valor):
    if valor is None:
        return None
    return json.dumps(valor, ensure_ascii=False)


def _fila_para_sql(fila: dict, parte: dict | None) -> tuple:
    return (
        _texto_elaborado(fila.get("elaborado")),
        _texto_objetivo(fila["objetivo"]),
        fila["ubicacion"],
        fila.get("uso"),
        fila.get("viento_ms"),
        fila.get("racha_ms"),
        fila.get("tmax"),
        fila.get("tmin"),
        fila.get("tmed"),
        fila.get("sol"),
        _texto_json(fila.get("tramos_cielo")),
        fila.get("orto"),
        fila.get("ocaso"),
        fila.get("uv_max"),
        _texto_json(parte),
        _texto_elaborado(fila.get("capturado_en")) or datetime.now().isoformat(),
    )


def save_forecast(conn, filas, parte: dict | None = None) -> int:
    """Guarda las filas de una captura sin duplicar (CA-4.1 a CA-4.3).

    La misma elaboración recapturada sustituye sus propios valores; una
    elaboración distinta se añade y la anterior se conserva.
    """
    filas = list(filas or [])
    if not filas:
        return 0

    marcadores = ", ".join("?" * len(COLUMNAS))
    actualizaciones = ", ".join(
        f"{columna} = excluded.{columna}" for columna in COLUMNAS
        if columna not in ("elaborado", "objetivo", "ubicacion")
    )
    sentencia = (
        f"INSERT INTO {TABLA} ({', '.join(COLUMNAS)}) VALUES ({marcadores}) "
        f"ON CONFLICT (elaborado, objetivo, ubicacion) DO UPDATE SET {actualizaciones}"
    )

    with _conexion(conn) as conexion:
        conexion.executemany(
            sentencia, [_fila_para_sql(fila, parte) for fila in filas],
        )
        conexion.commit()

    logger.info(f"Archivo de previsiones: {len(filas)} filas guardadas")
    return len(filas)


def register_capture(conn, ejecutada_en: datetime, ubicaciones_ok: int,
                     ubicaciones_error: int, filas_guardadas: int, estado: str,
                     detalle: str = "", dias_pendientes: int | None = None,
                     desde_pendiente=None) -> int:
    """Deja una fila por ejecución con lo guardado y lo que quedó pendiente (RF-13)."""
    with _conexion(conn) as conexion:
        cursor = conexion.execute(
            f"""
            INSERT INTO {TABLA_ESTADO}
                (ejecutada_en, ubicaciones_ok, ubicaciones_error, filas_guardadas,
                 dias_pendientes, desde_pendiente, estado, detalle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _texto_elaborado(ejecutada_en),
                int(ubicaciones_ok),
                int(ubicaciones_error),
                int(filas_guardadas),
                dias_pendientes,
                _texto_objetivo(desde_pendiente) if desde_pendiente else None,
                estado,
                detalle or None,
            ),
        )
        conexion.commit()
        return cursor.lastrowid


# ─────────────────────────────────────────────
# Lectura
# ─────────────────────────────────────────────

def _a_fecha(valor):
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def _a_instante(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def archived_days(conn=None) -> set:
    """Días objetivo que ya tienen alguna previsión archivada."""
    with _conexion(conn) as conexion:
        filas = conexion.execute(
            f"SELECT DISTINCT objetivo FROM {TABLA}"
        ).fetchall()
    return {_a_fecha(fila[0]) for fila in filas}


def _fila_de_archivo(registro) -> dict:
    (
        elaborado, objetivo, ubicacion, uso, viento_ms, racha_ms, tmax, tmin,
        tmed, sol, tramos_cielo, orto, ocaso, uv_max, parte_json, capturado_en,
    ) = registro
    return {
        "elaborado": _a_instante(elaborado),
        "objetivo": _a_fecha(objetivo),
        "ubicacion": ubicacion,
        "uso": uso,
        "viento_ms": viento_ms,
        "racha_ms": racha_ms,
        "tmax": tmax,
        "tmin": tmin,
        "tmed": tmed,
        "sol": sol,
        "tramos_cielo": json.loads(tramos_cielo) if tramos_cielo else [],
        "orto": orto,
        "ocaso": ocaso,
        "uv_max": uv_max,
        "parte_json": parte_json,
        "capturado_en": _a_instante(capturado_en),
    }


def rows_between(conn, desde, hasta) -> list:
    """Filas con día objetivo dentro del rango, en orden cronológico."""
    with _conexion(conn) as conexion:
        registros = conexion.execute(
            f"""
            SELECT {', '.join(COLUMNAS)} FROM {TABLA}
            WHERE objetivo >= ? AND objetivo <= ?
            ORDER BY objetivo, ubicacion
            """,
            (_texto_objetivo(desde), _texto_objetivo(hasta)),
        ).fetchall()
    return [_fila_de_archivo(registro) for registro in registros]


def choose_forecast(conn, objetivo, ubicacion: str, hoy):
    """Consulta equivalente a `forecast_logic.choose_forecast` (RF-5).

    Misma regla, misma respuesta: solo elaboraciones declaradas y no posteriores
    al día objetivo ni a hoy; de las válidas, la más reciente. La paridad entre
    las dos vías se comprueba en `test_forecast_parity.py`.
    """
    objetivo = _a_fecha(objetivo)
    tope = min(objetivo, _a_fecha(hoy))

    with _conexion(conn) as conexion:
        registro = conexion.execute(
            f"""
            SELECT {', '.join(COLUMNAS)} FROM {TABLA}
            WHERE objetivo = ?
              AND ubicacion = ?
              AND elaborado <> ?
              AND DATE(elaborado) <= ?
            ORDER BY elaborado DESC
            LIMIT 1
            """,
            (objetivo.isoformat(), ubicacion, SIN_ELABORACION, tope.isoformat()),
        ).fetchone()

    if registro is None:
        return None

    valores = _fila_de_archivo(registro)
    return {
        "valores": valores,
        "elaborado": valores["elaborado"],
        "antiguedad_dias": (objetivo - valores["elaborado"].date()).days,
    }


def last_capture(conn=None) -> dict | None:
    """Última ejecución registrada, o None si el archivo nunca se llenó."""
    with _conexion(conn) as conexion:
        registro = conexion.execute(
            f"""
            SELECT ejecutada_en, ubicaciones_ok, ubicaciones_error,
                   filas_guardadas, dias_pendientes, desde_pendiente, estado, detalle
            FROM {TABLA_ESTADO}
            ORDER BY ejecutada_en DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    if registro is None:
        return None
    return {
        "ejecutada_en": _a_instante(registro[0]),
        "ubicaciones_ok": registro[1],
        "ubicaciones_error": registro[2],
        "filas_guardadas": registro[3],
        "dias_pendientes": registro[4],
        "desde_pendiente": _a_fecha(registro[5]) if registro[5] else None,
        "estado": registro[6],
        "detalle": registro[7] or "",
    }


def capture_failed(resumen: dict | None) -> bool:
    """Una captura sin ninguna ubicación es un fallo visible (CA-13.2)."""
    return resumen is None or int(resumen.get("ubicaciones_ok") or 0) == 0


def capture_summary(hoy, archivados, esperados) -> dict:
    """Días pendientes y su fecha más antigua, para el resumen diario (CA-6.6)."""
    from .forecast_logic import pending_days

    estado = pending_days(hoy, esperados, archivados)
    recuperables = estado["recuperables"]
    return {
        "recuperables": recuperables,
        "perdidos": estado["perdidos"],
        "dias_pendientes": len(recuperables) + len(estado["perdidos"]),
        "desde_pendiente": recuperables[0] if recuperables else None,
    }


def first_capture_day(conn=None):
    """Primer día con una ejecución registrada: desde ahí el archivo es exigible."""
    with _conexion(conn) as conexion:
        registro = conexion.execute(
            f"SELECT MIN(ejecutada_en) FROM {TABLA_ESTADO}"
        ).fetchone()
    if registro is None or not registro[0]:
        return None
    return _a_fecha(registro[0])


def expected_days(hoy, desde: date, horizonte: int = 7) -> list:
    """Días que el archivo debería cubrir hasta hoy, desde la primera captura.

    Se acota a las últimas cuatro semanas para que un archivo viejo no convierta
    el resumen diario en una lista interminable.
    """
    inicio = max(_a_fecha(desde), _a_fecha(hoy) - timedelta(days=horizonte * 4))
    return [inicio + timedelta(days=desplazamiento)
            for desplazamiento in range((_a_fecha(hoy) - inicio).days + 1)]
