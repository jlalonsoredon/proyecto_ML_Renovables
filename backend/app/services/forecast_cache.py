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
from . import db_ree, forecast_db
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
ARCHIVO_DIAS = 21
ARCHIVO_MAX_AEMET = 600
ARCHIVO_MAX_REE = 60

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


def _as_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        instante = value
    elif isinstance(value, date):
        instante = datetime.combine(value, datetime.min.time())
    else:
        try:
            instante = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=MADRID)
    return instante.astimezone(timezone.utc)


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


def _prediction_records(snapshot: dict, hoy: date) -> list[dict]:
    """Extrae las emisiones durables del snapshot anterior (formato nuevo o viejo)."""
    if not isinstance(snapshot, dict):
        return []
    desde = hoy - timedelta(days=HISTORICO_DIAS - 1)
    hasta = hoy + timedelta(days=1)
    records = {}

    def add(row):
        if not isinstance(row, dict):
            return
        objetivo = _as_date(row.get("fecha_objetivo"))
        emision = _as_date(row.get("fecha_emision"))
        try:
            mwh = float(row.get("prediccion_mwh"))
        except (TypeError, ValueError):
            return
        if objetivo is None or emision is None or not (desde <= objetivo <= hasta):
            return
        if not math.isfinite(mwh) or mwh <= 0:
            return
        key = (objetivo.isoformat(), emision.isoformat())
        candidate = {
            "fecha_objetivo": key[0],
            "fecha_emision": key[1],
            "emitida_en": row.get("emitida_en"),
            "prediccion_mwh": mwh,
            "modelo": row.get("modelo"),
            "n_variables": row.get("n_variables"),
            "vector_entrada": row.get("vector_entrada"),
            "origenes": row.get("origenes"),
            "real_mwh": row.get("real_mwh"),
            "error_mwh": row.get("error_mwh"),
        }
        previous = records.get(key)
        if previous is None or (
            not previous.get("vector_entrada") and candidate.get("vector_entrada")
        ):
            records[key] = candidate

    grafico = snapshot.get("grafico") or {}
    for row in grafico.get("predicciones_propias") or []:
        add(row)
    manana = grafico.get("manana") or {}
    if manana.get("prediccion_mwh") is not None:
        add({
            "fecha_objetivo": manana.get("fecha"),
            "fecha_emision": manana.get("fecha_emision"),
            "emitida_en": manana.get("emitida_en"),
            "prediccion_mwh": manana.get("prediccion_mwh"),
            "modelo": manana.get("modelo"),
            "n_variables": manana.get("n_variables"),
            "vector_entrada": manana.get("vector_entrada"),
            "origenes": manana.get("origenes"),
        })
    for row in snapshot.get("historico") or []:
        prediccion = row.get("prediccion") if isinstance(row, dict) else None
        if isinstance(prediccion, dict):
            add({
                "fecha_objetivo": row.get("fecha"),
                "fecha_emision": prediccion.get("fecha_emision"),
                "emitida_en": prediccion.get("emitida_en"),
                "prediccion_mwh": prediccion.get("mwh"),
                "modelo": prediccion.get("modelo"),
                "n_variables": prediccion.get("n_variables"),
            })

    resultado = []
    for record in records.values():
        if not record.get("modelo"):
            record["modelo"] = "Linear Regression"
        if not record.get("n_variables"):
            record["n_variables"] = len(FEATURE_COLS)
        resultado.append(record)
    return resultado


def restore_predictions(snapshot_anterior, hoy: date) -> int:
    """Recupera del snapshot anterior las predicciones que la BD efímera perdió."""
    return db_ree.restore_own_predictions(_prediction_records(snapshot_anterior, hoy))


