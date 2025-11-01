"""
API endpoints for movie recommendations
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_active_user
from app.services.recommendation_service import RecommendationService
from pydantic import BaseModel

router = APIRouter()


class RecommendationResponse(BaseModel):
    """Single recommendation result"""
    movie_id: int
    title: str
    description: str | None
    poster_url: str | None
    backdrop_url: str | None
    release_year: int | None
    duration: int | None
    genres: List[str]
    recommendation_score: float
    reason: str


class SimilarMovieResponse(BaseModel):
    """Similar movie result"""
    movie_id: int
    title: str
    description: str | None
    poster_url: str | None
    release_year: int | None
    genres: List[str]
    similarity_score: float


class TrendingMovieResponse(BaseModel):
    """Trending movie result"""
    movie_id: int
    title: str
    description: str | None
    poster_url: str | None
    backdrop_url: str | None
    release_year: int | None
    genres: List[str]
    watch_count: int


@router.get("/for-you", response_model=List[RecommendationResponse])
async def get_personalized_recommendations(
    limit: int = Query(20, ge=1, le=50, description="Number of recommendations"),
    strategy: str = Query('auto', description="Recommendation strategy: auto, hybrid, collaborative, or content"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get personalized movie recommendations
    
    Uses machine learning to suggest movies based on:
    - Your watch history
    - Movies you rated highly
    - Similar users' preferences
    - Movie content similarity
    
    **Strategy options:**
    - **auto**: Automatically choose best strategy (default)
    - **hybrid**: Combine collaborative + content-based (70/30)
    - **collaborative**: Based on similar users
    - **content**: Based on movie features
    
    Returns movies you haven't watched with recommendation scores and reasons.
    """
    recommendations = RecommendationService.get_personalized_recommendations(
        user_id=current_user.id,
        db=db,
        limit=limit,
        strategy=strategy
    )
    
    return recommendations


@router.get("/similar/{movie_id}", response_model=List[SimilarMovieResponse])
async def get_similar_movies(
    movie_id: int,
    limit: int = Query(10, ge=1, le=20, description="Number of similar movies"),
    db: Session = Depends(get_db)
):
    """
    Get movies similar to a specific movie
    
    Uses content-based filtering to find movies with:
    - Similar genres
    - Similar themes
    - Similar cast/director
    
    Public endpoint - no authentication required.
    Perfect for "More Like This" sections.
    """
    similar_movies = RecommendationService.get_similar_movies(
        movie_id=movie_id,
        db=db,
        limit=limit
    )
    
    return similar_movies


@router.get("/trending", response_model=List[TrendingMovieResponse])
async def get_trending_movies(
    limit: int = Query(10, ge=1, le=20, description="Number of trending movies"),
    db: Session = Depends(get_db)
):
    """
    Get currently trending movies
    
    Based on recent watch activity (last 7 days).
    Shows what's popular right now.
    
    Public endpoint - no authentication required.
    """
    trending = RecommendationService.get_trending_recommendations(
        db=db,
        limit=limit
    )
    
    return trending


@router.get("/because-you-watched/{movie_id}", response_model=List[RecommendationResponse])
async def get_because_you_watched(
    movie_id: int,
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get recommendations based on a specific movie you watched
    
    "Because you watched [Movie Title]..." style recommendations.
    Combines similar movies with collaborative filtering.
    """
    from app.ml.content_based import ContentBasedFilter
    from app.models.movie import Movie
    
    # Get similar movies
    content_filter = ContentBasedFilter(db)
    similar = content_filter.get_similar_movies(movie_id, top_n=limit)
    
    if not similar:
        return []
    
    # Get source movie title
    source_movie = db.query(Movie).get(movie_id)
    reason = f"Because you watched {source_movie.title}" if source_movie else "Recommended for you"
    
    # Format results
    movie_ids = [mid for mid, _ in similar]
    score_map = {mid: score for mid, score in similar}
    
    movies = db.query(Movie).filter(
        Movie.id.in_(movie_ids),
        Movie.status == 'ready'
    ).all()
    
    results = []
    for movie in movies:
        results.append({
            'movie_id': movie.id,
            'title': movie.title,
            'description': movie.description,
            'poster_url': movie.poster_url,
            'backdrop_url': movie.backdrop_url,
            'release_year': movie.release_year,
            'duration': movie.duration,
            'genres': [g.name for g in movie.genres],
            'recommendation_score': round(score_map[movie.id], 2),
            'reason': reason
        })
    
    return results


@router.post("/refresh")
async def refresh_recommendation_engine(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Refresh recommendation engine
    
    Rebuilds the user-item matrix and recalculates similarities.
    Call this periodically (e.g., daily via cron job).
    
    Note: This can be resource-intensive for large datasets.
    """
    from app.ml.collaborative_filtering import CollaborativeFilter
    from app.ml.content_based import ContentBasedFilter
    
    # Rebuild matrices
    collab_filter = CollaborativeFilter(db)
    collab_filter.build_user_item_matrix()
    
    content_filter = ContentBasedFilter(db)
    content_filter.build_feature_matrix()
    
    return {
        "message": "Recommendation engine refreshed successfully",
        "users": len(collab_filter.user_ids) if collab_filter.user_ids else 0,
        "movies": len(collab_filter.movie_ids) if collab_filter.movie_ids else 0
    }