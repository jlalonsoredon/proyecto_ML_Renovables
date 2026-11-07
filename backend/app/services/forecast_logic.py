"""Copia vendorizada de `src/pipeline/forecast.py` (spec 003, RNF-1).

El backend se despliega con `rootDir: backend` (`render.yaml`), así que no
comparte árbol con el análisis. La copia debe ser exactamente igual al módulo
canónico; `src/pipeline/tests/test_forecast_parity.py` lo comprueba en cada
pasada de la puerta. No editar aquí: cambiar el original y volver a copiarlo.

Lógica pura del archivo de previsiones meteorológicas (spec 003, RF-1 a RF-10).

Sin E/S, sin pandas y sin reloj: el día actual entra siempre como parámetro
(``hoy``). Solo biblioteca estándar para que la puerta se ejecute sin instalar
nada (constitución, principio 4).

La pieza crítica es `choose_forecast`: dado un día objetivo, elige la previsión
que ya existía ese día. Una elaboración posterior al objetivo convertiría el
backtest en una medición con información del futuro, y todas las métricas
saldrían mejores de lo que serán en producción.

Convención de ausencia: `None`. Nunca un 0, nunca la observación, nunca una
interpolación (RNF-2, RNF-3).
"""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────────
# Contrato
# ─────────────────────────────────────────────

# Horizonte medido en el parte diario (2026-11-02): 7 días desde la elaboración.
HORIZONTE_DIAS = 7

USO_EOLICO = "eolica"
USO_SOLAR = "solar"

KMH_A_MS = 3.6

# Comparación y criterio (spec, RF-10).
UMBRAL_MEJORA = 0.02
TAMANO_VENTANA = 21
PASO_VENTANA = 7
DIAS_ENTRENAMIENTO = 14
MINIMO_VENTANAS = 3

# Calibración del proxy de insolación (CA-7.7).
MINIMO_MUESTRA_CALIBRACION = 20
CORRELACION_MINIMA_SOL = 0.7

# Una media de 7 horas nocturnas no es la media del día: por debajo de este
# número de horas se prefiere la media de los extremos, que sí cubre el día.
MINIMO_HORAS_TEMPERATURA = 12

# ─────────────────────────────────────────────
# Catálogo de ubicaciones (RF-3)
# ─────────────────────────────────────────────
# Claves iguales a las de producción para no romper la trazabilidad. Las cinco
# solares usan el municipio de la planta (mismo criterio que los parques
# eólicos) y los códigos se comprobaron contra la API de AEMET el 2026-11-02.

UBICACIONES = (
    # 7 eólicas: municipio ya usado por el modelo de producción.
    {"clave": "Gecama (Cuenca)", "municipio": "16078", "uso": USO_EOLICO, "lat": 39.4085},
    {"clave": "Maranchón (Guadalaj.)", "municipio": "19169", "uso": USO_EOLICO, "lat": 41.0636},
    {"clave": "Borja (Zaragoza)", "municipio": "50053", "uso": USO_EOLICO, "lat": 41.8770},
    {"clave": "Tarifa (Cádiz)", "municipio": "11033", "uso": USO_EOLICO, "lat": 36.0374},
    {"clave": "Briviesca (Burgos)", "municipio": "09059", "uso": USO_EOLICO, "lat": 42.5292},
    {"clave": "La Muela (Zaragoza)", "municipio": "50157", "uso": USO_EOLICO, "lat": 41.5924},
    {"clave": "El Andévalo (Huelva)", "municipio": "21041", "uso": USO_EOLICO, "lat": 37.2642},
    # 5 solares: municipio donde está la planta.
    {"clave": "Francisco Pizarro (Cáceres)", "municipio": "10186", "uso": USO_SOLAR, "lat": 39.5755},
    {"clave": "Núñez de Balboa (Badajoz)", "municipio": "06136", "uso": USO_SOLAR, "lat": 38.4585},
    {"clave": "Mula (Murcia)", "municipio": "30029", "uso": USO_SOLAR, "lat": 37.9500},
    {"clave": "Don Rodrigo (Sevilla)", "municipio": "41004", "uso": USO_SOLAR, "lat": 37.2200},
    {"clave": "Chiprana (Zaragoza)", "municipio": "50092", "uso": USO_SOLAR, "lat": 41.2600},
)

