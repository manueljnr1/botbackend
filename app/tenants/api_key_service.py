"""
Enhanced API Key Reset Service with Password Verification
Adds account password requirement for tenant API key resets
"""

import uuid
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext

from app.tenants.models import Tenant
from app.auth.models import TenantCredentials
from app.auth.supabase_service import supabase_auth_service
from app.database import get_db

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class EnhancedAPIKeyResetService:
    """Enhanced service for handling secure API key reset operations with password verification"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_new_api_key(self) -> str:
        """
        Generate a new secure API key with proper format
        Returns a cryptographically secure API key
        """
        # Generate a secure random key
        random_part = secrets.token_urlsafe(32)
        # Clean the key to ensure it's URL-safe and remove any padding
        clean_key = random_part.replace('=', '').replace('+', '').replace('/', '')[:32]
        return f"sk-{clean_key}"
    
    def validate_tenant_ownership(self, tenant_id: int, current_api_key: str) -> bool:
        """
        Validate that the current API key belongs to the tenant
        Prevents unauthorized API key resets
        """
        tenant = self.db.query(Tenant).filter(
            Tenant.id == tenant_id,
            Tenant.api_key == current_api_key,
            Tenant.is_active == True
        ).first()
        return tenant is not None
    
    async def verify_tenant_password(self, tenant_id: int, password: str) -> Dict[str, Any]:
        """
        Verify tenant password using both local credentials and Supabase
        
        Args:
            tenant_id: The tenant's ID
            password: Plain text password to verify
            
        Returns:
            Dict with verification result and method used
        """
        try:
            # Get tenant
            tenant = self.db.query(Tenant).filter(
                Tenant.id == tenant_id,
                Tenant.is_active == True
            ).first()
            
            if not tenant:
                return {
                    "success": False,
                    "error": "Tenant not found or inactive",
                    "method": "none"
                }
            
            # Method 1: Try Supabase authentication (preferred)
            if tenant.supabase_user_id and tenant.email:
                try:
                    supabase_result = await supabase_auth_service.sign_in(
                        email=tenant.email,
                        password=password
                    )
                    
                    if supabase_result["success"]:
                        logger.info(f"✅ Password verified via Supabase for tenant {tenant_id}")
                        return {
                            "success": True,
                            "method": "supabase",
                            "tenant_email": tenant.email
                        }
                    else:
                        logger.info(f"❌ Supabase password verification failed for tenant {tenant_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Supabase verification error for tenant {tenant_id}: {e}")
            
            # Method 2: Fallback to local credentials
            local_credentials = self.db.query(TenantCredentials).filter(
                TenantCredentials.tenant_id == tenant_id
            ).first()
            
            if local_credentials and local_credentials.hashed_password:
                is_valid = pwd_context.verify(password, local_credentials.hashed_password)
                
                if is_valid:
                    logger.info(f"✅ Password verified via local credentials for tenant {tenant_id}")
                    return {
                        "success": True,
                        "method": "local_credentials",
                        "tenant_email": tenant.email
                    }
                else:
                    logger.info(f"❌ Local password verification failed for tenant {tenant_id}")
            
            # If we reach here, password verification failed
            return {
                "success": False,
                "error": "Invalid password",
                "method": "both_failed"
            }
            
        except Exception as e:
            logger.error(f"❌ Password verification error for tenant {tenant_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Password verification failed: {str(e)}",
                "method": "error"
            }
    
    async def reset_tenant_api_key_with_password(
        self, 
        tenant_id: int, 
        current_api_key: str,
        password: str,
        reason: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Reset API key for a tenant with password verification
        
        Args:
            tenant_id: The tenant's ID
            current_api_key: Current API key for validation (unless force=True)
            password: Tenant's account password for verification
            reason: Optional reason for the reset
            force: Skip validation (admin override)
            
        Returns:
            Dict with success status, new API key, and metadata
        """
        try:
            # Get the tenant
            tenant = self.db.query(Tenant).filter(
                Tenant.id == tenant_id,
                Tenant.is_active == True
            ).first()
            
            if not tenant:
                return {
                    "success": False,
                    "error": "Tenant not found or inactive",
                    "tenant_id": tenant_id
                }
            
            # Validate ownership unless force is used (admin override)
            if not force and not self.validate_tenant_ownership(tenant_id, current_api_key):
                return {
                    "success": False,
                    "error": "Invalid current API key or unauthorized access",
                    "tenant_id": tenant_id
                }
            
            # 🔒 NEW: Verify password unless force is used (admin override)
            if not force:
                password_verification = await self.verify_tenant_password(tenant_id, password)
                
                if not password_verification["success"]:
                    # Log the failed password attempt for security monitoring
                    logger.warning(
                        f"🚨 Failed password verification for API key reset: "
                        f"Tenant {tenant_id} ({tenant.email}) - "
                        f"Method: {password_verification.get('method')} - "
                        f"Error: {password_verification.get('error')}"
                    )
                    
                    return {
                        "success": False,
                        "error": "Password verification failed. Please check your password and try again.",
                        "tenant_id": tenant_id,
                        "verification_method": password_verification.get("method")
                    }
                
                logger.info(
                    f"🔐 Password verified for API key reset: "
                    f"Tenant {tenant_id} via {password_verification.get('method')}"
                )
            
            # Store old API key for logging/audit
            old_api_key = tenant.api_key
            old_key_masked = f"{old_api_key[:8]}...{old_api_key[-4:]}" if old_api_key else "none"
            
            # Generate new API key
            new_api_key = self.generate_new_api_key()
            
            # Ensure uniqueness (very unlikely collision, but safety first)
            max_attempts = 5
            attempt = 0
            while attempt < max_attempts:
                existing = self.db.query(Tenant).filter(
                    Tenant.api_key == new_api_key
                ).first()
                
                if not existing:
                    break
                    
                new_api_key = self.generate_new_api_key()
                attempt += 1
            
            if attempt >= max_attempts:
                return {
                    "success": False,
                    "error": "Failed to generate unique API key after multiple attempts",
                    "tenant_id": tenant_id
                }
            
            # Update the tenant with new API key
            tenant.api_key = new_api_key
            tenant.updated_at = datetime.utcnow()
            
            # Commit the change
            self.db.commit()
            self.db.refresh(tenant)
            
            # Log the successful reset
            reset_method = "admin_force" if force else "password_verified"
            logger.info(
                f"✅ API key reset successful for tenant {tenant.name} (ID: {tenant_id}). "
                f"Method: {reset_method} | "
                f"Old: {old_key_masked}, New: {new_api_key[:8]}...{new_api_key[-4:]} | "
                f"Reason: {reason or 'Not specified'}"
            )
            
            # Return success response
            return {
                "success": True,
                "message": "API key reset successfully",
                "tenant_id": tenant_id,
                "tenant_name": tenant.name,
                "new_api_key": new_api_key,
                "old_api_key_masked": old_key_masked,
                "reset_timestamp": datetime.utcnow().isoformat(),
                "verification_method": "admin_force" if force else password_verification.get("method"),
                "reason": reason
            }
            
        except Exception as e:
            # Rollback on any error
            self.db.rollback()
            logger.error(f"❌ API key reset failed for tenant {tenant_id}: {str(e)}")
            
            return {
                "success": False,
                "error": f"API key reset failed: {str(e)}",
                "tenant_id": tenant_id
            }
    
    async def admin_reset_tenant_api_key(self, tenant_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Admin-only API key reset (bypasses password validation)
        
        Args:
            tenant_id: The tenant's ID to reset
            reason: Optional reason for the reset
            
        Returns:
            Dict with success status and new API key
        """
        return await self.reset_tenant_api_key_with_password(
            tenant_id=tenant_id,
            current_api_key="",  # Not used when force=True
            password="",  # Not used when force=True
            reason=reason or "Admin-initiated reset",
            force=True
        )
    
    def get_tenant_api_key_info(self, tenant_id: int) -> Dict[str, Any]:
        """
        Get API key information for a tenant (masked for security)
        
        Args:
            tenant_id: The tenant's ID
            
        Returns:
            Dict with masked API key info and metadata
        """
        try:
            tenant = self.db.query(Tenant).filter(
                Tenant.id == tenant_id,
                Tenant.is_active == True
            ).first()
            
            if not tenant:
                return {
                    "success": False,
                    "error": "Tenant not found or inactive"
                }
            
            # Mask the API key for security
            api_key = tenant.api_key
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if api_key else "No API key"
            
            # Check authentication methods available
            has_supabase = bool(tenant.supabase_user_id)
            has_local_creds = bool(
                self.db.query(TenantCredentials).filter(
                    TenantCredentials.tenant_id == tenant_id
                ).first()
            )
            
            return {
                "success": True,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "api_key_masked": masked_key,
                "last_updated": tenant.updated_at.isoformat() if tenant.updated_at else None,
                "tenant_active": tenant.is_active,
                "authentication_methods": {
                    "supabase_available": has_supabase,
                    "local_credentials_available": has_local_creds
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get API key info for tenant {tenant_id}: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get API key info: {str(e)}"
            }
    
    def audit_api_key_reset(self, tenant_id: int, reset_by: str, reason: str = "", verification_method: str = "") -> None:
        """
        Create an audit log entry for API key reset with enhanced security info
        
        Args:
            tenant_id: The tenant's ID
            reset_by: Who performed the reset
            reason: Optional reason for the reset
            verification_method: How the reset was verified (password/admin/etc)
        """
        try:
            logger.info(
                f"🔍 API Key Reset Audit: Tenant {tenant_id} | "
                f"Reset by: {reset_by} | "
                f"Verification: {verification_method} | "
                f"Reason: {reason or 'Not specified'} | "
                f"Timestamp: {datetime.utcnow().isoformat()}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to create audit log: {str(e)}")


# Utility function for dependency injection
def get_enhanced_api_key_reset_service(db: Session = None) -> EnhancedAPIKeyResetService:
    """
    Factory function to create EnhancedAPIKeyResetService instance
    """
    if db is None:
        # This should not happen in normal usage, but provides a fallback
        from app.database import SessionLocal
        db = SessionLocal()
    
    return EnhancedAPIKeyResetService(db)