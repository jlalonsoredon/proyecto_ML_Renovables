"""Snapshot diario de previsión: composición, validación y caché en memoria.

El snapshot reúne en un solo objeto los tres payloads que consume la web
(`prediccion`, `historico` y `grafico`). Se construye con funciones internas,
nunca con los endpoints HTTP del propio servicio, y solo se entrega si pasa la
validación V1–V12 de la spec 010.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..api import charts
from ..tasks.scheduler import scheduler_service
from .model_loader import FEATURE_COLS
from .prediction_service import prediction_service, today_in_madrid
from .redaction import redact_secrets

logger = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")

SCHEMA_VERSION = 1
HISTORICO_DIAS = 45
MIN_PUNTOS_HISTORICO = 30
MAX_ANTIGUEDAD_OBSERVACION = 2
ORIGENES_VALIDOS = {"observacion", "prevision", "mixta", "estimada"}
PASOS_SIN_INCIDENCIA = {"ok"}
# Avisos esperables a la hora de publicar: ESIOS aún no tiene el D+1 de madrugada
# y AEMET aún no tiene el diario de ayer. No impiden guardar la caché.
# Espejo de AVISOS_ESPERADOS en frontend/src/utils/forecast.mjs.
AVISOS_ESPERADOS = frozenset({
    "Paso capture_ree_forecast: fallo",
    "Paso download_aemet_data: parcial",
})
BACKFILL_TIMEOUT_S = 600

# Fragmentos que delatan una gráfica construida sin datos reales (V10).
MARCAS_DATOS_NO_REALES = (
    "no se pudieron leer",
    "sin datos históricos",
    "no hay una predicción propia",
    "simulad",
    "mock",
)

_VERSION = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z$")

_lock = threading.Lock()
_cache: dict | None = None


class RunInProgress(RuntimeError):
    """Ya hay una generación del snapshot en curso."""


class SnapshotInvalid(RuntimeError):
    """El snapshot no pasa la validación o no se pudo construir."""

    def __init__(self, problemas: list[str]):
        self.problemas = list(problemas)
        super().__init__("; ".join(self.problemas))


def _as_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _finite(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _non_finite_paths(value, path="snapshot") -> list[str]:
    if isinstance(value, float) and not math.isfinite(value):
        return [path]
    if isinstance(value, dict):
        found = []
        for key, item in value.items():
            found += _non_finite_paths(item, f"{path}.{key}")
        return found
    if isinstance(value, list):
        found = []
        for index, item in enumerate(value):
            found += _non_finite_paths(item, f"{path}[{index}]")
        return found
    return []


def _step_state(result) -> str:
    if result is None:
        return "fallo"
    if isinstance(result, dict):
        return str(result.get("estado") or "ok")
    return "ok"


def summarize_steps(pasos: dict) -> tuple[dict, list[str]]:
    """Devuelve el estado de cada paso y un aviso por cada uno con incidencia."""
    estados = {nombre: _step_state(resultado) for nombre, resultado in pasos.items()}
    avisos = [
        f"Paso {nombre}: {estado}"
        for nombre, estado in estados.items()
        if estado not in PASOS_SIN_INCIDENCIA
    ]
    return estados, avisos


def build_snapshot(hoy: date, ahora: datetime | None = None, avisos=None) -> dict:
    """Compone el snapshot con las funciones internas; no ejecuta la tarea diaria."""
    ahora = ahora or datetime.now(timezone.utc)
    historico = charts.get_historico_eolica(HISTORICO_DIAS, hoy=hoy)
    prediccion = prediction_service.get_prediction(hoy)
    grafico = charts.build_current_chart(hoy)
    return {
        "schema_version": SCHEMA_VERSION,
        "version": ahora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        "fecha_generacion": ahora.astimezone(MADRID).isoformat(timespec="seconds"),
        "fecha_objetivo": prediccion["fecha"],
        "fecha_emision": prediccion["fecha_emision"],
        "fecha_observacion": historico[-1]["fecha"] if historico else None,
        "prediccion": prediccion,
        "historico": historico,
        "grafico": grafico,
        "avisos": list(avisos or []),
    }


def validate_snapshot(snapshot, hoy: date) -> list[str]:
    """Aplica V1–V12; una lista vacía significa que el snapshot es válido."""
    if not isinstance(snapshot, dict):
        return ["V1: el snapshot no es un objeto"]

    problemas: list[str] = []
    manana = hoy + timedelta(days=1)
    prediccion = snapshot.get("prediccion")
    historico = snapshot.get("historico")
    grafico = snapshot.get("grafico")

    # V1
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        problemas.append("V1: schema_version no es 1")
    if not _VERSION.match(str(snapshot.get("version", ""))):
        problemas.append("V1: version no tiene formato YYYY-MM-DDTHHMMSSZ")
    for clave in ("fecha_generacion", "fecha_objetivo", "fecha_emision", "fecha_observacion"):
        if not snapshot.get(clave):
            problemas.append(f"V1: falta {clave}")
    if not isinstance(prediccion, dict):
        problemas.append("V1: falta prediccion")
        prediccion = {}
    if not isinstance(historico, list):
        problemas.append("V1: falta historico")
        historico = []
    if not isinstance(grafico, dict):
        problemas.append("V1: falta grafico")
        grafico = {}
    if not isinstance(snapshot.get("avisos"), list):
        problemas.append("V1: avisos no es una lista")

    # V2
    objetivo = snapshot.get("fecha_objetivo")
    if not (prediccion.get("fecha") == objetivo == manana.isoformat()):
        problemas.append(
            f"V2: fecha de la predicción ({prediccion.get('fecha')}), "
            f"fecha_objetivo ({objetivo}) y mañana ({manana.isoformat()}) no coinciden"
        )

    # V3
    emision = prediccion.get("fecha_emision")
    if not (emision == hoy.isoformat() and snapshot.get("fecha_emision") == emision):
        problemas.append("V3: fecha_emision no es hoy o no coincide con la de la predicción")

    # V4
    if not prediccion.get("modelo"):
        problemas.append("V4: modelo vacío")
    if prediccion.get("n_variables") != len(FEATURE_COLS):
        problemas.append(f"V4: n_variables no es {len(FEATURE_COLS)}")

    # V5
    valor = prediccion.get("prediccionMWh")
    if not (_finite(valor) and valor > 0):
        problemas.append("V5: prediccionMWh no es un número finito mayor que cero")

    # V6
    vector = prediccion.get("vector_entrada")
    origenes = prediccion.get("origenes")
    if not isinstance(vector, dict) or tuple(vector) != tuple(FEATURE_COLS):
        problemas.append("V6: vector_entrada no tiene las variables de FEATURE_COLS en orden")
    elif any(not _finite(item) for item in vector.values()):
        problemas.append("V6: vector_entrada contiene valores no finitos")
    if not isinstance(origenes, dict) or tuple(origenes) != tuple(FEATURE_COLS):
        problemas.append("V6: origenes no tiene las variables de FEATURE_COLS en orden")
    elif any(item not in ORIGENES_VALIDOS for item in origenes.values()):
        problemas.append("V6: origenes contiene un origen no permitido")

    # V7
    fechas = [_as_date(item.get("fecha")) if isinstance(item, dict) else None for item in historico]
    if not historico:
        problemas.append("V7: historico vacío")
    elif any(item is None for item in fechas):
        problemas.append("V7: historico contiene fechas ilegibles")
    else:
        if any(a >= b for a, b in zip(fechas, fechas[1:])):
            problemas.append("V7: historico no está ordenado ni es estrictamente creciente")
        observacion = _as_date(snapshot.get("fecha_observacion"))
        if observacion != fechas[-1]:
            problemas.append("V7: fecha_observacion no es la última fecha del historico")
        if observacion is None or observacion < hoy - timedelta(days=MAX_ANTIGUEDAD_OBSERVACION):
            problemas.append(
                f"V7: fecha_observacion tiene más de {MAX_ANTIGUEDAD_OBSERVACION} días de antigüedad"
            )

    # V8
    series = ("fechas_hist", "real_gwh", "pred_gwh", "vel_norm", "racha_norm", "vel_ms", "racha_ms")
    longitudes = {}
    for clave in series:
        lista = grafico.get(clave)
        if not isinstance(lista, list):
            problemas.append(f"V8: grafico.{clave} no es una lista")
        else:
            longitudes[clave] = len(lista)
    if len(set(longitudes.values())) > 1:
        problemas.append(f"V8: longitudes desalineadas en grafico: {longitudes}")

    # V8 (opcionales): origen del viento rellenado con previsión.
    for clave in ("vel_origen", "racha_origen"):
        lista = grafico.get(clave)
        if lista is None:
            continue
        if not isinstance(lista, list):
            problemas.append(f"V8: grafico.{clave} no es una lista")
        elif "fechas_hist" in longitudes and len(lista) != longitudes["fechas_hist"]:
            problemas.append(f"V8: grafico.{clave} no está alineada con fechas_hist")
        elif any(valor not in (None, "observacion", "prevision") for valor in lista):
            problemas.append(f"V8: grafico.{clave} tiene orígenes no válidos")

    # V9
    manana_grafico = grafico.get("manana")
    if not isinstance(manana_grafico, dict):
        problemas.append("V9: falta grafico.manana")
    else:
        valor_grafico = manana_grafico.get("prediccion_mwh")
        if manana_grafico.get("fecha") != objetivo:
            problemas.append("V9: grafico.manana.fecha no coincide con fecha_objetivo")
        if not (_finite(valor_grafico) and _finite(valor) and abs(valor_grafico - valor) < 1):
            problemas.append("V9: grafico.manana.prediccion_mwh difiere de prediccionMWh en 1 MWh o más")

    # V10
    avisos_grafico = grafico.get("avisos")
    if not isinstance(avisos_grafico, list):
        problemas.append("V10: grafico.avisos no es una lista")
    else:
        for aviso in avisos_grafico:
            texto = str(aviso).lower()
            if any(marca in texto for marca in MARCAS_DATOS_NO_REALES):
                problemas.append(f"V10: aviso de datos no reales en la gráfica: {aviso}")

    # V11
    for ruta in _non_finite_paths(snapshot):
        problemas.append(f"V11: valor no finito en {ruta}")
    for posicion, item in enumerate(historico):
        if isinstance(item, dict) and not _finite(item.get("eolica")):
            problemas.append(f"V11: historico[{posicion}].eolica no es un número")
            break

    # V12
    if len(historico) < MIN_PUNTOS_HISTORICO:
        problemas.append(
            f"V12: historico tiene {len(historico)} puntos; se exigen al menos {MIN_PUNTOS_HISTORICO}"
        )

    return problemas


def refresh(force: bool = False, hoy: date | None = None) -> dict:
    """Ejecuta la tarea diaria y devuelve el snapshot validado.

    Sin `force`, una segunda llamada para el mismo objetivo devuelve la ejecución
    cacheada. Solo se cachean las ejecuciones sin avisos bloqueantes: los de
    AVISOS_ESPERADOS no cuentan.
    """
    global _cache
    if not _lock.acquire(blocking=False):
        raise RunInProgress("hay una generación en curso")
    try:
        hoy = hoy or today_in_madrid()
        objetivo = (hoy + timedelta(days=1)).isoformat()
        if not force and _cache and _cache["snapshot"]["fecha_objetivo"] == objetivo:
            logger.info("Snapshot ya generado para %s (run_id=%s)", objetivo, _cache["run_id"])
            return {**_cache, "estado": "already_done"}

        inicio = time.monotonic()
        ahora = datetime.now(timezone.utc)
        run_id = ahora.strftime("%Y-%m-%dT%H%M%SZ")
        logger.info("Snapshot %s: iniciando para %s", run_id, objetivo)

        avisos_previos = []
        if not scheduler_service.backfill_done.wait(timeout=BACKFILL_TIMEOUT_S):
            aviso = (
                f"El backfill de AEMET no terminó en {BACKFILL_TIMEOUT_S / 60:g} minutos; "
                "se continúa sin esperar más"
            )
            logger.warning("Snapshot %s: %s", run_id, aviso)
            avisos_previos.append(aviso)

        pasos, avisos = summarize_steps(scheduler_service.run_daily_task(hoy))
        avisos = avisos_previos + avisos
        try:
            snapshot = build_snapshot(hoy, ahora=ahora, avisos=avisos)
        except Exception as error:
            problema = f"No se pudo componer el snapshot: {type(error).__name__}: {redact_secrets(error)}"
            logger.error("Snapshot %s: %s", run_id, problema)
            raise SnapshotInvalid([problema]) from error

        problemas = validate_snapshot(snapshot, hoy)
        duracion = round(time.monotonic() - inicio, 1)
        if problemas:
            logger.error(
                "Snapshot %s rechazado en %.1f s; pasos_fallidos=%s problemas=%s",
                run_id, duracion, avisos, problemas,
            )
            raise SnapshotInvalid(problemas)

        resultado = {
            "estado": "actualizado",
            "run_id": run_id,
            "duracion_s": duracion,
            "pasos": pasos,
            "avisos": avisos,
            "snapshot": snapshot,
        }
        bloqueantes = [aviso for aviso in avisos if aviso not in AVISOS_ESPERADOS]
        if bloqueantes:
            _cache = None
            logger.warning(
                "Snapshot %s válido con avisos en %.1f s; no se cachea: %s",
                run_id, duracion, bloqueantes,
            )
        else:
            _cache = resultado
            logger.info("Snapshot %s válido en %.1f s", run_id, duracion)
        return resultado
    finally:
        _lock.release()


def cached() -> dict | None:
    """Metadatos del snapshot en memoria, sin el contenido."""
    if not _cache:
        return None
    snapshot = _cache["snapshot"]
    return {
        "version": snapshot["version"],
        "fecha_objetivo": snapshot["fecha_objetivo"],
        "generado_en": snapshot["fecha_generacion"],
    }


def clear_cache() -> None:
    global _cache
    _cache = None
