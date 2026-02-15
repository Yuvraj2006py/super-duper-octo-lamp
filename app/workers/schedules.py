from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "placeholder-rss-sync": {
        "task": "app.workers.tasks.ingest_rss_sources",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
