"""Lógica pura del mapa de orígenes y de los reales (spec 004, RF-3 a RF-5).

Sin E/S, sin pandas y sin reloj: `hoy` entra siempre como parámetro (constitución,
principio 4). Solo biblioteca estándar para que la puerta `node --test` se ejecute
sin instalar nada.

La idea central es que el vector de mañana nunca miente sobre su procedencia:
cada variable lleva su origen (`observacion`, `prevision`, `mixta` o
`estimada`). Una media móvil toma cada día de la observación cuando existe y
lo completa con previsión oficial cuando falta, declarando el desglose. Un día
sin ninguna de las dos fuentes deja la ventana no disponible: no se interpola,
no se acorta y no se desplaza.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import forecast

VARIABLES_CALENDARIO = ("mes", "dia_semana", "dia_año")
VIENTO_DEL_DIA = ("velmedia", "racha")

VARIABLES_MODELO = (
    "mes", "dia_semana", "dia_año",
    "velmedia", "racha",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14",
    "sol_lag1", "tmed_lag1",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "eolica_ma7",
)

RETARDOS_GENERACION = (1, 2, 3, 7)
VENTANA_GENERACION = 7

NO_DISPONIBLE = {"valor": None, "origen": None}


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def _normalizar(serie) -> dict:
    """Copia la serie con claves `date`; nunca modifica la del llamador."""
    return {_fecha(fecha): valor for fecha, valor in (serie or {}).items()}


def _media(valores) -> float | None:
    valores = list(valores)
    return sum(valores) / len(valores) if valores else None


def _es_ausente(valor) -> bool:
    """`None` o `NaN`: la frontera con pandas no debe colarse como número.

    Una celda SQL NULL llega del notebook como `float('nan')`. Un NaN jamás es
    un dato: ni completa una ventana, ni hace de real, ni se declara origen.
    """
    return valor is None or (
        isinstance(valor, float) and math.isnan(valor)
    )


# ─────────────────────────────────────────────
# RF-4 — Ventanas con origen declarado por día
# ─────────────────────────────────────────────

def _ventana_detallada(serie_obs, serie_prev, objetivo, dias: int, hoy):
    """Resuelve la ventana día a día y devuelve su desglose de orígenes."""
    objetivo = _fecha(objetivo)
    hoy = _fecha(hoy)
    obs = _normalizar(serie_obs)
    prev = _normalizar(serie_prev)
    dias_ventana = [
        objetivo - timedelta(days=atras) for atras in range(dias - 1, -1, -1)
    ]

    valores = []
    observados = 0
    previstos = 0
    for dia in dias_ventana:
        # Una observación posterior a hoy no puede existir todavía aunque la
        # serie recibida la contenga: esa celda debe resolverse con previsión.
        if dia <= hoy and dia in obs and not _es_ausente(obs[dia]):
            valores.append(float(obs[dia]))
            observados += 1
        elif dia in prev and not _es_ausente(prev[dia]):
            valores.append(float(prev[dia]))
            previstos += 1
        else:
            return None

    origen = (
        "observacion" if previstos == 0
        else "prevision" if observados == 0
        else "mixta"
    )
    return {
        "valor": _media(valores),
        "origen": origen,
        "dias_observados": observados,
        "dias_previstos": previstos,
    }


def ventana_mixta(serie_obs, serie_prev, objetivo, dias: int, hoy):
    """Media de `dias` días terminada en `objetivo`, completada sin inventar.

    Cada día usa observación si ya está disponible; si no, previsión oficial.
    Solo si no existe ninguna de las dos la ventana devuelve `None`: nunca se
    interpola, se acorta ni se desplaza. Si participan ambas fuentes el origen
    es `mixta` (CA-4.1).
    """
    if dias <= 0:
        raise ValueError(f"la ventana debe ser positiva: {dias}")
    detalle = _ventana_detallada(serie_obs, serie_prev, objetivo, dias, hoy)
    if detalle is None:
        return None
    return detalle["valor"], detalle["origen"]


def _entrada_ventana(detalle: dict) -> dict:
    """Entrada del mapa; el desglose solo aparece si realmente hay mezcla."""
    entrada = _entrada(detalle["valor"], detalle["origen"])
    if detalle["origen"] == "mixta":
        entrada["dias_observados"] = detalle["dias_observados"]
        entrada["dias_previstos"] = detalle["dias_previstos"]
    return entrada


# ─────────────────────────────────────────────
# RF-4 — Origen de cada variable
# ─────────────────────────────────────────────

def origen_variable(nombre: str, valor_obs, valor_prev) -> str | None:
    """Origen de una variable según los valores disponibles (CA-4.4, CA-4.5).

    - El calendario pertenece al día objetivo: siempre `observacion`.
    - `velmedia` y `racha` son el día objetivo: mañana no se observa, así que su
      origen es `prevision` (aunque exista una observación reciente).
    - `sol_lag1` previsto es un proxy (`estimada`); `tmed_lag1` prevista es un
      dato directo del parte (`prevision`).
    - Sin ningún valor, la variable no tiene origen: queda no disponible.
    """
    if nombre in VARIABLES_CALENDARIO:
        return "observacion"
    if nombre in VIENTO_DEL_DIA:
        return "prevision" if not _es_ausente(valor_prev) else None
    if not _es_ausente(valor_obs):
        return "observacion"
    if not _es_ausente(valor_prev):
        return "estimada" if nombre == "sol_lag1" else "prevision"
    return None


def _entrada(valor, origen) -> dict:
    if _es_ausente(valor) or origen is None:
        return dict(NO_DISPONIBLE)
    return {"valor": float(valor), "origen": origen}


# ─────────────────────────────────────────────
# RF-4 — Mapa completo del vector de mañana
# ─────────────────────────────────────────────

def resolver_origenes(obs_meteo, obs_solar, obs_gen, prev, objetivo, hoy,
                      permitir_prev_gen: bool = False) -> dict:
    """Construye el vector de mañana declarando el origen de cada variable.

    `obs_meteo` es fecha → {velmedia, racha}; `obs_solar`, fecha → {sol, tmed};
    `obs_gen`, fecha → MWh (solo observación). `prev` agrupa las series de
    previsión con las claves `viento`, `racha`, `sol`, `tmed` y `generacion`.

    `permitir_prev_gen` queda en `False` por defecto (parada P-2): la previsión
    de REE solo completa los retardos de generación cuando el usuario lo decida.
    """
    objetivo = _fecha(objetivo)
    hoy = _fecha(hoy)
    prev = prev or {}

    obs_meteo = _normalizar_para_variable(obs_meteo, ("velmedia", "racha"))
    obs_solar = _normalizar_para_variable(obs_solar, ("sol", "tmed"))
    obs_gen = _normalizar(obs_gen)

    prev_viento = _normalizar(prev.get("viento"))
    prev_racha = _normalizar(prev.get("racha"))
    prev_sol = _normalizar(prev.get("sol"))
    prev_tmed = _normalizar(prev.get("tmed"))
    prev_gen = _normalizar(prev.get("generacion"))

    mapa = {}

    # Calendario: del día objetivo, nunca estimado (CA-4.5).
    mapa["mes"] = _entrada(objetivo.month, "observacion")
    mapa["dia_semana"] = _entrada(objetivo.weekday(), "observacion")
    mapa["dia_año"] = _entrada(objetivo.timetuple().tm_yday, "observacion")

    # Viento y racha del día objetivo: mañana no se puede observar.
    valor_viento = prev_viento.get(objetivo)
    valor_racha = prev_racha.get(objetivo)
    mapa["velmedia"] = _entrada(
        valor_viento, "prevision" if not _es_ausente(valor_viento) else None
    )
    mapa["racha"] = _entrada(
        valor_racha, "prevision" if not _es_ausente(valor_racha) else None
    )

    # Medias móviles: observación donde existe y previsión en los huecos; el
    # desglose acredita cuántos días aporta cada origen (CA-4.1).
    for nombre, obs_serie, prev_serie, dias in (
        ("vel_ma3", _serie_variable(obs_meteo, "velmedia"), prev_viento, 3),
        ("vel_ma7", _serie_variable(obs_meteo, "velmedia"), prev_viento, 7),
        ("vel_ma14", _serie_variable(obs_meteo, "velmedia"), prev_viento, 14),
        ("racha_ma3", _serie_variable(obs_meteo, "racha"), prev_racha, 3),
        ("racha_ma7", _serie_variable(obs_meteo, "racha"), prev_racha, 7),
        ("racha_ma14", _serie_variable(obs_meteo, "racha"), prev_racha, 14),
    ):
        ventana = _ventana_detallada(obs_serie, prev_serie, objetivo, dias, hoy)
        mapa[nombre] = (
            _entrada_ventana(ventana) if ventana else dict(NO_DISPONIBLE)
        )

    # Sol y temperatura del día anterior (CA-4.2).
    ayer = objetivo - timedelta(days=1)
    sol_obs = obs_solar.get(ayer, {}).get("sol")
    tmed_obs = obs_solar.get(ayer, {}).get("tmed")
    sol_prev = prev_sol.get(ayer)
    tmed_prev = prev_tmed.get(ayer)
    mapa["sol_lag1"] = _entrada(
        sol_obs if not _es_ausente(sol_obs) else sol_prev,
        "observacion" if not _es_ausente(sol_obs)
        else ("estimada" if not _es_ausente(sol_prev) else None),
    )
    mapa["tmed_lag1"] = _entrada(
        tmed_obs if not _es_ausente(tmed_obs) else tmed_prev,
        "observacion" if not _es_ausente(tmed_obs)
        else ("prevision" if not _es_ausente(tmed_prev) else None),
    )

    # Generación: última publicada completa (RF-12 de la spec 003) y, si se
    # permite, huecos completados con la previsión de REE (CA-4.3), declarando
    # también el origen mixto si la ventana reparte días entre ambas fuentes.
    diagnostico = forecast.generation_lags(obs_gen, objetivo)
    ancla = diagnostico["ancla"]

    for retraso in RETARDOS_GENERACION:
        nombre = f"eolica_lag{retraso}"
        valor = diagnostico["valores"].get(nombre)
        origen = "observacion" if not _es_ausente(valor) else None
        if _es_ausente(valor) and permitir_prev_gen and ancla is not None:
            valor = prev_gen.get(ancla - timedelta(days=retraso - 1))
            origen = "prevision" if not _es_ausente(valor) else None
        mapa[nombre] = _entrada(valor, origen)

    valor_ma7 = diagnostico["eolica_ma7"]
    entrada_ma7 = _entrada(
        valor_ma7,
        "observacion" if not _es_ausente(valor_ma7) else None,
    )
    if _es_ausente(valor_ma7) and permitir_prev_gen and ancla is not None:
        ventana = _ventana_detallada(
            obs_gen, prev_gen, ancla, VENTANA_GENERACION, hoy)
        if ventana:
            entrada_ma7 = _entrada_ventana(ventana)
    mapa["eolica_ma7"] = entrada_ma7

    return mapa


def _normalizar_para_variable(serie, variables) -> dict:
    """Serie de diccionarios por fecha → {variable: valor}, con claves `date`."""
    return {
        _fecha(fecha): {variable: datos.get(variable) for variable in variables}
        for fecha, datos in (serie or {}).items()
    }


def _serie_variable(serie, variable) -> dict:
    return {fecha: datos.get(variable) for fecha, datos in serie.items()}


# ─────────────────────────────────────────────
# RF-3 — Previsión de generación de REE (T-12)
# ─────────────────────────────────────────────

def instante_elaboracion(valor) -> datetime | None:
    """Sello de elaboración comparable: `date`, `datetime` o texto ISO.

    Se descarta la zona horaria para poder comparar elaboraciones de la misma
    fuente sin mezclar relojes: ESIOS publica hora local de la Península.
    """
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())

    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(
            texto.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def serie_prevision_generacion(filas, ubicacion: str = "peninsula") -> dict:
    """Fecha objetivo → MWh de la previsión de REE elegible (CA-1.2, CA-1.4).

    Por cada día gana la elaboración declarada más reciente que no sea
    posterior al propio día objetivo: usar una revisión de hoy como valor de
    anteayer sería una fuga. Sin elaboración declarada la fila no es elegible,
    y un hueco no se rellena: el día simplemente no está en el mapa.
    """
    elegidas = {}
    for fila in filas or []:
        if fila.get("ubicacion") != ubicacion:
            continue

        elaborado = instante_elaboracion(fila.get("elaborado"))
        if elaborado is None:
            continue

        fecha = _fecha(fila["objetivo"])
        if elaborado.date() > fecha:
            continue

        valor = fila.get("eolica_mwh")
        if _es_ausente(valor):
            continue

        anterior = elegidas.get(fecha)
        if anterior is None or elaborado > anterior[0]:
            elegidas[fecha] = (elaborado, float(valor))

    return {
        fecha: valor for fecha, (_, valor) in sorted(elegidas.items())
    }


# ─────────────────────────────────────────────
# RF-2, RF-5 — Reales y error de producción
# ─────────────────────────────────────────────

def reales_pendientes(predicciones, generacion, hoy) -> list[dict]:
    """Predicciones que ya pueden recibir su real, mirando solo `generacion`.

    Nunca se usa `prediccion_diaria` como fuente de verdad: una previsión
    archivada no puede convertirse en real (CA-5.1). Un día incompleto de REE se
    descarta como ancla, igual que en `forecast.generation_lags`.
    """
    hoy = _fecha(hoy)
    gen = _normalizar(generacion)

    frescura = forecast.generation_freshness(gen, hoy)
    incompletos = set()
    if frescura["anomalo"] and frescura["ultimo"] is not None:
        incompletos.add(frescura["ultimo"])

    pendientes = []
    for prediccion in predicciones or []:
        if not _es_ausente(prediccion.get("real_mwh")):
            continue
        fecha = _fecha(prediccion["fecha_objetivo"])
        if fecha > hoy or fecha in incompletos:
            continue
        valor = gen.get(fecha)
        if _es_ausente(valor):
            continue
        pendientes.append({
            "fecha_objetivo": fecha,
            "real_mwh": float(valor),
        })
    return sorted(pendientes, key=lambda fila: fila["fecha_objetivo"])


def con_error(prediccion_mwh, real_mwh):
    """Error con signo (`real - predicción`); sin real no se inventa (CE-7)."""
    if _es_ausente(prediccion_mwh) or _es_ausente(real_mwh):
        return None
    return float(real_mwh) - float(prediccion_mwh)


def mae_produccion(predicciones, limite: int = 30) -> dict:
    """MAE de las últimas `limite` predicciones con real (CA-2.4)."""
    validas = [
        {
            "fecha_objetivo": _fecha(fila["fecha_objetivo"]),
            "prediccion_mwh": float(fila["prediccion_mwh"]),
            "real_mwh": float(fila["real_mwh"]),
        }
        for fila in (predicciones or [])
        if not _es_ausente(fila.get("prediccion_mwh"))
        and not _es_ausente(fila.get("real_mwh"))
    ]
    validas.sort(key=lambda fila: fila["fecha_objetivo"])
    if limite is not None and limite > 0:
        validas = validas[-int(limite):]

    if not validas:
        return {"mae": None, "n": 0, "desde": None, "hasta": None}

    errores = [
        con_error(fila["prediccion_mwh"], fila["real_mwh"]) for fila in validas
    ]
    return {
        "mae": sum(abs(error) for error in errores) / len(errores),
        "n": len(validas),
        "desde": validas[0]["fecha_objetivo"],
        "hasta": validas[-1]["fecha_objetivo"],
    }
