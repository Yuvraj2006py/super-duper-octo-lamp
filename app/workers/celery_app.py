from celery import Celery

from app.core.config import get_settings
from app.workers.schedules import CELERY_BEAT_SCHEDULE

settings = get_settings()

celery = Celery(
    "job_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule=CELERY_BEAT_SCHEDULE,
)
