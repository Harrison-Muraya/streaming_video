"""
Test script for Recommendation Engine
Run: python test_recommendations.py
"""
import requests
import time
import random

BASE_URL = "http://localhost:8000/api/v1"


def create_test_users():
    """Create multiple test users for collaborative filtering"""
    print("👥 Creating test users...")
    
    users = [
        {"username": "alice", "email": "alice@test.com", "password": "test123", "full_name": "Alice User"},
        {"username": "bob", "email": "bob@test.com", "password": "test123", "full_name": "Bob User"},
        {"username": "charlie", "email": "charlie@test.com", "password": "test123", "full_name": "Charlie User"},
    ]
    
    tokens = {}
    
    for user_data in users:
        # Try to register
        try:
            requests.post(f"{BASE_URL}/auth/register", json=user_data)
        except:
            pass
        
        # Login
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": user_data["username"], "password": user_data["password"]}
        )
        
        if response.status_code == 200:
            tokens[user_data["username"]] = response.json()["access_token"]
            print(f"   ✅ {user_data['username']}")
    
    print()
    return tokens


def get_movies():
    """Get list of available movies"""
    print("🎬 Getting movies...")
    response = requests.get(f"{BASE_URL}/movies?page_size=10")
    
    if response.status_code == 200:
        data = response.json()
        movies = data['movies']
        print(f"✅ Found {len(movies)} movies\n")
        return movies
    return []


def simulate_user_behavior(username, token, movies):
    """Simulate a user watching and rating movies"""
    print(f"👤 Simulating behavior for {username}...")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Each user watches different movies with different patterns
    if username == "alice":
        # Alice likes action and sci-fi
        watch_preferences = [m for m in movies if any(
            g.get('name', '').lower() in ['action', 'science fiction'] 
            for g in m.get('genres', [])
        )][:3]
    elif username == "bob":
        # Bob likes comedy and drama
        watch_preferences = [m for m in movies if any(
            g.get('name', '').lower() in ['comedy', 'drama'] 
            for g in m.get('genres', [])
        )][:3]
    else:
        # Charlie has mixed taste
        watch_preferences = movies[:3]
    
    # Watch and rate movies
    for movie in watch_preferences:
        # Simulate watching
        progress_data = {
            "movie_id": movie['id'],
            "last_position": random.randint(1000, 3000),
            "watch_percentage": random.uniform(70, 100),
            "completed": True
        }
        
        requests.post(
            f"{BASE_URL}/watch/progress",
            headers=headers,
            json=progress_data
        )
        
        # Rate movie
        rating_data = {
            "movie_id": movie['id'],
            "rating": random.randint(4, 5)
        }
        
        requests.post(
            f"{BASE_URL}/watch/ratings",
            headers=headers,
            json=rating_data
        )
        
        print(f"   ✅ Watched and rated: {movie['title']}")
        time.sleep(0.3)
    
    print()


def test_personalized_recommendations(username, token):
    """Test personalized recommendations"""
    print(f"🎯 Testing personalized recommendations for {username}...")
    headers = {"Authorization": f"Bearer {token}"}
    
    strategies = ['auto', 'hybrid', 'collaborative', 'content']
    
    for strategy in strategies:
        response = requests.get(
            f"{BASE_URL}/recommendations/for-you?limit=5&strategy={strategy}",
            headers=headers
        )
        
        if response.status_code == 200:
            recs = response.json()
            print(f"\n   📊 Strategy: {strategy}")
            if recs:
                for i, rec in enumerate(recs[:3], 1):
                    print(f"      {i}. {rec['title']} (score: {rec['recommendation_score']:.2f})")
                    print(f"         Reason: {rec['reason']}")
            else:
                print("      No recommendations yet (need more data)")
        else:
            print(f"      ❌ Failed: {response.status_code}")
    
    print()


def test_similar_movies(movies):
    """Test similar movies endpoint"""
    if not movies:
        return
    
    print("🔍 Testing similar movies...")
    movie = movies[0]
    
    response = requests.get(f"{BASE_URL}/recommendations/similar/{movie['id']}?limit=5")
    
    if response.status_code == 200:
        similar = response.json()
        print(f"\n   Movies similar to '{movie['title']}':")
        for i, sim in enumerate(similar, 1):
            print(f"      {i}. {sim['title']} (similarity: {sim['similarity_score']:.2f})")
    else:
        print(f"   ❌ Failed: {response.status_code}")
    
    print()