def _archive_value(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _archive_iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _forecast_archive_rows(hoy: date) -> dict:
    """Filas de previsiones que el snapshot conserva para sobrevivir a un reinicio.

    Se guarda la última revisión de cada (fuente, objetivo, ubicación) en la
    ventana que cubre las medias móviles de 14 días y los lags de 7. Es un
    archivo pequeño: no incluye observaciones ni el parte original.
    """
    desde = hoy - timedelta(days=ARCHIVO_DIAS - 1)
    hasta = hoy + timedelta(days=1)
    with db_ree._get_conn() as conn:
        filas = forecast_db.rows_between(conn, desde, hasta)

    minimo = datetime.min.replace(tzinfo=timezone.utc)
    revisiones = {}
    for fila in filas:
        fuente = fila.get("fuente")
        objetivo = fila.get("objetivo")
        ubicacion = fila.get("ubicacion")
        elaborado = _as_datetime(fila.get("elaborado"))
        if (
            fuente not in ("aemet", "ree")
            or objetivo is None
            or not ubicacion
            or elaborado is None
        ):
            continue
        key = (fuente, objetivo.isoformat(), ubicacion, fila.get("uso"))
        orden = (
            elaborado,
            _as_datetime(fila.get("capturado_en")) or minimo,
        )
        revisiones.setdefault(key, []).append((orden, fila))

    # Última revisión de cada clave y, si le falta alguna variable, también la
    # última que sí la trae (un parte nocturno deja `sol` del día en null).
    elegidas = []
    for (fuente, _, _, _), candidatas in revisiones.items():
        candidatas.sort(key=lambda item: item[0], reverse=True)
        elegidas.append((fuente, candidatas[0][1]))
        if fuente != "aemet":
            continue
        extra = []
        for campo in ("viento_ms", "racha_ms", "tmed", "sol"):
            if _archive_value(candidatas[0][1].get(campo)) is not None:
                continue
            respaldo = next(
                (
                    fila for _, fila in candidatas[1:]
                    if _archive_value(fila.get(campo)) is not None
                ),
                None,
            )
            if respaldo is not None and all(respaldo is not otra for otra in extra):
                extra.append(respaldo)
        elegidas.extend(("aemet", fila) for fila in extra)

    aemet, ree = [], []
    for fuente, fila in elegidas:
        if fuente == "aemet":
            aemet.append({
                "objetivo": fila["objetivo"].isoformat(),
                "ubicacion": fila["ubicacion"],
                "uso": fila.get("uso"),
                "elaborado": _archive_iso(fila.get("elaborado")),
                "capturado_en": _archive_iso(fila.get("capturado_en")),
                "viento_ms": fila.get("viento_ms"),
                "racha_ms": fila.get("racha_ms"),
                "tmed": fila.get("tmed"),
                "sol": fila.get("sol"),
            })
        else:
            ree.append({
                "objetivo": fila["objetivo"].isoformat(),
                "ubicacion": fila["ubicacion"],
                "elaborado": _archive_iso(fila.get("elaborado")),
                "capturado_en": _archive_iso(fila.get("capturado_en")),
                "eolica_mwh": fila.get("eolica_mwh"),
            })
    aemet.sort(key=lambda row: (
        row["objetivo"], row["ubicacion"], row.get("uso") or "",
        str(row.get("elaborado") or ""),
    ))
    ree.sort(key=lambda row: (row["objetivo"], row["ubicacion"]))
    return {"aemet": aemet, "ree": ree}


def _archive_records_from_block(archivo: dict, hoy: date) -> tuple[list[dict], list[dict]]:
    desde = hoy - timedelta(days=ARCHIVO_DIAS - 1)
    hasta = hoy + timedelta(days=1)
    aemet, ree = [], []

    for fila in archivo.get("aemet") or []:
        if not isinstance(fila, dict):
            continue
        objetivo = _as_date(fila.get("objetivo"))
        ubicacion = str(fila.get("ubicacion") or "").strip()
        elaborado = _as_datetime(fila.get("elaborado"))
        if (
            objetivo is None
            or not (desde <= objetivo <= hasta)
            or not ubicacion
            or elaborado is None
        ):
            continue
        uso = str(fila.get("uso") or "eolica")
        if uso not in ("eolica", "solar"):
            continue
        valores = {
            "viento_ms": _archive_value(fila.get("viento_ms")),
            "racha_ms": _archive_value(fila.get("racha_ms")),
            "tmed": _archive_value(fila.get("tmed")),
            "sol": _archive_value(fila.get("sol")),
        }
        if not any(value is not None for value in valores.values()):
            continue
        aemet.append({
            "objetivo": objetivo,
            "ubicacion": ubicacion,
            "uso": uso,
            "elaborado": elaborado,
            "capturado_en": _as_datetime(fila.get("capturado_en")) or elaborado,
            **valores,
        })

    for fila in archivo.get("ree") or []:
        if not isinstance(fila, dict):
            continue
        objetivo = _as_date(fila.get("objetivo"))
        elaborado = _as_datetime(fila.get("elaborado"))
        valor = _archive_value(fila.get("eolica_mwh"))
        if (
            objetivo is None
            or not (desde <= objetivo <= hasta)
            or elaborado is None
            or valor is None
        ):
            continue
        ree.append({
            "objetivo": objetivo,
            "ubicacion": str(fila.get("ubicacion") or "peninsula"),
            "uso": "eolica",
            "elaborado": elaborado,
            "capturado_en": _as_datetime(fila.get("capturado_en")) or elaborado,
            "eolica_mwh": valor,
        })
    return aemet, ree


def _bootstrap_archive_records(snapshot: dict, hoy: date) -> tuple[list[dict], list[dict]]:
    """Recupera el agregado nacional que un snapshot viejo sí conserva.

    Los snapshots publicados antes de V13 no tienen `archivo_previsiones`, pero
    su `historico` guarda la media nacional con el origen de cada variable. Para
    el 22/11 eso es suficiente: se repone una fila `nacional` y la media de las
    ubicaciones no se inventa.
    """
    generado = _as_datetime(snapshot.get("fecha_generacion"))
    generado_local = generado.astimezone(MADRID) if generado is not None else None
    aemet = []
    for row in snapshot.get("historico") or []:
        if not isinstance(row, dict):
            continue
        objetivo = _as_date(row.get("fecha"))
        if objetivo is None or not (hoy - timedelta(days=7) <= objetivo <= hoy):
            continue
        dia = row.get("aemet") or {}
        origen = dia.get("origen") or {}
        viento = (
            _archive_value(dia.get("velmedia"))
            if origen.get("velmedia") == "prevision" else None
        )
        racha = (
            _archive_value(dia.get("racha"))
            if origen.get("racha") == "prevision" else None
        )
        if viento is None and racha is None:
            continue
        if generado_local is not None and generado_local.date() == objetivo:
            elaborado = generado
        else:
            # El snapshot no declara la elaboración de cada día; se usa el
            # inicio del objetivo para que la fila sea elegible sin fingir una
            # hora que no consta.
            elaborado = datetime.combine(
                objetivo, datetime.min.time(), tzinfo=MADRID
            )
        aemet.append({
            "objetivo": objetivo,
            "ubicacion": "nacional",
            "uso": "eolica",
            "elaborado": elaborado,
            "capturado_en": generado or elaborado,
            "viento_ms": viento,
            "racha_ms": racha,
            "tmed": None,
            "sol": None,
        })
    return aemet, []


def restore_forecast_archive(snapshot_anterior, hoy: date) -> int:
    """Repone AEMET/REE desde el snapshot anterior antes de calcular.

    Si el snapshot es anterior a V13, usa el agregado nacional del `historico`
    solo para los días que no tengan ya ninguna fila AEMET. La inserción es
    idempotente y nunca pisa una revisión existente.
    """
    if not isinstance(snapshot_anterior, dict):
        return 0
    archivo = snapshot_anterior.get("archivo_previsiones")
    if isinstance(archivo, dict):
        aemet_rows, ree_rows = _archive_records_from_block(archivo, hoy)
    else:
        aemet_rows, ree_rows = _bootstrap_archive_records(snapshot_anterior, hoy)
        if aemet_rows:
            existentes = forecast_db.archived_days(None, "aemet")
            aemet_rows = [
                row for row in aemet_rows if row["objetivo"] not in existentes
            ]

    restauradas = 0
    if aemet_rows:
        restauradas += forecast_db.restore_forecast_rows(None, aemet_rows, "aemet")
    if ree_rows:
        restauradas += forecast_db.restore_forecast_rows(None, ree_rows, "ree")
    return restauradas


def _validate_forecast_archive(archivo, hoy: date) -> list[str]:
    if not isinstance(archivo, dict):
        return ["V13: archivo_previsiones no es un objeto"]

    problemas = []
    desde = hoy - timedelta(days=ARCHIVO_DIAS - 1)
    hasta = hoy + timedelta(days=1)
    for clave, maximo in (
        ("aemet", ARCHIVO_MAX_AEMET),
        ("ree", ARCHIVO_MAX_REE),
    ):
        filas = archivo.get(clave)
        if not isinstance(filas, list):
            problemas.append(f"V13: archivo_previsiones.{clave} no es una lista")
            continue
        if len(filas) > maximo:
            problemas.append(
                f"V13: archivo_previsiones.{clave} supera {maximo} filas"
            )
        for posicion, fila in enumerate(filas):
            if not isinstance(fila, dict):
                problemas.append(
                    f"V13: archivo_previsiones.{clave}[{posicion}] no es un objeto"
                )
                continue
            objetivo = _as_date(fila.get("objetivo"))
            if objetivo is None or not (desde <= objetivo <= hasta):
                problemas.append(
                    f"V13: archivo_previsiones.{clave}[{posicion}].objetivo fuera de rango"
                )
                continue
            if not str(fila.get("ubicacion") or "").strip():
                problemas.append(
                    f"V13: archivo_previsiones.{clave}[{posicion}] sin ubicación"
                )
            if _as_datetime(fila.get("elaborado")) is None:
                problemas.append(
                    f"V13: archivo_previsiones.{clave}[{posicion}] sin elaborado"
                )
            campos = (
                ("viento_ms", "racha_ms", "tmed", "sol")
                if clave == "aemet" else ("eolica_mwh",)
            )
            for campo in campos:
                valor = fila.get(campo)
                if valor is not None and not _finite(valor):
                    problemas.append(
                        f"V13: archivo_previsiones.{clave}[{posicion}].{campo} no es finito"
                    )
    return problemas


def build_snapshot(hoy: date, ahora: datetime | None = None, avisos=None) -> dict:
    """Compone el snapshot con las funciones internas; no ejecuta la tarea diaria."""
    ahora = ahora or datetime.now(timezone.utc)
    grafico = charts.build_current_chart(hoy, dias_historico=HISTORICO_DIAS)
    historico = grafico.pop("historico", [])
    prediccion = prediction_service.get_prediction(hoy)
    return {
        "schema_version": SCHEMA_VERSION,
        "version": ahora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        "fecha_generacion": ahora.astimezone(MADRID).isoformat(timespec="seconds"),
        "fecha_objetivo": prediccion["fecha"],
        "fecha_emision": prediccion["fecha_emision"],
        "fecha_observacion": charts.last_observation(historico),
        "prediccion": prediccion,
        "historico": historico,
        "grafico": grafico,
        "archivo_previsiones": _forecast_archive_rows(hoy),
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
        observadas = [
            fecha for fecha, item in zip(fechas, historico)
            if _finite(item.get("eolica"))
        ]
        observacion = _as_date(snapshot.get("fecha_observacion"))
        if not observadas:
            problemas.append("V7: historico no tiene ningún día con generación real")
        elif observacion != observadas[-1]:
            problemas.append("V7: fecha_observacion no es la última fecha con generación real")
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
        if not isinstance(item, dict):
            problemas.append(f"V11: historico[{posicion}] no es un objeto")
            break
        if item.get("eolica") is not None and not _finite(item.get("eolica")):
            problemas.append(f"V11: historico[{posicion}].eolica no es un número")
            break
        aemet = item.get("aemet")
        if aemet is not None and not isinstance(aemet, dict):
            problemas.append(f"V11: historico[{posicion}].aemet no es un objeto")
            break
        if isinstance(aemet, dict):
            malo = next(
                (clave for clave in ("velmedia", "racha", "sol", "tmed")
                 if aemet.get(clave) is not None and not _finite(aemet.get(clave))),
                None,
            )
            if malo:
                problemas.append(f"V11: historico[{posicion}].aemet.{malo} no es un número")
                break
        prediccion_dia = item.get("prediccion")
        if prediccion_dia is not None and not isinstance(prediccion_dia, dict):
            problemas.append(f"V11: historico[{posicion}].prediccion no es un objeto")
            break
        if isinstance(prediccion_dia, dict):
            malo = next(
                (clave for clave in ("mwh", "gwh")
                 if prediccion_dia.get(clave) is not None
                 and not _finite(prediccion_dia.get(clave))),
                None,
            )
            if malo:
                problemas.append(f"V11: historico[{posicion}].prediccion.{malo} no es un número")
                break

    # V12
    observadas = sum(
        1 for item in historico
        if isinstance(item, dict) and _finite(item.get("eolica"))
    )
    if observadas < MIN_PUNTOS_HISTORICO:
        problemas.append(
            f"V12: historico tiene {observadas} días con generación real; "
            f"se exigen al menos {MIN_PUNTOS_HISTORICO}"
        )

    # V13: el archivo es opcional para seguir aceptando snapshots anteriores.
    if "archivo_previsiones" in snapshot:
        problemas.extend(
            _validate_forecast_archive(snapshot.get("archivo_previsiones"), hoy)
        )

    return problemas


def refresh(force: bool = False, hoy: date | None = None,
            snapshot_anterior: dict | None = None) -> dict:
    """Ejecuta la tarea diaria y devuelve el snapshot validado.

    `snapshot_anterior` es el archivo durable de predicciones: el workflow envía
    el último snapshot publicado para recuperar lo que la SQLite efímera perdió.
    La restauración se intenta antes del atajo de caché; si recupera filas, se
    recalcula aunque no haya `force`. Sin `force`, una segunda llamada para el
    mismo objetivo devuelve la ejecución cacheada. Solo se cachean las
    ejecuciones sin avisos bloqueantes: los de AVISOS_ESPERADOS no cuentan.
    """
    global _cache
    if not _lock.acquire(blocking=False):
        raise RunInProgress("hay una generación en curso")
    try:
        hoy = hoy or today_in_madrid()
        objetivo = (hoy + timedelta(days=1)).isoformat()

        # Se restaura antes del atajo de caché: tras un reinicio el scheduler de
        # las 03:00 puede haber cacheado un snapshot sin las predicciones
        # históricas. Si se recuperó alguna fila, hay que recalcular para que el
        # snapshot publicado las incluya.
        fuente = snapshot_anterior if snapshot_anterior is not None else (
            _cache.get("snapshot") if _cache else None
        )
        restauradas_predicciones = 0
        restauradas_previsiones = 0
        if fuente:
            try:
                restauradas_predicciones = restore_predictions(fuente, hoy)
                if restauradas_predicciones:
                    logger.info(
                        "%d predicciones históricas restauradas; se recalcula el snapshot",
                        restauradas_predicciones,
                    )
            except Exception as error:
                logger.warning(
                    "No se pudieron restaurar predicciones históricas: %s",
                    redact_secrets(error),
                )
            try:
                restauradas_previsiones = restore_forecast_archive(fuente, hoy)
                if restauradas_previsiones:
                    logger.info(
                        "%d previsiones AEMET/REE restauradas; se recalcula el snapshot",
                        restauradas_previsiones,
                    )
            except Exception as error:
                logger.warning(
                    "No se pudieron restaurar las previsiones AEMET/REE: %s",
                    redact_secrets(error),
                )
        restauradas = restauradas_predicciones + restauradas_previsiones

        if (
            not force
            and restauradas == 0
            and _cache
            and _cache["snapshot"]["fecha_objetivo"] == objetivo
        ):
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
