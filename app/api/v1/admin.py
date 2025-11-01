"""
Admin endpoints for video upload and management
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.database import get_db
from app.models.user import User
from app.utils.security import require_admin
from app.services.video_service import VideoService
from app.schemas.movie import ConversionJobResponse
from pydantic import BaseModel

router = APIRouter()


class UploadResponse(BaseModel):
    message: str
    movie_id: int
    job_id: int
    task_id: str
    status: str


class ConversionStatusResponse(BaseModel):
    job_id: int
    movie_id: int
    status: str
    progress: int
    current_step: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    
    class Config:
        from_attributes = True


@router.post("/upload/{movie_id}", response_model=UploadResponse)
async def upload_video(
    movie_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Upload video file for a movie (Admin only)
    
    The video will be automatically processed:
    - Converted to MP4 (if needed)
    - Multiple quality versions generated (1080p, 720p, 480p)
    - Thumbnails created
    - Stored in media directory
    
    **Supported formats:** MP4, MKV, AVI, MOV, FLV
    **Max file size:** 5GB
    
    Returns upload status and job ID for tracking progress
    """
    result = await VideoService.upload_video(file, movie_id, db)
    return result


@router.get("/conversions/{job_id}", response_model=ConversionStatusResponse)
async def get_conversion_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get status of video conversion job (Admin only)
    
    Track the progress of video processing:
    - **queued**: Waiting to start
    - **processing**: Currently converting
    - **completed**: Successfully finished
    - **failed**: Error occurred
    
    Progress is returned as percentage (0-100)
    """
    status = VideoService.get_conversion_status(job_id, db)
    return status


@router.get("/conversions", response_model=List[ConversionJobResponse])
async def list_conversion_jobs(
    status: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    List all conversion jobs (Admin only)
    
    Optionally filter by status: queued, processing, completed, failed
    """
    from app.models.movie import ConversionJob
    
    query = db.query(ConversionJob)
    
    if status:
        query = query.filter(ConversionJob.status == status)
    
    jobs = query.order_by(ConversionJob.created_at.desc()).limit(limit).all()
    return jobs


@router.delete("/conversions/{job_id}")
async def cancel_conversion(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Cancel a conversion job (Admin only)
    
    Note: This marks the job as cancelled but may not stop
    an already running process immediately
    """
    from app.models.movie import ConversionJob
    from celery.result import AsyncResult
    from app.tasks import celery_app
    
    job = db.query(ConversionJob).filter(ConversionJob.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Try to revoke Celery task
    if job.task_id:
        celery_app.control.revoke(job.task_id, terminate=True)
    
    job.status = "cancelled"
    db.commit()
    
    return {"message": "Conversion job cancelled", "job_id": job_id}
