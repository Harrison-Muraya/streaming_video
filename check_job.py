"""
Quick script to check the status of a conversion job
Usage: python check_job.py <job_id>
"""
import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"

def login():
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]

def check_job(job_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{BASE_URL}/admin/conversions/{job_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n📊 Job Status for ID: {job_id}")
        print("=" * 50)
        print(f"Movie ID:      {data['movie_id']}")
        print(f"Status:        {data['status']}")
        print(f"Progress:      {data['progress']}%")
        print(f"Current Step:  {data['current_step'] or 'N/A'}")
        print(f"Error:         {data['error_message'] or 'None'}")
        print(f"Started:       {data['started_at'] or 'N/A'}")
        print(f"Completed:     {data['completed_at'] or 'N/A'}")
        print("=" * 50)
        
        # Check movie status
        movie_response = requests.get(f"{BASE_URL}/movies/{data['movie_id']}")
        if movie_response.status_code == 200:
            movie = movie_response.json()
            print(f"\n🎬 Movie Status:")
            print(f"Title:         {movie['title']}")
            print(f"Status:        {movie['status']}")
            print(f"Video URL:     {movie['video_url'] or 'Not ready'}")
            print(f"Video Files:   {len(movie['video_files'])} quality versions")
            
            if movie['video_files']:
                print("\nAvailable Qualities:")
                for vf in movie['video_files']:
                    print(f"  - {vf['quality']}: {vf['file_size'] / (1024**2):.1f} MB")
    else:
        print(f"❌ Error: {response.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_job.py <job_id>")
        print("\nExample: python check_job.py 6")
        sys.exit(1)
    
    job_id = sys.argv[1]
    token = login()
    check_job(job_id, token)