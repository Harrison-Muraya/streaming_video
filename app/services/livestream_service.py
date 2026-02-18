"""
LiveStreamService
─────────────────
Manages one FFmpeg process per capture card.
FFmpeg reads from the capture card and writes HLS segments to disk.
FastAPI then serves those .m3u8 / .ts files as static media.

Architecture:
  Capture Card ──► FFmpeg (transcode) ──► HLS segments on disk
                                              │
                                    FastAPI /media/live/{id}/
                                              │
                                         Browser (HLS.js)

Requirements (install once):
  pip install ffmpeg-python   (already in your project)

System requirements:
  • FFmpeg must be installed and in PATH
  • On Windows with a capture card, use DirectShow input
  • On Linux with a capture card, use v4l2 input
"""
import os
import signal
import subprocess
import platform
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.livestream import LiveStream
from app.schemas.livestream import LiveStreamCreate, LiveStreamUpdate
from app.config import settings

# Where HLS output files are written (served as /media/live/<stream_id>/)
LIVE_MEDIA_ROOT = os.path.join(settings.MEDIA_ROOT, "live")


def _get_hls_dir(stream_id: int) -> str:
    path = os.path.join(LIVE_MEDIA_ROOT, str(stream_id))
    os.makedirs(path, exist_ok=True)
    return path


def _build_ffmpeg_command(device_path: str, hls_dir: str) -> list:
    """
    Build the FFmpeg command for the current OS and input type.

    Supports:
      - Windows DirectShow capture cards  (device_path starts with "video=")
      - Linux V4L2 capture cards          (device_path starts with "/dev/")
      - RTSP IP cameras                   (device_path starts with "rtsp://")
      - Any other FFmpeg-compatible URL   (passed through as-is)
    """
    playlist = os.path.join(hls_dir, "playlist.m3u8")
    segment  = os.path.join(hls_dir, "segment_%03d.ts")

    # ── Determine input format ────────────────────────────────────────────────
    is_windows = platform.system() == "Windows"

    if device_path.startswith("rtsp://") or device_path.startswith("http"):
        # IP camera / network stream — no special input format needed
        input_args = ["-i", device_path]

    elif is_windows:
        # Windows DirectShow — e.g. "video=AVerMedia Live Gamer"
        input_args = ["-f", "dshow", "-i", device_path]

    else:
        # Linux V4L2 — e.g. "/dev/video0"
        input_args = ["-f", "v4l2", "-i", device_path]

    # ── Full FFmpeg command ───────────────────────────────────────────────────
    cmd = [
        "ffmpeg",
        "-re",                          # Read at native frame rate
        *input_args,

        # Video encoding
        "-c:v", "libx264",
        "-preset", "veryfast",          # Low latency
        "-tune", "zerolatency",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-vf", "scale=1280:720",        # Force 720p output
        "-g", "30",                     # Keyframe every 30 frames (matches HLS segment)
        "-keyint_min", "30",
        "-sc_threshold", "0",

        # Audio encoding
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",

        # HLS output
        "-f", "hls",
        "-hls_time", "2",               # 2-second segments (low latency)
        "-hls_list_size", "10",         # Keep last 10 segments in playlist
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", segment,
        playlist,
    ]

    return cmd