# Factor de insolación por código de estado del cielo de AEMET (CA-7.4):
# fracción de las horas de luz que cuentan como sol. El código nocturno ("11n")
# comparte factor con su equivalente diurno; se normaliza al leerlo.
FACTORES_CIELO = {
    11: 1.00, 12: 0.85, 13: 0.60, 14: 0.35, 15: 0.12, 16: 0.00, 17: 0.85,
    23: 0.50, 24: 0.35, 25: 0.12, 26: 0.00,
    43: 0.45, 44: 0.30, 45: 0.10, 46: 0.00,
    51: 0.45, 52: 0.30, 53: 0.10, 54: 0.00,
    61: 0.40, 62: 0.25, 63: 0.08, 64: 0.00,
    71: 0.35, 72: 0.25, 73: 0.08, 74: 0.00,
    81: 0.35, 82: 0.20, 83: 0.06, 84: 0.00,
}


class CatalogoError(ValueError):
    """El catálogo de ubicaciones no es utilizable (RF-3)."""


# ─────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────

def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def _instante(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())
    return datetime.fromisoformat(str(valor))


def _numero(valor) -> float | None:
    """Número de AEMET o None. AEMET usa coma decimal y marca huecos con ''."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if math.isnan(float(valor)) else float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _codigo(valor) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _hora_decimal(valor) -> float | None:
    """'07:38' → 7,633. El parte horario da orto y ocaso así."""
    if not valor:
        return None
    partes = str(valor).strip().split(":")
    if len(partes) != 2:
        return None
    try:
        horas, minutos = int(partes[0]), int(partes[1])
    except ValueError:
        return None
    if not (0 <= horas <= 24 and 0 <= minutos < 60):
        return None
    return horas + minutos / 60


def _periodo_horas(periodo, por_defecto=None) -> tuple[float, float] | None:
    """'00-06' → (0, 6). '07' → (7, 8). None si no se entiende.

    AEMET omite `periodo` cuando el valor vale para todo el día (días lejanos
    del parte diario): el llamador decide con qué tramo sustituirlo.
    """
    if periodo is None or str(periodo).strip() == "":
        return por_defecto
    texto = str(periodo).strip()
    try:
        if "-" in texto:
            inicio, fin = texto.split("-", 1)
            a, b = float(inicio), float(fin)
            return (a, b) if b > a else None
        hora = int(texto)
        return (float(hora), float(hora + 1))
    except ValueError:
        return None


def _media(valores) -> float | None:
    valores = list(valores)
    return sum(valores) / len(valores) if valores else None


# ─────────────────────────────────────────────
# RF-3 — Catálogo
# ─────────────────────────────────────────────

def validate_locations(ubicaciones, esperadas: int = 12) -> None:
    """Comprueba que el catálogo está completo y sin claves repetidas."""
    ubicaciones = list(ubicaciones)
    if len(ubicaciones) != esperadas:
        raise CatalogoError(
            f"el catálogo debe tener {esperadas} ubicaciones; hay {len(ubicaciones)}"
        )

    claves = [ubicacion.get("clave") for ubicacion in ubicaciones]
    repetidas = sorted({clave for clave in claves if claves.count(clave) > 1})
    if repetidas:
        raise CatalogoError(f"clave repetida en el catálogo: {', '.join(repetidas)}")

    for ubicacion in ubicaciones:
        for campo in ("clave", "municipio", "uso", "lat"):
            if ubicacion.get(campo) in (None, ""):
                raise CatalogoError(f"falta '{campo}' en {ubicacion.get('clave')!r}")
        if ubicacion["uso"] not in (USO_EOLICO, USO_SOLAR):
            raise CatalogoError(
                f"uso desconocido en {ubicacion['clave']!r}: {ubicacion['uso']!r}"
            )


# ─────────────────────────────────────────────
# RF-1, RF-7, RF-8 — Parseo de los partes
# ─────────────────────────────────────────────

def parse_daily_parte(parte: dict) -> dict:
    """Parte diario de AEMET → elaboración declarada y días normalizados.

    Los tramos de cielo llegan con granularidad variable: 6 horas en los dos
    primeros días y 12 horas en el resto. Se queda el juego más fino disponible.
    """
    dias = []
    for dia in (parte.get("prediccion") or {}).get("dia") or []:
        dias.append({
            "fecha": _fecha(dia["fecha"]),
            "tmax": _numero((dia.get("temperatura") or {}).get("maxima")),
            "tmin": _numero((dia.get("temperatura") or {}).get("minima")),
            "viento_kmh": _media_periodos(dia.get("viento"), "velocidad"),
            "racha_kmh": _media_periodos(dia.get("rachaMax"), "value"),
            "tramos_cielo": _tramos_cielo(dia.get("estadoCielo")),
            "uv_max": _numero(dia.get("uvMax")),
        })
    return {"elaborado": _elaborado(parte), "dias": dias}


def parse_hourly_parte(parte: dict) -> dict:
    """Parte horario → temperaturas, viento, racha, cielo horario y orto/ocaso."""
    dias = []
    for dia in (parte.get("prediccion") or {}).get("dia") or []:
        vientos, rachas = _viento_y_racha(dia.get("vientoAndRachaMax"))
        tramos = []
        for entrada in dia.get("estadoCielo") or []:
            horas = _periodo_horas(entrada.get("periodo"))
            if horas and horas[1] - horas[0] == 1:
                tramos.append((horas[0], horas[1], _codigo(entrada.get("value"))))

        dias.append({
            "fecha": _fecha(dia["fecha"]),
            "temperaturas": [
                valor for valor in (_numero(e.get("value")) for e in dia.get("temperatura") or [])
                if valor is not None
            ],
            "vientos_kmh": vientos,
            "rachas_kmh": rachas,
            "tramos_cielo": tramos,
            "orto": _hora_decimal(dia.get("orto")),
            "ocaso": _hora_decimal(dia.get("ocaso")),
        })
    return {"elaborado": _elaborado(parte), "dias": dias}


def _elaborado(parte: dict) -> datetime | None:
    """La emisión la declara el parte; sin ella, el registro no es elegible."""
    valor = (parte or {}).get("elaborado")
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def _media_periodos(entradas, clave: str) -> float | None:
    """Media del juego de tramos más fino disponible (6 h, 12 h o 24 h)."""
    por_periodo = {}
    for entrada in entradas or []:
        horas = _periodo_horas(entrada.get("periodo"), por_defecto=(0.0, 24.0))
        valor = _numero(entrada.get(clave))
        if horas and valor is not None:
            por_periodo[horas] = valor

    for ancho in (6, 12, 24):
        valores = [
            valor for (inicio, fin), valor in sorted(por_periodo.items())
            if fin - inicio == ancho
        ]
        if valores:
            return sum(valores) / len(valores)
    return None


def _tramos_cielo(entradas) -> list[tuple[float, float, str | None]]:
    """Tramos del cielo con el ancho más fino disponible."""
    por_periodo = {}
    for entrada in entradas or []:
        horas = _periodo_horas(entrada.get("periodo"), por_defecto=(0.0, 24.0))
        if horas:
            por_periodo[horas] = _codigo(entrada.get("value"))

    for ancho in (6, 12, 24):
        tramos = [
            (inicio, fin, codigo)
            for (inicio, fin), codigo in sorted(por_periodo.items())
            if fin - inicio == ancho
        ]
        if tramos:
            return tramos
    return []


def _codigo_por_hora(tramos) -> dict:
    """Expande los tramos a un código por hora natural, saltando los huecos."""
    por_hora = {}
    for inicio, fin, codigo in tramos or []:
        if codigo is None:
            continue
        for hora in range(int(inicio), int(fin)):
            por_hora[hora] = codigo
    return por_hora


def merge_tramos(diario, horario) -> list[tuple[float, float, str | None]]:
    """Une los dos partes en tramos sin solape: manda el que tiene dato.

    El horario es más fino, pero cuando su horizonte ya ha pasado deja horas sin
    publicar (en la captura real del 2026-11-02 solo cubría de 00 a 06 del último
    día). Coger un juego u otro perdía el detalle del otro; aquí cada hora usa el
    horario si lo trae y, si no, el diario. Solo queda sin dato lo que ninguno de
    los dos declara.
    """
    por_hora = _codigo_por_hora(diario)
    por_hora.update(_codigo_por_hora(horario))

    tramos: list[tuple[float, float, str | None]] = []
    for hora in range(24):
        codigo = por_hora.get(hora)
        if tramos and tramos[-1][1] == hora and tramos[-1][2] == codigo:
            tramos[-1] = (tramos[-1][0], float(hora + 1), codigo)
        else:
            tramos.append((float(hora), float(hora + 1), codigo))
    return tramos


def _viento_y_racha(entradas) -> tuple[list[float], list[float]]:
    """El parte horario intercala viento y racha en la misma lista."""
    vientos, rachas = [], []
    for entrada in entradas or []:
        if "velocidad" in entrada:
            for valor in entrada.get("velocidad") or []:
                numero = _numero(valor)
                if numero is not None:
                    vientos.append(numero)
        elif "value" in entrada:
            numero = _numero(entrada.get("value"))
            if numero is not None:
                rachas.append(numero)
    return vientos, rachas


# ─────────────────────────────────────────────
# RF-1, RF-7, RF-8 — Fila de archivo por día y ubicación
# ─────────────────────────────────────────────

def forecast_rows(diario: dict, horario: dict | None, ubicacion: str, uso: str,
                  lat: float, capturado_en: datetime) -> list[dict]:
    """Fusiona los dos partes en una fila por día objetivo.

    El horario aporta el detalle hora a hora (temperaturas, racha y cielo) y el
    diario cubre lo que el horario ya no alcanza. La racha del diario llega vacía
    en AEMET, por eso el respaldo es el horario y no al revés.
    """
    por_fecha = {dia["fecha"]: dia for dia in (horario or {}).get("dias", [])}
    filas = []

    for dia in diario.get("dias", []):
        hora = por_fecha.get(dia["fecha"])
        viento_kmh = dia["viento_kmh"]
        racha_kmh = dia["racha_kmh"]
        tramos = dia["tramos_cielo"]
        orto = ocaso = None
        temperaturas = []

        if hora:
            temperaturas = hora["temperaturas"]
            if viento_kmh is None:
                viento_kmh = _media(hora["vientos_kmh"])
            if racha_kmh is None and hora["rachas_kmh"]:
                racha_kmh = max(hora["rachas_kmh"])
            tramos = merge_tramos(tramos, hora["tramos_cielo"])
            orto, ocaso = hora["orto"], hora["ocaso"]

        filas.append({
            "elaborado": diario.get("elaborado"),
            "objetivo": dia["fecha"],
            "ubicacion": ubicacion,
            "uso": uso,
            "viento_ms": round(viento_kmh / KMH_A_MS, 3) if viento_kmh is not None else None,
            "racha_ms": round(racha_kmh / KMH_A_MS, 3) if racha_kmh is not None else None,
            "tmax": dia["tmax"],
            "tmin": dia["tmin"],
            "tmed": mean_temperature(temperaturas, dia["tmax"], dia["tmin"]),
            "sol": estimate_sun(tramos, lat, dia["fecha"], orto, ocaso),
            "tramos_cielo": tramos,
            "orto": orto,
            "ocaso": ocaso,
            "uv_max": dia["uv_max"],
            "capturado_en": capturado_en,
        })

    return filas


# ─────────────────────────────────────────────
# RF-7 — Temperatura, horas de luz e insolación estimada
# ─────────────────────────────────────────────

def mean_temperature(temperaturas, tmax=None, tmin=None) -> float | None:
    """Media del día: horas si cubren el día; si no, media de extremos (CA-7.1).

    El parte horario puede quedarse en las primeras horas del último día de su
    horizonte; promediar solo esas horas daría una media nocturna haciéndola
    pasar por diaria. Por eso, con menos de `MINIMO_HORAS_TEMPERATURA` horas, se
    usa la media de máxima y mínima, que sí representa el día completo.
    """
    valores = [float(valor) for valor in temperaturas or [] if valor is not None]
    if len(valores) >= MINIMO_HORAS_TEMPERATURA:
        return sum(valores) / len(valores)
    if tmax is not None and tmin is not None:
        return (float(tmax) + float(tmin)) / 2
    if valores:
        return sum(valores) / len(valores)
    return None


def daylight_hours(lat: float, fecha) -> float:
    """Horas de luz astronómicas en (0, 24] (CA-7.3). Sin tablas por fecha."""
    dia = _fecha(fecha)
    n = dia.timetuple().tm_yday
    declinacion = math.radians(23.45) * math.sin(math.radians(360 * (284 + n) / 365))
    latitud = math.radians(float(lat))
    coseno = -math.tan(latitud) * math.tan(declinacion)

    if coseno <= -1:
        return 24.0
    if coseno >= 1:
        return 0.0
    return 24 * math.acos(coseno) / math.pi


def sky_factor(codigo) -> float | None:
    """Factor de insolación del código de cielo (CA-7.4). None si no se conoce."""
    if codigo is None:
        return None
    texto = str(codigo).strip().lower()
    if not texto:
        return None
    if texto.endswith("n"):
        texto = texto[:-1]
    try:
        return FACTORES_CIELO.get(int(texto))
    except ValueError:
        return None


def estimate_sun(tramos, lat: float, fecha, orto=None, ocaso=None) -> float | None:
    """Horas de sol estimadas a partir del cielo previsto (CA-7.2, CA-7.5, CA-7.6).

    La ventana de luz es la del parte (orto/ocaso) si es válida y, si no, la
    astronómica centrada en el mediodía. Un tramo de día sin estado del cielo
    deja el día sin dato: no se estima a ciegas.
    """
    luz = daylight_hours(lat, fecha)
    if luz <= 0:
        return 0.0

    if orto is not None and ocaso is not None and ocaso > orto:
        inicio, fin = float(orto), float(ocaso)
    else:
        inicio, fin = max(0.0, 12 - luz / 2), min(24.0, 12 + luz / 2)

    total, cubierto = 0.0, 0.0
    for tramo_inicio, tramo_fin, codigo in tramos or []:
        solape = min(float(tramo_fin), fin) - max(float(tramo_inicio), inicio)
        if solape <= 0:
            continue
        factor = sky_factor(codigo)
        if factor is None:
            return None
        total += solape * factor
        cubierto += solape

    if cubierto <= 0:
        return None

    # La parte de la ventana que ningún tramo cubre se prorratea con el factor
    # medio: es una estimación declarada como tal, no una observación.
    estimado = total * (fin - inicio) / cubierto
    return max(0.0, min(luz, estimado))


# ─────────────────────────────────────────────
# RF-5 — Elección de la previsión válida
# ─────────────────────────────────────────────

def forecast_age_days(elaborado, objetivo) -> int:
    """Días naturales entre la elaboración y el día objetivo."""
    return (_fecha(objetivo) - _fecha(elaborado)).days


def choose_forecast(filas, objetivo, ubicacion: str, hoy):
    """Previsión válida para `objetivo` en `ubicacion`, o None.

    Solo son elegibles las elaboraciones declaradas y anteriores o iguales al
    día objetivo y a `hoy`. De las válidas gana la más reciente. Nunca hay
    respaldo: sin elegible, el valor es None y la fila del modelo se descarta.
    """
    objetivo = _fecha(objetivo)
    tope = min(objetivo, _fecha(hoy))

    candidatas = [
        fila for fila in filas
        if _fecha(fila["objetivo"]) == objetivo
        and fila.get("ubicacion") == ubicacion
        and fila.get("elaborado") is not None
        and _fecha(fila["elaborado"]) <= tope
    ]
    if not candidatas:
        return None

    elegida = max(candidatas, key=lambda fila: _instante(fila["elaborado"]))
    return {
        "valores": elegida,
        "elaborado": _instante(elegida["elaborado"]),
        "antiguedad_dias": forecast_age_days(elegida["elaborado"], objetivo),
    }


# ─────────────────────────────────────────────
# RF-6 — Objetivos de captura y recuperación
# ─────────────────────────────────────────────

def capture_targets(hoy, archivados, horizonte: int = HORIZONTE_DIAS) -> list[date]:
    """Días objetivo que hoy tiene sentido pedir: en curso, siguientes y recuperables.

    La cota inferior es el día más antiguo que aún puede contener una
    elaboración viva: como una elaboración nunca incluye días anteriores a sí
    misma y el horizonte es de `horizonte` días, no se puede recuperar nada más
    atrás de `hoy - horizonte + 1`.
    """
    hoy = _fecha(hoy)
    archivados = {_fecha(dia) for dia in archivados}
    desde = hoy - timedelta(days=horizonte - 1)
    hasta = hoy + timedelta(days=horizonte - 1)
    return [
        desde + timedelta(days=desplazamiento)
        for desplazamiento in range((hasta - desde).days + 1)
        if desde + timedelta(days=desplazamiento) not in archivados
    ]


def pending_days(hoy, esperados, archivados,
                 horizonte: int = HORIZONTE_DIAS) -> dict:
    """Separa los días sin archivar en recuperables y perdidos (CA-6.3, CA-6.4)."""
    hoy = _fecha(hoy)
    archivados = {_fecha(dia) for dia in archivados}
    limite = hoy - timedelta(days=horizonte - 1)

    recuperables, perdidos = [], []
    for dia in sorted({_fecha(dia) for dia in esperados} - archivados):
        (recuperables if dia >= limite else perdidos).append(dia)

    return {"recuperables": recuperables, "perdidos": perdidos}


# ─────────────────────────────────────────────
# RF-8 — Serie nacional y medias móviles
# ─────────────────────────────────────────────

VARIABLES_SERIE = ("viento_ms", "racha_ms", "tmed", "sol")


def national_series(filas, uso: str) -> list[dict]:
    """Serie diaria de previsión: media de las ubicaciones con dato de ese uso.

    No rellena: una ubicación sin valor no aporta y el recuento lo declara.
    """
    por_fecha: dict[date, dict] = {}
    for fila in filas or []:
        if fila.get("uso") != uso:
            continue
        fecha = _fecha(fila["objetivo"])
        acumulado = por_fecha.setdefault(
            fecha, {variable: [] for variable in VARIABLES_SERIE},
        )
        for variable in VARIABLES_SERIE:
            valor = fila.get(variable)
            if valor is not None:
                acumulado[variable].append(float(valor))

    principal = "viento_ms" if uso == USO_EOLICO else "tmed"
    serie = []
    for fecha in sorted(por_fecha):
        acumulado = por_fecha[fecha]
        registro = {"fecha": fecha}
        for variable in VARIABLES_SERIE:
            registro[variable] = _media(acumulado[variable])
        registro["n"] = len(acumulado[principal])
        serie.append(registro)
    return serie


def moving_average(valores: dict, objetivo, ventana: int) -> float | None:
    """Media de los `ventana` días naturales que terminan en `objetivo`.

    Un hueco o un día ausente devuelve None: la ventana no se acorta ni se
    desplaza (CA-8.3, CA-8.4, CE-12).
    """
    if ventana <= 0:
        raise ValueError(f"la ventana debe ser positiva: {ventana}")

    objetivo = _fecha(objetivo)
    acumulados = []
    for atras in range(ventana):
        dia = objetivo - timedelta(days=atras)
        if dia not in valores or valores[dia] is None:
            return None
        acumulados.append(float(valores[dia]))
    return sum(acumulados) / ventana


# ─────────────────────────────────────────────
# RF-12 — Frescura de las variables de generación
# ─────────────────────────────────────────────

# El entorno se mide con la mediana de los días anteriores, que no se desplaza
# por un único día mal publicado. Por debajo de esta fracción se avisa.
DIAS_ENTORNO_GENERACION = 7
MINIMO_ENTORNO_GENERACION = 5
ANOMALIA_GENERACION = 0.6


def generation_freshness(serie, objetivo,
                         dias_entorno: int = DIAS_ENTORNO_GENERACION,
                         minimo_entorno: int = MINIMO_ENTORNO_GENERACION,
                         umbral_anomalia: float = ANOMALIA_GENERACION) -> dict:
    """Último día publicado, retraso frente al objetivo y aviso de día incompleto.

    `serie` es un mapa fecha → MWh. REE publica la generación antes que AEMET
    la observación, así que aquí no se recorta a la última fecha meteorológica
    (CA-12.1). Si el último día está muy por debajo de la mediana de su entorno,
    se señala antes de usarlo (CA-12.2): la serie no se corrige ni se rellena.
    """
    fechas = sorted(dia for dia, valor in (serie or {}).items() if valor is not None)
    if not fechas:
        return {
            "ultimo": None, "valor": None, "retraso_dias": None,
            "mediana_entorno": None, "ratio": None, "n_entorno": 0,
            "anomalo": False, "aviso": None,
        }

    ultimo = fechas[-1]
    valor = float(serie[ultimo])
    entorno = [
        float(serie[ultimo - timedelta(days=atras)])
        for atras in range(1, dias_entorno + 1)
        if serie.get(ultimo - timedelta(days=atras)) is not None
    ]
    mediana = statistics.median(entorno) if len(entorno) >= minimo_entorno else None
    ratio = valor / mediana if mediana else None
    anomalo = ratio is not None and ratio < umbral_anomalia

    aviso = None
    if anomalo:
        aviso = (
            f"la generación de {ultimo.isoformat()} parece incompleta "
            f"({ratio:.0%} de la mediana de los {len(entorno)} días anteriores)"
        )

    return {
        "ultimo": ultimo,
        "valor": valor,
        "retraso_dias": (_fecha(objetivo) - ultimo).days,
        "mediana_entorno": mediana,
        "ratio": ratio,
        "n_entorno": len(entorno),
        "anomalo": anomalo,
        "aviso": aviso,
    }


def generation_lags(serie, objetivo, retrasos=(1, 2, 3, 7), ventana: int = 7,
                    dias_entorno: int = DIAS_ENTORNO_GENERACION,
                    minimo_entorno: int = MINIMO_ENTORNO_GENERACION,
                    umbral_anomalia: float = ANOMALIA_GENERACION) -> dict:
    """Retardos y media móvil del target anclados en la última generación.

    El ancla es el último día publicado **completo**, nunca el último día con
    meteorología (CA-12.1). Un día que parece incompleto (muy por debajo de su
    entorno) se señala y se descarta en vez de entrar en silencio (CA-12.2). Si
    la generación aún no llega a `objetivo - 1`, la ventana se desplaza y el
    retraso se declara. Un día ausente deja su variable a None: no se rellena
    con el vecino ni con la observación (CA-9.4).
    """
    objetivo = _fecha(objetivo)
    nombres = [f"eolica_lag{retraso}" for retraso in retrasos]
    frescura = generation_freshness(
        serie, objetivo, dias_entorno, minimo_entorno, umbral_anomalia,
    )

    validas = dict(serie or {})
    descartados = []
    informe = frescura
    while informe["ultimo"] is not None and informe["anomalo"]:
        descartados.append({
            "fecha": informe["ultimo"],
            "valor": informe["valor"],
            "ratio": informe["ratio"],
        })
        validas.pop(informe["ultimo"], None)
        informe = generation_freshness(
            validas, objetivo, dias_entorno, minimo_entorno, umbral_anomalia,
        )
    frescura["descartados"] = descartados

    # El total del propio día objetivo no puede entrar como retardo: sería usar
    # el target como variable explicativa.
    if informe["ultimo"] is None:
        ancla = None
    else:
        ancla = min(informe["ultimo"], objetivo - timedelta(days=1))
        if descartados:
            frescura["aviso"] = (
                f"{frescura['aviso']}: se descartan {len(descartados)} día(s) "
                f"incompleto(s) y se ancla en {ancla.isoformat()}"
            )

    if ancla is None:
        return {
            "ancla": None, "retraso_dias": None,
            "valores": {nombre: None for nombre in nombres},
            "eolica_ma7": None, "ausentes": nombres + ["eolica_ma7"],
            "frescura": frescura,
        }

    valores = {}
    ausentes = []
    for retraso, nombre in zip(retrasos, nombres):
        dia = ancla - timedelta(days=retraso - 1)
        valor = serie.get(dia)
        valores[nombre] = float(valor) if valor is not None else None
        if valor is None:
            ausentes.append(nombre)

    media = moving_average(serie, ancla, ventana)
    if media is None:
        ausentes.append("eolica_ma7")

    return {
        "ancla": ancla,
        "retraso_dias": (objetivo - ancla).days,
        "valores": valores,
        "eolica_ma7": media,
        "ausentes": ausentes,
        "frescura": frescura,
    }


# ─────────────────────────────────────────────
# RF-9, RF-10 — Cobertura, ventanas, criterio y fidelidad
# ─────────────────────────────────────────────

def coverage_summary(filas, hoy, ubicaciones=None) -> dict:
    """Días cubiertos, huecos, antigüedad media y ubicaciones sin dato."""
    hoy = _fecha(hoy)
    filas = [fila for fila in filas or [] if _fecha(fila["objetivo"]) <= hoy]

    if not filas:
        return {
            "dias": 0,
            "con_dato": 0,
            "huecos": [],
            "antiguedad_media": None,
            "ubicaciones_sin_dato": sorted(ubicaciones or []),
        }

    objetivos = sorted({_fecha(fila["objetivo"]) for fila in filas})
    primero, ultimo = objetivos[0], objetivos[-1]
    dias = (ultimo - primero).days + 1
    con_dato = set(objetivos)
    huecos = [
        primero + timedelta(days=desplazamiento)
        for desplazamiento in range(dias)
        if primero + timedelta(days=desplazamiento) not in con_dato
    ]

    edades = [
        forecast_age_days(fila["elaborado"], fila["objetivo"])
        for fila in filas
        if fila.get("elaborado") is not None
    ]

    presentes = {fila.get("ubicacion") for fila in filas}
    return {
        "dias": dias,
        "con_dato": len(con_dato),
        "huecos": huecos,
        "antiguedad_media": _media(edades),
        "ubicaciones_sin_dato": sorted(set(ubicaciones or ()) - presentes),
    }


def evaluation_windows(primero, ultimo, hoy, tamano: int = TAMANO_VENTANA,
                       paso: int = PASO_VENTANA,
                       dias_entrenamiento: int = DIAS_ENTRENAMIENTO) -> list[dict]:
    """Ventanas móviles con entrenamiento anterior y prueba al final (CA-10.1, CA-10.2)."""
    if tamano <= dias_entrenamiento:
        raise ValueError(
            f"la ventana ({tamano}) debe ser mayor que el entrenamiento ({dias_entrenamiento})"
        )

    inicio = _fecha(primero)
    fin = min(_fecha(ultimo), _fecha(hoy))
    ventanas = []

    while inicio + timedelta(days=tamano - 1) <= fin:
        hasta = inicio + timedelta(days=tamano - 1)
        corte = inicio + timedelta(days=dias_entrenamiento)
        ventanas.append({
            "desde": inicio,
            "hasta": hasta,
            "train": (inicio, corte - timedelta(days=1)),
            "test": (corte, hasta),
        })
        inicio += timedelta(days=paso)

    return ventanas


def decide_improvement(rmse_base, rmse_variante, umbral: float = UMBRAL_MEJORA,
                       minimo_ventanas: int = MINIMO_VENTANAS) -> dict:
    """Criterio del usuario: ≥ umbral en más de la mitad de las ventanas (CA-10.3)."""
    base = [float(valor) for valor in rmse_base]
    variante = [float(valor) for valor in rmse_variante]
    if len(base) != len(variante):
        raise ValueError(
            f"las series de RMSE no coinciden: {len(base)} frente a {len(variante)}"
        )

    evaluadas = len(base)
    if evaluadas < minimo_ventanas:
        return {
            "aceptada": False,
            "evidencia_insuficiente": True,
            "ventanas_ganadas": 0,
            "ventanas_evaluadas": evaluadas,
            "motivo": (
                f"evidencia insuficiente: {evaluadas} ventanas, "
                f"se exigen al menos {minimo_ventanas}"
            ),
        }

    ganadas = sum(
        1 for referencia, nueva in zip(base, variante)
        if referencia > 0 and (referencia - nueva) / referencia >= umbral
    )
    aceptada = ganadas * 2 > evaluadas

    return {
        "aceptada": aceptada,
        "evidencia_insuficiente": False,
        "ventanas_ganadas": ganadas,
        "ventanas_evaluadas": evaluadas,
        "motivo": (
            f"mejora ≥ {umbral:.0%} en {ganadas} de {evaluadas} ventanas "
            f"({'más de la mitad' if aceptada else 'no supera la mitad'})"
        ),
    }


def truthfulness_report(pares) -> dict:
    """Error de la propia previsión frente a la observación (CA-10.6)."""
    pares = [(float(previsto), float(observado)) for previsto, observado in pares or []]
    if not pares:
        return {"mae": None, "sesgo": None, "n": 0}

    errores = [previsto - observado for previsto, observado in pares]
    return {
        "mae": sum(abs(error) for error in errores) / len(errores),
        "sesgo": sum(errores) / len(errores),
        "n": len(pares),
    }


# ─────────────────────────────────────────────
# RF-7 — Calibración del proxy de insolación
# ─────────────────────────────────────────────

def calibrate_sun(pares, min_muestra: int = MINIMO_MUESTRA_CALIBRACION,
                  correlacion_minima: float = CORRELACION_MINIMA_SOL) -> dict:
    """Decide si el `sol` estimado sirve como variable (CA-7.7).

    Devuelve `utilizable=False` con el motivo cuando la muestra es corta o la
    correlación no llega al umbral: el modelo se queda solo con la temperatura.
    """
    pares = [(float(estimado), float(observado)) for estimado, observado in pares or []]
    n = len(pares)
    if n < min_muestra:
        return {
            "utilizable": False,
            "motivo": f"muestra insuficiente: {n} días (mínimo {min_muestra})",
            "correlacion": None,
            "sesgo": None,
            "mae": None,
            "n": n,
        }

    estimados = [estimado for estimado, _ in pares]
    observados = [observado for _, observado in pares]
    media_estimados = sum(estimados) / n
    media_observados = sum(observados) / n

    covarianza = sum(
        (estimado - media_estimados) * (observado - media_observados)
        for estimado, observado in pares
    ) / n
    desviacion_estimados = math.sqrt(sum((e - media_estimados) ** 2 for e in estimados) / n)
    desviacion_observados = math.sqrt(sum((o - media_observados) ** 2 for o in observados) / n)

    if desviacion_estimados == 0 or desviacion_observados == 0:
        correlacion = 0.0
    else:
        correlacion = covarianza / (desviacion_estimados * desviacion_observados)

    errores = [estimado - observado for estimado, observado in pares]
    utilizable = correlacion >= correlacion_minima

    return {
        "utilizable": utilizable,
        "motivo": (
            "correlación suficiente"
            if utilizable
            else f"correlación {correlacion:.2f} < {correlacion_minima:.2f}: se descarta sol"
        ),
        "correlacion": correlacion,
        "sesgo": sum(errores) / n,
        "mae": sum(abs(error) for error in errores) / n,
        "n": n,
    }
