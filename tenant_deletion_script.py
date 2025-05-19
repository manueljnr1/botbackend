# tenant_deletion_script.py

import sys
import argparse
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Import your models and database settings
from app.database import Base, get_db
from app.tenants.models import Tenant
from app.auth.models import TenantCredentials, User
from app.config import settings

def create_db_session():
    # Create engine and session
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def list_tenants(db):
    """List all tenants in the system"""
    tenants = db.query(Tenant).all()
    if not tenants:
        print("No tenants found in the system.")
        return
    
    print("\nList of tenants:")
    print(f"{'ID':<5} {'Name':<20} {'Active':<10} {'Description':<30}")
    print("-" * 65)
    for tenant in tenants:
        active_status = "Active" if tenant.is_active else "Inactive"
        description = tenant.description if tenant.description else ""
        if len(description) > 27:
            description = description[:27] + "..."
        print(f"{tenant.id:<5} {tenant.name:<20} {active_status:<10} {description:<30}")
    print()

def deactivate_tenant(db, tenant_id):
    """Soft delete (deactivate) a tenant by ID"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        print(f"Error: Tenant with ID {tenant_id} not found")
        return False
    
    print(f"Deactivating tenant: {tenant.name} (ID: {tenant.id})")
    confirmation = input(f"Are you sure you want to deactivate '{tenant.name}'? This will make it inaccessible but keep its data. (y/n): ")
    
    if confirmation.lower() == 'y':
        tenant.is_active = False
        db.commit()
        print(f"Tenant '{tenant.name}' has been deactivated successfully.")
        return True
    else:
        print("Operation cancelled.")
        return False

def permanently_delete_tenant(db, tenant_id):
    """Permanently delete a tenant and its related data"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        print(f"Error: Tenant with ID {tenant_id} not found")
        return False
    
    # Check if there are users associated with this tenant
    users_count = db.query(User).filter(User.tenant_id == tenant_id).count()
    
    print(f"PERMANENTLY DELETING tenant: {tenant.name} (ID: {tenant.id})")
    if users_count > 0:
        print(f"Warning: This tenant has {users_count} associated users that will also be affected.")
    
    confirmation = input(f"Are you sure you want to PERMANENTLY DELETE '{tenant.name}' and all its data? This CANNOT be undone! (type 'DELETE' to confirm): ")
    
    if confirmation == 'DELETE':
        # Delete tenant credentials first
        credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant_id).all()
        for cred in credentials:
            db.delete(cred)
        
        # Update users to remove the tenant association or delete them
        # Option 1: Set tenant_id to NULL for associated users
        # db.query(User).filter(User.tenant_id == tenant_id).update({User.tenant_id: None})
        
        # Option 2: Delete associated users (more destructive)
        associated_users = db.query(User).filter(User.tenant_id == tenant_id).all()
        for user in associated_users:
            db.delete(user)
        
        # Finally delete the tenant
        db.delete(tenant)
        db.commit()
        print(f"Tenant '{tenant.name}' and its associated data have been permanently deleted.")
        return True
    else:
        print("Operation cancelled.")
        return False

def main():
    parser = argparse.ArgumentParser(description='Tenant Management Script')
    parser.add_argument('action', choices=['list', 'deactivate', 'delete'], 
                        help='Action to perform: list, deactivate, or delete')
    parser.add_argument('--tenant-id', type=int, help='ID of the tenant (required for deactivate and delete)')
    parser.add_argument('--force', action='store_true', help='Force operation without confirmation (use with caution)')
    
    args = parser.parse_args()
    
    db = create_db_session()
    
    try:
        if args.action == 'list':
            list_tenants(db)
        
        elif args.action == 'deactivate':
            if not args.tenant_id:
                print("Error: --tenant-id is required for deactivate action")
                parser.print_help()
                return 1
            
            deactivate_tenant(db, args.tenant_id)
        
        elif args.action == 'delete':
            if not args.tenant_id:
                print("Error: --tenant-id is required for delete action")
                parser.print_help()
                return 1
            
            permanently_delete_tenant(db, args.tenant_id)
    
    finally:
        db.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())