"""
Pydantic schemas for LiveStream
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LiveStreamCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # The capture card path/identifier — set by admin
    # Windows:  "video=AVerMedia Live Gamer Portable 2 Plus"
    # Linux:    "/dev/video0"
    # RTSP cam: "rtsp://192.168.1.10/live"
    device_path: str = Field(..., description="Capture card device path or RTSP URL")
    is_active: bool = True


class LiveStreamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    device_path: Optional[str] = None
    is_active: Optional[bool] = None


# ── What regular users see (no sensitive fields) ──────────────────────────────

class LiveStreamPublicResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    is_live: bool
    viewer_count: int
    stream_url: Optional[str]   # HLS playlist URL — only present when live
    started_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── What admins see (full detail) ────────────────────────────────────────────

class LiveStreamAdminResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    device_path: str
    is_live: bool
    is_active: bool
    viewer_count: int
    hls_playlist_path: Optional[str]
    stream_url: Optional[str]
    ffmpeg_pid: Optional[int]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StartStreamResponse(BaseModel):
    message: str
    stream_id: int
    stream_url: str
    hls_playlist: str


class StopStreamResponse(BaseModel):
    message: str
    stream_id: int
