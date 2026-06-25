"""
Live streaming service — supports HDMI capture cards with embedded audio.

Architecture:
  HDMI Capture Card (video + audio)
       │
       ▼
  FFmpeg  ──transcode──►  HLS segments on disk  (.m3u8 + .ts)
                                  │
                         FastAPI /media/live/{id}/
                                  │
                            Browser (HLS.js)
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

# Where HLS output files are written — served as /media/live/<stream_id>/
LIVE_MEDIA_ROOT = os.path.join(settings.MEDIA_ROOT, "live")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_hls_dir(stream_id: int) -> str:
    path = os.path.join(LIVE_MEDIA_ROOT, str(stream_id))
    os.makedirs(path, exist_ok=True)
    return path


def _detect_audio_device(video_device: str, audio_device: Optional[str]) -> Optional[str]:
    """
    Return the audio device string to use, or None if none is available.

    For HDMI capture cards:
      - Windows: the card exposes a combined dshow audio device,
                 e.g. "audio=USB Capture HDMI+".
      - Linux:   the card registers an ALSA device you can find with
                 `arecord -l`, e.g. "hw:2,0".

    If `audio_device` is explicitly provided it is always trusted.
    Otherwise we try a best-effort auto-detect on Linux.
    """
    if audio_device:
        return audio_device

    if platform.system() == "Windows":
        # Cannot reliably auto-detect on Windows without dshow enumeration;
        # the user must supply audio_device in the LiveStream record.
        return None

    # Linux auto-detect: look for the same soundcard index as the video device.
    # /dev/video2 → try card 2 first, then fall back to card 1.
    try:
        result = subprocess.run(
            ["arecord", "-l"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            # Pull card numbers from "card N:" lines
            import re
            cards = re.findall(r"card (\d+):", result.stdout)
            if cards:
                # Prefer the card that is NOT card 0 (card 0 is usually the
                # system mic; capture cards are typically card 1+).
                capture_cards = [c for c in cards if c != "0"]
                if capture_cards:
                    return f"hw:{capture_cards[0]},0"
    except Exception:
        pass

    return None


def _validate_video_device(device_path: str) -> None:
    """
    Raise HTTPException(400) if a local video device does not exist.
    Skips validation for RTSP/HTTP sources (checked at FFmpeg launch time).
    """
    if device_path.startswith("rtsp://") or device_path.startswith("http"):
        return  # network source — validate at runtime
    if platform.system() == "Windows":
        return  # dshow devices cannot be stat()-checked
    if not os.path.exists(device_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video device not found: {device_path}. "
                   f"Run `ls /dev/video*` to list available devices."
        )


def _build_ffmpeg_command(
    video_device: str,
    audio_device: Optional[str],
    hls_dir: str,
) -> list:
    """
    Build the FFmpeg command for the current OS and input type.

    Supported video sources
    ───────────────────────
    • Windows DirectShow HDMI card  — video_device = "video=USB Capture HDMI+"
    • Linux V4L2 HDMI card          — video_device = "/dev/video1"
    • RTSP IP camera                — video_device = "rtsp://..."
    • Any other FFmpeg-compatible   — passed through as-is

    Supported audio sources
    ───────────────────────
    • Windows DirectShow            — audio_device = "audio=USB Capture HDMI+"
    • Linux ALSA                    — audio_device = "hw:2,0"
    • None                          — silent AAC stream (anullsrc fallback)
    """
    playlist = os.path.join(hls_dir, "playlist.m3u8")
    segment  = os.path.join(hls_dir, "segment_%03d.ts")

    ffmpeg_bin = (
        settings.FFMPEG_PATH
        if os.path.isfile(settings.FFMPEG_PATH)
        else "ffmpeg"
    )
    is_windows  = platform.system() == "Windows"
    is_network  = video_device.startswith("rtsp://") or video_device.startswith("http")

    # ── Video input ───────────────────────────────────────────────────────────
    if is_network:
        # RTSP / HTTP — FFmpeg handles audio itself from the stream
        video_input_args = ["-i", video_device]
        audio_input_args = []
        map_args         = []

    elif is_windows:
        # Windows DirectShow — combine video + audio in ONE -i when both are
        # from the same capture card; otherwise use separate inputs.
        if audio_device and audio_device.startswith("audio="):
            # Single DirectShow source with embedded audio
            video_input_args = [
                "-f", "dshow",
                "-i", f"{video_device}:{audio_device}",
            ]
            audio_input_args = []
            map_args         = []
        elif audio_device:
            # Separate audio device
            video_input_args = ["-f", "dshow", "-i", video_device]
            audio_input_args = ["-f", "dshow", "-i", audio_device]
            map_args         = ["-map", "0:v", "-map", "1:a"]
        else:
            # No audio — generate silent stream
            video_input_args = ["-f", "dshow", "-i", video_device]
            audio_input_args = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            map_args         = ["-map", "0:v", "-map", "1:a"]

    else:
        # Linux V4L2 video
        video_input_args = [
            "-f", "v4l2","-input_format", "mjpeg",
            "-video_size", "1280x720",
            "-framerate", "30",
            "-thread_queue_size", "512", "-i", video_device
        ]

        if audio_device:
            # ALSA audio from the HDMI capture card (e.g. hw:2,0)
            audio_input_args = [
                "-f", "alsa","alsa",
                "-thread_queue_size", "512",
                "-i",
                audio_device
            ]
            map_args         = ["-map", "0:v", "-map", "1:a"]
        else:
            video_input_args = [
                "-f", "v4l2",
                "-input_format", "mjpeg",      # ← tell FFmpeg to use MJPEG from card
                "-video_size", "1280x720",     # ← explicit resolution
                "-framerate", "30",            # ← explicit framerate
                "-i", video_device,
            ]
            # No audio device found — generate silent stream
            # audio_input_args = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            # map_args         = ["-map", "0:v", "-map", "1:a"]

    # ── Full FFmpeg command ───────────────────────────────────────────────────
    #
    # Key low-latency settings:
    #   ultrafast preset   → lowest encode latency
    #   zerolatency tune   → disables lookahead buffers
    #   bufsize = 1× rate  → tight rate control, small output buffer
    #   hls_time 1         → 1-second segments
    #   hls_list_size 3    → ~3 s total live buffer
    #   omit_endlist       → signal live stream to player (no "stream ended" stall)
    #   delete_segments    → auto-delete old .ts files so disk does not fill up
    #
    cmd = [
        ffmpeg_bin,
        *video_input_args,
        *audio_input_args,

        # Video encoding
        "-c:v",         "libx264",
        "-preset",      "ultrafast",
        "-tune",        "zerolatency",
        "-b:v",         "1500k",
        "-maxrate",     "1500k",
        "-bufsize",     "1500k",
        "-vf",          "scale=1280:720",
        "-r",           "30",
        "-g",           "30",        # keyframe every 1 s at 30 fps
        "-keyint_min",  "30",
        "-sc_threshold","0",         # no scene-change keyframes (keeps segments clean)

        # Audio encoding
        "-c:a",  "aac",
        "-b:a",  "128k",
        "-ar",   "44100",

        # Stream mapping (only present when using separate inputs)
        *map_args,

        # HLS muxer
        "-f",                    "hls",
        "-hls_time",             "1",
        "-hls_list_size",        "3",
        "-hls_flags",            "delete_segments+append_list+omit_endlist",
        "-hls_segment_type",     "mpegts",
        "-hls_segment_filename", segment,
        playlist,
    ]

    return cmd


def _cleanup_hls_dir(hls_dir: str) -> None:
    """Remove all .ts segments and the playlist from an HLS output directory."""
    if not os.path.isdir(hls_dir):
        return
    for filename in os.listdir(hls_dir):
        if filename.endswith(".ts") or filename.endswith(".m3u8"):
            try:
                os.remove(os.path.join(hls_dir, filename))
            except OSError:
                pass


def _kill_process(pid: int) -> None:
    """Best-effort process termination, cross-platform."""
    try:
        if platform.system() == "Windows":
            subprocess.call(
                ["taskkill", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass  # already dead


# ─────────────────────────────────────────────────────────────────────────────
# Service class
# ─────────────────────────────────────────────────────────────────────────────

class LiveStreamService:

    # ── CRUD ─────────────────────────────────────────────────────────────────

    @staticmethod
    def create_stream(data: LiveStreamCreate, db: Session) -> LiveStream:
        stream = LiveStream(**data.dict())
        db.add(stream)
        db.commit()
        db.refresh(stream)
        _get_hls_dir(stream.id)   # pre-create HLS output folder
        return stream

    @staticmethod
    def get_stream(stream_id: int, db: Session) -> LiveStream:
        stream = db.query(LiveStream).filter(LiveStream.id == stream_id).first()
        if not stream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stream {stream_id} not found",
            )
        return stream

    @staticmethod
    def get_all_streams(db: Session, active_only: bool = False) -> List[LiveStream]:
        query = db.query(LiveStream)
        if active_only:
            query = query.filter(LiveStream.is_active == True)
        return query.all()

    @staticmethod
    def get_live_streams(db: Session) -> List[LiveStream]:
        """Return only currently live & active streams (user-facing list)."""
        return db.query(LiveStream).filter(
            LiveStream.is_live   == True,
            LiveStream.is_active == True,
        ).all()

    @staticmethod
    def update_stream(
        stream_id: int, data: LiveStreamUpdate, db: Session
    ) -> LiveStream:
        stream = LiveStreamService.get_stream(stream_id, db)
        for k, v in data.dict(exclude_unset=True).items():
            setattr(stream, k, v)
        db.commit()
        db.refresh(stream)
        return stream

    @staticmethod
    def delete_stream(stream_id: int, db: Session) -> dict:
        stream = LiveStreamService.get_stream(stream_id, db)
        if stream.is_live:
            LiveStreamService.stop_stream(stream_id, db)
        db.delete(stream)
        db.commit()
        return {"message": f"Stream {stream_id} deleted"}

    # ── Start ─────────────────────────────────────────────────────────────────

    @staticmethod
    def start_stream(stream_id: int, db: Session) -> dict:
        """
        Launch an FFmpeg process for this stream's HDMI capture card.

        Steps:
          1. Validate the stream is not already live.
          2. Validate the video device exists on disk (Linux/local only).
          3. Resolve the audio device (use stored value or auto-detect).
          4. Build and launch the FFmpeg command.
          5. Persist PID, HLS playlist path, and public URL to the DB.
        """
        stream = LiveStreamService.get_stream(stream_id, db)

        if stream.is_live:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream is already live",
            )

        # 1. Validate video device
        _validate_video_device(stream.device_path)

        # 2. Resolve audio device
        #    stream.audio_device is set by the user when creating/updating the
        #    stream record.  _detect_audio_device tries auto-detect if it is
        #    None, so new setups that don't know their ALSA hw address yet can
        #    still get audio automatically on Linux.
        audio_device = _detect_audio_device(stream.device_path, stream.audio_device)

        # 3. Prepare HLS output directory
        hls_dir       = _get_hls_dir(stream_id)
        playlist_path = os.path.join(hls_dir, "playlist.m3u8")

        # Build public URL (served via FastAPI's /media static mount)
        relative   = os.path.relpath(playlist_path, settings.MEDIA_ROOT).replace("\\", "/")
        public_url = f"{settings.MEDIA_URL.rstrip('/')}/{relative}"

        # 4. Build FFmpeg command
        cmd = _build_ffmpeg_command(stream.device_path, audio_device, hls_dir)

        # 5. Launch FFmpeg
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                # stderr=subprocess.PIPE,   # keep stderr so errors can be read later
                stdin=subprocess.DEVNULL,   # prevent FFmpeg from blocking on input
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if platform.system() == "Windows"
                    else 0
                ),
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="FFmpeg not found. Install FFmpeg and make sure it is in your PATH.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start FFmpeg: {exc}",
            )

        # 6. Persist state
        stream.is_live            = True
        stream.ffmpeg_pid         = proc.pid
        stream.hls_playlist_path  = playlist_path
        stream.stream_url         = public_url
        stream.audio_device       = audio_device   # save resolved value
        stream.started_at         = datetime.utcnow()
        stream.stopped_at         = None
        db.commit()

        return {
            "message":      "Stream started",
            "stream_id":    stream_id,
            "stream_url":   public_url,
            "hls_playlist": playlist_path,  
            "audio_device": audio_device or "none (silent fallback)",
        }

    # ── Stop ─────────────────────────────────────────────────────────────────

    @staticmethod
    def stop_stream(stream_id: int, db: Session) -> dict:
        """
        Kill the FFmpeg process, clean up HLS segments, and mark the stream offline.
        """
        stream = LiveStreamService.get_stream(stream_id, db)

        if not stream.is_live:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream is not currently live",
            )

        # Kill FFmpeg process
        if stream.ffmpeg_pid:
            _kill_process(stream.ffmpeg_pid)

        # Clean up stale HLS segments from disk so they don't accumulate
        hls_dir = _get_hls_dir(stream_id)
        _cleanup_hls_dir(hls_dir)

        # Update DB
        stream.is_live      = False
        stream.ffmpeg_pid   = None
        stream.stopped_at   = datetime.utcnow()
        stream.viewer_count = 0
        db.commit()

        return {"message": "Stream stopped", "stream_id": stream_id}

    # ── Viewer count ─────────────────────────────────────────────────────────

    @staticmethod
    def join_stream(stream_id: int, db: Session) -> None:
        stream = LiveStreamService.get_stream(stream_id, db)
        if not stream.is_live:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream is not live",
            )
        stream.viewer_count = max(0, stream.viewer_count + 1)
        db.commit()

    @staticmethod
    def leave_stream(stream_id: int, db: Session) -> None:
        stream = LiveStreamService.get_stream(stream_id, db)
        stream.viewer_count = max(0, stream.viewer_count - 1)
        db.commit()