"""Captura diaria del parte de AEMET (spec 003, RF-1, RF-3, RF-6, RF-13).

Descarga el parte diario y el horario de cada ubicación del catálogo, los
fusiona con `forecast_logic` y los guarda en el archivo propio. Un fallo de una
ubicación no detiene al resto (CA-3.3) y nunca se rellena con otra ubicación,
con la observación ni con una interpolación (CA-6.5).

El parte se pide con la API de dos pasos de AEMET (meta-URL → datos), con pausa
entre peticiones y un reintento ante el límite de peticiones (RNF-7).
"""

import logging
import os
import time
from datetime import date, datetime, timedelta

import requests

from . import forecast_db
from .forecast_logic import (
    HORIZONTE_DIAS,
    UBICACIONES,
    capture_targets,
    forecast_rows,
    parse_daily_parte,
    parse_hourly_parte,
)

logger = logging.getLogger(__name__)

AEMET_BASE_URL = "https://opendata.aemet.es/opendata/api"
RUTAS = ("diaria", "horaria")

ESPERA_ENTRE_PETICIONES = 0.6   # segundos; AEMET limita el ritmo de peticiones
ESPERA_TRAS_LIMITE = 60         # CA-1.5 / RNF-7: un 429 se reintenta, no se pierde
ESPERA_TRAS_ERROR = 3
INTENTOS = 2
TIEMPO_ESPERA = 20


# ─────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────

def _pedir_json(url: str, clave: str, sesion=requests):
    """Petición JSON con reintento en timeout y en el límite de peticiones.

    Devuelve (json, error). Nunca lanza: el fallo de una ubicación es una
    incidencia que se registra, no una excepción que tumba la captura.
    """
    for intento in range(INTENTOS):
        try:
            respuesta = sesion.get(url, params={"api_key": clave}, timeout=TIEMPO_ESPERA)
        except requests.exceptions.Timeout:
            if intento + 1 < INTENTOS:
                logger.warning(f"AEMET timeout — reintentando en {ESPERA_TRAS_ERROR}s")
                time.sleep(ESPERA_TRAS_ERROR)
                continue
            return None, "timeout"
        except requests.exceptions.RequestException as error:
            return None, f"red: {error}"

        if respuesta.status_code == 429:
            logger.warning(f"AEMET límite de peticiones (429) — esperando {ESPERA_TRAS_LIMITE}s")
            time.sleep(ESPERA_TRAS_LIMITE)
            continue

        if respuesta.status_code != 200:
            return None, f"HTTP {respuesta.status_code}"

        try:
            return respuesta.json(), None
        except ValueError:
            return None, "respuesta no es JSON"

    return None, "límite de peticiones persistente"


def descargar_parte(municipio: str, ruta: str, clave: str, sesion=requests):
    """Dos pasos de AEMET: la meta-URL y luego el parte. Devuelve (parte, error)."""
    url = f"{AEMET_BASE_URL}/prediccion/especifica/municipio/{ruta}/{municipio}"
    meta, error = _pedir_json(url, clave, sesion)
    if meta is None:
        return None, error

    datos_url = meta.get("datos")
    if not datos_url:
        return None, meta.get("descripcion") or "sin URL de datos"

    time.sleep(ESPERA_ENTRE_PETICIONES)
    contenido, error = _pedir_json(datos_url, clave, sesion)
    if contenido is None:
        return None, error

    if isinstance(contenido, list):
        if not contenido:
            return None, "parte vacío"
        contenido = contenido[0]

    if not isinstance(contenido, dict) or not contenido.get("prediccion"):
        return None, "parte sin previsión"
    return contenido, None


def descargar_partes(ubicacion: dict, clave: str, sesion=requests) -> dict:
    """Los dos partes de una ubicación. Los errores se devuelven, no se lanzan."""
    partes = {"diaria": None, "horaria": None, "errores": []}
    for ruta in RUTAS:
        parte, error = descargar_parte(ubicacion["municipio"], ruta, clave, sesion)
        if parte is None:
            partes["errores"].append(f"{ruta}: {error}")
            logger.warning(f"AEMET [{ubicacion['clave']}] {ruta}: {error}")
        else:
            partes[ruta] = parte
        time.sleep(ESPERA_ENTRE_PETICIONES)
    return partes


# ─────────────────────────────────────────────
# Captura
# ─────────────────────────────────────────────

