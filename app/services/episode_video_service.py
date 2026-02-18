"""
Episode video upload service — mirrors VideoService but targets Episode/EpisodeConversionJob
"""
import os
import uuid
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.models.series import Episode, EpisodeConversionJob
from app.utils.storage import StorageManager
from app.tasks.episode_tasks import process_episode
from app.config import settings


class EpisodeVideoService:

    @staticmethod
    async def upload_video(file: UploadFile, episode_id: int, db: Session) -> dict:
        """
        Upload and queue a video file for an episode.

        Flow:
          1. Validate episode exists
          2. Validate file extension & size
          3. Save raw upload to disk
          4. Create EpisodeConversionJob (status=queued)
          5. Dispatch process_episode Celery task
        """
        # 1. Validate episode
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Episode {episode_id} not found"
            )

        # 2. Validate file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}"
            )

        # 3. Read & check size
        unique_id = str(uuid.uuid4())[:8]
        filename = f"episode_{episode_id}_{unique_id}{file_ext}"
        file_content = await file.read()

        if len(file_content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / (1024**3):.1f}GB"
            )

        # 4. Save to uploads folder
        file_path = StorageManager.save_upload(file_content, filename, subfolder="episodes")

        # 5. Update episode & create job
        episode.original_filename = file.filename
        episode.status = "processing"

        conversion_job = EpisodeConversionJob(
            episode_id=episode_id,
            status="queued"
        )
        db.add(conversion_job)
        db.commit()
        db.refresh(conversion_job)

        # 6. Queue Celery task
        task = process_episode.delay(episode_id, file_path)

        conversion_job.task_id = task.id
        db.commit()

        return {
            "message": "Episode video upload successful",
            "episode_id": episode_id,
            "job_id": conversion_job.id,
            "task_id": task.id,
            "status": "queued",
        }

    @staticmethod
    def get_conversion_status(job_id: int, db: Session) -> dict:
        job = db.query(EpisodeConversionJob).filter(
            EpisodeConversionJob.id == job_id
        ).first()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversion job {job_id} not found"
            )

        return {
            "job_id": job.id,
            "episode_id": job.episode_id,
            "status": job.status,
            "progress": job.progress,
            "current_step": job.current_step,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }
