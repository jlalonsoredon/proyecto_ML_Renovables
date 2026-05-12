import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.ree_api_key = os.environ.get("REE_API_KEY", "")
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
            self.download_aemet_forecast()
        except Exception as e:
            logger.error(f"Error descargando forecast AEMET: {e}")

        try:
            self.run_prediction()
        except Exception as e:
            logger.error(f"Error en predicción: {e}")

        logger.info("Tarea diaria completada")

    def download_ree_data(self):
        from ..services import db_ree

        logger.info("Descargando datos de generación de REE...")

        try:
            import requests
            from datetime import datetime, timedelta

            REE_URL = "https://apidatos.ree.es/es/datos/generacion/estructura-generacion"
            HEADERS = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Host": "apidatos.ree.es",
            }

            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = f"{yesterday}T00:00"
            end_date = f"{yesterday}T23:59"

            url = (
                f"{REE_URL}?start_date={start_date}"
                f"&end_date={end_date}"
                f"&time_trunc=day"
                f"&geo_trunc=electric_system"
                f"&geo_limit=peninsular"
                f"&geo_ids=8741"
            )

            response = requests.get(url, headers=HEADERS, timeout=30)

            if response.status_code == 200:
                import pandas as pd
                data = response.json()
                registros = []

                for item in data.get("included", []):
                    for gen in item.get("attributes", {}).get("values", []):
                        registros.append({
                            "datetime": yesterday,
                            "tecnologia": item.get("attributes", {}).get("title", ""),
                            "tipo": item.get("attributes", {}).get("type", ""),
                            "valor_MWh": gen.get("value", 0) / 1000,
                            "porcentaje": gen.get("percentage", 0)
                        })

                if registros:
                    df = pd.DataFrame(registros)
                    db_ree.save_generation_data(df)
                    logger.info(f"Datos REE guardados: {len(registros)} registros")
                else:
                    logger.warning("No se encontraron datos para ayer")
            else:
                logger.warning(f"Error REE: {response.status_code}")

        except Exception as e:
            logger.error(f"Error en download_ree_data: {e}")

    def download_aemet_forecast(self):
        from ..services import aemet_client, db_ree

        logger.info("Descargando forecast de AEMET...")

        try:
            forecast = aemet_client.get_aggregated_forecast()
            if forecast:
                for estacion_id, data in forecast.get("estaciones", {}).items():
                    db_ree.save_aemet_data(
                        fecha=data.get("fecha"),
                        temp_max=data.get("temp_max", 0),
                        temp_min=data.get("temp_min", 0),
                        vel_media=data.get("vel_media", 0),
                        rachas_max=data.get("rachas_max", 0),
                        precipitacion=data.get("precipitacion", 0),
                        sol=data.get("sol", 0)
                    )
                logger.info("Forecast AEMET guardado")
            else:
                logger.warning("No se pudo obtener forecast de AEMET")
        except Exception as e:
            logger.error(f"Error en download_aemet_forecast: {e}")

    def run_prediction(self):
        from ..services import aemet_client, db_ree, model_loader

        logger.info("Ejecutando predicción...")

        try:
            forecast = aemet_client.get_aggregated_forecast()

            if forecast:
                velmedia = forecast.get("velmedia", 3.5)
                racha = forecast.get("racha", 8.0)
            else:
                velmedia = 3.5
                racha = 8.0
                logger.warning("Usando valores por defecto para predicción")

            result = model_loader.model_service.predict(velmedia, racha)

            if result:
                db_ree.save_prediction(
                    fecha=result.get("fecha"),
                    prediccion_mwh=result.get("prediccion_mwh"),
                    modelo=result.get("modelo"),
                    velmedia=result.get("velmedia"),
                    racha=result.get("racha")
                )
                logger.info(f"Predicción guardada: {result.get('prediccion_mwh')} MWh")
            else:
                logger.error("No se pudo generar predicción")

        except Exception as e:
            logger.error(f"Error en run_prediction: {e}")


scheduler_service = SchedulerService()