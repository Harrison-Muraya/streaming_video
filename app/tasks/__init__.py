from celery import Celery
from app.config import settings

# Initialize Celery
celery_app = Celery(
    'streaming_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 hours max per task
    worker_prefetch_multiplier=1,
)

# Import tasks
from app.tasks import video_tasks