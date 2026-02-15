"""
Service layer for recommendation system
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from app.ml.hybrid_recommender import HybridRecommender
from app.ml.collaborative_filtering import CollaborativeFilter
from app.ml.content_based import ContentBasedFilter


class RecommendationService:
    """Service for generating movie recommendations"""
    
    @staticmethod
    def get_personalized_recommendations(
        user_id: int,
        db: Session,
        limit: int = 20,
        strategy: str = 'auto'
    ) -> List[Dict]:
        """
        Get personalized recommendations for user
        
        Args:
            user_id: User ID
            db: Database session
            limit: Number of recommendations
            strategy: 'auto', 'hybrid', 'collaborative', or 'content'
        
        Returns:
            List of recommended movies with scores
        """
        recommender = HybridRecommender(db)
        recommendations = recommender.get_recommendations(
            user_id=user_id,
            top_n=limit,
            strategy=strategy
        )
        
        return recommendations
    
    @staticmethod
    def get_similar_movies(
        movie_id: int,
        db: Session,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get movies similar to a specific movie
        
        Uses content-based filtering
        """
        content_filter = ContentBasedFilter(db)
        similar = content_filter.get_similar_movies(movie_id, top_n=limit)
        
        # Format results
        from app.models.movie import Movie
        
        if not similar:
            return []
        
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
                'release_year': movie.release_year,
                'genres': [g.name for g in movie.genres],
                'similarity_score': round(score_map[movie.id], 2)
            })
        
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return results
    
    @staticmethod
    def get_trending_recommendations(
        db: Session,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get trending movies based on recent activity
        """
        from app.models.movie import Movie
        from app.models.watch_history import WatchHistory
        from sqlalchemy import func
        from datetime import datetime, timedelta
        
        # Get most watched movies in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        trending = db.query(
            WatchHistory.movie_id,
            func.count(WatchHistory.id).label('watch_count')
        ).filter(
            WatchHistory.watched_at >= week_ago
        ).group_by(
            WatchHistory.movie_id
        ).order_by(
            func.count(WatchHistory.id).desc()
        ).limit(limit).all()
        
        if not trending:
            # Fallback to view count
            movies = db.query(Movie).filter(
                Movie.status == 'ready'
            ).order_by(Movie.view_count.desc()).limit(limit).all()
            
            return [{
                'movie_id': m.id,
                'title': m.title,
                'poster_url': m.poster_url,
                'watch_count': m.view_count
            } for m in movies]
        
        movie_ids = [t[0] for t in trending]
        watch_counts = {t[0]: t[1] for t in trending}
        
        movies = db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        
        results = []
        for movie in movies:
            results.append({
                'movie_id': movie.id,
                'title': movie.title,
                'description': movie.description,
                'poster_url': movie.poster_url,
                'backdrop_url': movie.backdrop_url,
                'release_year': movie.release_year,
                'genres': [g.name for g in movie.genres],
                'watch_count': watch_counts[movie.id]
            })
        
        results.sort(key=lambda x: x['watch_count'], reverse=True)
        return results