def capture_forecast(hoy: date | None = None, descargador=None, conn=None,
                     clave: str | None = None) -> dict:
    """Captura completa y resumen de la ejecución (CA-13.1, CA-13.2).

    `descargador` permite sustituir la red en las pruebas; recibe la ubicación y
    devuelve `{"diaria", "horaria", "errores"}`.
    """
    hoy = hoy or date.today()
    clave = clave if clave is not None else os.environ.get("AEMET_API_KEY", "")
    descargador = descargador or (lambda ubicacion: descargar_partes(ubicacion, clave))
    if not clave:
        logger.warning(
            "AEMET_API_KEY no configurada — la captura fallará en todas las ubicaciones"
        )

    forecast_db.ensure_schema(conn)
    capturado_en = datetime.now()

    # Solo se archivan los días del horizonte que el mapa va a consultar. El
    # filtro usa la ventana completa, no la de pendientes: una elaboración nueva
    # de un día ya cubierto también debe guardarse (CA-4.2).
    ventana = set(capture_targets(hoy, set(), horizonte=HORIZONTE_DIAS))
    a_pedir = set(capture_targets(
        hoy, forecast_db.archived_days(conn), horizonte=HORIZONTE_DIAS,
    ))

    guardadas = 0
    ubicaciones_ok = 0
    errores = []
    obtenidos = set()
    elaboraciones = set()

    for ubicacion in UBICACIONES:
        try:
            partes = descargador(ubicacion) or {}
        except Exception as error:  # una ubicación no puede tumbar la captura
            errores.append(f"{ubicacion['clave']}: {error}")
            logger.error(f"Captura [{ubicacion['clave']}]: {error}")
            continue

        for error in partes.get("errores") or []:
            errores.append(f"{ubicacion['clave']} {error}")

        diario = partes.get("diaria")
        if not diario:
            continue

        horario = partes.get("horaria")
        filas = forecast_rows(
            parse_daily_parte(diario),
            parse_hourly_parte(horario) if horario else None,
            ubicacion["clave"],
            ubicacion["uso"],
            ubicacion["lat"],
            capturado_en,
        )
        filas = [fila for fila in filas if fila["objetivo"] in ventana]

        # Se guardan los dos partes: sin ellos el indicador no se puede recalcular.
        partes_originales = {"diaria": diario, "horaria": horario}
        guardadas += forecast_db.save_forecast(conn, filas, partes_originales)
        ubicaciones_ok += 1
        obtenidos.update(fila["objetivo"] for fila in filas)
        elaboraciones.add(str(diario.get("elaborado") or "sin elaboración"))

    # Días del horizonte inmediato que la fuente no ha servido (CA-1.2, CE-6).
    pendientes_de_hoy = sorted(
        dia for dia in a_pedir
        if hoy <= dia <= hoy + timedelta(days=HORIZONTE_DIAS - 1) and dia not in obtenidos
    )

    archivados = forecast_db.archived_days(conn)
    desde = forecast_db.first_capture_day(conn) or hoy
    esperados = forecast_db.expected_days(hoy, desde, horizonte=HORIZONTE_DIAS)
    cobertura = forecast_db.capture_summary(hoy, archivados, esperados)

    estado = _estado(ubicaciones_ok, len(UBICACIONES))
    resumen = {
        "ejecutada_en": capturado_en,
        "hoy": hoy,
        "ubicaciones_ok": ubicaciones_ok,
        "ubicaciones_error": len(UBICACIONES) - ubicaciones_ok,
        "filas_guardadas": guardadas,
        "horizonte_dias": len({dia for dia in obtenidos if dia >= hoy}),
        "dias_sin_capturar": pendientes_de_hoy,
        "dias_pendientes": cobertura["dias_pendientes"],
        "desde_pendiente": cobertura["desde_pendiente"],
        "errores": errores,
        "elaboraciones": sorted(elaboraciones),
        "estado": estado,
    }
    resumen["detalle"] = _detalle(resumen)

    forecast_db.register_capture(
        conn,
        ejecutada_en=capturado_en,
        ubicaciones_ok=ubicaciones_ok,
        ubicaciones_error=resumen["ubicaciones_error"],
        filas_guardadas=guardadas,
        estado=estado,
        detalle=resumen["detalle"],
        dias_pendientes=resumen["dias_pendientes"],
        desde_pendiente=resumen["desde_pendiente"],
    )

    nivel = logging.ERROR if estado == "fallo" else logging.INFO
    logger.log(nivel, f"Captura AEMET: {resumen['detalle']}")
    return resumen


def _estado(ubicaciones_ok: int, total: int) -> str:
    if ubicaciones_ok == 0:
        return "fallo"
    return "ok" if ubicaciones_ok == total else "parcial"


def _detalle(resumen: dict) -> str:
    partes = [
        f"{resumen['ubicaciones_ok']} ubicaciones capturadas",
        f"{resumen['filas_guardadas']} filas guardadas",
    ]
    if resumen["horizonte_dias"]:
        partes.append(f"horizonte de {resumen['horizonte_dias']} días")
    if resumen["dias_pendientes"]:
        desde = resumen["desde_pendiente"]
        partes.append(
            f"{resumen['dias_pendientes']} días pendientes"
            + (f" desde {desde.isoformat()}" if desde else "")
        )
    if resumen.get("elaboraciones"):
        partes.append("elaboración " + ", ".join(resumen["elaboraciones"]))
    if resumen["errores"]:
        partes.append(f"{len(resumen['errores'])} errores: " + "; ".join(resumen["errores"][:5]))
    return " · ".join(partes)
