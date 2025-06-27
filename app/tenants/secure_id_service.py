import random
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.tenants.models import Tenant
from app.database import SessionLocal

logger = logging.getLogger(__name__)

class SecureTenantIDService:
    """Service for generating secure tenant IDs"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
    
    @staticmethod
    def generate_secure_tenant_id() -> int:
        """Generate a secure random 9-digit tenant ID"""
        return random.randint(100000000, 999999999)
    
    def is_id_available(self, tenant_id: int) -> bool:
        """Check if a tenant ID is available"""
        existing = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        return existing is None
    
    def generate_unique_tenant_id(self, max_attempts: int = 100) -> int:
        """Generate a unique secure tenant ID"""
        for attempt in range(max_attempts):
            new_id = self.generate_secure_tenant_id()
            if self.is_id_available(new_id):
                logger.info(f"Generated unique secure tenant ID: {new_id} (attempt {attempt + 1})")
                return new_id
        
        raise ValueError(f"Could not generate unique tenant ID after {max_attempts} attempts")
    
    def validate_tenant_id_format(self, tenant_id: int) -> bool:
        """Validate that a tenant ID follows the secure format (9 digits)"""
        return 100000000 <= tenant_id <= 999999999

# Utility function for dependency injection
def get_secure_tenant_id_service(db: Session = None) -> SecureTenantIDService:
    """Factory function to create SecureTenantIDService instance"""
    if db is None:
        db = SessionLocal()
    return SecureTenantIDService(db)