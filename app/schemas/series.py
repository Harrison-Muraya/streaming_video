"""
Pydantic schemas for Series, Season, Episode
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────
# Episode Schemas
# ─────────────────────────────────────────────

class EpisodeCreate(BaseModel):
    episode_number: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    duration: Optional[int] = None  # seconds


class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = None
    thumbnail_url: Optional[str] = None
    status: Optional[str] = None


class EpisodeVideoFileResponse(BaseModel):
    id: int
    quality: str
    file_path: str
    file_size: Optional[int]
    codec: Optional[str]
    format_type: Optional[str]

    class Config:
        from_attributes = True


class EpisodeConversionJobResponse(BaseModel):
    id: int
    episode_id: int
    status: str
    progress: int
    current_step: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class EpisodeResponse(BaseModel):
    id: int
    season_id: int
    episode_number: int
    title: str
    description: Optional[str]
    duration: Optional[int]
    thumbnail_url: Optional[str]
    video_url: Optional[str]
    status: str
    view_count: int
    created_at: datetime
    updated_at: datetime
    video_files: List[EpisodeVideoFileResponse] = []

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Season Schemas
# ─────────────────────────────────────────────

class SeasonCreate(BaseModel):
    season_number: int = Field(..., ge=1)
    title: Optional[str] = None
    description: Optional[str] = None
    release_year: Optional[int] = None
    poster_url: Optional[str] = None


class SeasonUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    release_year: Optional[int] = None
    poster_url: Optional[str] = None


class SeasonResponse(BaseModel):
    id: int
    series_id: int
    season_number: int
    title: Optional[str]
    description: Optional[str]
    release_year: Optional[int]
    poster_url: Optional[str]
    created_at: datetime
    episodes: List[EpisodeResponse] = []

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Series Schemas
# ─────────────────────────────────────────────

class SeriesCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    release_year: Optional[int] = None
    director: Optional[str] = None
    cast: Optional[str] = None          # JSON string
    rating: Optional[str] = None        # PG, R, etc.
    language: str = "English"
    country: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    trailer_url: Optional[str] = None


class SeriesUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    release_year: Optional[int] = None
    director: Optional[str] = None
    cast: Optional[str] = None
    rating: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    trailer_url: Optional[str] = None
    is_featured: Optional[bool] = None
    is_trending: Optional[bool] = None
    status: Optional[str] = None


class SeriesResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    release_year: Optional[int]
    director: Optional[str]
    cast: Optional[str]
    rating: Optional[str]
    language: str
    country: Optional[str]
    poster_url: Optional[str]
    backdrop_url: Optional[str]
    trailer_url: Optional[str]
    is_featured: bool
    is_trending: bool
    status: str
    view_count: int
    created_at: datetime
    updated_at: datetime
    seasons: List[SeasonResponse] = []

    class Config:
        from_attributes = True


class SeriesListResponse(BaseModel):
    series: List[SeriesResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
