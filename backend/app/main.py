import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)


def create_app(run_background_tasks: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Inicializando aplicación...")
        from .services.db_ree import init_db

        init_db()
        logger.info("Base de datos inicializada")
        scheduler = None
        if run_background_tasks:
            from apscheduler.schedulers.background import BackgroundScheduler
            from .tasks.scheduler import scheduler_service

            scheduler = BackgroundScheduler()
            scheduler.add_job(
                scheduler_service.run_daily_snapshot,
                "cron",
                hour=3,
                minute=0,
                timezone="Europe/Madrid",
            )
            scheduler.add_job(
                scheduler_service.retry_forecast_capture,
                "cron",
                hour=9,
                minute=0,
                timezone="Europe/Madrid",
            )
            scheduler.start()
            logger.info("Scheduler iniciado (03:00 y reintento a las 09:00)")

            def _backfill():
                try:
                    scheduler_service.backfill_aemet_diario(days=35)
                except Exception as error:
                    logger.error("Error en backfill AEMET: %s", error)
                finally:
                    scheduler_service.backfill_done.set()

            scheduler_service.backfill_done.clear()
            threading.Thread(target=_backfill, daemon=True).start()
            logger.info("Backfill AEMET iniciado en segundo plano")
        else:
            logger.info("Modo de prueba: scheduler y backfill desactivados")

        yield

        if scheduler is not None:
            scheduler.shutdown()
        logger.info("Aplicación cerrada")

    app = FastAPI(
        title="AeroPredictor API",
        description="API para predicción de generación eólica en España",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.run_background_tasks = run_background_tasks
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api.prediction import router as prediction_router
    from .api.charts import router as charts_router
    from .api.internal import router as internal_router

    app.include_router(prediction_router)
    app.include_router(charts_router)
    app.include_router(internal_router, include_in_schema=False)

    @app.get("/")
    def root():
        return {
            "message": "AeroPredictor API",
            "version": "1.0.0",
            "endpoints": [
                "/api/prediction",
                "/api/prediction/refresh",
                "/api/forecast",
                "/api/historical",
                "/api/energy-mix",
                "/api/model-comparison",
                "/api/feature-importance",
                "/api/wind-parks",
                "/api/prediction-chart",
            ],
        }

    @app.get("/health")
    def health_check():
        from .services.db_ree import health_check as database_health
        from .services.model_loader import model_service

        try:
            database_health()
        except Exception as error:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "detail": f"BD no disponible: {error}"},
            )
        if not model_service.ready:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "detail": "Modelo LR-19 no disponible o incompatible",
                },
            )
        return {"status": "ok"}

    return app


app = create_app()
test_app = create_app(run_background_tasks=False)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
