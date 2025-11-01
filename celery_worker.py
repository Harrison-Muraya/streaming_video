"""
Celery worker entry point
Run with: celery -A celery_worker worker --loglevel=info
"""
from app.tasks import celery_app
from app.tasks import video_tasks

# Import all tasks to register them
__all__ = ['celery_app']
