"""
Storage utilities for handling file uploads and storage
"""
import os
import shutil
from typing import Optional
from app.config import settings


class StorageManager:
    """Manage file storage (local or S3)"""
    
    @staticmethod
    def save_upload(file_content: bytes, filename: str, subfolder: str = "") -> str:
        """
        Save uploaded file to storage
        
        Args:
            file_content: File bytes
            filename: Target filename
            subfolder: Optional subfolder (e.g., 'movies', 'thumbnails')
        
        Returns:
            Full path to saved file
        """
        # Create directory structure
        if subfolder:
            directory = os.path.join(settings.UPLOAD_DIR, subfolder)
        else:
            directory = settings.UPLOAD_DIR
        
        os.makedirs(directory, exist_ok=True)
        
        # Save file
        file_path = os.path.join(directory, filename)
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return file_path
    
    @staticmethod
    def move_to_media(source_path: str, destination_folder: str, filename: str) -> str:
        """
        Move file from upload/temp to media storage
        
        Args:
            source_path: Current file location
            destination_folder: Media subfolder
            filename: Target filename
        
        Returns:
            New file path
        """
        # Create destination directory
        dest_dir = os.path.join(settings.MEDIA_ROOT, destination_folder)
        os.makedirs(dest_dir, exist_ok=True)
        
        # Move file
        dest_path = os.path.join(dest_dir, filename)
        shutil.move(source_path, dest_path)
        
        return dest_path
    
    @staticmethod
    def get_media_url(file_path: str) -> str:
        """
        Convert file path to public URL
        
        Args:
            file_path: Full file path
        
        Returns:
            Public URL
        """
        # Extract relative path from media root
        if settings.MEDIA_ROOT in file_path:
            relative_path = file_path.replace(settings.MEDIA_ROOT, '').lstrip(os.sep)
            return f"{settings.MEDIA_URL}{relative_path.replace(os.sep, '/')}"
        return file_path
    
    @staticmethod
    def delete_file(file_path: str) -> bool:
        """Delete a file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes"""
        return os.path.getsize(file_path)