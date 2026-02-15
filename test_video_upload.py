"""
Test script for video upload functionality
"""
import requests
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"


def login_as_admin():
    """Login and get token"""
    print("🔐 Logging in as admin...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print("✅ Login successful\n")
        return token
    else:
        print(f"❌ Login failed: {response.text}")
        return None


def create_test_movie(token):
    """Create a test movie to upload video to"""
    print("🎬 Creating test movie...")
    headers = {"Authorization": f"Bearer {token}"}
    
    movie_data = {
        "title": "Video Upload Test Movie",
        "description": "Testing video upload and processing",
        "release_year": 2024,
        "genre_ids": [1]
    }
    
    response = requests.post(
        f"{BASE_URL}/movies/",
        headers=headers,
        json=movie_data
    )
    
    if response.status_code == 201:
        movie = response.json()
        movie_id = movie['id']
        print(f"✅ Movie created with ID: {movie_id}\n")
        return movie_id
    else:
        print(f"❌ Failed to create movie: {response.text}")
        return None


def upload_video(token, movie_id, video_file_path):
    """Upload video file"""
    print(f"📤 Uploading video: {video_file_path}")
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        with open(video_file_path, 'rb') as f:
            files = {'file': (video_file_path, f, 'video/mp4')}
            response = requests.post(
                f"{BASE_URL}/admin/upload/{movie_id}",
                headers=headers,
                files=files
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"   Job ID: {result['job_id']}")
            print(f"   Task ID: {result['task_id']}")
            print(f"   Status: {result['status']}\n")
            return result['job_id']
        else:
            print(f"❌ Upload failed: {response.text}")
            return None
    except FileNotFoundError:
        print(f"❌ Video file not found: {video_file_path}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def check_conversion_status(token, job_id, interval=5, max_wait=36000):
    """Check conversion status periodically"""
    print(f"⏳ Monitoring conversion job {job_id}...")
    print(f"   (This may take several minutes for large videos)")
    print(f"   Max wait time: {max_wait // 60} minutes\n")
    headers = {"Authorization": f"Bearer {token}"}
    
    start_time = time.time()
    last_progress = -1
    
    while True:
        response = requests.get(
            f"{BASE_URL}/admin/conversions/{job_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            status_data = response.json()
            progress = status_data['progress']
            status = status_data['status']
            step = status_data['current_step'] or 'Processing...'
            
            # Only print if progress changed
            if progress != last_progress:
                elapsed = int(time.time() - start_time)
                print(f"   [{progress}%] {status} - {step} (elapsed: {elapsed}s)")
                last_progress = progress
            
            if status == "completed":
                print(f"\n✅ Conversion completed successfully!")
                print(f"   Total time: {elapsed}s ({elapsed // 60}m {elapsed % 60}s)")
                return True
            elif status == "failed":
                error = status_data['error_message']
                print(f"\n❌ Conversion failed: {error}")
                return False
            
            # Check timeout
            if time.time() - start_time > max_wait:
                print(f"\n⚠️  Timeout after {max_wait}s")
                print(f"   Job is still processing. Check status later with:")
                print(f"   python check_job.py {job_id}")
                return False
            
            time.sleep(interval)
        else:
            print(f"❌ Error checking status: {response.text}")
            return False


def main():
    """Main test flow"""
    print("=" * 60)
    print("🎥 VIDEO UPLOAD TEST")
    print("=" * 60 + "\n")
    
    # Check if video file path provided
    if len(sys.argv) < 2:
        print("Usage: python test_video_upload.py <path_to_video_file>")
        print("\nExample:")
        print("  python test_video_upload.py C:\\Videos\\sample.mp4")
        print("  python test_video_upload.py /home/user/videos/sample.mkv")
        sys.exit(1)
    
    video_file = sys.argv[1]
    
    # Login
    token = login_as_admin()
    if not token:
        sys.exit(1)
    
    # Create movie
    movie_id = create_test_movie(token)
    if not movie_id:
        sys.exit(1)
    
    # Upload video
    job_id = upload_video(token, movie_id, video_file)
    if not job_id:
        sys.exit(1)
    
    # Monitor conversion
    success = check_conversion_status(token, job_id)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ VIDEO UPLOAD AND PROCESSING COMPLETE!")
        print("=" * 60)
        print(f"\n📺 View your movie at:")
        print(f"   http://localhost:8000/api/v1/movies/{movie_id}")
    else:
        print("\n" + "=" * 60)
        print("❌ VIDEO PROCESSING FAILED")
        print("=" * 60)


if __name__ == "__main__":
    main()