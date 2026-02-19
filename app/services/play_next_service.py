"""
PlayNextService
───────────────
Decides what to play automatically when the current content finishes.

Rules:
  • If watching a SERIES episode:
      1. Play the next episode in the same season.
      2. If it was the season finale, play S(n+1)E1.
      3. If it was the series finale, recommend a similar series.

  • If watching a MOVIE:
      1. Recommend the highest-scored movie from the unified ML engine.
      2. Fall back to most-similar movie by content if ML has no data.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.series import Episode, Season, Series
from app.models.movie import Movie
from app.models.series_watch import EpisodeWatchHistory
from app.ml.unified_recommender import UnifiedHybridRecommender, UnifiedContentFilter


class PlayNextService:

    # ── Series: get next episode ──────────────────────────────────────────────

    @staticmethod
    def next_for_episode(episode_id: int, user_id: int, db: Session) -> Dict[str, Any]:
        """
        Called when an episode finishes.
        Returns the next episode, or a series recommendation if series is done.
        """
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            return {"type": "none", "reason": "Episode not found"}

        season = db.query(Season).filter(Season.id == episode.season_id).first()
        if not season:
            return {"type": "none", "reason": "Season not found"}

        # ── Try next episode in same season ───────────────────────────────
        next_ep = (
            db.query(Episode)
            .filter(
                Episode.season_id == season.id,
                Episode.episode_number == episode.episode_number + 1,
                Episode.status == "ready",
            )
            .first()
        )

        if next_ep:
            return {
                "type":           "episode",
                "episode_id":     next_ep.id,
                "episode_number": next_ep.episode_number,
                "season_number":  season.season_number,
                "title":          next_ep.title,
                "description":    next_ep.description,
                "duration":       next_ep.duration,
                "thumbnail_url":  next_ep.thumbnail_url,
                "video_url":      next_ep.video_url,
                "reason":         f"Next episode: S{season.season_number}E{next_ep.episode_number}",
            }

        # ── Try first episode of next season ──────────────────────────────
        next_season = (
            db.query(Season)
            .filter(
                Season.series_id == season.series_id,
                Season.season_number == season.season_number + 1,
            )
            .first()
        )

        if next_season:
            first_ep = (
                db.query(Episode)
                .filter(Episode.season_id == next_season.id, Episode.status == "ready")
                .order_by(Episode.episode_number)
                .first()
            )
            if first_ep:
                return {
                    "type":           "episode",
                    "episode_id":     first_ep.id,
                    "episode_number": first_ep.episode_number,
                    "season_number":  next_season.season_number,
                    "title":          first_ep.title,
                    "description":    first_ep.description,
                    "duration":       first_ep.duration,
                    "thumbnail_url":  first_ep.thumbnail_url,
                    "video_url":      first_ep.video_url,
                    "reason":         f"Next season: S{next_season.season_number}E{first_ep.episode_number}",
                }

        # ── Series is fully watched — recommend a similar series ──────────
        series = db.query(Series).filter(Series.id == season.series_id).first()
        similar = PlayNextService._similar_series(season.series_id, user_id, db)

        return {
            "type":    "series_recommendation",
            "reason":  f"You finished {series.title if series else 'this series'}! Here's what to watch next:",
            "items":   similar,
        }

    # ── Movie: get next recommendation ───────────────────────────────────────

    @staticmethod
    def next_for_movie(movie_id: int, user_id: int, db: Session) -> Dict[str, Any]:
        """
        Called when a movie finishes.
        Returns ML-based recommendation — movie or series.
        """
        recommender = UnifiedHybridRecommender(db)
        recs = recommender.recommend(user_id, top_n=5)

        # Prefer movies first, fall back to series
        if recs["movies"]:
            top = recs["movies"][0]
            return {
                "type":       "movie",
                "movie_id":   top["movie_id"],
                "title":      top["title"],
                "poster_url": top.get("poster_url"),
                "duration":   top.get("duration"),
                "genres":     top.get("genres", []),
                "reason":     top["reason"],
            }

        if recs["series"]:
            top = recs["series"][0]
            return {
                "type":      "series",
                "series_id": top["series_id"],
                "title":     top["title"],
                "poster_url": top.get("poster_url"),
                "reason":    top["reason"],
            }

        # Ultimate fallback — most similar movie by content
        content = UnifiedContentFilter(db)
        content.build()
        similar = content.get_similar(f"movie_{movie_id}", top_n=5)

        for key, score in similar:
            if key.startswith("movie_"):
                mid = int(key.split("_")[1])
                m = db.query(Movie).filter(Movie.id == mid, Movie.status == "ready").first()
                if m:
                    return {
                        "type":       "movie",
                        "movie_id":   m.id,
                        "title":      m.title,
                        "poster_url": m.poster_url,
                        "duration":   m.duration,
                        "genres":     [g.name for g in m.genres],
                        "reason":     "You might also like",
                    }

        return {"type": "none", "reason": "No recommendations available"}

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _similar_series(series_id: int, user_id: int, db: Session) -> list:
        content = UnifiedContentFilter(db)
        content.build()
        similar_keys = content.get_similar(f"series_{series_id}", top_n=5)

        results = []
        for key, score in similar_keys:
            if key.startswith("series_"):
                sid = int(key.split("_")[1])
                s = db.query(Series).filter(Series.id == sid, Series.status == "active").first()
                if s:
                    results.append({
                        "series_id":  s.id,
                        "title":      s.title,
                        "poster_url": s.poster_url,
                        "score":      round(score, 3),
                    })

        # Also add top ML series recommendation
        recommender = UnifiedHybridRecommender(db)
        recs = recommender.recommend(user_id, top_n=3)
        for r in recs.get("series", []):
            if r["series_id"] != series_id and not any(x["series_id"] == r["series_id"] for x in results):
                results.append({
                    "series_id":  r["series_id"],
                    "title":      r["title"],
                    "poster_url": r.get("poster_url"),
                    "score":      r["recommendation_score"],
                })

        return results[:5]
