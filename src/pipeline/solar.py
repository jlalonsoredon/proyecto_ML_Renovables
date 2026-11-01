"""Lógica pura del bloque fotovoltaico (spec 001-fotovoltaicas).

Sin E/S, sin pandas y sin estado global: recibe datos, devuelve datos o lanza
una excepción propia. La interfaz con la base de datos y con pandas vive en el
notebook; aquí solo hay reglas.

Solo biblioteca estándar para que la suite se pueda ejecutar sin instalar nada
(constitución, principio 4).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────────
# Contrato del catálogo y de las variables
# ─────────────────────────────────────────────

CLAVES_CATALOGO = (
    "planta", "indicativo", "nombre",
    "lat", "lon", "planta_lat", "planta_lon", "distancia_km",
)

ESTACIONES_ESPERADAS = 5

MIN_COBERTURA_SOL_PCT = 90.0   # provisional: duda D-1
MAX_HUECO_SOL_DIAS = 7         # provisional: duda D-1

# Espejo exacto de las 16 variables del modelo eólico.
FEATURES = [
    "sol", "tmed", "mes", "dia_semana", "dia_año",
    "solar_lag1", "solar_lag2", "solar_lag3", "solar_lag7",
    "sol_ma3", "sol_ma7", "sol_ma14",
    "tmed_ma3", "tmed_ma7", "tmed_ma14",
    "solar_ma7",
]


class CatalogError(Exception):
    """El catálogo de plantas y estaciones no es utilizable."""


class InsolationError(Exception):
    """Los datos de insolación no permiten seguir (spec RF-3)."""


# ─────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────

def _is_missing(value) -> bool:
    """None, NaN de pandas o cadena vacía cuentan como ausente."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _max_run(fechas: list[date]) -> int:
    """Racha más larga de días consecutivos en una lista ordenada de fechas."""
    mejor = racha = 0
    anterior = None
    for fecha in fechas:
        racha = racha + 1 if anterior and (fecha - anterior).days == 1 else 1
        mejor = max(mejor, racha)
        anterior = fecha
    return mejor


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


# ─────────────────────────────────────────────
# RF-2 — Ventana de estudio
# ─────────────────────────────────────────────

def study_window(today: date, start: date = date(2022, 1, 1), lag_days: int = 3):
    """Periodo de estudio: mismo inicio del proyecto y fin con margen de publicación."""
    if not isinstance(today, date):
        today = _to_date(today)
    return start, today - timedelta(days=lag_days)


# ─────────────────────────────────────────────
# RF-1 — Catálogo planta–estación
# ─────────────────────────────────────────────

def validate_catalog(catalog: list[dict], download_map: dict) -> None:
    """Comprueba que hay 5 pares auditables y que coinciden con lo que se descarga."""
    if len(catalog) != ESTACIONES_ESPERADAS:
        raise CatalogError(
            f"El catálogo debe tener exactamente {ESTACIONES_ESPERADAS} pares planta–estación; "
            f"hay {len(catalog)}"
        )

    indicativos = [entrada.get("indicativo") for entrada in catalog]
    duplicados = sorted({i for i in indicativos if indicativos.count(i) > 1})
    if duplicados:
        raise CatalogError(f"Indicativo duplicado en el catálogo: {', '.join(duplicados)}")

    for entrada in catalog:
        for clave in CLAVES_CATALOGO:
            if clave not in entrada or entrada[clave] in (None, ""):
                raise CatalogError(
                    f"Falta '{clave}' en la estación {entrada.get('indicativo')} "
                    f"({entrada.get('planta')})"
                )

    ids_mapa = set(download_map.values())
    ids_catalogo = set(indicativos)
    if ids_catalogo != ids_mapa:
        sin_descarga = sorted(ids_catalogo - ids_mapa)
        sin_catalogo = sorted(ids_mapa - ids_catalogo)
        raise CatalogError(
            "El catálogo y el diccionario de descarga no coinciden: "
            f"sin descarga={sin_descarga or 'ninguno'}, "
            f"sin catálogo={sin_catalogo or 'ninguno'}"
        )


# ─────────────────────────────────────────────
# RF-3 / CE-3 / CE-4 — Valores de insolación
# ─────────────────────────────────────────────

def validate_sol_values(rows: list[dict]) -> None:
    """Rechaza insolaciones imposibles. Cero es un valor válido (día sin sol)."""
    for fila in rows:
        valor = fila.get("sol")
        if _is_missing(valor):
            continue

        try:
            horas = float(valor)
        except (TypeError, ValueError):
            raise InsolationError(
                f"Insolación no numérica en {fila.get('fecha')} "
                f"(estación {fila.get('indicativo')}): {valor!r}"
            ) from None

        if math.isnan(horas):
            continue

        if horas < 0 or horas > 24:
            raise InsolationError(
                f"Insolación fuera de rango en {fila.get('fecha')} "
                f"(estación {fila.get('indicativo')}): {horas} h; "
                "debe estar entre 0 y 24 (valor físicamente imposible)"
            )


