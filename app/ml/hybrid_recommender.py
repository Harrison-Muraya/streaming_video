"""
Hybrid recommender combining collaborative and content-based filtering
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from app.ml.collaborative_filtering import CollaborativeFilter
from app.ml.content_based import ContentBasedFilter
from app.models.movie import Movie


class HybridRecommender:
    """
    Hybrid recommendation system
    Combines collaborative filtering and content-based filtering
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.collaborative = CollaborativeFilter(db)
        self.content_based = ContentBasedFilter(db)
        
        # Weights for combining scores
        self.collaborative_weight = 0.7
        self.content_weight = 0.3
    
    def get_recommendations(
        self,
        user_id: int,
        top_n: int = 20,
        strategy: str = 'hybrid'
    ) -> List[Dict]:
        """
        Get personalized recommendations for user
        
        Args:
            user_id: Target user ID
            top_n: Number of recommendations
            strategy: 'hybrid', 'collaborative', 'content', or 'auto'
        
        Returns:
            List of movie dictionaries with recommendation scores
        """
        if strategy == 'auto':
            # Decide strategy based on user data
            from app.models.watch_history import WatchHistory
            watch_count = self.db.query(WatchHistory).filter(
                WatchHistory.user_id == user_id
            ).count()
            
            if watch_count < 5:
                strategy = 'content'  # Cold start - use content-based
            else:
                strategy = 'hybrid'  # Established user - use hybrid
        
        if strategy == 'collaborative':
            return self._get_collaborative_recommendations(user_id, top_n)
        elif strategy == 'content':
            return self._get_content_recommendations(user_id, top_n)
        else:  # hybrid
            return self._get_hybrid_recommendations(user_id, top_n)
    
    def _get_collaborative_recommendations(
        self,
        user_id: int,
        top_n: int
    ) -> List[Dict]:
        """Get recommendations using collaborative filtering only"""
        recommendations = self.collaborative.recommend_for_user(user_id, top_n)
        return self._format_recommendations(recommendations)
    
    def _get_content_recommendations(
        self,
        user_id: int,
        top_n: int
    ) -> List[Dict]:
        """Get recommendations using content-based filtering only"""
        recommendations = self.content_based.recommend_based_on_history(user_id, top_n)
        return self._format_recommendations(recommendations)
    
    def _get_hybrid_recommendations(
        self,
        user_id: int,
        top_n: int
    ) -> List[Dict]:
        """
        Combine collaborative and content-based recommendations
        Uses weighted average of scores
        """
        # Get recommendations from both methods
        collab_recs = self.collaborative.recommend_for_user(user_id, top_n * 2)
        content_recs = self.content_based.recommend_based_on_history(user_id, top_n * 2)
        
        # Combine scores
        combined_scores = {}
        
        # Add collaborative scores
        for movie_id, score in collab_recs:
            combined_scores[movie_id] = score * self.collaborative_weight
        
        # Add content-based scores
        for movie_id, score in content_recs:
            if movie_id in combined_scores:
                combined_scores[movie_id] += score * self.content_weight
            else:
                combined_scores[movie_id] = score * self.content_weight
        
        # Sort by combined score
        recommendations = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        return self._format_recommendations(recommendations)
    
    def _format_recommendations(
        self,
        recommendations: List[tuple]
    ) -> List[Dict]:
        """
        Format recommendations with full movie data
        
        Args:
            recommendations: List of (movie_id, score) tuples
        
        Returns:
            List of dictionaries with movie data and scores
        """
        if not recommendations:
            return []
        
        movie_ids = [movie_id for movie_id, _ in recommendations]
        score_map = {movie_id: score for movie_id, score in recommendations}
        
        # Get movie details
        movies = self.db.query(Movie).filter(
            Movie.id.in_(movie_ids),
            Movie.status == 'ready'
        ).all()
        
        # Format results
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
                'reason': self._generate_reason(movie.id, user_id)
            })
        
        # Sort by score
        results.sort(key=lambda x: x['recommendation_score'], reverse=True)
        
        return results
    
    def _generate_reason(self, movie_id: int, user_id: int) -> str:
        """
        Generate explanation for why movie was recommended
        """
        # Get similar movies user has watched
        from app.models.watch_history import WatchHistory
        
        watched = self.db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id
        ).order_by(WatchHistory.watched_at.desc()).limit(5).all()
        
        if not watched:
            return "Popular with other users"
        
        # Find if recommended movie is similar to watched movies
        for watch in watched:
            similar = self.content_based.get_similar_movies(watch.movie_id, top_n=10)
            if any(mid == movie_id for mid, _ in similar):
                watched_movie = self.db.query(Movie).get(watch.movie_id)
                return f"Because you watched {watched_movie.title}"
        
        return "Recommended based on your viewing history"