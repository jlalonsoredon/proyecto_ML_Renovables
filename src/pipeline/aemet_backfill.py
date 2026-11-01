"""Relleno del histórico AEMET para las cinco estaciones fotovoltaicas.

`descargar_aemet` vive en el notebook y depende de pandas. Este script hace la
misma descarga (API de dos pasos, `INSERT OR IGNORE`, pausas) con biblioteca
estándar para poder ejecutarla sin Jupyter.

AEMET rechaza peticiones de más de 6 meses, así que el rango se trocea en
ventanas de `DIAS_POR_VENTANA` días (verificado el 2026-10-27).

Uso:
    python src/pipeline/aemet_backfill.py --desde 2022-01-01 --hasta 2026-06-23
    python src/pipeline/aemet_backfill.py --estaciones 3469A 7228 --simular
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
DB_POR_DEFECTO = RAIZ / "src" / "data" / "ree_generacion.db"
TABLA = "aemet_diario"
COLUMNAS = (
    "fecha", "indicativo", "nombre", "provincia",
    "tmed", "tmin", "tmax", "velmedia", "racha", "prec", "sol",
)

DIAS_POR_VENTANA = 150      # AEMET no admite más de 6 meses por petición
PAUSA_SEGUNDOS = 6.0        # el proveedor limita las peticiones por minuto
REINTENTOS_429 = 3

ESTACIONES_POR_DEFECTO = ("3469A", "4452", "7228", "5783", "9434")

log = logging.getLogger("aemet_backfill")


# ─────────────────────────────────────────────
# Utilidades puras
# ─────────────────────────────────────────────

def ventanas(desde: date, hasta: date, dias: int = DIAS_POR_VENTANA) -> list[tuple[date, date]]:
    """Trocea [desde, hasta] en tramos consecutivos de como máximo `dias` días."""
    if desde > hasta:
        raise ValueError(f"rango invertido: {desde} → {hasta}")
    if dias < 1:
        raise ValueError(f"tamaño de ventana inválido: {dias}")

    tramos = []
    inicio = desde
    while inicio <= hasta:
        fin = min(inicio + timedelta(days=dias - 1), hasta)
        tramos.append((inicio, fin))
        inicio = fin + timedelta(days=1)
    return tramos


def numero(valor) -> float | None:
    """Convierte los valores de AEMET ('7,9', 'Ip', 'Acum', '') a float o None."""
    if valor is None or str(valor).strip() in ("", "Ip", "Acum"):
        return None
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def leer_clave(ruta_env: Path | None = None) -> str:
    """Clave de AEMET: primero el entorno, después `.env`. Nunca se imprime."""
    clave = os.getenv("AEMET_API_KEY")
    if clave:
        return clave.strip()

    ruta_env = ruta_env or (RAIZ / ".env")
    if not ruta_env.exists():
        raise SystemExit(f"No hay AEMET_API_KEY ni {ruta_env}")
    encontrada = re.search(r'AEMET_API_KEY\s*=\s*"?([^"\r\n]+)"?', ruta_env.read_text(encoding="utf-8"))
    if not encontrada:
        raise SystemExit(f"{ruta_env} no contiene AEMET_API_KEY")
    return encontrada.group(1).strip()


# ─────────────────────────────────────────────
# Base de datos
# ─────────────────────────────────────────────

def crear_tabla(conn: sqlite3.Connection) -> None:
    """Misma definición que `_init_aemet_db` del notebook."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLA} (
            fecha TEXT NOT NULL, indicativo TEXT NOT NULL, nombre TEXT, provincia TEXT,
            tmed REAL, tmin REAL, tmax REAL, velmedia REAL, racha REAL, prec REAL, sol REAL,
            PRIMARY KEY (fecha, indicativo)
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_aemet_fecha ON {TABLA} (fecha)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_aemet_ind   ON {TABLA} (indicativo)")
    conn.commit()


def fechas_en_bd(conn: sqlite3.Connection, indicativo: str,
                 desde: date, hasta: date) -> set[str]:
    filas = conn.execute(
        f"SELECT fecha FROM {TABLA} WHERE indicativo = ? AND fecha BETWEEN ? AND ?",
        (indicativo, desde.isoformat(), hasta.isoformat()),
    ).fetchall()
    return {fila[0] for fila in filas}


def guardar(conn: sqlite3.Connection, filas: list[tuple]) -> None:
    conn.executemany(
        f"INSERT OR IGNORE INTO {TABLA} ({', '.join(COLUMNAS)}) "
        f"VALUES ({', '.join('?' * len(COLUMNAS))})",
        filas,
    )
    conn.commit()


# ─────────────────────────────────────────────
# API de AEMET
# ─────────────────────────────────────────────

