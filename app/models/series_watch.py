"""
EpisodeWatchHistory — tracks per-episode watch progress for series.
Mirrors WatchHistory (movies) but points to Episode instead of Movie.
"""
from sqlalchemy import Column, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class EpisodeWatchHistory(Base):
    __tablename__ = "episode_watch_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    episode_id = Column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)

    # Playback state
    watch_percentage = Column(Float, default=0.0)   # 0.0 – 100.0
    last_position = Column(Integer, default=0)       # seconds
    completed = Column(Boolean, default=False)

    watched_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="episode_watch_history")
    episode = relationship("Episode", backref="watch_history")

    __table_args__ = (
        UniqueConstraint("user_id", "episode_id", name="unique_user_episode_watch"),
    )

    def __repr__(self):
        return f"<EpisodeWatchHistory user={self.user_id} ep={self.episode_id}>"


class SeriesRating(Base):
    __tablename__ = "series_ratings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    series_id = Column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)   # 1-5 stars
    review = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="series_ratings")
    series = relationship("Series", backref="ratings")

    __table_args__ = (
        UniqueConstraint("user_id", "series_id", name="unique_user_series_rating"),
    )
