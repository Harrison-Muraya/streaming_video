"""
Content-based filtering using movie attributes
"""
from typing import List, Tuple
from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from app.models.movie import Movie
from app.models.watch_history import WatchHistory


class ContentBasedFilter:
    """Content-based recommendation using movie features"""
    
    def __init__(self, db: Session):
        self.db = db
        self.movies_df = None
        self.tfidf_matrix = None
        self.movie_ids = []
        
    def build_feature_matrix(self):
        """
        Build TF-IDF matrix from movie features
        Combines: genres, description, director, cast
        """
        # Get all movies
        movies = self.db.query(Movie).filter(Movie.status == 'ready').all()
        
        if not movies:
            return
        
        movie_data = []
        for movie in movies:
            # Combine features into text
            genres = ' '.join([g.name for g in movie.genres])
            description = movie.description or ''
            director = movie.director or ''
            cast = movie.cast or ''
            
            # Create feature string
            features = f"{genres} {genres} {description} {director} {cast}"
            
            movie_data.append({
                'id': movie.id,
                'features': features
            })
        
        self.movie_ids = [m['id'] for m in movie_data]
        feature_texts = [m['features'] for m in movie_data]
        
        # Create TF-IDF matrix
        vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        self.tfidf_matrix = vectorizer.fit_transform(feature_texts)
    
    def get_similar_movies(
        self,
        movie_id: int,
        top_n: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Find movies similar to given movie
        
        Args:
            movie_id: Target movie ID
            top_n: Number of similar movies to return
        
        Returns:
            List of (movie_id, similarity_score) tuples
        """
        if self.tfidf_matrix is None:
            self.build_feature_matrix()
        
        if movie_id not in self.movie_ids:
            return []
        
        movie_idx = self.movie_ids.index(movie_id)
        
        # Calculate similarity with all other movies
        movie_vector = self.tfidf_matrix[movie_idx]
        similarities = cosine_similarity(movie_vector, self.tfidf_matrix).flatten()
        
        # Get top N similar movies (excluding self)
        similar_indices = similarities.argsort()[::-1][1:top_n+1]
        
        similar_movies = [
            (self.movie_ids[idx], similarities[idx])
            for idx in similar_indices
        ]
        
        return similar_movies
    
    def recommend_based_on_history(
        self,
        user_id: int,
        top_n: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Recommend movies based on user's watch history
        
        Finds movies similar to what user has watched and liked
        """
        # Get user's highly rated movies (watch percentage > 70%)
        watched_movies = self.db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id,
            WatchHistory.watch_percentage > 70
        ).order_by(WatchHistory.watched_at.desc()).limit(10).all()
        
        if not watched_movies:
            return []
        
        # Get similar movies for each watched movie
        all_recommendations = {}
        
        for watch in watched_movies:
            similar = self.get_similar_movies(watch.movie_id, top_n=5)
            
            for movie_id, score in similar:
                # Weight by how much user liked the source movie
                weight = watch.watch_percentage / 100.0
                weighted_score = score * weight
                
                if movie_id not in all_recommendations:
                    all_recommendations[movie_id] = 0
                
                all_recommendations[movie_id] += weighted_score
        
        # Remove already watched movies
        watched_ids = {w.movie_id for w in self.db.query(WatchHistory.movie_id).filter(
            WatchHistory.user_id == user_id
        ).all()}
        
        recommendations = [
            (movie_id, score)
            for movie_id, score in all_recommendations.items()
            if movie_id not in watched_ids
        ]
        
        # Sort by score and return top N
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations[:top_n]