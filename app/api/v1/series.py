"""
Series / Season / Episode API endpoints
Mounted at: /api/v1/series
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.series import (
    SeriesCreate, SeriesUpdate, SeriesResponse, SeriesListResponse,
    SeasonCreate, SeasonUpdate, SeasonResponse,
    EpisodeCreate, EpisodeUpdate, EpisodeResponse,
    EpisodeConversionJobResponse,
)
from app.services.series_service import SeriesService, SeasonService, EpisodeService
from app.services.episode_video_service import EpisodeVideoService
from app.utils.security import get_current_active_user, require_admin
from app.models.user import User

router = APIRouter()


# ════════════════════════════════════════════════════════════════
# SERIES ENDPOINTS
# ════════════════════════════════════════════════════════════════

@router.post("/", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
async def create_series(
    data: SeriesCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new series (Admin only)"""
    return SeriesService.create_series(data, db)


@router.get("/", response_model=SeriesListResponse)
async def list_series(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    trending: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List all series with optional filtering and pagination"""
    return SeriesService.get_all_series(
        db, page=page, page_size=page_size,
        search=search, featured=featured, trending=trending
    )


@router.get("/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single series with all its seasons and episodes"""
    series = SeriesService.get_series_by_id(series_id, db)
    SeriesService.increment_view(series_id, db)
    return series


@router.put("/{series_id}", response_model=SeriesResponse)
async def update_series(
    series_id: int,
    data: SeriesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update series metadata (Admin only)"""
    return SeriesService.update_series(series_id, data, db)


@router.delete("/{series_id}", status_code=status.HTTP_200_OK)
async def delete_series(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a series and all its seasons/episodes (Admin only)"""
    return SeriesService.delete_series(series_id, db)


# ════════════════════════════════════════════════════════════════
# SEASON ENDPOINTS
# ════════════════════════════════════════════════════════════════

@router.post("/{series_id}/seasons", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
async def create_season(
    series_id: int,
    data: SeasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Add a new season to a series (Admin only)"""
    return SeasonService.create_season(series_id, data, db)


@router.put("/seasons/{season_id}", response_model=SeasonResponse)
async def update_season(
    season_id: int,
    data: SeasonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a season (Admin only)"""
    return SeasonService.update_season(season_id, data, db)


@router.delete("/seasons/{season_id}", status_code=status.HTTP_200_OK)
async def delete_season(
    season_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a season and all its episodes (Admin only)"""
    return SeasonService.delete_season(season_id, db)


# ════════════════════════════════════════════════════════════════
# EPISODE ENDPOINTS
# ════════════════════════════════════════════════════════════════

@router.post("/seasons/{season_id}/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    season_id: int,
    data: EpisodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Add a new episode to a season (Admin only)"""
    return EpisodeService.create_episode(season_id, data, db)


@router.get("/episodes/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single episode (increments view count)"""
    episode = EpisodeService.get_episode(episode_id, db)
    EpisodeService.increment_view(episode_id, db)
    return episode


@router.put("/episodes/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    episode_id: int,
    data: EpisodeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update episode metadata (Admin only)"""
    return EpisodeService.update_episode(episode_id, data, db)


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_200_OK)
async def delete_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete an episode (Admin only)"""
    return EpisodeService.delete_episode(episode_id, db)


# ════════════════════════════════════════════════════════════════
# EPISODE VIDEO UPLOAD
# ════════════════════════════════════════════════════════════════

@router.post("/episodes/{episode_id}/upload")
async def upload_episode_video(
    episode_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Upload a video file for an episode.

    The file is saved and queued for background processing
    (multi-quality conversion via FFmpeg + Celery).

    Returns a job_id you can poll via:
      GET /api/v1/series/episodes/conversions/{job_id}
    """
    return await EpisodeVideoService.upload_video(file, episode_id, db)


@router.get("/episodes/conversions/{job_id}")
async def get_episode_conversion_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Check the processing status of an episode video upload.

    Poll this endpoint after uploading to track progress.
    """
    return EpisodeVideoService.get_conversion_status(job_id, db)