# ─────────────────────────────────────────────
# RF-4 — Diagnóstico de cobertura
# ─────────────────────────────────────────────

def coverage_report(rows: list[dict], stations: list[str],
                    variables: tuple[str, ...] = ("sol",),
                    desde: date | None = None, hasta: date | None = None) -> dict:
    """% de ausentes y hueco consecutivo más largo, por estación y variable.

    Con `desde` y `hasta` el denominador es la ventana completa, así que los días
    sin fila cuentan como ausencia. Sin ventana, el denominador son los días que
    aparecen en `rows`.
    """
    acumulado = {
        estacion: {variable: {"fechas": set(), "con_dato": set()} for variable in variables}
        for estacion in stations
    }

    for fila in rows:
        estacion = fila.get("indicativo")
        if estacion not in acumulado:
            continue

        fecha = _to_date(fila["fecha"])
        for variable in variables:
            acumulado[estacion][variable]["fechas"].add(fecha)
            if not _is_missing(fila.get(variable)):
                acumulado[estacion][variable]["con_dato"].add(fecha)

    ventana = None
    if desde is not None and hasta is not None:
        inicio, fin = _to_date(desde), _to_date(hasta)
        if inicio > fin:
            raise ValueError(f"ventana invertida: {inicio} → {fin}")
        ventana = {inicio + timedelta(days=dia) for dia in range((fin - inicio).days + 1)}

    informe = {}
    for estacion, por_variable in acumulado.items():
        informe[estacion] = {}
        for variable, datos in por_variable.items():
            con_dato = set(datos["con_dato"])
            if ventana is not None:
                con_dato &= ventana
                dias = ventana
            else:
                dias = set(datos["fechas"])

            total = len(dias)
            con_valor = len(con_dato)
            ausentes = sorted(dias - con_dato)
            informe[estacion][variable] = {
                "days": total,
                "with_data": con_valor,
                "missing_pct": round(len(ausentes) / total * 100, 1) if total else 100.0,
                "max_gap_days": _max_run(ausentes),
            }

    return informe


# ─────────────────────────────────────────────
# RF-3 — Puerta de insolación
# ─────────────────────────────────────────────

def assert_insolation(report: dict, catalog: list[dict],
                      min_cobertura_pct: float = MIN_COBERTURA_SOL_PCT,
                      max_hueco_dias: int = MAX_HUECO_SOL_DIAS) -> None:
    """Detiene el proceso si alguna estación no sirve para el modelo solar (CA-3.1–3.3)."""
    plantas = {entrada["indicativo"]: entrada.get("planta", "?") for entrada in catalog}
    problemas = []

    for indicativo, planta in plantas.items():
        datos = (report.get(indicativo) or {}).get("sol")
        quien = f"{planta} ({indicativo})"

        if not datos or datos["with_data"] == 0:
            problemas.append(
                f"{quien}: no publica insolación en el periodo. "
                "Revisar la estación y, si no mide, sustituirla."
            )
            continue

        # Se acumulan todos los motivos de la estación: si falla cobertura y hueco,
        # quien lea el error debe ver los dos, no solo el primero.
        cobertura = 100.0 - datos["missing_pct"]
        if cobertura < min_cobertura_pct:
            problemas.append(
                f"{quien}: cobertura {cobertura:.1f} % < {min_cobertura_pct:.0f} %. "
                "Revisar la estación y, si no mide, sustituirla."
            )

        if datos["max_gap_days"] > max_hueco_dias:
            problemas.append(
                f"{quien}: {datos['max_gap_days']} días consecutivos sin dato "
                f"(máximo admitido {max_hueco_dias}). Revisar la estación."
            )

    if problemas:
        raise InsolationError(
            "Insolación no utilizable:\n  - " + "\n  - ".join(problemas)
        )


# ─────────────────────────────────────────────
# RF-5 — Serie diaria nacional
# ─────────────────────────────────────────────

