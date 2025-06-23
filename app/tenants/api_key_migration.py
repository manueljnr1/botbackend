"""
API Key Migration and Validation Utilities
Ensures all tenants have valid, unique API keys
"""

import uuid
import secrets
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.tenants.models import Tenant
from app.database import SessionLocal

logger = logging.getLogger(__name__)


class APIKeyMigrationService:
    """Service for migrating and validating API keys"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
    
    def generate_api_key(self) -> str:
        """Generate a new API key with the correct format"""
        random_part = secrets.token_urlsafe(32)
        clean_key = random_part.replace('=', '').replace('+', '').replace('/', '')[:32]
        return f"sk-{clean_key}"
    
    def validate_api_key_format(self, api_key: str) -> bool:
        """Validate that an API key has the correct format"""
        if not api_key:
            return False
        
        # Should start with 'sk-' and be followed by 32+ characters
        if not api_key.startswith('sk-'):
            return False
        
        key_part = api_key[3:]  # Remove 'sk-' prefix
        return len(key_part) >= 32 and key_part.isalnum()
    
    def find_duplicate_api_keys(self) -> List[Dict[str, Any]]:
        """Find tenants with duplicate API keys"""
        try:
            # Query for duplicate API keys
            duplicates = self.db.query(
                Tenant.api_key,
                func.count(Tenant.id).label('count'),
                func.array_agg(Tenant.id).label('tenant_ids')
            ).filter(
                Tenant.api_key.isnot(None)
            ).group_by(
                Tenant.api_key
            ).having(
                func.count(Tenant.id) > 1
            ).all()
            
            duplicate_info = []
            for api_key, count, tenant_ids in duplicates:
                duplicate_info.append({
                    "api_key_masked": f"{api_key[:8]}...{api_key[-4:]}",
                    "duplicate_count": count,
                    "tenant_ids": tenant_ids
                })
            
            return duplicate_info
            
        except Exception as e:
            logger.error(f"❌ Error finding duplicate API keys: {str(e)}")
            return []
    
    def find_invalid_api_keys(self) -> List[Dict[str, Any]]:
        """Find tenants with invalid or missing API keys"""
        try:
            tenants = self.db.query(Tenant).filter(Tenant.is_active == True).all()
            
            invalid_keys = []
            for tenant in tenants:
                if not tenant.api_key:
                    invalid_keys.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "issue": "Missing API key",
                        "api_key": None
                    })
                elif not self.validate_api_key_format(tenant.api_key):
                    invalid_keys.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "issue": "Invalid API key format",
                        "api_key_masked": f"{tenant.api_key[:8]}...{tenant.api_key[-4:]}" if len(tenant.api_key) > 12 else tenant.api_key
                    })
            
            return invalid_keys
            
        except Exception as e:
            logger.error(f"❌ Error finding invalid API keys: {str(e)}")
            return []
    
    def fix_duplicate_api_keys(self, dry_run: bool = True) -> Dict[str, Any]:
        """Fix duplicate API keys by generating new ones"""
        try:
            duplicates = self.find_duplicate_api_keys()
            
            if not duplicates:
                return {
                    "success": True,
                    "message": "No duplicate API keys found",
                    "fixed_count": 0
                }
            
            fixed_tenants = []
            
            for duplicate in duplicates:
                tenant_ids = duplicate["tenant_ids"]
                
                # Keep the first tenant's API key, change the others
                for i, tenant_id in enumerate(tenant_ids[1:], 1):
                    tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
                    
                    if tenant:
                        old_key = tenant.api_key
                        new_key = self.generate_api_key()
                        
                        # Ensure uniqueness
                        while self.db.query(Tenant).filter(Tenant.api_key == new_key).first():
                            new_key = self.generate_api_key()
                        
                        if not dry_run:
                            tenant.api_key = new_key
                            self.db.commit()
                        
                        fixed_tenants.append({
                            "tenant_id": tenant_id,
                            "tenant_name": tenant.name,
                            "old_key_masked": f"{old_key[:8]}...{old_key[-4:]}",
                            "new_key_masked": f"{new_key[:8]}...{new_key[-4:]}",
                            "dry_run": dry_run
                        })
            
            return {
                "success": True,
                "message": f"Fixed {len(fixed_tenants)} duplicate API keys",
                "fixed_count": len(fixed_tenants),
                "fixed_tenants": fixed_tenants,
                "dry_run": dry_run
            }
            
        except Exception as e:
            if not dry_run:
                self.db.rollback()
            logger.error(f"❌ Error fixing duplicate API keys: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to fix duplicate API keys: {str(e)}",
                "fixed_count": 0
            }
    
    def fix_invalid_api_keys(self, dry_run: bool = True) -> Dict[str, Any]:
        """Fix invalid or missing API keys"""
        try:
            invalid_keys = self.find_invalid_api_keys()
            
            if not invalid_keys:
                return {
                    "success": True,
                    "message": "No invalid API keys found",
                    "fixed_count": 0
                }
            
            fixed_tenants = []
            
            for invalid in invalid_keys:
                tenant_id = invalid["tenant_id"]
                tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
                
                if tenant:
                    old_key = tenant.api_key
                    new_key = self.generate_api_key()
                    
                    # Ensure uniqueness
                    while self.db.query(Tenant).filter(Tenant.api_key == new_key).first():
                        new_key = self.generate_api_key()
                    
                    if not dry_run:
                        tenant.api_key = new_key
                        self.db.commit()
                    
                    fixed_tenants.append({
                        "tenant_id": tenant_id,
                        "tenant_name": tenant.name,
                        "issue": invalid["issue"],
                        "old_key": old_key or "None",
                        "new_key_masked": f"{new_key[:8]}...{new_key[-4:]}",
                        "dry_run": dry_run
                    })
            
            return {
                "success": True,
                "message": f"Fixed {len(fixed_tenants)} invalid API keys",
                "fixed_count": len(fixed_tenants),
                "fixed_tenants": fixed_tenants,
                "dry_run": dry_run
            }
            
        except Exception as e:
            if not dry_run:
                self.db.rollback()
            logger.error(f"❌ Error fixing invalid API keys: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to fix invalid API keys: {str(e)}",
                "fixed_count": 0
            }
    
    def comprehensive_api_key_audit(self) -> Dict[str, Any]:
        """Perform a comprehensive audit of all API keys"""
        try:
            # Get all tenants
            total_tenants = self.db.query(Tenant).count()
            active_tenants = self.db.query(Tenant).filter(Tenant.is_active == True).count()
            
            # Find issues
            duplicates = self.find_duplicate_api_keys()
            invalid_keys = self.find_invalid_api_keys()
            
            # Check for any null API keys
            null_api_keys = self.db.query(Tenant).filter(
                Tenant.api_key.is_(None),
                Tenant.is_active == True
            ).count()
            
            # Check for empty string API keys
            empty_api_keys = self.db.query(Tenant).filter(
                Tenant.api_key == "",
                Tenant.is_active == True
            ).count()
            
            return {
                "success": True,
                "audit_timestamp": logger.handlers[0].formatter.formatTime(logger.makeRecord("", 0, "", 0, "", (), None)) if logger.handlers else None,
                "summary": {
                    "total_tenants": total_tenants,
                    "active_tenants": active_tenants,
                    "duplicate_api_keys": len(duplicates),
                    "invalid_api_keys": len(invalid_keys),
                    "null_api_keys": null_api_keys,
                    "empty_api_keys": empty_api_keys
                },
                "duplicate_details": duplicates,
                "invalid_key_details": invalid_keys,
                "recommendations": self._generate_recommendations(duplicates, invalid_keys, null_api_keys, empty_api_keys)
            }
            
        except Exception as e:
            logger.error(f"❌ Error during API key audit: {str(e)}")
            return {
                "success": False,
                "error": f"Audit failed: {str(e)}"
            }
    
    def _generate_recommendations(self, duplicates, invalid_keys, null_keys, empty_keys) -> List[str]:
        """Generate recommendations based on audit findings"""
        recommendations = []
        
        if duplicates:
            recommendations.append(f"Fix {len(duplicates)} duplicate API key groups using fix_duplicate_api_keys()")
        
        if invalid_keys:
            recommendations.append(f"Fix {len(invalid_keys)} invalid API keys using fix_invalid_api_keys()")
        
        if null_keys > 0:
            recommendations.append(f"Fix {null_keys} tenants with null API keys")
        
        if empty_keys > 0:
            recommendations.append(f"Fix {empty_keys} tenants with empty API keys")
        
        if not any([duplicates, invalid_keys, null_keys, empty_keys]):
            recommendations.append("All API keys are valid and unique. No action required.")
        
        return recommendations


def run_api_key_migration(dry_run: bool = True) -> Dict[str, Any]:
    """
    Main migration function to fix all API key issues
    
    Args:
        dry_run: If True, only shows what would be fixed without making changes
    
    Returns:
        Dict with migration results
    """
    logger.info(f"🔧 Starting API key migration (dry_run={dry_run})")
    
    try:
        migration_service = APIKeyMigrationService()
        
        # First, run a comprehensive audit
        audit_result = migration_service.comprehensive_api_key_audit()
        
        if not audit_result["success"]:
            return audit_result
        
        # Fix duplicates first
        duplicate_fix_result = migration_service.fix_duplicate_api_keys(dry_run=dry_run)
        
        # Then fix invalid keys
        invalid_fix_result = migration_service.fix_invalid_api_keys(dry_run=dry_run)
        
        # Run final audit to verify
        final_audit = migration_service.comprehensive_api_key_audit()
        
        return {
            "success": True,
            "migration_type": "dry_run" if dry_run else "actual",
            "initial_audit": audit_result,
            "duplicate_fixes": duplicate_fix_result,
            "invalid_fixes": invalid_fix_result,
            "final_audit": final_audit,
            "total_fixes": duplicate_fix_result.get("fixed_count", 0) + invalid_fix_result.get("fixed_count", 0)
        }
        
    except Exception as e:
        logger.error(f"❌ API key migration failed: {str(e)}")
        return {
            "success": False,
            "error": f"Migration failed: {str(e)}"
        }


if __name__ == "__main__":
    # Example usage for testing
    print("Running API Key Migration (Dry Run)")
    result = run_api_key_migration(dry_run=True)
    
    if result["success"]:
        print(f"✅ Migration completed successfully")
        print(f"Total fixes needed: {result['total_fixes']}")
    else:
        print(f"❌ Migration failed: {result.get('error')}")