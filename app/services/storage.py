import os
import tempfile
import logging
from typing import Optional, List
from supabase import create_client, Client
from app.config import settings
from fastapi import UploadFile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class SupabaseStorageService:
    """Handles all file operations with Supabase Storage"""
    
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise ValueError("Supabase URL and SERVICE_KEY must be configured")
        
        self.client: Client = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_KEY
        )
        self.knowledge_base_bucket = "knowledge-base-files"
        self.vector_store_bucket = "vector-stores"
        
        # Ensure buckets exist
        self._ensure_buckets_exist()
        
    
    def _ensure_buckets_exist(self):
        """Create storage buckets if they don't exist"""
        try:
            # List existing buckets
            buckets_response = self.client.storage.list_buckets()
            existing_buckets = [bucket.name for bucket in buckets_response]
            
            # Create knowledge-base-files bucket if not exists
            if self.knowledge_base_bucket not in existing_buckets:
                self.client.storage.create_bucket(self.knowledge_base_bucket, {"public": False})
                logger.info(f"Created bucket: {self.knowledge_base_bucket}")
            
            # Create vector-stores bucket if not exists
            if self.vector_store_bucket not in existing_buckets:
                self.client.storage.create_bucket(self.vector_store_bucket, {"public": False})
                logger.info(f"Created bucket: {self.vector_store_bucket}")
                
        except Exception as e:
            logger.warning(f"Could not verify/create buckets: {e}")
            # Continue anyway - buckets might exist but we can't list them
    
    def upload_file(self, bucket: str, path: str, file_content: bytes) -> bool:
        """Upload file to Supabase Storage"""
        try:
            response = self.client.storage.from_(bucket).upload(path, file_content)
            if hasattr(response, 'error') and response.error:
                raise Exception(f"Upload failed: {response.error}")
            logger.info(f"Uploaded file to {bucket}/{path}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {path} to {bucket}: {e}")
            raise
    
    def download_file(self, bucket: str, path: str) -> bytes:
        """Download file from Supabase Storage"""
        try:
            response = self.client.storage.from_(bucket).download(path)
            if isinstance(response, bytes):
                logger.info(f"Downloaded file from {bucket}/{path}")
                return response
            else:
                raise Exception(f"Download failed: {response}")
        except Exception as e:
            logger.error(f"Failed to download {path} from {bucket}: {e}")
            raise
    
    def delete_file(self, bucket: str, path: str) -> bool:
        """Delete file from Supabase Storage"""
        try:
            response = self.client.storage.from_(bucket).remove([path])
            if hasattr(response, 'error') and response.error:
                raise Exception(f"Delete failed: {response.error}")
            logger.info(f"Deleted file from {bucket}/{path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {path} from {bucket}: {e}")
            return False
    
    def delete_folder(self, bucket: str, folder_path: str) -> bool:
        """Delete all files in a folder"""
        try:
            # List files in folder
            files_response = self.client.storage.from_(bucket).list(folder_path)
            if not files_response:
                logger.info(f"No files found in {bucket}/{folder_path}")
                return True
            
            # Delete all files
            file_paths = [f"{folder_path}/{file.name}" for file in files_response]
            response = self.client.storage.from_(bucket).remove(file_paths)
            
            if hasattr(response, 'error') and response.error:
                raise Exception(f"Folder delete failed: {response.error}")
            
            logger.info(f"Deleted folder {bucket}/{folder_path} with {len(file_paths)} files")
            return True
        except Exception as e:
            logger.error(f"Failed to delete folder {folder_path} from {bucket}: {e}")
            return False
    
    def download_to_temp(self, bucket: str, path: str) -> str:
        """Download file to temporary location and return path"""
        try:
            content = self.download_file(bucket, path)
            
            # Create temp file with proper extension
            file_extension = os.path.splitext(path)[1]
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=file_extension
            )
            temp_file.write(content)
            temp_file.close()
            
            logger.info(f"Downloaded {bucket}/{path} to temp file: {temp_file.name}")
            return temp_file.name
        except Exception as e:
            logger.error(f"Failed to download {path} to temp: {e}")
            raise
    
    def upload_knowledge_base_file(self, tenant_id: int, filename: str, content: bytes) -> str:
        """Upload knowledge base file and return cloud path"""
        import uuid
        cloud_path = f"tenant_{tenant_id}/uploads/{uuid.uuid4()}_{filename}"
        self.upload_file(self.knowledge_base_bucket, cloud_path, content)
        return cloud_path
    
    def upload_vector_store_files(self, tenant_id: int, vector_store_id: str, local_dir: str):
        """Upload all vector store files from local directory"""
        for filename in os.listdir(local_dir):
            local_file_path = os.path.join(local_dir, filename)
            cloud_path = f"tenant_{tenant_id}/vector_stores/{vector_store_id}/{filename}"
            
            with open(local_file_path, 'rb') as f:
                content = f.read()
            
            self.upload_file(self.vector_store_bucket, cloud_path, content)
    
    def download_vector_store_files(self, tenant_id: int, vector_store_id: str) -> str:
        """Download vector store files to temp directory and return path"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Download required FAISS files
            for filename in ["index.faiss", "index.pkl"]:
                cloud_path = f"tenant_{tenant_id}/vector_stores/{vector_store_id}/{filename}"
                content = self.download_file(self.vector_store_bucket, cloud_path)
                
                local_path = os.path.join(temp_dir, filename)
                with open(local_path, 'wb') as f:
                    f.write(content)
            
            logger.info(f"Downloaded vector store {vector_store_id} to {temp_dir}")
            return temp_dir
        except Exception as e:
            # Clean up on failure
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    
    def delete_vector_store(self, tenant_id: int, vector_store_id: str) -> bool:
        """Delete all vector store files"""
        folder_path = f"tenant_{tenant_id}/vector_stores/{vector_store_id}"
        return self.delete_folder(self.vector_store_bucket, folder_path)
    
    def file_exists(self, bucket: str, path: str) -> bool:
        """Check if file exists in storage"""
        try:
            # Try to get file info
            self.client.storage.from_(bucket).get_public_url(path)
            return True
        except:
            return False
        

class LogoUploadService:
    def __init__(self):
        # Initialize Supabase client with service key (for admin operations)
        self.supabase: Client = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_KEY
        )
        self.bucket_name = settings.SUPABASE_STORAGE_BUCKET or "tenant-logos"
        self.max_size = settings.MAX_LOGO_SIZE or 2 * 1024 * 1024  # 2MB
        
        # Allowed file types
        self.allowed_types = [
            "image/jpeg", "image/jpg", "image/png", 
            "image/webp", "image/svg+xml"
        ]
    
    async def upload_logo(self, tenant_id: int, file: UploadFile) -> Tuple[bool, str, Optional[str]]:
        """
        Upload logo to Supabase Storage
        Returns: (success, message, logo_url)
        """
        try:
            # Validate file
            validation_result = await self._validate_file(file)
            if not validation_result[0]:
                return False, validation_result[1], None
            
            # Generate unique filename
            file_extension = self._get_file_extension(file.filename)
            filename = f"tenant_{tenant_id}_{uuid.uuid4().hex}{file_extension}"
            
            # Read file content
            file_content = await file.read()
            
            # Optimize image (except SVG)
            if file.content_type != "image/svg+xml":
                optimized_content = self._optimize_image(file_content, file.content_type)
            else:
                optimized_content = file_content
            
            # Upload to Supabase Storage
            logger.info(f"Uploading logo for tenant {tenant_id}: {filename}")
            
            response = self.supabase.storage.from_(self.bucket_name).upload(
                filename, 
                optimized_content,
                file_options={
                    "content-type": file.content_type,
                    "cache-control": "3600"  # Cache for 1 hour
                }
            )
            
            # Check for upload errors
            if hasattr(response, 'error') and response.error:
                logger.error(f"Supabase upload error: {response.error}")
                return False, f"Upload failed: {response.error}", None
            
            # Get public URL
            public_url_response = self.supabase.storage.from_(self.bucket_name).get_public_url(filename)
            
            if not public_url_response:
                return False, "Failed to get public URL", None
            
            public_url = public_url_response
            logger.info(f"Logo uploaded successfully: {public_url}")
            
            return True, "Logo uploaded successfully", public_url
            
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            return False, f"Upload error: {str(e)}", None
    
    async def _validate_file(self, file: UploadFile) -> Tuple[bool, str]:
        """Validate uploaded file"""
        
        # Check file type
        if file.content_type not in self.allowed_types:
            return False, f"Invalid file type. Allowed: {', '.join(self.allowed_types)}"
        
        # Check file size
        if hasattr(file, 'size') and file.size and file.size > self.max_size:
            max_mb = self.max_size / (1024 * 1024)
            return False, f"File too large. Maximum size: {max_mb:.1f}MB"
        
        # Additional check - read a small portion to verify it's actually an image
        if file.content_type != "image/svg+xml":
            try:
                # Save current position
                current_pos = file.file.tell() if hasattr(file.file, 'tell') else 0
                
                # Read first few bytes
                file.file.seek(0)
                header = file.file.read(512)
                
                # Reset position
                file.file.seek(current_pos)
                
                # Try to verify it's an image
                Image.open(io.BytesIO(header))
                
            except Exception:
                return False, "File appears to be corrupted or not a valid image"
        
        return True, "Valid"
    
    def _get_file_extension(self, filename: str) -> str:
        """Get file extension from filename"""
        if not filename:
            return ".png"  # Default
        return os.path.splitext(filename)[1].lower() or ".png"
    
    def _optimize_image(self, content: bytes, content_type: str) -> bytes:
        """Optimize image for web use"""
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(content))
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'P') and content_type == "image/jpeg":
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image)
                image = background
            
            # Resize if too large (max 512x512 for logos)
            max_size = (512, 512)
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {image.size}")
            
            # Save optimized image
            output = io.BytesIO()
            
            if content_type == "image/png":
                image.save(output, format="PNG", optimize=True)
            elif content_type == "image/webp":
                image.save(output, format="WEBP", optimize=True, quality=85)
            else:  # JPEG
                image.save(output, format="JPEG", optimize=True, quality=85)
            
            optimized_content = output.getvalue()
            
            # Log compression results
            original_size = len(content)
            optimized_size = len(optimized_content)
            compression_ratio = (1 - optimized_size / original_size) * 100
            
            logger.info(f"Image optimized: {original_size} → {optimized_size} bytes ({compression_ratio:.1f}% reduction)")
            
            return optimized_content
            
        except Exception as e:
            logger.warning(f"Image optimization failed: {e}. Using original.")
            return content
    
    async def delete_logo(self, logo_url: str) -> bool:
        """Delete logo from Supabase Storage"""
        try:
            # Extract filename from URL
            # URL format: https://project.supabase.co/storage/v1/object/public/tenant-logos/filename
            if '/tenant-logos/' in logo_url:
                filename = logo_url.split('/tenant-logos/')[-1]
            else:
                logger.warning(f"Cannot extract filename from URL: {logo_url}")
                return False
            
            logger.info(f"Deleting logo: {filename}")
            
            response = self.supabase.storage.from_(self.bucket_name).remove([filename])
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Delete error: {response.error}")
                return False
            
            logger.info(f"Logo deleted successfully: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting logo: {e}")
            return False
    
    def get_logo_info(self, tenant_id: int) -> dict:
        """Get logo upload guidelines and settings"""
        return {
            "max_size_mb": self.max_size / (1024 * 1024),
            "allowed_types": self.allowed_types,
            "recommended_size": "512x512 pixels or smaller",
            "recommended_formats": [
                "PNG with transparency (best for logos)",
                "SVG for perfect scalability", 
                "WebP for smallest file size",
                "JPEG for photos"
            ],
            "bucket_name": self.bucket_name,
            "tenant_prefix": f"tenant_{tenant_id}_"
        }
    
storage_service = SupabaseStorageService()