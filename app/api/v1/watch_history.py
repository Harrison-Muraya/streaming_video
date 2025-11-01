"""
API endpoints for watch history and progress tracking
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_active_user
from app.schemas.watch_history import (
    WatchProgressUpdate, WatchHistoryResponse, 
    MovieRatingCreate, MovieRatingResponse
)
from app.services.watch_history_service import WatchHistoryService, RatingService
from pydantic import BaseModel

router = APIRouter()

# ============================================
# WATCH PROGRESS ENDPOINTS
# ============================================

@router.post("/progress", response_model=WatchHistoryResponse)
async def update_watch_progress(
    progress_data: WatchProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update watch progress for a movie
    
    Call this endpoint periodically while user is watching:
    - Every 30 seconds during playback
    - When user pauses
    - When user stops/exits
    
    **Fields:**
    - **movie_id**: ID of the movie being watched
    - **last_position**: Current playback position in seconds
    - **watch_percentage**: Percentage of movie watched (0-100)
    - **completed**: True if user finished the movie
    """
    watch_history = WatchHistoryService.update_progress(
        user_id=current_user.id,
        movie_id=progress_data.movie_id,
        last_position=progress_data.last_position,
        watch_percentage=progress_data.watch_percentage,
        completed=progress_data.completed,
        db=db
    )
    return watch_history


@router.get("/progress/{movie_id}", response_model=WatchHistoryResponse | None)
async def get_watch_progress(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get watch progress for a specific movie
    
    Returns None if user hasn't watched this movie yet
    Use this to resume playback from last position
    """
    progress = WatchHistoryService.get_user_progress(
        user_id=current_user.id,
        movie_id=movie_id,
        db=db
    )
    return progress


@router.get("/history", response_model=List[WatchHistoryResponse])
async def get_watch_history(
    completed_only: bool = Query(False, description="Only show completed movies"),
    limit: int = Query(50, ge=1, le=100, description="Max number of results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get user's complete watch history
    
    Shows all movies user has watched, ordered by most recent
    """
    history = WatchHistoryService.get_watch_history(
        user_id=current_user.id,
        db=db,
        limit=limit,
        completed_only=completed_only
    )
    return history


@router.get("/continue-watching", response_model=List[WatchHistoryResponse])
async def get_continue_watching(
    limit: int = Query(10, ge=1, le=50, description="Max number of results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get movies user started but didn't finish
    
    Perfect for "Continue Watching" section on home screen
    Only includes movies watched at least 5%
    """
    continue_watching = WatchHistoryService.get_continue_watching(
        user_id=current_user.id,
        db=db,
        limit=limit
    )
    return continue_watching


@router.delete("/history/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_item(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Remove a specific movie from watch history
    """
    WatchHistoryService.delete_history_item(
        user_id=current_user.id,
        movie_id=movie_id,
        db=db
    )
    return None


@router.delete("/history", status_code=status.HTTP_200_OK)
async def clear_watch_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Clear all watch history for current user
    """
    count = WatchHistoryService.clear_all_history(
        user_id=current_user.id,
        db=db
    )
    return {"message": f"Cleared {count} items from watch history"}


# ============================================
# RATING ENDPOINTS
# ============================================

@router.post("/ratings", response_model=MovieRatingResponse, status_code=status.HTTP_201_CREATED)
async def rate_movie(
    rating_data: MovieRatingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Rate a movie (1-5 stars)
    
    Optionally include a text review
    """
    rating = RatingService.rate_movie(
        user_id=current_user.id,
        movie_id=rating_data.movie_id,
        rating=rating_data.rating,
        review=rating_data.review,
        db=db
    )
    return rating


@router.get("/ratings/{movie_id}/my-rating", response_model=MovieRatingResponse | None)
async def get_my_rating(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user's rating for a specific movie
    
    Returns None if user hasn't rated this movie
    """
    rating = RatingService.get_user_rating(
        user_id=current_user.id,
        movie_id=movie_id,
        db=db
    )
    return rating


@router.get("/ratings/{movie_id}", response_model=List[MovieRatingResponse])
async def get_movie_ratings(
    movie_id: int,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get all ratings for a specific movie
    
    Public endpoint - no authentication required
    """
    ratings = RatingService.get_movie_ratings(
        movie_id=movie_id,
        db=db,
        limit=limit
    )
    return ratings


class AverageRatingResponse(BaseModel):
    movie_id: int
    average_rating: float | None
    total_ratings: int


@router.get("/ratings/{movie_id}/average", response_model=AverageRatingResponse)
async def get_average_rating(
    movie_id: int,
    db: Session = Depends(get_db)
):
    """
    Get average rating for a movie
    
    Public endpoint - no authentication required
    """
    from app.models.watch_history import MovieRating
    
    avg_rating = RatingService.get_average_rating(movie_id, db)
    count = db.query(MovieRating).filter(MovieRating.movie_id == movie_id).count()
    
    return {
        "movie_id": movie_id,
        "average_rating": avg_rating,
        "total_ratings": count
    }


@router.delete("/ratings/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_rating(
    movie_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete current user's rating for a movie
    """
    RatingService.delete_rating(
        user_id=current_user.id,
        movie_id=movie_id,
        db=db
    )
    return None