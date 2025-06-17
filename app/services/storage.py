import os
import tempfile
import logging
from typing import Optional, List
from supabase import create_client, Client
from app.config import settings

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


# Global instance
storage_service = SupabaseStorageService()