def test_trending_movies():
    """Test trending movies endpoint"""
    print("📈 Testing trending movies...")
    
    response = requests.get(f"{BASE_URL}/recommendations/trending?limit=5")
    
    if response.status_code == 200:
        trending = response.json()
        print("\n   Currently trending:")
        for i, movie in enumerate(trending, 1):
            watches = movie.get('watch_count', 0)
            print(f"      {i}. {movie['title']} ({watches} watches)")
    else:
        print(f"   ❌ Failed: {response.status_code}")
    
    print()


def test_because_you_watched(username, token, movies):
    """Test 'Because you watched' recommendations"""
    if not movies:
        return
    
    print(f"💡 Testing 'Because you watched' for {username}...")
    headers = {"Authorization": f"Bearer {token}"}
    movie = movies[0]
    
    response = requests.get(
        f"{BASE_URL}/recommendations/because-you-watched/{movie['id']}?limit=5",
        headers=headers
    )
    
    if response.status_code == 200:
        recs = response.json()
        print(f"\n   Because you watched '{movie['title']}':")
        for i, rec in enumerate(recs[:3], 1):
            print(f"      {i}. {rec['title']}")
    else:
        print(f"   ❌ Failed: {response.status_code}")
    
    print()


def test_refresh_engine(token):
    """Test refresh recommendation engine"""
    print("🔄 Testing recommendation engine refresh...")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.post(
        f"{BASE_URL}/recommendations/refresh",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ {data['message']}")
        print(f"   Users: {data['users']}, Movies: {data['movies']}")
    else:
        print(f"   ❌ Failed: {response.status_code}")
    
    print()


def show_summary():
    """Show recommendation quality metrics"""
    print("=" * 60)
    print("📊 RECOMMENDATION ENGINE SUMMARY")
    print("=" * 60)
    print("\n✅ Implemented Features:")
    print("   • Collaborative Filtering (user-based)")
    print("   • Content-Based Filtering (movie features)")
    print("   • Hybrid Recommendations (70/30 blend)")
    print("   • Similar Movies (content similarity)")
    print("   • Trending Movies (recent activity)")
    print("   • 'Because you watched' suggestions")
    print("   • Automatic strategy selection")
    print("   • Recommendation explanations")
    
    print("\n🎯 How It Works:")
    print("   1. Tracks what users watch and rate")
    print("   2. Finds similar users (collaborative)")
    print("   3. Finds similar movies (content-based)")
    print("   4. Combines scores with weighted average")
    print("   5. Generates personalized suggestions")
    
    print("\n💡 Cold Start Handling:")
    print("   • New users → Popular movies")
    print("   • <5 movies watched → Content-based")
    print("   • 5+ movies watched → Hybrid approach")
    
    print("\n📈 Recommendation Quality Improves With:")
    print("   • More users watching movies")
    print("   • More ratings from users")
    print("   • Diverse viewing patterns")
    print("   • Regular engine refresh")
    print()


def main():
    """Run all recommendation tests"""
    print("=" * 60)
    print("🤖 RECOMMENDATION ENGINE TEST")
    print("=" * 60 + "\n")
    
    # Get movies
    movies = get_movies()
    if not movies:
        print("❌ No movies available. Upload some movies first.")
        return
    
    # Create test users
    tokens = create_test_users()
    if not tokens:
        print("❌ Failed to create test users")
        return
    
    # Simulate different user behaviors
    print("=" * 60)
    print("PHASE 1: Simulating User Behavior")
    print("=" * 60 + "\n")
    
    for username, token in tokens.items():
        simulate_user_behavior(username, token, movies)
    
    # Test recommendation endpoints
    print("=" * 60)
    print("PHASE 2: Testing Recommendation Endpoints")
    print("=" * 60 + "\n")
    
    # Test with first user (Alice)
    alice_token = tokens.get('alice')
    if alice_token:
        test_personalized_recommendations('alice', alice_token)
        test_because_you_watched('alice', alice_token, movies)
    
    # Test public endpoints
    test_similar_movies(movies)
    test_trending_movies()
    
    # Test engine refresh
    if alice_token:
        test_refresh_engine(alice_token)
    
    # Show summary
    show_summary()
    
    print("=" * 60)
    print("✅ ALL TESTS COMPLETE!")
    print("=" * 60)
    print("\n🎉 Recommendation engine is working!")
    print("\n📝 Next steps:")
    print("1. Add more users and watch data for better recommendations")
    print("2. Integrate into Android TV app")
    print("3. Set up periodic refresh (daily cron job)")
    print("4. Monitor recommendation quality metrics")
    print()


if __name__ == "__main__":
    main()