class LiveStreamService:

    # ── CRUD ─────────────────────────────────────────────────────────────────

    @staticmethod
    def create_stream(data: LiveStreamCreate, db: Session) -> LiveStream:
        stream = LiveStream(**data.dict())
        db.add(stream)
        db.commit()
        db.refresh(stream)
        # Pre-create the HLS directory
        _get_hls_dir(stream.id)
        return stream

    @staticmethod
    def get_stream(stream_id: int, db: Session) -> LiveStream:
        stream = db.query(LiveStream).filter(LiveStream.id == stream_id).first()
        if not stream:
            raise HTTPException(status_code=404, detail=f"Stream {stream_id} not found")
        return stream

    @staticmethod
    def get_all_streams(db: Session, active_only: bool = False) -> List[LiveStream]:
        query = db.query(LiveStream)
        if active_only:
            query = query.filter(LiveStream.is_active == True)
        return query.all()

    @staticmethod
    def get_live_streams(db: Session) -> List[LiveStream]:
        """Return only currently live & active streams (for the user-facing list)"""
        return db.query(LiveStream).filter(
            LiveStream.is_live == True,
            LiveStream.is_active == True,
        ).all()

    @staticmethod
    def update_stream(stream_id: int, data: LiveStreamUpdate, db: Session) -> LiveStream:
        stream = LiveStreamService.get_stream(stream_id, db)
        for k, v in data.dict(exclude_unset=True).items():
            setattr(stream, k, v)
        db.commit()
        db.refresh(stream)
        return stream

    @staticmethod
    def delete_stream(stream_id: int, db: Session):
        stream = LiveStreamService.get_stream(stream_id, db)
        if stream.is_live:
            LiveStreamService.stop_stream(stream_id, db)
        db.delete(stream)
        db.commit()
        return {"message": f"Stream {stream_id} deleted"}

    # ── Start / Stop ─────────────────────────────────────────────────────────

    @staticmethod
    def start_stream(stream_id: int, db: Session) -> dict:
        """
        Launch an FFmpeg process for this stream's capture card.
        The process writes HLS segments to disk continuously.
        """
        stream = LiveStreamService.get_stream(stream_id, db)

        if stream.is_live:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream is already live"
            )

        hls_dir = _get_hls_dir(stream_id)
        playlist_path = os.path.join(hls_dir, "playlist.m3u8")

        # Build public URL (served via FastAPI's /media static mount)
        relative = os.path.relpath(playlist_path, settings.MEDIA_ROOT).replace("\\", "/")
        public_url = f"{settings.MEDIA_URL.rstrip('/')}/{relative}"

        # Build and launch FFmpeg
        cmd = _build_ffmpeg_command(stream.device_path, hls_dir)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,   # Capture stderr for debugging
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="FFmpeg not found. Make sure FFmpeg is installed and in your PATH."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start FFmpeg: {e}")

        # Persist state
        stream.is_live = True
        stream.ffmpeg_pid = proc.pid
        stream.hls_playlist_path = playlist_path
        stream.stream_url = public_url
        stream.started_at = datetime.utcnow()
        stream.stopped_at = None
        db.commit()

        return {
            "message": "Stream started",
            "stream_id": stream_id,
            "stream_url": public_url,
            "hls_playlist": playlist_path,
        }

    @staticmethod
    def stop_stream(stream_id: int, db: Session) -> dict:
        """Kill the FFmpeg process and mark the stream as offline."""
        stream = LiveStreamService.get_stream(stream_id, db)

        if not stream.is_live:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream is not currently live"
            )

        if stream.ffmpeg_pid:
            try:
                if platform.system() == "Windows":
                    subprocess.call(
                        ["taskkill", "/F", "/PID", str(stream.ffmpeg_pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                else:
                    os.kill(stream.ffmpeg_pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass  # Process already dead — that's fine

        stream.is_live = False
        stream.ffmpeg_pid = None
        stream.stopped_at = datetime.utcnow()
        stream.viewer_count = 0
        db.commit()

        return {"message": "Stream stopped", "stream_id": stream_id}

    # ── Viewer count ─────────────────────────────────────────────────────────

    @staticmethod
    def join_stream(stream_id: int, db: Session):
        stream = LiveStreamService.get_stream(stream_id, db)
        if not stream.is_live:
            raise HTTPException(status_code=400, detail="Stream is not live")
        stream.viewer_count = max(0, stream.viewer_count + 1)
        db.commit()

    @staticmethod
    def leave_stream(stream_id: int, db: Session):
        stream = LiveStreamService.get_stream(stream_id, db)
        stream.viewer_count = max(0, stream.viewer_count - 1)
        db.commit()
