#!/usr/bin/env python3
"""
Script to create a new tenant with API key and secure password
"""
import sys
import os
import logging
import uuid
import re
from getpass import getpass
from passlib.context import CryptContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Add the project root to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_password_hash(password):
    """Generate a hashed password"""
    return pwd_context.hash(password)

def validate_password(password):
    """
    Validate password strength:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, "Password meets requirements"

def create_tenant():
    """Create a new tenant with a unique API key and secure password"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Get tenant details
        print("\n=== Create New Tenant ===")
        tenant_name = input("Tenant Name: ")
        tenant_description = input("Description (optional): ")
        
        if not tenant_name:
            logger.error("Tenant name is required")
            return
        
        # Check if tenant exists
        existing_tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
        if existing_tenant:
            logger.error(f"Tenant with name '{tenant_name}' already exists")
            return
        
        # Get password with validation
        print("\n=== Password Requirements ===")
        print("- At least 8 characters")
        print("- At least one uppercase letter")
        print("- At least one lowercase letter")
        print("- At least one digit")
        print("- At least one special character (!@#$%^&*(),.?\":{}|<>)")
        
        password = None
        while True:
            password = getpass("\nTenant Password: ")
            valid, message = validate_password(password)
            
            if not valid:
                logger.error(message)
                continue
            
            confirm_password = getpass("Confirm Password: ")
            if password != confirm_password:
                logger.error("Passwords do not match")
                continue
            
            break
        
        # Create tenant with unique API key
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        new_tenant = Tenant(
            name=tenant_name,
            description=tenant_description,
            api_key=api_key,
            is_active=True
        )
        
        # Here we would typically store the password hash somewhere
        # Since your model doesn't directly store it, we'll just print it
        # But you might want to extend your model or create a separate passwords table
        password_hash = get_password_hash(password)
        
        db.add(new_tenant)
        db.commit()
        db.refresh(new_tenant)
        
        # Print success information
        print("\n=== Tenant Created Successfully ===")
        print(f"Tenant Name: {new_tenant.name}")
        print(f"Tenant ID: {new_tenant.id}")
        print(f"API Key: {new_tenant.api_key}")
        print(f"Password Hash: {password_hash}")
        print("\nImportant: Save this API key and password in a secure place!")
        
        # Optionally save to a file
        save_to_file = input("\nWould you like to save the tenant info to a file? (y/n): ")
        if save_to_file.lower() == 'y':
            filename = f"tenant_{new_tenant.id}_info.txt"
            with open(filename, 'w') as f:
                f.write(f"Tenant Name: {new_tenant.name}\n")
                f.write(f"Tenant ID: {new_tenant.id}\n")
                f.write(f"API Key: {new_tenant.api_key}\n")
                f.write(f"Password Hash: {password_hash}\n")
                f.write(f"Created: {new_tenant.created_at}\n")
            print(f"Tenant information saved to {filename}")
        
    except Exception as e:
        logger.error(f"Error creating tenant: {e}")
        db.rollback()
    finally:
        db.close()

def list_tenants():
    """List all existing tenants"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    # Create database session
    db = SessionLocal()
    
    try:
        tenants = db.query(Tenant).all()
        
        if not tenants:
            print("\nNo tenants found.")
            return
        
        print("\n=== Existing Tenants ===")
        for tenant in tenants:
            status = "Active" if tenant.is_active else "Inactive"
            print(f"ID: {tenant.id} | Name: {tenant.name} | Status: {status}")
        
    except Exception as e:
        logger.error(f"Error listing tenants: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Show existing tenants first
    list_tenants()
    
    # Create a new tenant
    create_tenant()