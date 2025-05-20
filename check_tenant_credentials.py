# check_tenant_credentials.py
import sys
from sqlalchemy.orm import Session

# Adjust these imports to match your project structure
from app.database import SessionLocal
from app.tenants.models import Tenant
from app.auth.models import TenantCredentials  # Changed from app.tenants.models
from app.core.security import get_password_hash

def check_and_fix_credentials():
    db = SessionLocal()
    try:
        # List all tenants
        tenants = db.query(Tenant).all()
        print(f"Found {len(tenants)} tenants in database:")
        
        for i, tenant in enumerate(tenants):
            print(f"{i+1}. Tenant ID: {tenant.id}, Name: {tenant.name}, API Key: {tenant.api_key}")
            
            # Check for credentials
            credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
            
            if credentials:
                print(f"   - Credentials found for tenant {tenant.name} (ID: {tenant.id})")
            else:
                print(f"   - WARNING: No credentials found for tenant {tenant.name} (ID: {tenant.id})")
                # Ask if we should create credentials
                create = input(f"   Create credentials for tenant '{tenant.name}'? (y/n): ")
                if create.lower() == 'y':
                    # Get password
                    password = input(f"   Enter password for tenant '{tenant.name}': ")
                    # Create credentials
                    hashed_password = get_password_hash(password)
                    new_credentials = TenantCredentials(
                        tenant_id=tenant.id,
                        hashed_password=hashed_password
                    )
                    db.add(new_credentials)
                    db.commit()
                    print(f"   ✓ Credentials created for tenant '{tenant.name}'")
        
        # Also check for orphaned credentials
        all_credentials = db.query(TenantCredentials).all()
        for cred in all_credentials:
            tenant = db.query(Tenant).filter(Tenant.id == cred.tenant_id).first()
            if not tenant:
                print(f"WARNING: Found orphaned credentials for non-existent tenant ID: {cred.tenant_id}")
    
    finally:
        db.close()

if __name__ == "__main__":
    check_and_fix_credentials()