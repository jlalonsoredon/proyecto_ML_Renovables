"""Parseo puro de la previsión diaria ESIOS 1777."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

GEO_PENINSULA = 8741
UBICACION_PENINSULA = "peninsula"
MAXIMO_PREVISION_MWH = 720_000.0


def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _numero(valor) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def parse_ree_d1(payload, objetivo, hoy, capturado_en) -> dict:
    """Extrae solo el D+1 peninsular y conserva el sello declarado por ESIOS.

    La fecha natural se lee de ``datetime`` local, nunca de ``datetime_utc``.
    Si falta `values_updated_at`, se conserva la fila con elaboración vacía:
    queda archivada para diagnóstico, pero no puede ser elegida por el modelo.
    """
    objetivo = _fecha(objetivo)
    hoy = _fecha(hoy)
    if objetivo != hoy + timedelta(days=1):
        return {"fila": None, "motivos": ["el objetivo no es D+1 respecto de hoy"]}

    if not isinstance(payload, dict) or not isinstance(payload.get("indicator"), dict):
        return {"fila": None, "motivos": ["respuesta sin indicator"]}
    indicador = payload["indicator"]
    valores = indicador.get("values")
    if not isinstance(valores, list):
        return {"fila": None, "motivos": ["indicator.values no es una lista"]}

    sello = str(indicador.get("values_updated_at") or "").strip()
    motivos = []
    candidatas = []
    for valor in valores:
        if not isinstance(valor, dict):
            motivos.append("valor ESIOS no es un objeto")
            continue
        try:
            fecha_local = _fecha(str(valor.get("datetime") or "")[:10])
        except ValueError:
            motivos.append("valor ESIOS sin datetime local legible")
            continue
        geo = valor.get("geo_id")
        if geo is not None:
            try:
                if int(geo) != GEO_PENINSULA:
                    continue
            except (TypeError, ValueError):
                motivos.append("geo_id ESIOS no legible")
                continue
        if fecha_local != objetivo:
            continue
        energia = _numero(valor.get("value"))
        if energia is None:
            motivos.append("previsión D+1 sin valor numérico")
            continue
        candidatas.append(energia)

    if not candidatas:
        motivos.append("ESIOS no devolvió un valor D+1 peninsular")
        return {"fila": None, "motivos": motivos}
    if len(candidatas) > 1:
        motivos.append("ESIOS devolvió valores D+1 duplicados; se conserva el último")
    if not sello:
        motivos.append("ESIOS no declaró values_updated_at; la fila no será elegible")

    return {
        "fila": {
            "objetivo": objetivo,
            "ubicacion": UBICACION_PENINSULA,
            "uso": "eolica",
            "eolica_mwh": candidatas[-1],
            "elaborado": sello,
            "capturado_en": capturado_en,
            "parte_json": payload,
        },
        "motivos": motivos,
    }
