"""Lógica pura de evaluación del modelo (spec 002-sol-feature-eolica, RF-5, RF-6 y RF-9).

Sin E/S, sin pandas y sin sklearn: recibe fechas y métricas ya calculadas y
devuelve folds, veredicto o informe. Solo biblioteca estándar para que la suite
se pueda ejecutar sin instalar nada (constitución, principio 4).

La comparación se hace fold a fold y nunca sobre el agregado: un único split de
351 días no distingue una mejora de 1.000 MWh del ruido (CA-6.3).
"""

from __future__ import annotations

from datetime import date

from fechas import a_fecha

MINIMO_DIAS_TRAIN = 200
MINIMO_DIAS_TEST = 100
MINIMO_FOLDS_VALIDOS = 4
MINIMO_FOLDS_MEJORA = 3


# ─────────────────────────────────────────────
# RF-5 — Folds cronológicos
# ─────────────────────────────────────────────

def walk_forward_folds(fechas, hoy,
                       minimo_train: int = MINIMO_DIAS_TRAIN,
                       minimo_test: int = MINIMO_DIAS_TEST) -> list[dict]:
    """Folds anuales: se evalúa cada año con todo lo anterior como entrenamiento.

    Devuelve las fechas de train y test como texto ISO, así que el orden de
    entrada no importa y no hay índices que reordenar en el notebook. Un fold sin
    días suficientes se devuelve marcado como omitido, con el motivo.
    """
    dias = sorted({a_fecha(fecha) for fecha in fechas})
    if not dias:
        raise ValueError("no hay fechas para construir los folds")
    if minimo_train < 1 or minimo_test < 1:
        raise ValueError("los mínimos de días deben ser positivos")

    hoy_dia = a_fecha(hoy)
    primero, ultimo = dias[0].year, hoy_dia.year

    folds = []
    for ano in range(primero + 1, ultimo + 1):
        train = [dia.isoformat() for dia in dias if dia.year < ano]
        test = [dia.isoformat() for dia in dias if dia.year == ano]

        motivo = None
        if len(train) < minimo_train:
            motivo = f"entrenamiento insuficiente: {len(train)} días (mínimo {minimo_train})"
        elif len(test) < minimo_test:
            motivo = f"prueba insuficiente: {len(test)} días (mínimo {minimo_test})"

        folds.append({
            "año": ano,
            "train": train,
            "test": test,
            "omitido": motivo is not None,
            "motivo": motivo,
        })

    return folds


# ─────────────────────────────────────────────
# RF-6 — Criterio de aceptación
# ─────────────────────────────────────────────

def criterio_aceptacion(rmse_base, rmse_variante,
                        minimo: int = MINIMO_FOLDS_MEJORA,
                        minimo_validos: int = MINIMO_FOLDS_VALIDOS) -> dict:
    """Acepta la variante solo si mejora el RMSE de forma estricta en `minimo` folds.

    Un `None` marca el fold omitido y no cuenta ni como mejora ni como empeoramiento.
    El empate no es mejora. Si no hay folds suficientes, no se decide: se rechaza
    con el motivo explícito.
    """
    if len(rmse_base) != len(rmse_variante):
        raise ValueError(
            f"número de folds distinto: base={len(rmse_base)}, variante={len(rmse_variante)}"
        )
    if not rmse_base:
        raise ValueError("no hay folds que evaluar")
    if minimo < 1:
        raise ValueError(f"el mínimo de folds debe ser positivo: {minimo}")

    detalle, mejoras, validos = [], 0, 0
    for indice, (base, variante) in enumerate(zip(rmse_base, rmse_variante)):
        if base is None or variante is None:
            detalle.append({"fold": indice, "base": base, "variante": variante, "mejora": None})
            continue

        validos += 1
        mejora = float(variante) < float(base)
        mejoras += 1 if mejora else 0
        detalle.append({"fold": indice, "base": float(base), "variante": float(variante), "mejora": mejora})

    if validos < minimo_validos:
        return {
            "aceptado": False,
            "mejoras": mejoras,
            "validos": validos,
            "motivo": f"folds insuficientes: {validos} válidos de {len(rmse_base)}",
            "detalle": detalle,
        }

    aceptado = mejoras >= minimo
    motivo = f"mejora en {mejoras} de {validos} folds válidos (mínimo {minimo})"
    return {
        "aceptado": aceptado,
        "mejoras": mejoras,
        "validos": validos,
        "motivo": motivo,
        "detalle": detalle,
    }


# ─────────────────────────────────────────────
# RF-9 — Resumen para imprimir y para el JSON
# ─────────────────────────────────────────────

def resumen_folds(folds, metricas: dict, decision: dict, cobertura: dict, hoy) -> dict:
    """Informe completo: por fold, veredicto, cobertura y fecha de ejecución."""
    if not folds:
        raise ValueError("no hay folds que resumir")

    for nombre in ("base", "variante"):
        if nombre not in metricas:
            raise ValueError(f"faltan las métricas de la variante {nombre!r}")
        for clave in ("rmse", "r2", "mae"):
            valores = metricas[nombre].get(clave)
            if valores is None:
                continue
            if len(valores) != len(folds):
                raise ValueError(
                    f"métricas incoherentes: {nombre}.{clave} tiene "
                    f"{len(valores)} valores para {len(folds)} folds"
                )

    informe = {
        "fecha_ejecucion": a_fecha(hoy).isoformat(),
        "criterio": dict(decision),
        "cobertura": cobertura,
        "decision": "aceptado" if decision.get("aceptado") else "rechazado",
        "folds": [],
    }

    for indice, fold in enumerate(folds):
        entrada = {
            "año": fold["año"],
            "omitido": fold["omitido"],
            "motivo": fold["motivo"],
            "dias_train": len(fold["train"]),
            "dias_test": len(fold["test"]),
        }
        for nombre in ("base", "variante"):
            datos = {
                "rmse": metricas[nombre]["rmse"][indice],
                "r2": metricas[nombre]["r2"][indice],
            }
            # El MAE es opcional: el acta solar no lo aporta y conserva su forma.
            if metricas[nombre].get("mae") is not None:
                datos["mae"] = metricas[nombre]["mae"][indice]
            entrada[nombre] = datos
        informe["folds"].append(entrada)

    return informe