def daily_national_series(rows: list[dict],
                          variables: tuple[str, ...] = ("sol", "tmed")) -> list[dict]:
    """Media diaria de las estaciones CON dato. No interpola: nunca inventa un valor."""
    principal = variables[0]
    por_fecha: dict[date, dict] = {}

    for fila in rows:
        fecha = _to_date(fila["fecha"])
        hueco = por_fecha.setdefault(
            fecha,
            {"valores": {variable: [] for variable in variables}, "con_principal": set()},
        )

        for variable in variables:
            valor = fila.get(variable)
            if not _is_missing(valor):
                hueco["valores"][variable].append(float(valor))

        if not _is_missing(fila.get(principal)):
            hueco["con_principal"].add(fila.get("indicativo"))

    serie = []
    for fecha in sorted(por_fecha):
        datos = por_fecha[fecha]
        if not datos["con_principal"]:
            raise InsolationError(
                f"El {fecha.isoformat()} ninguna estación tiene {principal}: "
                "es un hueco del bloque completo y no se puede promediar"
            )

        registro = {"fecha": fecha.isoformat()}
        for variable in variables:
            registro[variable] = _media(datos["valores"][variable])
        registro["n_estaciones"] = len(datos["con_principal"])
        serie.append(registro)

    return serie


# ─────────────────────────────────────────────
# RF-4 (spec 002) — Valor del día natural anterior
# ─────────────────────────────────────────────

def lag_series(daily: list[dict], clave: str) -> list[float | None]:
    """Valor de `clave` en el día natural anterior, alineado con `daily`.

    Un hueco devuelve `None`: nunca se arrastra el último día con dato (CA-4.1),
    porque eso convertiría "ayer" en "el último día que hubo" y desplazaría el
    retardo justo en los huecos. Misma longitud que la entrada.
    """
    if not daily:
        return []
    if not any(clave in registro for registro in daily):
        raise ValueError(f"la serie no contiene la variable {clave!r}")

    por_fecha = {_to_date(registro["fecha"]): registro for registro in daily}

    salida: list[float | None] = []
    for registro in daily:
        anterior = por_fecha.get(_to_date(registro["fecha"]) - timedelta(days=1))
        if anterior is None:
            salida.append(None)
            continue

        valor = anterior.get(clave)
        salida.append(None if _is_missing(valor) else float(valor))

    return salida


# ─────────────────────────────────────────────
# RF-5 / RF-6 — Variables y objetivo
# ─────────────────────────────────────────────

def _media_ventana(diario: dict[date, dict], fecha: date, clave: str, ventana: int) -> float | None:
    """Media de los últimos `ventana` días naturales que tengan dato (sin desplazar la ventana)."""
    valores = []
    for atras in range(ventana):
        registro = diario.get(fecha - timedelta(days=atras))
        if registro is None:
            continue
        valor = registro.get(clave)
        if not _is_missing(valor):
            valores.append(float(valor))
    return _media(valores)


def build_features(daily: list[dict], target: list[dict],
                   lags: tuple[int, ...] = (1, 2, 3, 7),
                   ventanas: tuple[int, ...] = (3, 7, 14)):
    """Une meteorología y objetivo y construye las 16 variables del modelo solar.

    Los retardos se resuelven por FECHA, no por posición: un hueco elimina la
    fila afectada pero nunca desplaza el retardo de los días siguientes (CA-5.3).
    """
    diario = {_to_date(fila["fecha"]): fila for fila in daily}
    objetivo = {_to_date(fila["fecha"]): float(fila["valor"]) for fila in target}

    for nombre, original, unicos in (("meteorología", daily, diario), ("objetivo", target, objetivo)):
        if len(unicos) != len(original):
            raise ValueError(
                f"La serie de {nombre} tiene fechas duplicadas: "
                f"{len(original)} filas para {len(unicos)} días distintos (CA-6.1)"
            )

    comunes = sorted(set(diario) & set(objetivo))
    resumen = {
        "dias_meteo": len(diario),
        "dias_objetivo": len(objetivo),
        "dias_comunes": len(comunes),
        "recorte_dias": len(set(diario) | set(objetivo)) - len(comunes),
        "descartados": 0,
        "desde": comunes[0].isoformat() if comunes else None,
        "hasta": comunes[-1].isoformat() if comunes else None,
    }

    registros = []
    for fecha in comunes:
        fila = {"fecha": fecha.isoformat()}

        for variable in ("sol", "tmed"):
            valor = diario[fecha].get(variable)
            fila[variable] = None if _is_missing(valor) else float(valor)

        fila["mes"] = fecha.month
        fila["dia_semana"] = fecha.weekday()
        fila["dia_año"] = fecha.timetuple().tm_yday

        for lag in lags:
            fila[f"solar_lag{lag}"] = objetivo.get(fecha - timedelta(days=lag))

        for ventana in ventanas:
            fila[f"sol_ma{ventana}"] = _media_ventana(diario, fecha, "sol", ventana)
        for ventana in ventanas:
            fila[f"tmed_ma{ventana}"] = _media_ventana(diario, fecha, "tmed", ventana)

        # Media móvil del objetivo desplazada: solo días anteriores (sin fuga).
        anteriores = [objetivo[fecha - timedelta(days=atras)] for atras in range(1, 8)
                      if fecha - timedelta(days=atras) in objetivo]
        fila["solar_ma7"] = _media(anteriores)

        fila["objetivo"] = objetivo[fecha]

        if any(fila[columna] is None for columna in FEATURES):
            resumen["descartados"] += 1
            continue

        registros.append({clave: fila[clave] for clave in ["fecha"] + FEATURES + ["objetivo"]})

    return registros, list(FEATURES), resumen


