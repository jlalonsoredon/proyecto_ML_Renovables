import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando aplicación...")

    from .services.db_ree import init_db
    init_db()
    logger.info("Base de datos inicializada")

    from apscheduler.schedulers.background import BackgroundScheduler
    from .tasks.scheduler import scheduler_service

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduler_service.run_daily_task,
        "cron",
        hour=3,
        minute=0,
        timezone="Europe/Madrid"
    )
    scheduler.start()
    logger.info("Scheduler iniciado (ejecutará a las 3:00 AM)")

    yield

    scheduler.shutdown()
    logger.info("Aplicación cerrada")


app = FastAPI(
    title="AeroPredictor API",
    description="API para predicción de generación eólica en España",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api.prediction import router as prediction_router
from .api.charts import router as charts_router

app.include_router(prediction_router)
app.include_router(charts_router)


@app.get("/")
def root():
    return {
        "message": "AeroPredictor API",
        "version": "1.0.0",
        "endpoints": [
            "/api/prediction",
            "/api/historical",
            "/api/energy-mix",
            "/api/model-comparison",
            "/api/feature-importance",
            "/api/wind-parks"
        ]
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)