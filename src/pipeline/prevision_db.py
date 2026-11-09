"""Persistencia del archivo de previsiones y de la predicción propia (spec 004).

Solo E/S con la biblioteca estándar (`sqlite3`, `json`): la lógica de decisión
vive en `prevision.py` y `forecast.py`. Así esta capa se prueba en la puerta
`node --test` sin pandas y sin red.

Dos tablas y una regla común: el archivo crece hacia delante. La misma
elaboración recapturada sustituye sus valores; una elaboración nueva se añade y
nunca pisa la anterior. No hay `DELETE` en `prediccion_diaria`. La única
sustitución permitida es la predicción propia del mismo día, que es la misma
información recalculada (CA-2.2).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime

TABLA_PREVISION = "prediccion_diaria"
TABLA_PROPIA = "prediccion_propia"

FUENTES = ("aemet", "ree")

# Sin elaboración declarada el registro se guarda, pero no es elegible (CA-1.4).
# SQLite admite NULL en una PRIMARY KEY, así que la ausencia se marca con "".
SIN_ELABORACION = ""

COLUMNAS_PREVISION = (
    "fuente", "elaborado", "objetivo", "ubicacion", "uso",
    "viento_ms", "racha_ms", "tmax", "tmin", "tmed", "sol",
    "tramos_cielo", "orto", "ocaso", "uv_max", "eolica_mwh",
    "parte_json", "capturado_en",
)

COLUMNAS_PROPIAS = (
    "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
    "modelo", "n_variables", "vector_entrada", "origenes",
    "real_mwh", "error_mwh",
)

ESQUEMA_PREVISION = f"""
CREATE TABLE IF NOT EXISTS {TABLA_PREVISION} (
    fuente       TEXT NOT NULL,
    elaborado    TEXT NOT NULL,
    objetivo     TEXT NOT NULL,
    ubicacion    TEXT NOT NULL,
    uso          TEXT,
    viento_ms    REAL,
    racha_ms     REAL,
    tmax         REAL,
    tmin         REAL,
    tmed         REAL,
    sol          REAL,
    tramos_cielo TEXT,
    orto         REAL,
    ocaso        REAL,
    uv_max       REAL,
    eolica_mwh   REAL,
    parte_json   TEXT,
    capturado_en TEXT NOT NULL,
    PRIMARY KEY (fuente, elaborado, objetivo, ubicacion)
)
"""

ESQUEMA_PROPIA = f"""
CREATE TABLE IF NOT EXISTS {TABLA_PROPIA} (
    fecha_objetivo TEXT NOT NULL,
    fecha_emision  TEXT NOT NULL,
    emitida_en     TEXT NOT NULL,
    prediccion_mwh REAL NOT NULL,
    modelo         TEXT NOT NULL,
    n_variables    INTEGER NOT NULL,
    vector_entrada TEXT,
    origenes       TEXT,
    real_mwh       REAL,
    error_mwh      REAL,
    PRIMARY KEY (fecha_objetivo, fecha_emision)
)
"""


# ─────────────────────────────────────────────
# Conexión y esquema
# ─────────────────────────────────────────────

def connect(ruta: str = ":memory:") -> sqlite3.Connection:
    """Conexión propia para tests y herramientas."""
    if ruta != ":memory:":
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
    return sqlite3.connect(ruta)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crea las dos tablas. Es idempotente: se llama en cada ejecución."""
    conn.execute(ESQUEMA_PREVISION)
    conn.execute(ESQUEMA_PROPIA)
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLA_PREVISION}_objetivo "
        f"ON {TABLA_PREVISION} (objetivo)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLA_PROPIA}_objetivo "
        f"ON {TABLA_PROPIA} (fecha_objetivo)"
    )
    conn.commit()


# ─────────────────────────────────────────────
# Conversiones
# ─────────────────────────────────────────────

def _texto_elaborado(valor) -> str:
    if valor is None:
        return SIN_ELABORACION
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


def _texto_fecha(valor) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)[:10]


def _texto_json(valor):
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False)


