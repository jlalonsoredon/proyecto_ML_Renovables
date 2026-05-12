import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)
os.makedirs("modelos", exist_ok=True)

from app.services.db_ree import init_db
init_db()

from apscheduler.schedulers.blocking import BlockingScheduler
from app.tasks.scheduler import scheduler_service

scheduler = BlockingScheduler(timezone="Europe/Madrid")

scheduler.add_job(
    scheduler_service.run_daily_task,
    "cron",
    hour=3,
    minute=0,
    misfire_grace_time=3600
)

logger.info("Scheduler iniciado. La tarea se ejecutará a las 3:00 AM (hora de Madrid)")

try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("Scheduler detenido")