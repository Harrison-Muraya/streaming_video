"""
Add this task to app/tasks/video_tasks.py
-------------------------------------------
Copy the process_episode function and update_episode_progress helper
into your existing video_tasks.py file.

OR if you prefer a separate file, import it in celery_worker.py:
    from app.tasks import episode_tasks
"""
import os
from app.tasks import celery_app
from app.database import SessionLocal
from app.models.series import Episode, EpisodeVideoFile, EpisodeConversionJob
from app.utils.ffmpeg_utils import FFmpegProcessor
from app.utils.storage import StorageManager
from datetime import datetime


def update_episode_progress(db, job, progress: int, step: str):
    """Helper to update conversion job progress"""
    if job:
        job.progress = progress
        job.current_step = step
        db.commit()


@celery_app.task(bind=True, name='tasks.process_episode')
def process_episode(self, episode_id: int, original_file_path: str):
    """
    Process an uploaded episode video file.

    Steps:
      1. Analyse video (duration, resolution)
      2. Convert to high-quality MP4 master
      3. Generate 1080p / 720p / 480p versions
      4. Generate thumbnail
      5. Save EpisodeVideoFile records to DB
      6. Update Episode.video_url & status
    """
    db = SessionLocal()

    try:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            raise Exception(f"Episode {episode_id} not found")

        job = db.query(EpisodeConversionJob).filter(
            EpisodeConversionJob.episode_id == episode_id
        ).order_by(EpisodeConversionJob.created_at.desc()).first()

        if job:
            job.status = "processing"
            job.started_at = datetime.utcnow()
            job.task_id = self.request.id
            db.commit()

        # ── Step 1: Analyse ──────────────────────────────────────────────
        update_episode_progress(db, job, 5, "Analysing video...")
        video_info = FFmpegProcessor.get_video_info(original_file_path)
        episode.duration = int(video_info['duration'])
        db.commit()

        # ── Step 2: Master MP4 ───────────────────────────────────────────
        update_episode_progress(db, job, 10, "Converting to MP4...")
        base_filename = f"episode_{episode_id}"
        temp_dir = os.path.join(
            os.path.dirname(original_file_path), f"temp_ep_{episode_id}"
        )
        os.makedirs(temp_dir, exist_ok=True)

        master_file = os.path.join(temp_dir, f"{base_filename}_master.mp4")
        FFmpegProcessor.convert_to_mp4(original_file_path, master_file, quality='high')

        # ── Step 3: Quality versions ─────────────────────────────────────
        qualities = [
            {'name': '1080p', 'width': 1920, 'height': 1080, 'bitrate': '5M', 'progress': 35},
            {'name': '720p',  'width': 1280, 'height': 720,  'bitrate': '3M', 'progress': 55},
            {'name': '480p',  'width': 854,  'height': 480,  'bitrate': '1M', 'progress': 72},
        ]

        video_files_data = []

        for q in qualities:
            update_episode_progress(db, job, q['progress'], f"Creating {q['name']} version...")
            output_file = os.path.join(temp_dir, f"{base_filename}_{q['name']}.mp4")

            if video_info['height'] >= q['height']:
                FFmpegProcessor.create_quality_version(
                    master_file, output_file,
                    q['width'], q['height'], q['bitrate']
                )

                final_path = StorageManager.move_to_media(
                    output_file,
                    f"episodes/{episode_id}",
                    f"{base_filename}_{q['name']}.mp4"
                )

                video_files_data.append({
                    'quality': q['name'],
                    'path': final_path,
                    'size': StorageManager.get_file_size(final_path),
                })

        # ── Step 4: Thumbnail ────────────────────────────────────────────
        update_episode_progress(db, job, 85, "Generating thumbnail...")
        thumb_path = os.path.join(temp_dir, f"{base_filename}_thumb.jpg")
        FFmpegProcessor.generate_thumbnail(master_file, thumb_path, timestamp=10)

        final_thumb = StorageManager.move_to_media(
            thumb_path, "thumbnails/episodes", f"{base_filename}_thumb.jpg"
        )
        episode.thumbnail_url = StorageManager.get_media_url(final_thumb)

        # ── Step 5: Save EpisodeVideoFile records ────────────────────────
        update_episode_progress(db, job, 90, "Saving file information...")
        for vf in video_files_data:
            ev = EpisodeVideoFile(
                episode_id=episode_id,
                quality=vf['quality'],
                file_path=StorageManager.get_media_url(vf['path']),
                file_size=vf['size'],
                codec='h264',
                format_type='mp4',
            )
            db.add(ev)

        # ── Step 6: Finalise episode ─────────────────────────────────────
        if video_files_data:
            episode.video_url = StorageManager.get_media_url(video_files_data[0]['path'])

        episode.status = "ready"
        db.commit()

        # Mark job complete
        if job:
            job.status = "completed"
            job.progress = 100
            job.current_step = "Done"
            job.completed_at = datetime.utcnow()
            db.commit()

        # Cleanup temp files
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            if os.path.exists(original_file_path):
                os.remove(original_file_path)
        except Exception:
            pass

        return {"status": "completed", "episode_id": episode_id}

    except Exception as e:
        db.rollback()
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if episode:
            episode.status = "failed"
            db.commit()

        job = db.query(EpisodeConversionJob).filter(
            EpisodeConversionJob.episode_id == episode_id
        ).order_by(EpisodeConversionJob.created_at.desc()).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()

        raise
    finally:
        db.close()
