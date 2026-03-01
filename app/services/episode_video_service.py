"""
Episode video upload service — streams large files in chunks, never loads into RAM.
"""
import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.models.series import Episode, EpisodeConversionJob
from app.tasks.episode_tasks import process_episode
from app.config import settings

CHUNK_SIZE = 1024 * 1024  # 1MB


class EpisodeVideoService:

    @staticmethod
    async def upload_video(file: UploadFile, episode_id: int, db: Session) -> dict:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}"
            )

        unique_id = str(uuid.uuid4())[:8]
        filename = f"episode_{episode_id}_{unique_id}{file_ext}"
        directory = os.path.join(settings.UPLOAD_DIR, "episodes")
        os.makedirs(directory, exist_ok=True)
        file_path = os.path.join(directory, filename)

        total_bytes = 0
        try:
            async with aiofiles.open(file_path, "wb") as out:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > settings.MAX_UPLOAD_SIZE:
                        await out.close()
                        os.remove(file_path)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Max: {settings.MAX_UPLOAD_SIZE / (1024**3):.0f}GB"
                        )
                    await out.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

        episode.original_filename = file.filename
        episode.status = "processing"

        conversion_job = EpisodeConversionJob(episode_id=episode_id, status="queued")
        db.add(conversion_job)
        db.commit()
        db.refresh(conversion_job)

        task = process_episode.delay(episode_id, file_path)
        conversion_job.task_id = task.id
        db.commit()

        return {
            "message": "Episode video upload successful",
            "episode_id": episode_id,
            "job_id": conversion_job.id,
            "task_id": task.id,
            "status": "queued",
            "file_size_mb": round(total_bytes / (1024 * 1024), 1),
        }

    @staticmethod
    def get_conversion_status(job_id: int, db: Session) -> dict:
        job = db.query(EpisodeConversionJob).filter(EpisodeConversionJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Conversion job {job_id} not found")
        return {
            "job_id":        job.id,
            "episode_id":    job.episode_id,
            "status":        job.status,
            "progress":      job.progress,
            "current_step":  job.current_step,
            "error_message": job.error_message,
            "started_at":    job.started_at,
            "completed_at":  job.completed_at,
        }


# """
# Episode video upload service — mirrors VideoService but targets Episode/EpisodeConversionJob
# """
# import os
# import uuid
# from fastapi import UploadFile, HTTPException, status
# from sqlalchemy.orm import Session

# from app.models.series import Episode, EpisodeConversionJob
# from app.utils.storage import StorageManager
# from app.tasks.episode_tasks import process_episode
# from app.config import settings


# class EpisodeVideoService:

#     @staticmethod
#     async def upload_video(file: UploadFile, episode_id: int, db: Session) -> dict:
#         """
#         Upload and queue a video file for an episode.

#         Flow:
#           1. Validate episode exists
#           2. Validate file extension & size
#           3. Save raw upload to disk
#           4. Create EpisodeConversionJob (status=queued)
#           5. Dispatch process_episode Celery task
#         """
#         # 1. Validate episode
#         episode = db.query(Episode).filter(Episode.id == episode_id).first()
#         if not episode:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Episode {episode_id} not found"
#             )

#         # 2. Validate file extension
#         file_ext = os.path.splitext(file.filename)[1].lower()
#         if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}"
#             )

#         # 3. Read & check size
#         unique_id = str(uuid.uuid4())[:8]
#         filename = f"episode_{episode_id}_{unique_id}{file_ext}"
#         file_content = await file.read()

#         if len(file_content) > settings.MAX_UPLOAD_SIZE:
#             raise HTTPException(
#                 status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
#                 detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / (1024**3):.1f}GB"
#             )

#         # 4. Save to uploads folder
#         file_path = StorageManager.save_upload(file_content, filename, subfolder="episodes")

#         # 5. Update episode & create job
#         episode.original_filename = file.filename
#         episode.status = "processing"

#         conversion_job = EpisodeConversionJob(
#             episode_id=episode_id,
#             status="queued"
#         )
#         db.add(conversion_job)
#         db.commit()
#         db.refresh(conversion_job)

#         # 6. Queue Celery task
#         task = process_episode.delay(episode_id, file_path)

#         conversion_job.task_id = task.id
#         db.commit()

#         return {
#             "message": "Episode video upload successful",
#             "episode_id": episode_id,
#             "job_id": conversion_job.id,
#             "task_id": task.id,
#             "status": "queued",
#         }

#     @staticmethod
#     def get_conversion_status(job_id: int, db: Session) -> dict:
#         job = db.query(EpisodeConversionJob).filter(
#             EpisodeConversionJob.id == job_id
#         ).first()

#         if not job:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Conversion job {job_id} not found"
#             )

#         return {
#             "job_id": job.id,
#             "episode_id": job.episode_id,
#             "status": job.status,
#             "progress": job.progress,
#             "current_step": job.current_step,
#             "error_message": job.error_message,
#             "started_at": job.started_at,
#             "completed_at": job.completed_at,
#         }
