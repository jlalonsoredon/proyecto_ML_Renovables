"""Estudio de correlación de las variables nuevas (spec 006, RF-1).

Funciones puras con la biblioteca estándar: el notebook les pasa las columnas
del dataset y la puerta `node --test` las prueba sin pandas ni numpy.
"""

from __future__ import annotations

import math


def _es_ausente(valor) -> bool:
    """None, NaN o texto vacío: el par no cuenta para la correlación."""
    if valor is None:
        return True
    try:
        return math.isnan(float(valor))
    except (TypeError, ValueError):
        return True


def correlacion_pearson(xs, ys) -> dict:
    """Correlación de Pearson de los pares completos de dos series.

    Devuelve `{"n": pares_válidos, "r": coeficiente_o_None}`. Un par entra solo
    si las dos posiciones tienen un número; con menos de dos pares o con
    varianza cero en cualquiera de las series, `r` es `None` (CE-1): no hay
    correlación que declarar, pero tampoco se inventa un cero.
    """
    # Sin `or`: una Serie de pandas no se puede evaluar como booleano.
    xs = [] if xs is None else list(xs)
    ys = [] if ys is None else list(ys)
    if len(xs) != len(ys):
        raise ValueError(f"series de distinto tamaño: {len(xs)} y {len(ys)}")

    pares = [
        (float(x), float(y))
        for x, y in zip(xs, ys)
        if not _es_ausente(x) and not _es_ausente(y)
    ]
    total = len(pares)
    if total < 2:
        return {"n": total, "r": None}

    media_x = sum(x for x, _ in pares) / total
    media_y = sum(y for _, y in pares) / total
    covarianza = sum((x - media_x) * (y - media_y) for x, y in pares)
    varianza_x = sum((x - media_x) ** 2 for x, _ in pares)
    varianza_y = sum((y - media_y) ** 2 for _, y in pares)
    if varianza_x == 0 or varianza_y == 0:
        return {"n": total, "r": None}

    return {
        "n": total,
        "r": covarianza / math.sqrt(varianza_x * varianza_y),
    }
