"""
Collaborative Filtering for movie recommendations
Uses user-item matrix and similarity calculations
"""
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict
from sqlalchemy.orm import Session
from sklearn.metrics.pairwise import cosine_similarity
from app.models.watch_history import WatchHistory, MovieRating
from app.models.movie import Movie


class CollaborativeFilter:
    """Collaborative filtering recommendation engine"""
    
    def __init__(self, db: Session):
        self.db = db
        self.user_item_matrix = None
        self.user_ids = []
        self.movie_ids = []
        
    def build_user_item_matrix(self) -> pd.DataFrame:
        """
        Build user-item interaction matrix from watch history
        
        Returns:
            DataFrame with users as rows, movies as columns, ratings as values
        """
        # Get all watch history
        watch_data = self.db.query(
            WatchHistory.user_id,
            WatchHistory.movie_id,
            WatchHistory.watch_percentage,
            WatchHistory.completed
        ).all()
        
        if not watch_data:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(watch_data, columns=['user_id', 'movie_id', 'watch_percentage', 'completed'])
        
        # Calculate implicit rating from watch percentage
        # 0-25% = 1 star, 25-50% = 2 stars, 50-75% = 3 stars, 75-90% = 4 stars, 90%+ = 5 stars
        def calculate_implicit_rating(row):
            percentage = row['watch_percentage']
            if percentage >= 90:
                return 5
            elif percentage >= 75:
                return 4
            elif percentage >= 50:
                return 3
            elif percentage >= 25:
                return 2
            else:
                return 1
        
        df['implicit_rating'] = df.apply(calculate_implicit_rating, axis=1)
        
        # Also incorporate explicit ratings if available
        ratings_data = self.db.query(
            MovieRating.user_id,
            MovieRating.movie_id,
            MovieRating.rating
        ).all()
        
        if ratings_data:
            ratings_df = pd.DataFrame(ratings_data, columns=['user_id', 'movie_id', 'rating'])
            # Merge with watch data, preferring explicit ratings
            df = df.merge(ratings_df, on=['user_id', 'movie_id'], how='left')
            df['final_rating'] = df['rating'].fillna(df['implicit_rating'])
        else:
            df['final_rating'] = df['implicit_rating']
        
        # Create pivot table (user-item matrix)
        matrix = df.pivot_table(
            index='user_id',
            columns='movie_id',
            values='final_rating',
            fill_value=0
        )
        
        self.user_item_matrix = matrix
        self.user_ids = matrix.index.tolist()
        self.movie_ids = matrix.columns.tolist()
        
        return matrix
    
    def calculate_user_similarity(self) -> np.ndarray:
        """
        Calculate similarity between users using cosine similarity
        
        Returns:
            Similarity matrix (users x users)
        """
        if self.user_item_matrix is None:
            self.build_user_item_matrix()
        
        if self.user_item_matrix.empty:
            return np.array([])
        
        # Calculate cosine similarity between users
        similarity_matrix = cosine_similarity(self.user_item_matrix)
        
        return similarity_matrix
    
    def get_similar_users(self, user_id: int, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Find K most similar users to target user
        
        Args:
            user_id: Target user ID
            top_k: Number of similar users to return
        
        Returns:
            List of (user_id, similarity_score) tuples
        """
        if self.user_item_matrix is None:
            self.build_user_item_matrix()
        
        if user_id not in self.user_ids:
            return []
        
        similarity_matrix = self.calculate_user_similarity()
        user_idx = self.user_ids.index(user_id)
        
        # Get similarity scores for target user
        user_similarities = similarity_matrix[user_idx]
        
        # Get indices of top K similar users (excluding self)
        similar_indices = np.argsort(user_similarities)[::-1][1:top_k+1]
        
        # Return user IDs and their similarity scores
        similar_users = [
            (self.user_ids[idx], user_similarities[idx])
            for idx in similar_indices
        ]
        
        return similar_users
    
    def recommend_for_user(
        self,
        user_id: int,
        top_n: int = 10,
        exclude_watched: bool = True
    ) -> List[Tuple[int, float]]:
        """
        Generate movie recommendations for a user
        
        Args:
            user_id: Target user ID
            top_n: Number of recommendations to return
            exclude_watched: Exclude movies user has already watched
        
        Returns:
            List of (movie_id, predicted_rating) tuples
        """
        if self.user_item_matrix is None:
            self.build_user_item_matrix()
        
        if user_id not in self.user_ids:
            # New user - return popular movies
            return self._get_popular_movies(top_n)
        
        # Get similar users
        similar_users = self.get_similar_users(user_id, top_k=20)
        
        if not similar_users:
            return self._get_popular_movies(top_n)
        
        # Get movies watched by target user
        user_idx = self.user_ids.index(user_id)
        user_watched = set(
            movie_id for movie_id, rating in 
            zip(self.movie_ids, self.user_item_matrix.iloc[user_idx])
            if rating > 0
        )
        
        # Calculate weighted ratings from similar users
        movie_scores = {}
        total_similarity = sum(sim for _, sim in similar_users)
        
        for similar_user_id, similarity in similar_users:
            similar_user_idx = self.user_ids.index(similar_user_id)
            
            for movie_idx, movie_id in enumerate(self.movie_ids):
                # Skip if user already watched
                if exclude_watched and movie_id in user_watched:
                    continue
                
                rating = self.user_item_matrix.iloc[similar_user_idx, movie_idx]
                
                if rating > 0:
                    if movie_id not in movie_scores:
                        movie_scores[movie_id] = 0
                    
                    # Weighted by similarity
                    movie_scores[movie_id] += rating * similarity
        
        # Normalize scores
        if total_similarity > 0:
            movie_scores = {
                movie_id: score / total_similarity
                for movie_id, score in movie_scores.items()
            }
        
        # Sort by score and return top N
        recommendations = sorted(
            movie_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        return recommendations
    
    def _get_popular_movies(self, top_n: int = 10) -> List[Tuple[int, float]]:
        """
        Get popular movies (fallback for cold start)
        
        Returns movies with highest view counts and ratings
        """
        movies = self.db.query(Movie).filter(
            Movie.status == 'ready'
        ).order_by(
            Movie.view_count.desc()
        ).limit(top_n).all()
        
        return [(movie.id, 5.0) for movie in movies]