def consultar(sesion: requests.Session, indicativo: str, desde: date, hasta: date,
              clave: str) -> list[tuple]:
    """Dos peticiones (meta-URL → datos) y devuelve las filas listas para la BD."""
    url = (
        "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos"
        f"/fechaini/{desde.isoformat()}T00:00:00UTC/fechafin/{hasta.isoformat()}T23:59:59UTC"
        f"/estacion/{indicativo}"
    )

    respuesta = None
    for intento in range(1, REINTENTOS_429 + 1):
        respuesta = sesion.get(url, params={"api_key": clave}, timeout=60)
        if respuesta.status_code != 429:
            break
        espera = 20 * intento
        log.warning("AEMET 429 en %s (%s→%s); espero %s s", indicativo, desde, hasta, espera)
        time.sleep(espera)

    if respuesta is None or respuesta.status_code != 200:
        estado = respuesta.status_code if respuesta is not None else "sin respuesta"
        detalle = ""
        if respuesta is not None:
            try:
                detalle = respuesta.json().get("descripcion", "")
            except ValueError:
                detalle = respuesta.text[:200]
        raise RuntimeError(f"AEMET {indicativo}: estado {estado} - {detalle}")

    meta = respuesta.json()
    url_datos = meta.get("datos")
    if not url_datos:
        raise RuntimeError(f"AEMET {indicativo}: sin URL de datos ({meta.get('descripcion')})")

    datos = sesion.get(url_datos, timeout=120).json()
    if not isinstance(datos, list):
        raise RuntimeError(f"AEMET {indicativo}: respuesta inesperada ({str(datos)[:200]})")

    return [
        (
            fila.get("fecha"), fila.get("indicativo"), fila.get("nombre"), fila.get("provincia"),
            numero(fila.get("tmed")), numero(fila.get("tmin")), numero(fila.get("tmax")),
            numero(fila.get("velmedia")), numero(fila.get("racha")),
            numero(fila.get("prec")), numero(fila.get("sol")),
        )
        for fila in datos
    ]


# ─────────────────────────────────────────────
# Orquestación
# ─────────────────────────────────────────────

def rellenar(conn: sqlite3.Connection, estaciones: list[str], desde: date, hasta: date,
             clave: str, pausa: float = PAUSA_SEGUNDOS, simular: bool = False) -> dict:
    """Descarga solo lo que falta. Idempotente: relanzarlo no añade filas."""
    crear_tabla(conn)
    sesion = requests.Session()
    resumen = {"peticiones": 0, "insertados": 0, "omitidos": 0, "errores": []}

    with sesion:
        for indice, indicativo in enumerate(estaciones, 1):
            log.info("[%d/%d] %s", indice, len(estaciones), indicativo)
            for desde_v, hasta_v in ventanas(desde, hasta):
                ya = fechas_en_bd(conn, indicativo, desde_v, hasta_v)
                esperados = (hasta_v - desde_v).days + 1
                if len(ya) >= esperados:
                    resumen["omitidos"] += esperados
                    log.info("   %s → %s completo en BD (%d días)", desde_v, hasta_v, esperados)
                    continue

                if simular:
                    log.info("   %s → %s pediría %d días", desde_v, hasta_v, esperados - len(ya))
                    continue

                try:
                    filas = consultar(sesion, indicativo, desde_v, hasta_v, clave)
                except (RuntimeError, requests.RequestException) as error:
                    resumen["errores"].append(str(error))
                    log.error("   %s → %s falló: %s", desde_v, hasta_v, error)
                    time.sleep(pausa)
                    continue

                resumen["peticiones"] += 1
                antes = conn.total_changes
                guardar(conn, filas)
                nuevos = conn.total_changes - antes
                resumen["insertados"] += nuevos
                log.info("   %s → %s  %d filas recibidas, %d nuevas", desde_v, hasta_v, len(filas), nuevos)
                time.sleep(pausa)

    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rellena aemet_diario con las estaciones fotovoltaicas.")
    parser.add_argument("--desde", default="2022-01-01")
    parser.add_argument("--hasta", default=(date.today() - timedelta(days=3)).isoformat())
    parser.add_argument("--estaciones", nargs="+", default=list(ESTACIONES_POR_DEFECTO))
    parser.add_argument("--db", type=Path, default=DB_POR_DEFECTO)
    parser.add_argument("--pausa", type=float, default=PAUSA_SEGUNDOS,
                        help="segundos entre ventanas (respeto al límite de AEMET)")
    parser.add_argument("--simular", action="store_true", help="no descarga, solo dice qué pediría")
    args = parser.parse_args(argv)

    # En Windows la consola suele ser cp1252 y los mensajes llevan tildes y flechas.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    desde = date.fromisoformat(args.desde)
    hasta = date.fromisoformat(args.hasta)
    clave = "" if args.simular else leer_clave()

    conn = sqlite3.connect(args.db)
    try:
        resumen = rellenar(conn, args.estaciones, desde, hasta, clave, args.pausa, args.simular)
    finally:
        conn.close()

    print(
        f"\nResumen: peticiones={resumen['peticiones']} insertados={resumen['insertados']} "
        f"omitidos={resumen['omitidos']} errores={len(resumen['errores'])}"
    )
    for error in resumen["errores"]:
        print(f"  - {error}")
    return 1 if resumen["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
