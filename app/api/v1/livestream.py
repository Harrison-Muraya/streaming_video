"""
Live Stream API endpoints
Mounted at: /api/v1/live
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.livestream import (
    LiveStreamCreate, LiveStreamUpdate,
    LiveStreamPublicResponse, LiveStreamAdminResponse,
    StartStreamResponse, StopStreamResponse,
)
from app.services.livestream_service import LiveStreamService
from app.utils.security import get_current_active_user, require_admin
from app.models.user import User

router = APIRouter()


# ════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS  (any logged-in user)
# ════════════════════════════════════════════════════════════════

@router.get("/", response_model=List[LiveStreamPublicResponse])
async def list_live_streams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all currently live streams.
    Users see this list and pick the stream they want to watch.
    """
    return LiveStreamService.get_live_streams(db)


@router.get("/{stream_id}", response_model=LiveStreamPublicResponse)
async def get_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single stream's public info + HLS URL."""
    return LiveStreamService.get_stream(stream_id, db)


@router.post("/{stream_id}/join", status_code=status.HTTP_200_OK)
async def join_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Call this when the user opens the stream player.
    Increments the live viewer count.
    """
    LiveStreamService.join_stream(stream_id, db)
    return {"message": "Joined stream", "stream_id": stream_id}


@router.post("/{stream_id}/leave", status_code=status.HTTP_200_OK)
async def leave_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Call this when the user closes the stream player.
    Decrements the live viewer count.
    """
    LiveStreamService.leave_stream(stream_id, db)
    return {"message": "Left stream", "stream_id": stream_id}


# ════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ════════════════════════════════════════════════════════════════

@router.get("/admin/all", response_model=List[LiveStreamAdminResponse])
async def admin_list_all_streams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all streams (including offline/inactive) — Admin only."""
    return LiveStreamService.get_all_streams(db, active_only=False)


@router.post("/admin/create", response_model=LiveStreamAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_stream(
    data: LiveStreamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Register a new capture card / stream source — Admin only.

    **device_path examples:**
    - Windows capture card: `video=AVerMedia Live Gamer Portable 2 Plus`
    - Linux capture card:   `/dev/video0`
    - Second Linux card:    `/dev/video1`
    - IP / RTSP camera:     `rtsp://192.168.1.100/live`
    """
    return LiveStreamService.create_stream(data, db)


@router.put("/admin/{stream_id}", response_model=LiveStreamAdminResponse)
async def update_stream(
    stream_id: int,
    data: LiveStreamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update stream metadata or device path — Admin only."""
    return LiveStreamService.update_stream(stream_id, data, db)


@router.delete("/admin/{stream_id}", status_code=status.HTTP_200_OK)
async def delete_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a stream (stops it first if live) — Admin only."""
    return LiveStreamService.delete_stream(stream_id, db)


@router.post("/admin/{stream_id}/start", response_model=StartStreamResponse)
async def start_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Start capturing from the capture card and begin live streaming — Admin only.

    FFmpeg will be launched in the background. The returned `stream_url`
    is the HLS playlist URL that users should pass to their video player.

    The stream becomes visible to users immediately via `GET /api/v1/live/`.
    """
    return LiveStreamService.start_stream(stream_id, db)


@router.post("/admin/{stream_id}/stop", response_model=StopStreamResponse)
async def stop_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Stop capturing and end the live stream — Admin only."""
    return LiveStreamService.stop_stream(stream_id, db)
