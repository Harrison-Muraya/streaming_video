"""
Video upload and management service
Fixed: streams large files to disk in chunks instead of reading all into RAM
Fixed: deletes raw upload file immediately after Celery task is queued
"""
import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from app.models.movie import Movie, ConversionJob
from app.utils.storage import StorageManager
from app.tasks.video_tasks import process_video
from app.config import settings

# 1MB chunks — never loads more than this into RAM at once
CHUNK_SIZE = 1024 * 1024


class VideoService:

    @staticmethod
    async def upload_video(file: UploadFile, movie_id: int, db: Session) -> dict:
        """
        Upload video file for a movie.

        Streams the file to disk in 1MB chunks — safe for files of any size.
        Raw upload file is deleted automatically after Celery picks it up.
        """
        # Validate movie exists
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Movie {movie_id} not found"
            )

        # Validate file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}"
            )

        # Build destination path
        unique_id = str(uuid.uuid4())[:8]
        filename = f"upload_{movie_id}_{unique_id}{file_ext}"
        directory = os.path.join(settings.UPLOAD_DIR, "videos")
        os.makedirs(directory, exist_ok=True)
        file_path = os.path.join(directory, filename)

        # ── Stream to disk in chunks (never loads full file into RAM) ─────────
        total_bytes = 0
        try:
            async with aiofiles.open(file_path, "wb") as out:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)

                    # Check size limit incrementally
                    if total_bytes > settings.MAX_UPLOAD_SIZE:
                        await out.close()
                        os.remove(file_path)
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File too large. Max: {settings.MAX_UPLOAD_SIZE / (1024**3):.0f}GB"
                        )

                    await out.write(chunk)

        except HTTPException:
            raise
        except Exception as e:
            # Clean up partial file on any write error
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save upload: {str(e)}"
            )

        # Update movie status
        movie.original_filename = file.filename
        movie.status = "processing"

        # Create conversion job
        conversion_job = ConversionJob(movie_id=movie_id, status="queued")
        db.add(conversion_job)
        db.commit()
        db.refresh(conversion_job)

        # Queue Celery task — task will delete the raw file when done
        task = process_video.delay(movie_id, file_path)

        conversion_job.task_id = task.id
        db.commit()

        return {
            "message": "Video upload successful",
            "movie_id": movie_id,
            "job_id": conversion_job.id,
            "task_id": task.id,
            "status": "queued",
            "file_size_mb": round(total_bytes / (1024 * 1024), 1),
        }

    @staticmethod
    def get_conversion_status(job_id: int, db: Session) -> dict:
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversion job {job_id} not found"
            )
        return {
            "job_id":        job.id,
            "movie_id":      job.movie_id,
            "status":        job.status,
            "progress":      job.progress,
            "current_step":  job.current_step,
            "error_message": job.error_message,
            "started_at":    job.started_at,
            "completed_at":  job.completed_at,
        }