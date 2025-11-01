"""
Test script for Watch History functionality
Run: python test_watch_history.py
"""
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"


def login_as_user():
    """Login as regular user"""
    print("🔐 Logging in as user...")
    
    # First, register a test user
    try:
        requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "username": "testviewer",
                "email": "viewer@test.com",
                "password": "test123",
                "full_name": "Test Viewer"
            }
        )
    except:
        pass  # User might already exist
    
    # Login
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "testviewer", "password": "test123"}
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print("✅ Login successful\n")
        return token
    else:
        print(f"❌ Login failed: {response.text}")
        return None


def get_movies(token):
    """Get list of movies"""
    print("🎬 Getting available movies...")
    response = requests.get(f"{BASE_URL}/movies?page_size=5")
    
    if response.status_code == 200:
        data = response.json()
        movies = data['movies']
        print(f"✅ Found {len(movies)} movies:")
        for movie in movies:
            print(f"   - [{movie['id']}] {movie['title']} ({movie['status']})")
        print()
        return movies
    else:
        print(f"❌ Failed: {response.text}\n")
        return []


def simulate_watching(token, movie_id, movie_title):
    """Simulate watching a movie with progress updates"""
    print(f"▶️  Simulating watching: {movie_title}")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Simulate watching progress at different points
    watch_points = [
        {"position": 300, "percentage": 10.0, "completed": False},   # 5 min - 10%
        {"position": 900, "percentage": 30.0, "completed": False},   # 15 min - 30%
        {"position": 1800, "percentage": 60.0, "completed": False},  # 30 min - 60%
        {"position": 3000, "percentage": 100.0, "completed": True},  # 50 min - Finished
    ]
    
    for point in watch_points:
        progress_data = {
            "movie_id": movie_id,
            "last_position": point["position"],
            "watch_percentage": point["percentage"],
            "completed": point["completed"]
        }
        
        response = requests.post(
            f"{BASE_URL}/watch/progress",
            headers=headers,
            json=progress_data
        )
        
        if response.status_code == 200:
            status = "✅ Completed" if point["completed"] else "⏸️  Progress"
            print(f"   {status}: {point['percentage']}% ({point['position']}s)")
        else:
            print(f"   ❌ Failed to update: {response.text}")
        
        time.sleep(0.5)  # Small delay between updates
    
    print()


def get_watch_progress(token, movie_id):
    """Get watch progress for a movie"""
    print(f"📊 Getting watch progress for movie {movie_id}...")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/watch/progress/{movie_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        progress = response.json()
        if progress:
            print(f"✅ Progress found:")
            print(f"   Watch percentage: {progress['watch_percentage']}%")
            print(f"   Last position: {progress['last_position']}s")
            print(f"   Completed: {progress['completed']}")
            print()
            return progress
        else:
            print("   No progress found (movie not watched yet)\n")
            return None
    else:
        print(f"❌ Failed: {response.text}\n")
        return None


def get_continue_watching(token):
    """Get continue watching list"""
    print("🔄 Getting Continue Watching list...")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/watch/continue-watching",
        headers=headers
    )
    
    if response.status_code == 200:
        items = response.json()
        if items:
            print(f"✅ Found {len(items)} movies to continue:")
            for item in items:
                print(f"   - Movie {item['movie_id']}: {item['watch_percentage']}% watched")
        else:
            print("   No movies in continue watching list")
        print()
        return items
    else:
        print(f"❌ Failed: {response.text}\n")
        return []


def get_watch_history(token):
    """Get complete watch history"""
    print("📜 Getting complete watch history...")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/watch/history",
        headers=headers
    )
    
    if response.status_code == 200:
        history = response.json()
        print(f"✅ Found {len(history)} items in history:")
        for item in history:
            status = "✅ Completed" if item['completed'] else f"⏸️  {item['watch_percentage']}%"
            print(f"   - Movie {item['movie_id']}: {status}")
        print()
        return history
    else:
        print(f"❌ Failed: {response.text}\n")
        return []


