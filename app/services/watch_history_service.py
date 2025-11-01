"""
Service for tracking user watch history and progress
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status
from app.models.watch_history import WatchHistory, MovieRating
from app.models.movie import Movie
from app.models.user import User
from datetime import datetime


class WatchHistoryService:
    """Handle watch history and progress tracking"""
    
    @staticmethod
    def update_progress(
        user_id: int,
        movie_id: int,
        last_position: int,
        watch_percentage: float,
        completed: bool,
        db: Session
    ) -> WatchHistory:
        """
        Update or create watch progress for a user
        
        Args:
            user_id: User ID
            movie_id: Movie ID
            last_position: Current position in seconds
            watch_percentage: Percentage watched (0-100)
            completed: Whether movie was completed
            db: Database session
        
        Returns:
            Updated WatchHistory record
        """
        # Verify movie exists
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Movie {movie_id} not found"
            )
        
        # Get or create watch history
        watch_history = db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id,
            WatchHistory.movie_id == movie_id
        ).first()
        
        if watch_history:
            # Update existing record
            watch_history.last_position = last_position
            watch_history.watch_percentage = watch_percentage
            watch_history.completed = completed
            watch_history.watched_at = datetime.utcnow()
        else:
            # Create new record
            watch_history = WatchHistory(
                user_id=user_id,
                movie_id=movie_id,
                last_position=last_position,
                watch_percentage=watch_percentage,
                completed=completed
            )
            db.add(watch_history)
        
        db.commit()
        db.refresh(watch_history)
        
        return watch_history
    
    @staticmethod
    def get_user_progress(
        user_id: int,
        movie_id: int,
        db: Session
    ) -> Optional[WatchHistory]:
        """
        Get watch progress for a specific movie
        
        Returns None if user hasn't watched this movie
        """
        return db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id,
            WatchHistory.movie_id == movie_id
        ).first()
    
    @staticmethod
    def get_watch_history(
        user_id: int,
        db: Session,
        limit: int = 50,
        completed_only: bool = False
    ) -> List[WatchHistory]:
        """
        Get user's complete watch history
        
        Args:
            user_id: User ID
            db: Database session
            limit: Max number of records
            completed_only: Only return completed movies
        
        Returns:
            List of watch history records (most recent first)
        """
        query = db.query(WatchHistory).filter(WatchHistory.user_id == user_id)
        
        if completed_only:
            query = query.filter(WatchHistory.completed == True)
        
        return query.order_by(desc(WatchHistory.watched_at)).limit(limit).all()
    
    @staticmethod
    def get_continue_watching(
        user_id: int,
        db: Session,
        limit: int = 10
    ) -> List[WatchHistory]:
        """
        Get movies user started but didn't finish
        
        Perfect for "Continue Watching" section
        """
        return db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id,
            WatchHistory.completed == False,
            WatchHistory.watch_percentage > 5.0  # At least 5% watched
        ).order_by(desc(WatchHistory.watched_at)).limit(limit).all()
    
    @staticmethod
    def delete_history_item(
        user_id: int,
        movie_id: int,
        db: Session
    ) -> bool:
        """Remove a movie from user's watch history"""
        watch_history = db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id,
            WatchHistory.movie_id == movie_id
        ).first()
        
        if not watch_history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watch history not found"
            )
        
        db.delete(watch_history)
        db.commit()
        return True
    
    @staticmethod
    def clear_all_history(user_id: int, db: Session) -> int:
        """Clear all watch history for a user"""
        count = db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id
        ).delete()
        db.commit()
        return count


class RatingService:
    """Handle movie ratings and reviews"""
    
    @staticmethod
    def rate_movie(
        user_id: int,
        movie_id: int,
        rating: int,
        review: Optional[str],
        db: Session
    ) -> MovieRating:
        """
        Rate a movie (1-5 stars)
        
        Args:
            user_id: User ID
            movie_id: Movie ID
            rating: Rating (1-5)
            review: Optional text review
            db: Database session
        """
        # Verify movie exists
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Movie {movie_id} not found"
            )
        
        # Get or create rating
        movie_rating = db.query(MovieRating).filter(
            MovieRating.user_id == user_id,
            MovieRating.movie_id == movie_id
        ).first()
        
        if movie_rating:
            # Update existing rating
            movie_rating.rating = rating
            movie_rating.review = review
            movie_rating.updated_at = datetime.utcnow()
        else:
            # Create new rating
            movie_rating = MovieRating(
                user_id=user_id,
                movie_id=movie_id,
                rating=rating,
                review=review
            )
            db.add(movie_rating)
        
        db.commit()
        db.refresh(movie_rating)
        
        return movie_rating
    
    @staticmethod
    def get_user_rating(
        user_id: int,
        movie_id: int,
        db: Session
    ) -> Optional[MovieRating]:
        """Get user's rating for a specific movie"""
        return db.query(MovieRating).filter(
            MovieRating.user_id == user_id,
            MovieRating.movie_id == movie_id
        ).first()
    
    @staticmethod
    def get_movie_ratings(
        movie_id: int,
        db: Session,
        limit: int = 50
    ) -> List[MovieRating]:
        """Get all ratings for a movie"""
        return db.query(MovieRating).filter(
            MovieRating.movie_id == movie_id
        ).order_by(desc(MovieRating.created_at)).limit(limit).all()
    
    @staticmethod
    def get_average_rating(movie_id: int, db: Session) -> Optional[float]:
        """Calculate average rating for a movie"""
        from sqlalchemy import func
        
        result = db.query(func.avg(MovieRating.rating)).filter(
            MovieRating.movie_id == movie_id
        ).scalar()
        
        return round(result, 2) if result else None
    
    @staticmethod
    def delete_rating(
        user_id: int,
        movie_id: int,
        db: Session
    ) -> bool:
        """Delete user's rating for a movie"""
        rating = db.query(MovieRating).filter(
            MovieRating.user_id == user_id,
            MovieRating.movie_id == movie_id
        ).first()
        
        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rating not found"
            )
        
        db.delete(rating)
        db.commit()
        return True
