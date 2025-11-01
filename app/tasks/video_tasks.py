"""
Celery tasks for video processing
"""
import os
import time
from app.tasks import celery_app
from app.database import SessionLocal
from app.models.movie import Movie, VideoFile, ConversionJob
from app.utils.ffmpeg_utils import FFmpegProcessor
from app.utils.storage import StorageManager
from datetime import datetime


@celery_app.task(bind=True, name='tasks.process_video')
def process_video(self, movie_id: int, original_file_path: str):
    """
    Main task to process uploaded video
    
    Steps:
    1. Get video information
    2. Convert to MP4 (if needed)
    3. Generate multiple quality versions
    4. Generate thumbnails
    5. Generate HLS segments (optional)
    6. Move files to media storage
    7. Update database
    """
    db = SessionLocal()
    
    try:
        # Get movie and conversion job
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise Exception(f"Movie {movie_id} not found")
        
        conversion_job = db.query(ConversionJob).filter(
            ConversionJob.movie_id == movie_id
        ).order_by(ConversionJob.created_at.desc()).first()
        
        if conversion_job:
            conversion_job.status = "processing"
            conversion_job.started_at = datetime.utcnow()
            conversion_job.task_id = self.request.id
            db.commit()
        
        # Step 1: Get video info
        update_progress(db, conversion_job, 5, "Analyzing video...")
        video_info = FFmpegProcessor.get_video_info(original_file_path)
        
        # Update movie duration
        movie.duration = int(video_info['duration'])
        db.commit()
        
        # Step 2: Convert to MP4 if needed
        update_progress(db, conversion_job, 10, "Converting to MP4...")
        
        base_filename = f"movie_{movie_id}"
        temp_dir = os.path.join(os.path.dirname(original_file_path), f"temp_{movie_id}")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Master file (high quality)
        master_file = os.path.join(temp_dir, f"{base_filename}_master.mp4")
        FFmpegProcessor.convert_to_mp4(original_file_path, master_file, quality='high')
        
        # Step 3: Generate quality versions
        qualities = [
            {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate': '5M', 'progress': 30},
            {'name': '720p', 'width': 1280, 'height': 720, 'bitrate': '3M', 'progress': 50},
            {'name': '480p', 'width': 854, 'height': 480, 'bitrate': '1M', 'progress': 70},
        ]
        
        video_files_data = []
        
        for quality in qualities:
            update_progress(db, conversion_job, quality['progress'], f"Creating {quality['name']} version...")
            
            output_file = os.path.join(temp_dir, f"{base_filename}_{quality['name']}.mp4")
            
            # Only create if video is larger than target resolution
            if video_info['height'] >= quality['height']:
                FFmpegProcessor.create_quality_version(
                    master_file,
                    output_file,
                    quality['width'],
                    quality['height'],
                    quality['bitrate']
                )
                
                # Move to media storage
                final_path = StorageManager.move_to_media(
                    output_file,
                    f"movies/{movie_id}",
                    f"{base_filename}_{quality['name']}.mp4"
                )
                
                video_files_data.append({
                    'quality': quality['name'],
                    'path': final_path,
                    'size': StorageManager.get_file_size(final_path)
                })
        
        # Step 4: Generate thumbnails
        update_progress(db, conversion_job, 85, "Generating thumbnails...")
        
        thumbnail_path = os.path.join(temp_dir, f"{base_filename}_thumb.jpg")
        FFmpegProcessor.generate_thumbnail(master_file, thumbnail_path, timestamp=10)
        
        # Move thumbnail
        final_thumb_path = StorageManager.move_to_media(
            thumbnail_path,
            f"thumbnails",
            f"{base_filename}_thumb.jpg"
        )
        movie.poster_url = StorageManager.get_media_url(final_thumb_path)
        
        # Generate backdrop (larger thumbnail)
        backdrop_path = os.path.join(temp_dir, f"{base_filename}_backdrop.jpg")
        FFmpegProcessor.generate_thumbnail(
            master_file, 
            backdrop_path, 
            timestamp=30,
            width=1280,
            height=720
        )
        final_backdrop_path = StorageManager.move_to_media(
            backdrop_path,
            f"backdrops",
            f"{base_filename}_backdrop.jpg"
        )
        movie.backdrop_url = StorageManager.get_media_url(final_backdrop_path)
        
        # Step 5: Save video file records
        update_progress(db, conversion_job, 90, "Saving file information...")
        
        for vf_data in video_files_data:
            video_file = VideoFile(
                movie_id=movie_id,
                quality=vf_data['quality'],
                file_path=StorageManager.get_media_url(vf_data['path']),
                file_size=vf_data['size'],
                codec='h264',
                format_type='mp4'
            )
            db.add(video_file)
        
        # Set primary video URL (highest quality available)
        if video_files_data:
            movie.video_url = StorageManager.get_media_url(video_files_data[0]['path'])
        
        # Update movie status
        movie.status = "ready"
        
        # Update conversion job
        if conversion_job:
            conversion_job.status = "completed"
            conversion_job.progress = 100
            conversion_job.completed_at = datetime.utcnow()
        
        db.commit()
        
        # Cleanup
        update_progress(db, conversion_job, 95, "Cleaning up...")
        cleanup_temp_files(temp_dir, original_file_path)
        
        return {
            'status': 'success',
            'movie_id': movie_id,
            'video_files': len(video_files_data)
        }
        
    except Exception as e:
        # Handle error
        if conversion_job:
            conversion_job.status = "failed"
            conversion_job.error_message = str(e)
            conversion_job.completed_at = datetime.utcnow()
            db.commit()
        
        if movie:
            movie.status = "failed"
            db.commit()
        
        raise e
    
    finally:
        db.close()


def update_progress(db, conversion_job, progress: int, message: str):
    """Update conversion job progress"""
    if conversion_job:
        conversion_job.progress = progress
        conversion_job.current_step = message
        db.commit()
        print(f"[{progress}%] {message}")


def cleanup_temp_files(*paths):
    """Clean up temporary files and directories"""
    for path in paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
        except Exception as e:
            print(f"Error cleaning up {path}: {e}")