import requests
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

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


def fetch_generation(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
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
        r = requests.get(url, headers=REE_HEADERS, timeout=30)
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
            dt_norm = pd.to_datetime(dt_raw, utc=True).strftime("%Y-%m-%d")
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


def ensure_recent_data(days: int = 30) -> Tuple[bool, str]:
    """
    Garantiza que la BD tenga datos de los últimos `days` días.
    - Si la BD está al día (< 2 días de retraso) no hace nada.
    - Si hay datos más antiguos, descarga solo los que faltan (incremental).
    Devuelve (actualizado: bool, mensaje: str).
    """
    from app.services.db_ree import get_date_range, save_generation_data

    hoy  = datetime.now().date()
    ayer = hoy - timedelta(days=1)
    desde = hoy - timedelta(days=days)

    _, max_fecha = get_date_range()

    if max_fecha:
        ultimo = datetime.strptime(max_fecha[:10], "%Y-%m-%d").date()
        if ultimo >= ayer:
            logger.info("REE data al día, no se requiere descarga")
            return False, "al_dia"
        inicio_descarga = ultimo + timedelta(days=1)
    else:
        inicio_descarga = desde

    logger.info(f"Descargando REE: {inicio_descarga} → {ayer}")
    actual = inicio_descarga
    total_guardados = 0

    while actual <= ayer:
        tramo_fin = min(actual + timedelta(days=DAYS_PER_REQUEST - 1), ayer)
        t_ini = actual.strftime("%Y-%m-%d")
        t_fin = tramo_fin.strftime("%Y-%m-%d")

        df = fetch_generation(t_ini, t_fin)
        if not df.empty:
            save_generation_data(df)
            total_guardados += len(df)
            logger.info(f"  REE guardados {len(df)} registros ({t_ini}→{t_fin})")

        actual = tramo_fin + timedelta(days=1)
        if actual <= ayer:
            time.sleep(SLEEP_BETWEEN)

    msg = f"guardados {total_guardados} registros"
    return True, msg
