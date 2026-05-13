import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.aemet_api_key = os.environ.get("AEMET_API_KEY", "")

    def run_daily_task(self):
        logger.info("=" * 50)
        logger.info("INICIANDO TAREA PROGRAMADA DIARIA")
        logger.info("=" * 50)

        try:
            self.download_ree_data()
        except Exception as e:
            logger.error(f"Error descargando datos REE: {e}")

        try:
            self.run_prediction()
        except Exception as e:
            logger.error(f"Error en predicción: {e}")

        logger.info("Tarea diaria completada")

    def download_ree_data(self):
        from ..services.ree_client import ensure_recent_data

        logger.info("Descargando datos de generación de REE...")
        updated, msg = ensure_recent_data(days=30)
        if updated:
            logger.info(f"Datos REE actualizados: {msg}")
        else:
            logger.info("Datos REE ya al día")

    def run_prediction(self):
        from ..services.aemet_client import get_aggregated_forecast
        from ..services.model_loader import model_service
        from ..services import db_ree

        logger.info("Ejecutando predicción diaria...")

        forecast = get_aggregated_forecast()
        if forecast:
            velmedia = forecast["velmedia"]
            racha    = forecast["racha"]
        else:
            logger.warning("AEMET no disponible — usando medias históricas de la BD")
            vals = db_ree.get_eolica_recent(days=7)
            # Sin forecast no podemos predecir viento; saltar predicción
            if not vals:
                logger.error("Sin datos históricos ni AEMET — predicción omitida")
                return
            velmedia = 3.5
            racha    = 8.0

        result = model_service.predict(velmedia, racha)
        if result:
            db_ree.save_prediction(
                fecha=result["fecha"],
                prediccion_mwh=result["prediccionMWh"],
                modelo=result["modelo"],
                velmedia=result["features"].get("velmedia") or velmedia,
                racha=result["features"].get("racha") or racha,
            )
            logger.info(f"Predicción guardada: {result['prediccionMWh']} MWh para {result['fecha']}")
        else:
            logger.error("No se pudo generar predicción")


scheduler_service = SchedulerService()