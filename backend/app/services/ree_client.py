import requests
import pandas as pd
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

REE_URL = "https://apidatos.ree.es/es/datos/generacion/estructura-generacion"
REE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Host": "apidatos.ree.es",
}

RENOVABLES = {
    "Eólica", "Solar fotovoltaica", "Solar térmica",
    "Hidráulica", "Hidroeólica", "Otras renovables", "Residuos renovables",
}

DAYS_PER_REQUEST = 30   # la API REE soporta rangos amplios con time_trunc=day
SLEEP_BETWEEN   = 1.0   # segundos entre peticiones consecutivas
MADRID = ZoneInfo("Europe/Madrid")


def _local_date(value) -> date:
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(MADRID).date()


def _missing_ranges(missing: list[date]) -> list[tuple[date, date]]:
    if not missing:
        return []
    days = sorted(set(missing))
    ranges = []
    start = previous = days[0]
    for day in days[1:]:
        if day != previous + timedelta(days=1) or (day - start).days >= DAYS_PER_REQUEST:
            ranges.append((start, previous))
            start = day
        previous = day
    ranges.append((start, previous))
    return ranges


def missing_generation_dates(present, hoy, days: int = 30) -> list[date]:
    """Fechas locales ausentes en la ventana reciente que termina ayer."""
    hoy = _local_date(hoy)
    ayer = hoy - timedelta(days=1)
    inicio = ayer - timedelta(days=max(1, int(days)) - 1)
    presentes = {_local_date(day) for day in (present or [])}
    return [
        inicio + timedelta(days=offset)
        for offset in range((ayer - inicio).days + 1)
        if inicio + timedelta(days=offset) not in presentes
    ]


def fetch_generation(fecha_inicio: str, fecha_fin: str, session=requests) -> pd.DataFrame:
    """
    Llama a la API REE para el rango [fecha_inicio, fecha_fin] (formato YYYY-MM-DD).
    Devuelve un DataFrame con columnas: datetime, tecnologia, tipo, valor_MWh, porcentaje.
    Solo incluye tecnologías renovables (igual que en api.ipynb).
    datetime se normaliza a 'YYYY-MM-DD' (dato diario).
    """
    url = (
        f"{REE_URL}"
        f"?start_date={fecha_inicio}T00:00"
        f"&end_date={fecha_fin}T23:59"
        f"&time_trunc=day"
        f"&geo_trunc=electric_system"
        f"&geo_limit=peninsular"
        f"&geo_ids=8741"
    )
    try:
        r = session.get(url, headers=REE_HEADERS, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.warning(f"REE error de red: {e}")
        return pd.DataFrame()

    if r.status_code != 200:
        logger.warning(f"REE HTTP {r.status_code} para {fecha_inicio}→{fecha_fin}: {r.text[:120]}")
        return pd.DataFrame()

    registros = []
    for tec in r.json().get("included", []):
        nombre = tec.get("attributes", {}).get("title", "")
        tipo   = tec.get("attributes", {}).get("type", "")
        if nombre not in RENOVABLES:
            continue
        for val in tec.get("attributes", {}).get("values", []):
            dt_raw = val.get("datetime")
            if not dt_raw:
                continue
            # Normalizar a fecha diaria (igual que en api.ipynb → _consultar_api)
            dt_utc = pd.to_datetime(dt_raw, utc=True).to_pydatetime()
            dt_norm = dt_utc.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
            registros.append({
                "datetime":   dt_norm,
                "tecnologia": nombre,
                "tipo":       tipo,
                "valor_MWh":  val.get("value"),
                "porcentaje": val.get("percentage"),
            })

    if not registros:
        logger.warning(f"REE sin registros para {fecha_inicio}→{fecha_fin}")
        return pd.DataFrame()

    return pd.DataFrame(registros)


def ensure_recent_data(days: int = 30, hoy=None, session=requests,
                       sleeper=time.sleep) -> Tuple[bool, str]:
    """
    Garantiza que la BD tenga datos de los últimos `days` días.
    - Si la BD está al día (< 2 días de retraso) no hace nada.
    - Si hay datos más antiguos, descarga solo los que faltan (incremental).
    Devuelve (actualizado: bool, mensaje: str).
    """
    hoy = hoy or datetime.now(MADRID).date()
    from app.services.db_ree import get_generation_series, save_generation_data
    from app.services.forecast_logic import generation_freshness

    hoy = _local_date(hoy)
    ayer = hoy - timedelta(days=1)
    inicio = ayer - timedelta(days=max(1, int(days)) - 1)
    presentes = get_generation_series(hoy=hoy, desde=inicio)
    faltantes = missing_generation_dates(presentes, hoy, days)
    diagnostico = generation_freshness(presentes, hoy)
    incompletos = set()
    if diagnostico["anomalo"] and diagnostico["ultimo"] is not None:
        incompletos.add(diagnostico["ultimo"])
        if diagnostico["ultimo"] not in faltantes:
            faltantes.append(diagnostico["ultimo"])
            faltantes.sort()
    rangos = _missing_ranges(faltantes)
    if not rangos:
        logger.info("REE data al día en la ventana reciente")
        return False, "al_dia"

    total_guardados = 0
    logger.info(
        "Descargando REE para %d días ausentes en %d rango(s) (%s → %s)",
        len(faltantes),
        len(rangos),
        faltantes[0].isoformat(),
        faltantes[-1].isoformat(),
    )
    for inicio_rango, fin_rango in rangos:
        t_ini = inicio_rango.isoformat()
        t_fin = fin_rango.isoformat()
        df = fetch_generation(t_ini, t_fin, session=session)
        if not df.empty:
            save_generation_data(df, replace_existing_dates=incompletos)
            total_guardados += len(df)
            logger.info(f"  REE guardados {len(df)} registros ({t_ini}→{t_fin})")
        if (inicio_rango, fin_rango) != rangos[-1]:
            sleeper(SLEEP_BETWEEN)

    msg = f"faltaban {len(faltantes)} días; guardados {total_guardados} registros"
    return True, msg