# ─────────────────────────────────────────────
# RF-8 — Partición temporal
# ─────────────────────────────────────────────

def temporal_split_index(n: int, ratio: float = 0.80) -> int:
    """Índice de corte cronológico. Train = [:idx], test = [idx:]."""
    if n <= 0:
        raise ValueError(f"No hay días para partir (n={n})")
    corte = int(n * ratio)
    if corte < 1 or corte >= n:
        raise ValueError(
            f"Serie demasiado corta para partir ({n} días): no se puede separar "
            "entrenamiento y prueba con garantías"
        )
    return corte


# ─────────────────────────────────────────────
# RF-9 — Métricas
# ─────────────────────────────────────────────

def quintile_edges(y_train, n_bins: int = 5) -> list[float]:
    """Bordes de quintiles calculados SOLO con train (interpolación lineal)."""
    valores = sorted(float(valor) for valor in y_train)
    if not valores:
        raise ValueError("No hay valores de entrenamiento para calcular los quintiles")

    n = len(valores)
    bordes = [-math.inf]
    for q in range(1, n_bins):
        posicion = q * (n - 1) / n_bins
        inferior = math.floor(posicion)
        fraccion = posicion - inferior
        if inferior + 1 < n:
            bordes.append(valores[inferior] + fraccion * (valores[inferior + 1] - valores[inferior]))
        else:
            bordes.append(valores[inferior])
    bordes.append(math.inf)
    return bordes


def to_quintiles(values, edges: list[float]) -> list[int]:
    return [bisect_right(edges, float(valor)) - 1 for valor in values]


def regression_metrics(y_true, y_pred, edges: list[float]) -> dict:
    """RMSE, MAE, R², MAPE y acierto por tramos sobre el conjunto de prueba."""
    pares = [(float(real), float(predicho)) for real, predicho in zip(y_true, y_pred)]
    if not pares:
        raise ValueError("No hay días para evaluar")

    n = len(pares)
    errores = [predicho - real for real, predicho in pares]

    rmse = math.sqrt(sum(error * error for error in errores) / n)
    mae = sum(abs(error) for error in errores) / n

    media_real = sum(real for real, _ in pares) / n
    ss_res = sum(error * error for error in errores)
    ss_tot = sum((real - media_real) ** 2 for real, _ in pares)
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")

    # El MAPE excluye los días con objetivo 0 para no dividir por cero (CE-5).
    mape_validos = [abs(error) / real * 100 for (real, _), error in zip(pares, errores) if real != 0]
    mape = _media(mape_validos)
    mape_excluidos = n - len(mape_validos)

    reales = [real for real, _ in pares]
    predichos = [predicho for _, predicho in pares]
    aciertos = sum(
        1 for a, b in zip(to_quintiles(reales, edges), to_quintiles(predichos, edges)) if a == b
    )

    return {
        "rmse": rmse,
        "mae": mae,
        "r2": r2,
        "mape": mape if mape is not None else float("nan"),
        "mape_excluidos": mape_excluidos,
        "accuracy": aciertos / n * 100,
        "n": n,
    }


# ─────────────────────────────────────────────
# RF-11 — Trazabilidad
# ─────────────────────────────────────────────

def solar_report(catalog: list[dict], coverage: dict, metrics: dict, today: date) -> dict:
    """Registro serializable de la decisión: qué estación, con qué cobertura y qué métricas."""
    if not isinstance(today, date):
        today = _to_date(today)

    return {
        "fecha_ejecucion": today.isoformat(),
        "estaciones": [
            {
                "planta": entrada["planta"],
                "indicativo": entrada["indicativo"],
                "nombre": entrada["nombre"],
                "distancia_km": entrada["distancia_km"],
                "cobertura": coverage.get(entrada["indicativo"], {}),
            }
            for entrada in catalog
        ],
        "umbrales": {
            "cobertura_minima_pct": MIN_COBERTURA_SOL_PCT,
            "hueco_maximo_dias": MAX_HUECO_SOL_DIAS,
        },
        "metricas": metrics,
    }
