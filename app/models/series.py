"""
Series, Season, Episode models for TV show / series content
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Series(Base):
    __tablename__ = "series"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    release_year = Column(Integer)
    director = Column(String(100))
    cast = Column(Text)           # JSON string of actors
    rating = Column(String(10))   # PG, PG-13, R, etc.
    language = Column(String(50), default="English")
    country = Column(String(50))

    # Media
    poster_url = Column(String(500))
    backdrop_url = Column(String(500))
    trailer_url = Column(String(500))

    # Flags
    is_featured = Column(Boolean, default=False)
    is_trending = Column(Boolean, default=False)
    status = Column(String(50), default="active")  # active, inactive
    view_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    seasons = relationship("Season", back_populates="series", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Series {self.title}>"


class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    season_number = Column(Integer, nullable=False)
    title = Column(String(255))
    description = Column(Text)
    release_year = Column(Integer)
    poster_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    series = relationship("Series", back_populates="seasons")
    episodes = relationship("Episode", back_populates="season", cascade="all, delete-orphan",
                            order_by="Episode.episode_number")

    def __repr__(self):
        return f"<Season series_id={self.series_id} season={self.season_number}>"


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration = Column(Integer)          # seconds
    thumbnail_url = Column(String(500))
    video_url = Column(String(500))     # Primary (highest quality) URL
    original_filename = Column(String(255))

    # Processing
    status = Column(String(50), default="pending")  # pending, processing, ready, failed
    view_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    season = relationship("Season", back_populates="episodes")
    video_files = relationship("EpisodeVideoFile", back_populates="episode",
                               cascade="all, delete-orphan")
    conversion_jobs = relationship("EpisodeConversionJob", back_populates="episode",
                                   cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Episode season_id={self.season_id} ep={self.episode_number}>"


class EpisodeVideoFile(Base):
    __tablename__ = "episode_video_files"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    quality = Column(String(20), nullable=False)   # 1080p, 720p, 480p
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger)                 # bytes
    codec = Column(String(50))
    bitrate = Column(Integer)                      # kbps
    resolution_width = Column(Integer)
    resolution_height = Column(Integer)
    format_type = Column(String(20))               # mp4, hls
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    episode = relationship("Episode", back_populates="video_files")

    def __repr__(self):
        return f"<EpisodeVideoFile episode_id={self.episode_id} quality={self.quality}>"


class EpisodeConversionJob(Base):
    __tablename__ = "episode_conversion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="queued")   # queued, processing, completed, failed
    progress = Column(Integer, default=0)            # 0-100
    current_step = Column(String(100))
    error_message = Column(Text)
    task_id = Column(String(255))                    # Celery task ID
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    episode = relationship("Episode", back_populates="conversion_jobs")

    def __repr__(self):
        return f"<EpisodeConversionJob episode_id={self.episode_id} status={self.status}>"
