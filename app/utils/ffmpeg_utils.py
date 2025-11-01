"""
FFmpeg utilities for video processing
"""
import ffmpeg
import os
import subprocess
from typing import Dict, Optional, Tuple
from app.config import settings


class FFmpegProcessor:
    """Handle video processing with FFmpeg"""
    
    @staticmethod
    def get_video_info(file_path: str) -> Dict:
        """
        Get video metadata using ffprobe
        Returns: dict with duration, width, height, codec, bitrate
        """
        try:
            probe = ffmpeg.probe(file_path)
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
            
            info = {
                'duration': float(probe['format']['duration']),
                'size': int(probe['format']['size']),
                'bitrate': int(probe['format']['bit_rate']) // 1000,  # Convert to kbps
                'format': probe['format']['format_name'],
            }
            
            if video_stream:
                info.update({
                    'width': int(video_stream['width']),
                    'height': int(video_stream['height']),
                    'video_codec': video_stream['codec_name'],
                    'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                })
            
            if audio_stream:
                info.update({
                    'audio_codec': audio_stream['codec_name'],
                    'audio_bitrate': int(audio_stream.get('bit_rate', 0)) // 1000,
                })
            
            return info
        except Exception as e:
            raise Exception(f"Failed to get video info: {str(e)}")
    
    @staticmethod
    def convert_to_mp4(
        input_path: str,
        output_path: str,
        quality: str = "high",
        progress_callback=None
    ) -> bool:
        """
        Convert video to MP4 format
        
        Args:
            input_path: Source video file
            output_path: Destination MP4 file
            quality: 'high', 'medium', 'low'
            progress_callback: Function to call with progress updates
        
        Returns:
            True if successful
        """
        try:
            # Quality settings
            quality_settings = {
                'high': {'crf': 18, 'preset': 'slow'},
                'medium': {'crf': 23, 'preset': 'medium'},
                'low': {'crf': 28, 'preset': 'fast'}
            }
            
            settings_dict = quality_settings.get(quality, quality_settings['high'])
            
            # Build FFmpeg command
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                vcodec='libx264',
                acodec='aac',
                audio_bitrate='192k',
                crf=settings_dict['crf'],
                preset=settings_dict['preset'],
                movflags='faststart',
                **{'c:a': 'aac'}
            )
            
            # Run conversion
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            return True
        except ffmpeg.Error as e:
            raise Exception(f"FFmpeg conversion failed: {e.stderr.decode()}")
    
    @staticmethod
    def create_quality_version(
        input_path: str,
        output_path: str,
        width: int,
        height: int,
        bitrate: str,
        progress_callback=None
    ) -> bool:
        """
        Create a specific quality version of the video
        
        Args:
            input_path: Source video
            output_path: Output file
            width: Target width
            height: Target height
            bitrate: Video bitrate (e.g., '5M', '2M')
        """
        try:
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                vf=f'scale={width}:{height}',
                vcodec='libx264',
                preset='slow',
                video_bitrate=bitrate,
                acodec='aac',
                audio_bitrate='128k',
                movflags='faststart'
            )
            
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            return True
        except ffmpeg.Error as e:
            raise Exception(f"Quality version creation failed: {e.stderr.decode()}")
    
    @staticmethod
    def generate_thumbnail(
        input_path: str,
        output_path: str,
        timestamp: int = 10,
        width: int = 640,
        height: int = 360
    ) -> bool:
        """
        Generate thumbnail from video at specific timestamp
        
        Args:
            input_path: Source video
            output_path: Output image file
            timestamp: Time in seconds to capture frame
            width: Thumbnail width
            height: Thumbnail height
        """
        try:
            stream = ffmpeg.input(input_path, ss=timestamp)
            stream = ffmpeg.output(
                stream,
                output_path,
                vframes=1,
                vf=f'scale={width}:{height}'
            )
            
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            return True
        except ffmpeg.Error as e:
            raise Exception(f"Thumbnail generation failed: {e.stderr.decode()}")
    
    @staticmethod
    def generate_hls_stream(
        input_path: str,
        output_dir: str,
        segment_time: int = 10
    ) -> str:
        """
        Generate HLS streaming segments
        
        Args:
            input_path: Source video
            output_dir: Directory for HLS files
            segment_time: Segment duration in seconds
        
        Returns:
            Path to master playlist (m3u8)
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            playlist_path = os.path.join(output_dir, 'playlist.m3u8')
            segment_pattern = os.path.join(output_dir, 'segment_%03d.ts')
            
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                segment_pattern,
                format='hls',
                hls_time=segment_time,
                hls_playlist_type='vod',
                hls_segment_filename=segment_pattern
            )
            
            ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            return playlist_path
        except ffmpeg.Error as e:
            raise Exception(f"HLS generation failed: {e.stderr.decode()}")