def _a_fecha(valor):
    if not valor:
        return None
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def _a_instante(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def _json_o_none(valor):
    if not valor:
        return None
    try:
        return json.loads(valor)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────
# Escritura del archivo de fuentes (RF-1)
# ─────────────────────────────────────────────

def _fila_prevision(fila: dict, fuente: str, parte) -> tuple:
    return (
        fuente,
        _texto_elaborado(fila.get("elaborado")),
        _texto_fecha(fila["objetivo"]),
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
        fila.get("eolica_mwh"),
        _texto_json(fila.get("parte_json") if parte is None else parte),
        _texto_elaborado(
            fila.get("capturado_en") or datetime.now().isoformat()),
    )


def save_forecast_rows(conn: sqlite3.Connection, filas, fuente: str,
                       parte=None) -> int:
    """Guarda una captura sin duplicar (CA-1.2 a CA-1.4, CE-8).

    La misma elaboración recapturada sustituye sus propios valores; una
    elaboración distinta se añade y la anterior se conserva. El parte original
    se guarda entero para poder recalcular en el futuro sin volver a la fuente.
    """
    if fuente not in FUENTES:
        raise ValueError(f"fuente desconocida: {fuente!r}")

    filas = list(filas or [])
    if not filas:
        return 0

    marcadores = ", ".join("?" * len(COLUMNAS_PREVISION))
    actualizaciones = ", ".join(
        f"{columna} = excluded.{columna}" for columna in COLUMNAS_PREVISION
        if columna not in ("fuente", "elaborado", "objetivo", "ubicacion")
    )
    sentencia = (
        f"INSERT INTO {TABLA_PREVISION} ({', '.join(COLUMNAS_PREVISION)}) "
        f"VALUES ({marcadores}) "
        f"ON CONFLICT (fuente, elaborado, objetivo, ubicacion) "
        f"DO UPDATE SET {actualizaciones}"
    )
    conn.executemany(
        sentencia, [_fila_prevision(fila, fuente, parte) for fila in filas])
    conn.commit()
    return len(filas)


# ─────────────────────────────────────────────
# Lectura del archivo de fuentes
# ─────────────────────────────────────────────

def _fila_desde_sql(registro) -> dict:
    (
        fuente, elaborado, objetivo, ubicacion, uso, viento_ms, racha_ms,
        tmax, tmin, tmed, sol, tramos_cielo, orto, ocaso, uv_max, eolica_mwh,
        parte_json, capturado_en,
    ) = registro
    return {
        "fuente": fuente,
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
        "tramos_cielo": _json_o_none(tramos_cielo) or [],
        "orto": orto,
        "ocaso": ocaso,
        "uv_max": uv_max,
        "eolica_mwh": eolica_mwh,
        "parte_json": parte_json,
        "capturado_en": _a_instante(capturado_en),
    }


def rows_between(conn: sqlite3.Connection, fuente: str | None = None,
                 desde=None, hasta=None) -> list[dict]:
    """Filas por fuente y rango de días objetivo, en orden cronológico."""
    condiciones = []
    parametros = []
    if fuente is not None:
        condiciones.append("fuente = ?")
        parametros.append(fuente)
    if desde is not None:
        condiciones.append("objetivo >= ?")
        parametros.append(_texto_fecha(desde))
    if hasta is not None:
        condiciones.append("objetivo <= ?")
        parametros.append(_texto_fecha(hasta))

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    registros = conn.execute(
        f"SELECT {', '.join(COLUMNAS_PREVISION)} FROM {TABLA_PREVISION} "
        f"{where} ORDER BY objetivo, ubicacion, fuente",
        parametros,
    ).fetchall()
    return [_fila_desde_sql(registro) for registro in registros]


def objetivos_cubiertos(conn: sqlite3.Connection, fuente: str,
                        desde=None, hasta=None) -> set:
    """Días que ya tienen alguna elaboración archivada para esa fuente.

    El relleno histórico lo usa para no volver a pedir ni reetiquetar un día que
    ya está cubierto, sea por una captura en vivo o por otra reconstrucción.
    """
    condiciones = ["fuente = ?"]
    parametros = [fuente]
    if desde is not None:
        condiciones.append("objetivo >= ?")
        parametros.append(_texto_fecha(desde))
    if hasta is not None:
        condiciones.append("objetivo <= ?")
        parametros.append(_texto_fecha(hasta))

    registros = conn.execute(
        f"SELECT DISTINCT objetivo FROM {TABLA_PREVISION} "
        f"WHERE {' AND '.join(condiciones)}",
        parametros,
    ).fetchall()
    return {_a_fecha(registro[0]) for registro in registros}


# ─────────────────────────────────────────────
# Predicción propia (RF-2)
# ─────────────────────────────────────────────

def _fila_propia(fila: dict) -> tuple:
    emitida_en = fila.get("emitida_en") or datetime.now()
    fecha_emision = fila.get("fecha_emision") or (
        emitida_en.date() if isinstance(emitida_en, datetime)
        else _texto_fecha(emitida_en)
    )
    return (
        _texto_fecha(fila["fecha_objetivo"]),
        _texto_fecha(fecha_emision),
        _texto_elaborado(emitida_en),
        float(fila["prediccion_mwh"]),
        fila["modelo"],
        int(fila.get("n_variables") or 0),
        _texto_json(fila.get("vector_entrada")),
        _texto_json(fila.get("origenes")),
        fila.get("real_mwh"),
        fila.get("error_mwh"),
    )


def save_own_prediction(conn: sqlite3.Connection, fila: dict) -> None:
    """Inserta o sustituye la predicción del mismo objetivo y día (CA-2.1, CA-2.2).

    Sustituir es correcto aquí: es la misma información recalculada. Si ya había
    un real publicado, se conserva y se recalcula su error, nunca se pierde.
    """
    marcadores = ", ".join("?" * len(COLUMNAS_PROPIAS))
    conn.execute(
        f"INSERT INTO {TABLA_PROPIA} ({', '.join(COLUMNAS_PROPIAS)}) "
        f"VALUES ({marcadores}) "
        f"ON CONFLICT (fecha_objetivo, fecha_emision) DO UPDATE SET "
        f"emitida_en = excluded.emitida_en, "
        f"prediccion_mwh = excluded.prediccion_mwh, "
        f"modelo = excluded.modelo, "
        f"n_variables = excluded.n_variables, "
        f"vector_entrada = excluded.vector_entrada, "
        f"origenes = excluded.origenes, "
        f"error_mwh = CASE WHEN real_mwh IS NULL THEN NULL "
        f"ELSE real_mwh - excluded.prediccion_mwh END",
        _fila_propia(fila),
    )
    conn.commit()


def _fila_propia_desde_sql(registro) -> dict:
    (
        fecha_objetivo, fecha_emision, emitida_en, prediccion_mwh, modelo,
        n_variables, vector_entrada, origenes, real_mwh, error_mwh,
    ) = registro
    return {
        "fecha_objetivo": _a_fecha(fecha_objetivo),
        "fecha_emision": _a_fecha(fecha_emision),
        "emitida_en": _a_instante(emitida_en),
        "prediccion_mwh": prediccion_mwh,
        "modelo": modelo,
        "n_variables": n_variables,
        "vector_entrada": _json_o_none(vector_entrada) or {},
        "origenes": _json_o_none(origenes) or {},
        "real_mwh": real_mwh,
        "error_mwh": error_mwh,
    }


def own_predictions(conn: sqlite3.Connection, limite: int | None = None) -> list[dict]:
    """Serie de predicciones emitidas, en orden cronológico."""
    sentencia = (
        f"SELECT {', '.join(COLUMNAS_PROPIAS)} FROM {TABLA_PROPIA} "
        f"ORDER BY fecha_objetivo, fecha_emision"
    )
    parametros = ()
    if limite is not None:
        sentencia = (
            f"SELECT {', '.join(COLUMNAS_PROPIAS)} FROM {TABLA_PROPIA} "
            f"ORDER BY fecha_objetivo DESC, fecha_emision DESC LIMIT ?"
        )
        parametros = (int(limite),)

    registros = conn.execute(sentencia, parametros).fetchall()
    filas = [_fila_propia_desde_sql(registro) for registro in registros]
    return list(reversed(filas)) if limite is not None else filas


def predictions_without_real(conn: sqlite3.Connection, hoy) -> list[dict]:
    """Predicciones con objetivo ya cumplido y real pendiente (CA-2.3).

    No decide si el real está publicado: eso depende de la generación y lo
    resuelve `prevision.reales_pendientes`. Aquí solo se descartan los objetivos
    futuros y las que ya tienen real.
    """
    registros = conn.execute(
        f"SELECT {', '.join(COLUMNAS_PROPIAS)} FROM {TABLA_PROPIA} "
        f"WHERE real_mwh IS NULL AND fecha_objetivo <= ? "
        f"ORDER BY fecha_objetivo, fecha_emision",
        (_texto_fecha(hoy),),
    ).fetchall()
    return [_fila_propia_desde_sql(registro) for registro in registros]


def update_real(conn: sqlite3.Connection, fecha_objetivo, real_mwh) -> int:
    """Escribe el real y recalcula el error; jamás toca la predicción (CA-2.3).

    Se actualizan todas las emisiones de ese objetivo: cada una conserva su
    predicción y su error, de modo que la serie de producción sigue siendo
    auditable. Una corrección posterior del real también se propaga.
    """
    cursor = conn.execute(
        f"UPDATE {TABLA_PROPIA} "
        f"SET real_mwh = ?, error_mwh = ? - prediccion_mwh "
        f"WHERE fecha_objetivo = ?",
        (float(real_mwh), float(real_mwh), _texto_fecha(fecha_objetivo)),
    )
    conn.commit()
    return cursor.rowcount


def recent_with_real(conn: sqlite3.Connection, limite: int = 30) -> list[dict]:
    """Últimas predicciones con real, en orden cronológico (CA-2.4)."""
    registros = conn.execute(
        f"SELECT {', '.join(COLUMNAS_PROPIAS)} FROM {TABLA_PROPIA} "
        f"WHERE real_mwh IS NOT NULL "
        f"ORDER BY fecha_objetivo DESC, fecha_emision DESC LIMIT ?",
        (int(limite),),
    ).fetchall()
    return list(reversed(
        [_fila_propia_desde_sql(registro) for registro in registros]))
