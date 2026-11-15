import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..services.redaction import redact_secrets

logger = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")


class SchedulerService:
    def run_daily_task(self, hoy: date | None = None):
        hoy = hoy or datetime.now(MADRID).date()
        logger.info("=" * 50)
        logger.info("INICIANDO TAREA PROGRAMADA DIARIA")
        logger.info("=" * 50)

        pasos = (
            ("capture_aemet_forecast", lambda: self.capture_aemet_forecast(hoy)),
            ("capture_ree_forecast", lambda: self.capture_ree_forecast(hoy)),
            ("download_ree_data", lambda: self.download_ree_data(hoy)),
            ("download_aemet_data", lambda: self.download_aemet_data(hoy)),
            ("reconcile_own_predictions", lambda: self.reconcile_own_predictions(hoy)),
            ("run_prediction", lambda: self.run_prediction(hoy)),
        )
        resultados = {}
        for nombre, accion in pasos:
            try:
                resultados[nombre] = accion()
            except Exception as error:
                resultados[nombre] = None
                logger.error(
                    "Fallo en paso programado (%s): %s",
                    nombre,
                    redact_secrets(error),
                )
        fallidos = [
            nombre for nombre, resultado in resultados.items()
            if resultado is None
            or (
                isinstance(resultado, dict)
                and resultado.get("estado") in ("fallo", "no_disponible")
            )
        ]
        if fallidos:
            logger.warning("Tarea diaria con incidencias: %s", ", ".join(fallidos))
        else:
            logger.info("Tarea diaria completada")
        return resultados

    def capture_aemet_forecast(self, hoy: date | None = None):
        """Archiva la previsión vigente de las 12 ubicaciones (RF-1, RF-3)."""
        from ..services import forecast_db
        from ..services.aemet_forecast import capture_forecast

        resumen = capture_forecast(hoy=hoy)
        if forecast_db.capture_failed(resumen):
            raise RuntimeError(
                f"captura sin ninguna ubicación: {len(resumen['errores'])} errores"
            )
        if resumen["estado"] == "parcial":
            logger.warning(
                f"Captura AEMET parcial: {len(resumen['errores'])} incidencias"
            )
        return resumen

    def capture_ree_forecast(self, hoy: date | None = None):
        from ..services.ree_forecast import capture_ree_forecast

        resumen = capture_ree_forecast(hoy=hoy)
        if resumen["estado"] != "ok":
            logger.warning("Captura REE no completada: %s", resumen["errores"])
        return resumen

    def retry_forecast_capture(self, hoy: date | None = None):
        """Reintento del mismo día si la captura de madrugada no cubrió el día (CA-1.5)."""
        from ..services import forecast_db
        from ..services.prediction_service import prediction_service

        ultima = forecast_db.last_capture()
        hoy = hoy or datetime.now(MADRID).date()
        if (
            ultima
            and ultima["estado"] == "ok"
            and ultima["desde_pendiente"] is None
            and ultima["ejecutada_en"] is not None
            and ultima["ejecutada_en"].date() == hoy
        ):
            logger.info("Captura AEMET ya completa hoy — sin reintento")
            return

        logger.info("Reintentando la captura de previsiones del día")
        try:
            resumen = self.capture_aemet_forecast(hoy)
            if resumen and resumen["filas_guardadas"]:
                try:
                    prediction_service.refresh_prediction(hoy)
                except Exception as error:
                    logger.warning(
                        "Reintento sin predicción válida: %s",
                        redact_secrets(error),
                    )
        except Exception as e:
            logger.error(
                "Reintento de captura AEMET fallido: %s",
                redact_secrets(e),
            )

    def backfill_aemet_diario(self, days: int = 35, hoy: date | None = None):
        """Rellena faltantes estación/día de la ventana local, sin recapturar lo completo."""
        from ..services.aemet_client import ESTACIONES_OBSERVACION, download_aemet_diario
        from ..services.db_ree import save_aemet_diario, _get_conn

        hoy = hoy or datetime.now(MADRID).date()
        fin = hoy - timedelta(days=1)
        inicio = fin - timedelta(days=days - 1)
        esperadas = {
            (inicio + timedelta(days=offset)).isoformat()
            for offset in range((fin - inicio).days + 1)
        }
        cubiertas = set()
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT fecha, indicativo FROM aemet_diario
                   WHERE fecha >= ? AND fecha <= ?""",
                (inicio.isoformat(), fin.isoformat()),
            ).fetchall()
        por_fecha = {}
        for row in rows:
            por_fecha.setdefault(row[0], set()).add(row[1])
        pendientes = [
            fecha for fecha in sorted(esperadas)
            if not set(ESTACIONES_OBSERVACION).issubset(por_fecha.get(fecha, set()))
        ]

        if not pendientes:
            logger.info("aemet_diario ya al día — sin backfill necesario")
            return

        logger.info(f"Backfill AEMET: {len(pendientes)} días pendientes")
        for fecha in pendientes:
            try:
                records = download_aemet_diario(fecha)
                if records:
                    save_aemet_diario(records)
                    logger.info(f"Backfill AEMET {fecha}: {len(records)} registros")
            except Exception as e:
                logger.error(
                    "Backfill AEMET error [%s]: %s",
                    fecha,
                    redact_secrets(e),
                )
            time.sleep(1.0)
        return {"estado": "ok", "dias_pendientes": len(pendientes)}

    def download_ree_data(self, hoy: date | None = None):
        from ..services.ree_client import ensure_recent_data

        logger.info("Descargando datos de generación de REE...")
        updated, msg = ensure_recent_data(days=30, hoy=hoy)
        if updated:
            logger.info(f"Datos REE actualizados: {msg}")
        else:
            logger.info("Datos REE ya al día")
        return {"estado": "ok", "actualizado": updated, "detalle": msg}

    def download_aemet_data(self, hoy: date | None = None):
        from ..services.aemet_client import download_aemet_diario
        from ..services.db_ree import save_aemet_diario

        hoy = hoy or datetime.now(MADRID).date()
        ayer = (hoy - timedelta(days=1)).isoformat()
        logger.info(f"Descargando mediciones AEMET históricas para {ayer}...")
        records = download_aemet_diario(ayer)
        if records:
            save_aemet_diario(records)
            logger.info(f"AEMET diario: {len(records)} registros guardados para {ayer}")
            return {"estado": "ok", "fecha": ayer, "filas": len(records)}
        else:
            logger.warning(
                f"AEMET diario: ningún registro para {ayer}"
            )
            return {"estado": "parcial", "fecha": ayer, "filas": 0}

    def reconcile_own_predictions(self, hoy: date | None = None):
        from ..services.prediction_service import prediction_service

        actualizadas = prediction_service.reconcile_reals(hoy)
        logger.info("Predicciones propias actualizadas con real: %d emisiones", actualizadas)
        return {"estado": "ok", "emisiones_actualizadas": actualizadas}

    def run_prediction(self, hoy: date | None = None):
        from ..services.prediction_service import PredictionUnavailable, prediction_service

        logger.info("Ejecutando predicción diaria LR-19...")
        try:
            result = prediction_service.refresh_prediction(hoy)
        except PredictionUnavailable as error:
            logger.warning(
                "Predicción no emitida para %s; faltan=%s avisos=%s",
                error.fecha,
                error.faltan,
                error.avisos,
            )
            return {
                "estado": "no_disponible",
                "fecha": error.fecha,
                "faltan": error.faltan,
                "avisos": error.avisos,
            }
        logger.info(
            "Predicción guardada: %s MWh para %s con %d variables",
            result["prediccionMWh"],
            result["fecha"],
            result["n_variables"],
        )
        return {"estado": "ok", **result}


scheduler_service = SchedulerService()
