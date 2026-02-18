"""
LiveStream model — one row per capture card / stream source
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class LiveStream(Base):
    __tablename__ = "live_streams"

    id = Column(Integer, primary_key=True, index=True)

    # Display info (shown to user on the selection screen)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    thumbnail_url = Column(String(500))    # Optional cover image

    # Capture card / source config (admin-only, never sent to users)
    # Examples:
    #   device_path = "/dev/video0"           (Linux V4L2)
    #   device_path = "video=AVerMedia Live Gamer"  (Windows DirectShow)
    #   device_path = "rtsp://192.168.1.10/stream"  (IP camera / RTSP)
    device_path = Column(String(500), nullable=False)

    # Runtime state
    is_live = Column(Boolean, default=False)       # True while FFmpeg is running
    is_active = Column(Boolean, default=True)      # False = hidden from users
    viewer_count = Column(Integer, default=0)

    # HLS output
    # e.g. "media/live/stream_1/playlist.m3u8"
    hls_playlist_path = Column(String(500))
    # Public URL served to clients
    # e.g. "http://yourserver/media/live/stream_1/playlist.m3u8"
    stream_url = Column(String(500))

    # FFmpeg process PID (so we can stop it later)
    ffmpeg_pid = Column(Integer)

    # Timestamps
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<LiveStream id={self.id} title={self.title} live={self.is_live}>"
