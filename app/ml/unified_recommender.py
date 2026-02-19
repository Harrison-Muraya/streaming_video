"""
SeriesRecommender
─────────────────
Extends the existing ML pipeline to include series.

How it works:
  • Collaborative filtering  — builds a user × (movie + series) interaction
    matrix using both WatchHistory (movies) and EpisodeWatchHistory (series).
    A user's implicit rating for a series is derived from the average
    watch-percentage across all episodes they've seen.

  • Content-based filtering  — adds series to the TF-IDF feature matrix
    using genres, description, director, cast — identical pipeline to movies.

  • Hybrid output            — merges both signals with the same 70/30 weight
    as the movie recommender, then separates results into movies vs series
    so the frontend can render them correctly.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.movie import Movie
from app.models.series import Series, Season, Episode
from app.models.watch_history import WatchHistory, MovieRating
from app.models.series_watch import EpisodeWatchHistory, SeriesRating


# ─────────────────────────────────────────────────────────────────────────────
# Helper: derive implicit rating from watch percentage
# ─────────────────────────────────────────────────────────────────────────────

def _implicit_rating(watch_pct: float) -> float:
    if watch_pct >= 90: return 5.0
    if watch_pct >= 75: return 4.0
    if watch_pct >= 50: return 3.0
    if watch_pct >= 25: return 2.0
    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Unified content-based filter (movies + series)
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedContentFilter:
    """
    TF-IDF content similarity across both movies and series.
    item_ids use a namespaced key: "movie_<id>" or "series_<id>"
    """

    def __init__(self, db: Session):
        self.db = db
        self.item_ids: List[str] = []
        self.tfidf_matrix = None

    def build(self):
        items = []

        for movie in self.db.query(Movie).filter(Movie.status == "ready").all():
            genres = " ".join(g.name for g in movie.genres)
            text = f"{genres} {genres} {movie.description or ''} {movie.director or ''} {movie.cast or ''}"
            items.append({"id": f"movie_{movie.id}", "text": text})

        for series in self.db.query(Series).filter(Series.status == "active").all():
            # Series don't have genres linked yet (you can add a SeriesGenre table later)
            # For now use description + director + cast
            text = f"{series.description or ''} {series.director or ''} {series.cast or ''}"
            items.append({"id": f"series_{series.id}", "text": text})

        if not items:
            return

        self.item_ids = [i["id"] for i in items]
        vectorizer = TfidfVectorizer(max_features=200, stop_words="english", ngram_range=(1, 2))
        self.tfidf_matrix = vectorizer.fit_transform([i["text"] for i in items])

    def get_similar(self, item_key: str, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        item_key: "movie_<id>" or "series_<id>"
        Returns list of (item_key, score) sorted by similarity descending.
        """
        if self.tfidf_matrix is None:
            self.build()
        if item_key not in self.item_ids:
            return []

        idx = self.item_ids.index(item_key)
        vec = self.tfidf_matrix[idx]
        sims = cosine_similarity(vec, self.tfidf_matrix).flatten()
        top_indices = sims.argsort()[::-1][1:top_n + 1]
        return [(self.item_ids[i], float(sims[i])) for i in top_indices]

    def recommend_for_history(self, watched_keys: List[str], top_n: int = 20) -> List[Tuple[str, float]]:
        """Score all items by average similarity to watched items."""
        if self.tfidf_matrix is None:
            self.build()
        if not watched_keys or not self.item_ids:
            return []

        valid_indices = [self.item_ids.index(k) for k in watched_keys if k in self.item_ids]
        if not valid_indices:
            return []

        watched_matrix = self.tfidf_matrix[valid_indices]
        avg_sim = cosine_similarity(watched_matrix, self.tfidf_matrix).mean(axis=0)

        scores = {}
        for i, key in enumerate(self.item_ids):
            if key not in watched_keys:
                scores[key] = float(avg_sim[i])

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# Unified collaborative filter (movies + series)
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedCollaborativeFilter:
    """
    User × item matrix where items = movies + series.
    Series rating = average implicit rating across all watched episodes.
    """

    def __init__(self, db: Session):
        self.db = db
        self.matrix: Optional[pd.DataFrame] = None

    def build(self):
        rows = []

        # ── Movies ────────────────────────────────────────────────────────
        for wh in self.db.query(WatchHistory).all():
            rows.append({
                "user_id": wh.user_id,
                "item_id": f"movie_{wh.movie_id}",
                "rating": _implicit_rating(wh.watch_percentage),
            })

        # Override with explicit movie ratings
        for mr in self.db.query(MovieRating).all():
            rows.append({
                "user_id": mr.user_id,
                "item_id": f"movie_{mr.movie_id}",
                "rating": float(mr.rating),
            })

        # ── Series (aggregate episode watches per series) ─────────────────
        ep_watches = self.db.query(EpisodeWatchHistory).all()

        # Map episode_id → series_id
        ep_to_series: Dict[int, int] = {}
        for ep in self.db.query(Episode).all():
            season = self.db.query(Season).filter(Season.id == ep.season_id).first()
            if season:
                ep_to_series[ep.id] = season.series_id

        # Aggregate: user → series → list of watch percentages
        user_series_pct: Dict[Tuple[int, int], List[float]] = {}
        for ewh in ep_watches:
            series_id = ep_to_series.get(ewh.episode_id)
            if series_id:
                key = (ewh.user_id, series_id)
                user_series_pct.setdefault(key, []).append(ewh.watch_percentage)

        for (user_id, series_id), pcts in user_series_pct.items():
            avg_pct = sum(pcts) / len(pcts)
            rows.append({
                "user_id": user_id,
                "item_id": f"series_{series_id}",
                "rating": _implicit_rating(avg_pct),
            })

        # Override with explicit series ratings
        for sr in self.db.query(SeriesRating).all():
            rows.append({
                "user_id": sr.user_id,
                "item_id": f"series_{sr.series_id}",
                "rating": float(sr.rating),
            })

        if not rows:
            return

        df = pd.DataFrame(rows)
        # Last write wins (explicit rating overrides implicit)
        df = df.drop_duplicates(subset=["user_id", "item_id"], keep="last")

        self.matrix = df.pivot_table(
            index="user_id", columns="item_id", values="rating", fill_value=0
        )

    def recommend(self, user_id: int, top_n: int = 20) -> List[Tuple[str, float]]:
        if self.matrix is None:
            self.build()
        if self.matrix is None or self.matrix.empty:
            return []

        if user_id not in self.matrix.index:
            return self._popular(top_n)

        sim_matrix = cosine_similarity(self.matrix)
        user_idx = list(self.matrix.index).index(user_id)
        user_sims = sim_matrix[user_idx]

        # Weighted predicted ratings
        similar_indices = np.argsort(user_sims)[::-1][1:21]
        sim_weights = user_sims[similar_indices]
        if sim_weights.sum() == 0:
            return self._popular(top_n)

        similar_ratings = self.matrix.iloc[similar_indices]
        predicted = similar_ratings.T.dot(sim_weights) / sim_weights.sum()

        # Exclude items already watched
        user_row = self.matrix.loc[user_id]
        already_watched = set(user_row[user_row > 0].index)

        scores = {
            item: float(score)
            for item, score in predicted.items()
            if item not in already_watched
        }

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def _popular(self, top_n: int) -> List[Tuple[str, float]]:
        """Fallback for new users — most interacted-with items."""
        if self.matrix is None or self.matrix.empty:
            return []
        popularity = (self.matrix > 0).sum(axis=0).sort_values(ascending=False)
        return [(item, float(score)) for item, score in popularity.head(top_n).items()]


