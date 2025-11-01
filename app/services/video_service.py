"""
Video upload and management service
"""
import os
import uuid
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from app.models.movie import Movie, ConversionJob
from app.utils.storage import StorageManager
from app.tasks.video_tasks import process_video
from app.config import settings


class VideoService:
    """Handle video upload and processing"""
    
    @staticmethod
    async def upload_video(
        file: UploadFile,
        movie_id: int,
        db: Session
    ) -> dict:
        """
        Upload video file for a movie
        
        Args:
            file: Uploaded video file
            movie_id: Movie ID
            db: Database session
        
        Returns:
            Upload status and job ID
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
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        filename = f"upload_{movie_id}_{unique_id}{file_ext}"
        
        # Read and save file
        file_content = await file.read()
        
        # Check file size
        if len(file_content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / (1024**3):.1f}GB"
            )
        
        # Save to upload directory
        file_path = StorageManager.save_upload(file_content, filename, subfolder="videos")
        
        # Update movie
        movie.original_filename = file.filename
        movie.status = "processing"
        
        # Create conversion job
        conversion_job = ConversionJob(
            movie_id=movie_id,
            status="queued"
        )
        db.add(conversion_job)
        db.commit()
        db.refresh(conversion_job)
        
        # Queue processing task
        task = process_video.delay(movie_id, file_path)
        
        conversion_job.task_id = task.id
        db.commit()
        
        return {
            'message': 'Video upload successful',
            'movie_id': movie_id,
            'job_id': conversion_job.id,
            'task_id': task.id,
            'status': 'queued'
        }
    
    @staticmethod
    def get_conversion_status(job_id: int, db: Session) -> dict:
        """Get status of video conversion job"""
        job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversion job {job_id} not found"
            )
        
        return {
            'job_id': job.id,
            'movie_id': job.movie_id,
            'status': job.status,
            'progress': job.progress,
            'current_step': job.current_step,
            'error_message': job.error_message,
            'started_at': job.started_at,
            'completed_at': job.completed_at
        }