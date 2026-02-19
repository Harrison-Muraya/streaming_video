"""
Series watch history service.
Tracks episode-level progress and series ratings.
Feeds into the ML recommendation engine.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status
from datetime import datetime

from app.models.series_watch import EpisodeWatchHistory, SeriesRating
from app.models.series import Episode, Season, Series


class EpisodeWatchService:

    @staticmethod
    def update_progress(
        user_id: int,
        episode_id: int,
        last_position: int,
        watch_percentage: float,
        completed: bool,
        db: Session,
    ) -> EpisodeWatchHistory:
        """
        Save or update playback position for an episode.
        Call every 30 seconds during playback, on pause, and on exit.
        """
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

        record = db.query(EpisodeWatchHistory).filter(
            EpisodeWatchHistory.user_id == user_id,
            EpisodeWatchHistory.episode_id == episode_id,
        ).first()

        if record:
            record.last_position = last_position
            record.watch_percentage = watch_percentage
            record.completed = completed
            record.watched_at = datetime.utcnow()
        else:
            record = EpisodeWatchHistory(
                user_id=user_id,
                episode_id=episode_id,
                last_position=last_position,
                watch_percentage=watch_percentage,
                completed=completed,
            )
            db.add(record)
            # Increment episode view count on first watch
            episode.view_count += 1

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_progress(user_id: int, episode_id: int, db: Session) -> Optional[EpisodeWatchHistory]:
        return db.query(EpisodeWatchHistory).filter(
            EpisodeWatchHistory.user_id == user_id,
            EpisodeWatchHistory.episode_id == episode_id,
        ).first()

    @staticmethod
    def get_series_progress(user_id: int, series_id: int, db: Session) -> List[EpisodeWatchHistory]:
        """Return watch records for every episode in a series the user has touched."""
        return (
            db.query(EpisodeWatchHistory)
            .join(Episode, EpisodeWatchHistory.episode_id == Episode.id)
            .join(Season, Episode.season_id == Season.id)
            .filter(Season.series_id == series_id, EpisodeWatchHistory.user_id == user_id)
            .order_by(Season.season_number, Episode.episode_number)
            .all()
        )

    @staticmethod
    def get_continue_watching_series(user_id: int, db: Session, limit: int = 10):
        """
        Series the user has started but not finished.
        Returns the specific episode to resume + series metadata.
        """
        # Find episodes partially watched (5-99%)
        partial = (
            db.query(EpisodeWatchHistory)
            .filter(
                EpisodeWatchHistory.user_id == user_id,
                EpisodeWatchHistory.watch_percentage >= 5.0,
                EpisodeWatchHistory.completed == False,
            )
            .order_by(desc(EpisodeWatchHistory.watched_at))
            .all()
        )

        results = []
        seen_series = set()

        for record in partial:
            episode = db.query(Episode).filter(Episode.id == record.episode_id).first()
            if not episode:
                continue
            season = db.query(Season).filter(Season.id == episode.season_id).first()
            if not season or season.series_id in seen_series:
                continue

            series = db.query(Series).filter(Series.id == season.series_id).first()
            seen_series.add(season.series_id)

            results.append({
                "series_id": season.series_id,
                "series_title": series.title if series else "",
                "series_poster": series.poster_url if series else None,
                "resume_episode_id": episode.id,
                "resume_episode_number": episode.episode_number,
                "resume_season_number": season.season_number,
                "last_position": record.last_position,
                "watch_percentage": record.watch_percentage,
                "watched_at": record.watched_at,
            })

            if len(results) >= limit:
                break

        return results


class SeriesRatingService:

    @staticmethod
    def rate_series(user_id: int, series_id: int, rating: int, review: Optional[str], db: Session) -> SeriesRating:
        if not 1 <= rating <= 5:
            raise HTTPException(status_code=400, detail="Rating must be 1-5")

        series = db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise HTTPException(status_code=404, detail=f"Series {series_id} not found")

        record = db.query(SeriesRating).filter(
            SeriesRating.user_id == user_id,
            SeriesRating.series_id == series_id,
        ).first()

        if record:
            record.rating = rating
            record.review = review
            record.updated_at = datetime.utcnow()
        else:
            record = SeriesRating(
                user_id=user_id, series_id=series_id, rating=rating, review=review
            )
            db.add(record)

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_average_rating(series_id: int, db: Session) -> dict:
        ratings = db.query(SeriesRating).filter(SeriesRating.series_id == series_id).all()
        if not ratings:
            return {"average_rating": None, "total_ratings": 0}
        avg = sum(r.rating for r in ratings) / len(ratings)
        return {"average_rating": round(avg, 1), "total_ratings": len(ratings)}
