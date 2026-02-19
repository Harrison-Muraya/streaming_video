"""
Series watch tracking, ratings, and play-next endpoints.
Mounted at: /api/v1/series-watch
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_active_user
from app.services.series_watch_service import EpisodeWatchService, SeriesRatingService
from app.services.play_next_service import PlayNextService

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class EpisodeProgressUpdate(BaseModel):
    episode_id: int
    last_position: int = Field(..., ge=0, description="Playback position in seconds")
    watch_percentage: float = Field(..., ge=0, le=100)
    completed: bool = False


class EpisodeProgressResponse(BaseModel):
    id: int
    user_id: int
    episode_id: int
    watch_percentage: float
    last_position: int
    completed: bool
    watched_at: datetime
    class Config:
        from_attributes = True


class SeriesRatingCreate(BaseModel):
    series_id: int
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = None


class SeriesRatingResponse(BaseModel):
    id: int
    user_id: int
    series_id: int
    rating: int
    review: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


# ════════════════════════════════════════════════════════════════
# EPISODE WATCH PROGRESS
# ════════════════════════════════════════════════════════════════

@router.post("/progress", response_model=EpisodeProgressResponse)
async def update_episode_progress(
    data: EpisodeProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Save episode watch progress.

    Call every 30 seconds during playback, on pause, and on exit.
    This data feeds directly into the ML recommendation engine.
    """
    return EpisodeWatchService.update_progress(
        user_id=current_user.id,
        episode_id=data.episode_id,
        last_position=data.last_position,
        watch_percentage=data.watch_percentage,
        completed=data.completed,
        db=db,
    )


@router.get("/progress/{episode_id}", response_model=EpisodeProgressResponse | None)
async def get_episode_progress(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get playback position for an episode (used to resume watching)."""
    return EpisodeWatchService.get_progress(current_user.id, episode_id, db)


@router.get("/series/{series_id}/progress")
async def get_series_progress(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get watch progress for every episode in a series.
    Used to show per-episode completion indicators on the series detail page.
    """
    records = EpisodeWatchService.get_series_progress(current_user.id, series_id, db)
    return [
        {
            "episode_id":       r.episode_id,
            "watch_percentage": r.watch_percentage,
            "last_position":    r.last_position,
            "completed":        r.completed,
            "watched_at":       r.watched_at,
        }
        for r in records
    ]


@router.get("/continue-watching")
async def continue_watching_series(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Series the user has started but not finished, with the specific episode to resume.
    Combine with the movies continue-watching endpoint on the home screen.
    """
    return EpisodeWatchService.get_continue_watching_series(current_user.id, db, limit)


# ════════════════════════════════════════════════════════════════
# SERIES RATINGS
# ════════════════════════════════════════════════════════════════

@router.post("/ratings", response_model=SeriesRatingResponse, status_code=status.HTTP_201_CREATED)
async def rate_series(
    data: SeriesRatingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Rate a series 1-5 stars. Ratings boost recommendation accuracy."""
    return SeriesRatingService.rate_series(
        current_user.id, data.series_id, data.rating, data.review, db
    )


@router.get("/ratings/{series_id}/average")
async def get_series_average_rating(series_id: int, db: Session = Depends(get_db)):
    """Get average star rating for a series."""
    return SeriesRatingService.get_average_rating(series_id, db)


# ════════════════════════════════════════════════════════════════
# PLAY NEXT  (the key autoplay endpoint)
# ════════════════════════════════════════════════════════════════

@router.get("/play-next/episode/{episode_id}")
async def play_next_after_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Call this when an episode finishes playing.

    Response tells the player what to load next:

    • **type = "episode"**             → next episode details + video_url (autoplay immediately)
    • **type = "series_recommendation"** → series is done; show a "Watch Next" card
    • **type = "none"**                → nothing to suggest

    The watch progress for the finished episode should already have been saved
    via `POST /series-watch/progress` before calling this endpoint.
    """
    return PlayNextService.next_for_episode(episode_id, current_user.id, db)


@router.get("/play-next/movie/{movie_id}")
async def play_next_after_movie(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Call this when a movie finishes playing.

    The ML engine picks the best next content for this user —
    could be another movie or a series they haven't tried yet.

    • **type = "movie"**   → recommended movie details
    • **type = "series"**  → recommended series to start
    • **type = "none"**    → nothing to suggest
    """
    return PlayNextService.next_for_movie(movie_id, current_user.id, db)


# ════════════════════════════════════════════════════════════════
# UNIFIED RECOMMENDATIONS  (movies + series together)
# ════════════════════════════════════════════════════════════════

@router.get("/recommendations/for-you")
async def unified_recommendations(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    ML-powered recommendations that include BOTH movies and series.

    Returns two lists so the frontend can render them in separate rows:
      - **movies**  — recommended movies
      - **series**  — recommended series to start

    Uses hybrid collaborative + content-based filtering (70 / 30 split).
    New users get content-based suggestions; established users get the hybrid.
    """
    from app.ml.unified_recommender import UnifiedHybridRecommender
    recommender = UnifiedHybridRecommender(db)
    return recommender.recommend(current_user.id, top_n=limit)


@router.get("/recommendations/similar-to/{content_type}/{content_id}")
async def similar_content(
    content_type: str,   # "movie" or "series"
    content_id: int,
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Content-based similarity — "More like this".

    Pass content_type = "movie" or "series" and the corresponding ID.
    Returns a mixed list of similar movies and series.
    """
    from app.ml.unified_recommender import UnifiedContentFilter

    if content_type not in ("movie", "series"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content_type must be 'movie' or 'series'")

    item_key = f"{content_type}_{content_id}"
    cf = UnifiedContentFilter(db)
    cf.build()
    similar = cf.get_similar(item_key, top_n=limit * 2)

    from app.models.movie import Movie
    from app.models.series import Series

    results = []
    for key, score in similar[:limit * 2]:
        if key.startswith("movie_"):
            mid = int(key.split("_")[1])
            m = db.query(Movie).filter(Movie.id == mid, Movie.status == "ready").first()
            if m:
                results.append({
                    "type": "movie", "id": m.id, "title": m.title,
                    "poster_url": m.poster_url, "score": round(score, 3),
                })
        elif key.startswith("series_"):
            sid = int(key.split("_")[1])
            s = db.query(Series).filter(Series.id == sid).first()
            if s:
                results.append({
                    "type": "series", "id": s.id, "title": s.title,
                    "poster_url": s.poster_url, "score": round(score, 3),
                })
        if len(results) >= limit:
            break

    return results