# ─────────────────────────────────────────────────────────────────────────────
# Unified hybrid recommender
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedHybridRecommender:
    """
    Combines collaborative + content-based for movies AND series.
    Returns results split into two lists for easy rendering.
    """

    COLLAB_WEIGHT  = 0.7
    CONTENT_WEIGHT = 0.3

    def __init__(self, db: Session):
        self.db = db
        self.collab  = UnifiedCollaborativeFilter(db)
        self.content = UnifiedContentFilter(db)

    def _get_watched_keys(self, user_id: int) -> List[str]:
        movie_ids = [
            f"movie_{wh.movie_id}"
            for wh in self.db.query(WatchHistory).filter(WatchHistory.user_id == user_id).all()
        ]
        # Get distinct series watched
        ep_ids = [
            ewh.episode_id
            for ewh in self.db.query(EpisodeWatchHistory).filter(
                EpisodeWatchHistory.user_id == user_id
            ).all()
        ]
        series_ids = set()
        for ep_id in ep_ids:
            ep = self.db.query(Episode).filter(Episode.id == ep_id).first()
            if ep:
                season = self.db.query(Season).filter(Season.id == ep.season_id).first()
                if season:
                    series_ids.add(f"series_{season.series_id}")
        return movie_ids + list(series_ids)

    def recommend(self, user_id: int, top_n: int = 20) -> Dict:
        """
        Returns:
          {
            "movies":  [{"movie_id": int, "title": str, "score": float, "reason": str}, ...],
            "series":  [{"series_id": int, "title": str, "score": float, "reason": str}, ...],
          }
        """
        watch_count = self.db.query(WatchHistory).filter(WatchHistory.user_id == user_id).count()
        ep_count    = self.db.query(EpisodeWatchHistory).filter(EpisodeWatchHistory.user_id == user_id).count()
        total_watch = watch_count + ep_count

        # Strategy selection (mirrors existing HybridRecommender logic)
        if total_watch < 5:
            watched_keys = self._get_watched_keys(user_id)
            content_recs = self.content.recommend_for_history(watched_keys, top_n * 2)
            combined = {k: v * self.CONTENT_WEIGHT for k, v in content_recs}
            reason = "Based on what you've watched"
        else:
            collab_recs  = dict(self.collab.recommend(user_id, top_n * 2))
            watched_keys = self._get_watched_keys(user_id)
            content_recs = dict(self.content.recommend_for_history(watched_keys, top_n * 2))

            all_keys = set(collab_recs) | set(content_recs)
            combined = {}
            for key in all_keys:
                combined[key] = (
                    collab_recs.get(key, 0)  * self.COLLAB_WEIGHT +
                    content_recs.get(key, 0) * self.CONTENT_WEIGHT
                )
            reason = "Recommended for you"

        sorted_items = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        movies_out  = []
        series_out  = []

        for key, score in sorted_items:
            if key.startswith("movie_"):
                movie_id = int(key.split("_")[1])
                movie = self.db.query(Movie).filter(Movie.id == movie_id, Movie.status == "ready").first()
                if movie:
                    movies_out.append({
                        "movie_id":   movie.id,
                        "title":      movie.title,
                        "poster_url": movie.poster_url,
                        "backdrop_url": movie.backdrop_url,
                        "release_year": movie.release_year,
                        "duration":   movie.duration,
                        "genres":     [g.name for g in movie.genres],
                        "recommendation_score": round(score, 3),
                        "reason":     reason,
                        "type":       "movie",
                    })
            elif key.startswith("series_"):
                series_id = int(key.split("_")[1])
                series = self.db.query(Series).filter(Series.id == series_id, Series.status == "active").first()
                if series:
                    season_count  = self.db.query(Season).filter(Season.series_id == series_id).count()
                    episode_count = (
                        self.db.query(Episode)
                        .join(Season, Episode.season_id == Season.id)
                        .filter(Season.series_id == series_id)
                        .count()
                    )
                    series_out.append({
                        "series_id":     series.id,
                        "title":         series.title,
                        "poster_url":    series.poster_url,
                        "backdrop_url":  series.backdrop_url,
                        "release_year":  series.release_year,
                        "season_count":  season_count,
                        "episode_count": episode_count,
                        "recommendation_score": round(score, 3),
                        "reason":        reason,
                        "type":          "series",
                    })

            if len(movies_out) >= top_n and len(series_out) >= top_n:
                break

        return {"movies": movies_out[:top_n], "series": series_out[:top_n]}
