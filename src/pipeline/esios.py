"""Previsión diaria de generación eólica de REE vía ESIOS (spec 004, T-12).

Sin E/S y sin reloj: la respuesta de la API entra como parámetro y el día
objetivo también. Solo biblioteca estándar, igual que `forecast.py`, para que la
puerta `node --test` lo pruebe sin red ni credenciales.

El indicador 1777 es la previsión D+1 de energía eólica peninsular, en MWh, con
la Península como único ámbito (`geo_id = 8741`). La fuente declara un único
sello de elaboración por respuesta (`values_updated_at`) y aquí se archiva tal
cual: sin él la fila se guarda, pero no es elegible (CA-1.4).

El día se lee SIEMPRE de `datetime` (hora local de la Península) y nunca de
`datetime_utc`: las 00:00 locales del día 8 son las 23:00 UTC del 7, y el
objetivo se desplazaría un día.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────────
# Contrato del indicador
# ─────────────────────────────────────────────

INDICADOR_PREVISION_EOLICA = 1777
GEO_PENINSULA = 8741
UBICACION_PENINSULA = "peninsula"
USO_EOLICA = "eolica"

URL_BASE = "https://api.esios.ree.es"
TIME_TRUNC = "day"


class RespuestaInesperada(ValueError):
    """La respuesta de ESIOS no tiene la forma esperada (CA-3.3)."""


# ─────────────────────────────────────────────
# Petición
# ─────────────────────────────────────────────

def url_indicador(indicador: int = INDICADOR_PREVISION_EOLICA) -> str:
    """URL del indicador; la credencial viaja en la cabecera `x-api-key`."""
    return f"{URL_BASE}/indicators/{int(indicador)}"


def parametros_dia(objetivo,
                   indicador: int = INDICADOR_PREVISION_EOLICA) -> dict:
    """Parámetros de un solo día objetivo, agregado diario y ámbito peninsular.

    Pedir únicamente el día objetivo evita archivar días pasados con la
    elaboración de hoy: ESIOS devuelve un único `values_updated_at` para toda la
    respuesta y no se puede saber cuándo se elaboró cada día anterior.
    """
    dia = _fecha(objetivo).isoformat()
    return {
        "start_date": f"{dia}T00:00",
        "end_date": f"{dia}T23:59",
        "time_trunc": TIME_TRUNC,
        "geo_ids[]": GEO_PENINSULA,
    }


def parametros_rango(desde, hasta,
                     indicador: int = INDICADOR_PREVISION_EOLICA) -> dict:
    """Parámetros de un rango cerrado de días, para el relleno histórico."""
    return {
        "start_date": f"{_fecha(desde).isoformat()}T00:00",
        "end_date": f"{_fecha(hasta).isoformat()}T23:59",
        "time_trunc": TIME_TRUNC,
        "geo_ids[]": GEO_PENINSULA,
    }


# ─────────────────────────────────────────────
# Lectura de la respuesta
# ─────────────────────────────────────────────

def parse_indicador(payload) -> dict:
    """Devuelve el bloque `indicator` o lanza `RespuestaInesperada`."""
    if not isinstance(payload, dict):
        raise RespuestaInesperada("la respuesta no es un objeto JSON")
    indicador = payload.get("indicator")
    if not isinstance(indicador, dict):
        raise RespuestaInesperada("la respuesta no trae `indicator`")
    valores = indicador.get("values")
    if valores is None:
        raise RespuestaInesperada("el indicador no trae `values`")
    if not isinstance(valores, list):
        raise RespuestaInesperada("`indicator.values` no es una lista")
    return indicador


def filas_prevision(payload, objetivo=None, reconstruido: bool = False,
                    ventana_solicitada=None):
    """Filas del archivo de previsiones y motivos de descarte.

    Cada fila tiene las claves que espera `prevision_db.save_forecast_rows`.
    Con `objetivo=None` se archivan todos los días de la respuesta; con un día
    concreto, los demás se ignoran sin contarlos como incidencia.

    Con `reconstruido=True` la fila viene del relleno histórico: la fuente no
    declara la elaboración de cada día, así que se etiqueta con el día anterior
    al objetivo (el 1777 es D+1) y el parte se reduce al valor y su procedencia,
    sin duplicar cinco años de respuesta en cada fila.

    ESIOS devuelve un día más que `end_date`, así que el relleno pasa la ventana
    pedida (`desde, hasta`) para no archivar ni etiquetar ese día extra.
    """
    indicador = parse_indicador(payload)
    sello = indicador.get("values_updated_at") or ""
    objetivo = _fecha(objetivo) if objetivo is not None else None
    ventana = (_ventana_pedida(ventana_solicitada)
               if ventana_solicitada is not None
               else _ventana_presente(indicador))

    motivos = []
    por_fecha = {}
    for valor in indicador["values"]:
        if not isinstance(valor, dict):
            motivos.append("hay un valor que no es un objeto JSON")
            continue

        fecha = _fecha_del_valor(valor)
        if fecha is None:
            motivos.append("hay un valor sin `datetime` legible")
            continue

        geo = valor.get("geo_id")
        if geo is not None and _entero(geo) != GEO_PENINSULA:
            motivos.append(f"{fecha}: ámbito {geo} fuera de la Península")
            continue

        if objetivo is not None and fecha != objetivo:
            continue
        if ventana_solicitada is not None and not (ventana[0] <= fecha <= ventana[1]):
            continue

        energia = _numero(valor.get("value"))
        if energia is None:
            motivos.append(f"{fecha}: sin energía publicada")
            continue

        if fecha in por_fecha:
            motivos.append(f"{fecha}: valor duplicado, se conserva el último")

        if reconstruido:
            elaborado = (fecha - timedelta(days=1)).isoformat()
            parte = {
                "valor": valor,
                "sello_ventana": sello,
                "ventana": [dia.isoformat() for dia in ventana],
                "regla": "objetivo-1",
                "reconstruido": True,
            }
        else:
            elaborado = sello
            parte = payload

        por_fecha[fecha] = {
            "objetivo": fecha,
            "ubicacion": UBICACION_PENINSULA,
            "uso": USO_EOLICA,
            "eolica_mwh": energia,
            "elaborado": elaborado,
            "parte_json": parte,
        }

    if not por_fecha and not motivos:
        motivos.append(
            f"la respuesta no trae valores para {objetivo}"
            if objetivo is not None else "la respuesta no trae valores")

    filas = [por_fecha[fecha] for fecha in sorted(por_fecha)]
    return filas, motivos


def huecos(filas, desde, hasta):
    """Días del rango cerrado sin fila, en orden; nunca rellena nada.

    Acepta las filas del archivo (diccionarios con `objetivo`) o una colección
    de fechas. Sirve para declarar un bloque incompleto en vez de darlo por
    bueno: el relleno reintenta solo los años con días ausentes.
    """
    presentes = {
        _fecha(fila["objetivo"] if isinstance(fila, dict) else fila)
        for fila in filas or []
    }
    inicio, fin = _fecha(desde), _fecha(hasta)
    if fin < inicio:
        return []
    return [
        dia for dia in (inicio + timedelta(days=atras)
                        for atras in range((fin - inicio).days + 1))
        if dia not in presentes
    ]


def bloque_verificable(indicador, hasta):
    """Un bloque histórico es fiable si su sello es el día anterior a `hasta`.

    ESIOS da un único `values_updated_at` por respuesta y lo sitúa en la última
    actualización anterior a `end_date`, que es cuando se publicó el valor del
    último día pedido (el 1777 es D+1). Si el sello es posterior, algún día del
    bloque se revisó después de publicarse y no se puede etiquetar con
    `elaborado = objetivo - 1`: el bloque se descarta.

    Devuelve `(verificable, motivo)`.
    """
    sello = str(indicador.get("values_updated_at") or "").strip()
    if not sello:
        return False, "la respuesta no declara `values_updated_at`"

    if not indicador.get("values"):
        return False, "la respuesta no trae ningún día con valor"

    esperado = _fecha(hasta) - timedelta(days=1)
    if sello[:10] != esperado.isoformat():
        return False, (
            f"el sello {sello[:10]} no es el día anterior al final del bloque "
            f"({esperado.isoformat()}): pudo revisarse después"
        )
    return True, ""


# ─────────────────────────────────────────────
# Conversiones
# ─────────────────────────────────────────────

def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _fecha_del_valor(valor) -> date | None:
    """Día natural publicado por ESIOS, en hora local (`datetime`)."""
    texto = str(valor.get("datetime") or "").strip()[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _ventana_presente(indicador) -> tuple:
    """Primer y último día de la respuesta, para dejar constancia del bloque."""
    fechas = [
        _fecha_del_valor(valor)
        for valor in indicador.get("values") or []
        if isinstance(valor, dict)
    ]
    presentes = [fecha for fecha in fechas if fecha is not None]
    return (min(presentes), max(presentes)) if presentes else ()


def _ventana_pedida(ventana) -> tuple:
    """Ventana cerrada `(desde, hasta)` a partir de dos fechas."""
    desde, hasta = ventana
    return (_fecha(desde), _fecha(hasta))


def _numero(valor) -> float | None:
    """Número o None; `NaN`, `""` y los booleanos no son un dato."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(numero) else numero


def _entero(valor) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
