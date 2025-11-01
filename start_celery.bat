@echo off
echo Starting Celery Worker for Video Processing...
celery -A celery_worker worker --loglevel=info --pool=solo
pause