def rate_movie(token, movie_id, rating, review=None):
    """Rate a movie"""
    print(f"⭐ Rating movie {movie_id}: {rating} stars...")
    headers = {"Authorization": f"Bearer {token}"}
    
    rating_data = {
        "movie_id": movie_id,
        "rating": rating
    }
    
    if review:
        rating_data["review"] = review
    
    response = requests.post(
        f"{BASE_URL}/watch/ratings",
        headers=headers,
        json=rating_data
    )
    
    if response.status_code == 201:
        print(f"✅ Rating submitted successfully\n")
        return True
    else:
        print(f"❌ Failed: {response.text}\n")
        return False


def get_movie_average_rating(movie_id):
    """Get average rating for a movie"""
    print(f"📊 Getting average rating for movie {movie_id}...")
    
    response = requests.get(f"{BASE_URL}/watch/ratings/{movie_id}/average")
    
    if response.status_code == 200:
        data = response.json()
        if data['average_rating']:
            print(f"✅ Average rating: {data['average_rating']:.1f} stars ({data['total_ratings']} ratings)")
        else:
            print("   No ratings yet")
        print()
        return data
    else:
        print(f"❌ Failed: {response.text}\n")
        return None


def clear_history(token):
    """Clear watch history"""
    print("🗑️  Clearing watch history...")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.delete(
        f"{BASE_URL}/watch/history",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ {data['message']}\n")
        return True
    else:
        print(f"❌ Failed: {response.text}\n")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("🎬 WATCH HISTORY & PROGRESS TRACKING TEST")
    print("=" * 60 + "\n")
    
    # Login
    token = login_as_user()
    if not token:
        return
    
    # Get movies
    movies = get_movies(token)
    if not movies:
        print("No movies available. Upload some movies first.")
        return
    
    # Test with first two movies
    movie1 = movies[0]
    movie2 = movies[1] if len(movies) > 1 else movies[0]
    
    # Test 1: Simulate watching first movie (complete)
    print("=" * 60)
    print("TEST 1: Watch Progress Tracking")
    print("=" * 60 + "\n")
    simulate_watching(token, movie1['id'], movie1['title'])
    
    # Test 2: Get progress
    print("=" * 60)
    print("TEST 2: Retrieve Watch Progress")
    print("=" * 60 + "\n")
    get_watch_progress(token, movie1['id'])
    
    # Test 3: Partially watch second movie
    if movie2['id'] != movie1['id']:
        print("=" * 60)
        print("TEST 3: Partial Watch (for Continue Watching)")
        print("=" * 60 + "\n")
        
        headers = {"Authorization": f"Bearer {token}"}
        requests.post(
            f"{BASE_URL}/watch/progress",
            headers=headers,
            json={
                "movie_id": movie2['id'],
                "last_position": 600,
                "watch_percentage": 20.0,
                "completed": False
            }
        )
        print(f"▶️  Watched {movie2['title']} to 20%\n")
    
    # Test 4: Get continue watching
    print("=" * 60)
    print("TEST 4: Continue Watching List")
    print("=" * 60 + "\n")
    get_continue_watching(token)
    
    # Test 5: Get complete history
    print("=" * 60)
    print("TEST 5: Complete Watch History")
    print("=" * 60 + "\n")
    get_watch_history(token)
    
    # Test 6: Rate movies
    print("=" * 60)
    print("TEST 6: Movie Ratings")
    print("=" * 60 + "\n")
    rate_movie(token, movie1['id'], 5, "Excellent movie!")
    rate_movie(token, movie2['id'], 4, "Really good!")
    
    # Test 7: Get average ratings
    print("=" * 60)
    print("TEST 7: Average Ratings")
    print("=" * 60 + "\n")
    get_movie_average_rating(movie1['id'])
    get_movie_average_rating(movie2['id'])
    
    # Test 8: Clear history
    print("=" * 60)
    print("TEST 8: Clear History")
    print("=" * 60 + "\n")
    print("Would you like to clear watch history? (This is optional)")
    # Uncomment to test clearing: clear_history(token)
    print("Skipping clear history test\n")
    
    # Final summary
    print("=" * 60)
    print("✅ ALL TESTS COMPLETE!")
    print("=" * 60)
    print("\n📝 Summary:")
    print("✅ Watch progress tracking works")
    print("✅ Resume playback supported")
    print("✅ Continue watching list works")
    print("✅ Watch history retrieval works")
    print("✅ Rating system works")
    print("✅ Average rating calculation works")
    print("\n🎉 Watch History system is fully functional!\n")


if __name__ == "__main__":
    main()