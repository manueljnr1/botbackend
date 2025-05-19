#!/usr/bin/env python3
"""
Script to create tenants with passwords in the chatbot system
"""
import os
import sys
import uuid
import logging
from getpass import getpass
from passlib.context import CryptContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_tenant_with_password():
    """Create a new tenant with password"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    from sqlalchemy import Column, String
    
    print("=== Tenant Creation Tool ===")
    
    # Get tenant information
    name = input("Tenant Name: ")
    description = input("Description (optional): ")
    contact_email = input("Contact Email: ")  # Added contact email field
    password = getpass("Password: ")
    confirm_password = getpass("Confirm Password: ")
    
    if not name:
        print("Error: Tenant name is required")
        return
    
    if not password:
        print("Error: Password is required")
        return
    
    if password != confirm_password:
        print("Error: Passwords don't match")
        return
    
    # Check if contact email is provided
    if not contact_email:
        print("Warning: No contact email provided. It's recommended to add one for password recovery.")
        proceed = input("Do you want to proceed without a contact email? (y/n): ")
        if proceed.lower() != 'y':
            return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if tenant with this name already exists
        existing_tenant = db.query(Tenant).filter(Tenant.name == name).first()
        if existing_tenant:
            print(f"Error: A tenant with the name '{name}' already exists")
            return
        
        # Generate API key
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        
        # Check if the Tenant model has a hashed_password column
        # If not, we need to add it first
        has_password_column = False
        has_contact_email_column = False
        
        for column in Tenant.__table__.columns:
            if column.name == 'hashed_password':
                has_password_column = True
            if column.name == 'contact_email':
                has_contact_email_column = True
        
        if not has_password_column:
            print("The Tenant model does not have a hashed_password column.")
            print("Let's add it to the database schema.")
            
            # This is a simplified approach - in a production system,
            # you should use Alembic migrations for schema changes
            from sqlalchemy import text
            db.execute(text("ALTER TABLE tenants ADD COLUMN hashed_password TEXT"))
            db.commit()
            print("Added hashed_password column to tenants table")
            
            # Add the column to the model as well
            Tenant.hashed_password = Column(String)
        
        if not has_contact_email_column:
            print("The Tenant model does not have a contact_email column.")
            print("Let's add it to the database schema.")
            
            from sqlalchemy import text
            db.execute(text("ALTER TABLE tenants ADD COLUMN contact_email TEXT"))
            db.commit()
            print("Added contact_email column to tenants table")
            
            # Add the column to the model as well
            Tenant.contact_email = Column(String)
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        # Create tenant
        tenant = Tenant(
            name=name,
            description=description,
            api_key=api_key,
            is_active=True,
            hashed_password=hashed_password,  # Add the hashed password
            contact_email=contact_email       # Add the contact email
        )
        
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        print("\n=== Tenant created successfully ===")
        print(f"Tenant ID: {tenant.id}")
        print(f"Tenant Name: {tenant.name}")
        print(f"Contact Email: {tenant.contact_email if tenant.contact_email else 'Not provided'}")
        print(f"API Key: {tenant.api_key}")
        print("\nKeep this API key secure. Users will need it to access the chatbot.")
        
    except Exception as e:
        print(f"Error creating tenant: {e}")
        db.rollback()
    finally:
        db.close()

def authenticate_tenant():
    """Test tenant authentication with password"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    print("=== Tenant Authentication Test ===")
    
    # Get authentication details
    name = input("Tenant Name: ")
    password = getpass("Password: ")
    
    if not name or not password:
        print("Error: Tenant name and password are required")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if tenant exists
        tenant = db.query(Tenant).filter(
            Tenant.name == name,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            print("Error: Tenant not found or inactive")
            return
        
        # Check if tenant has a password
        if not hasattr(tenant, 'hashed_password') or not tenant.hashed_password:
            print("Error: Tenant does not have a password set")
            return
        
        # Verify password
        if verify_password(password, tenant.hashed_password):
            print(f"Authentication successful for tenant: {tenant.name}")
            print(f"Tenant API Key: {tenant.api_key}")
        else:
            print("Error: Invalid password")
        
    except Exception as e:
        print(f"Error during authentication: {e}")
    finally:
        db.close()

def list_tenants():
    """List all tenants in the system"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    print("=== Tenant List ===")
    
    # Create database session
    db = SessionLocal()
    
    try:
        tenants = db.query(Tenant).all()
        
        if not tenants:
            print("No tenants found in the system")
            return
        
        print(f"Found {len(tenants)} tenant(s):")
        for i, tenant in enumerate(tenants, 1):
            status = "Active" if tenant.is_active else "Inactive"
            print(f"{i}. {tenant.name} (ID: {tenant.id}) - {status}")
            print(f"   API Key: {tenant.api_key}")
            if tenant.description:
                print(f"   Description: {tenant.description}")
            
            # Show contact email if it exists
            has_email = hasattr(tenant, 'contact_email') and tenant.contact_email is not None
            if has_email:
                print(f"   Contact Email: {tenant.contact_email}")
            else:
                print("   Contact Email: Not provided")
            
            has_password = hasattr(tenant, 'hashed_password') and tenant.hashed_password is not None
            print(f"   Password Protected: {'Yes' if has_password else 'No'}")
            print()
        
    except Exception as e:
        print(f"Error listing tenants: {e}")
    finally:
        db.close()

def reset_tenant_password():
    """Reset a tenant's password"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    print("=== Reset Tenant Password ===")
    
    # Get tenant ID
    tenant_id = input("Enter Tenant ID: ")
    if not tenant_id or not tenant_id.isdigit():
        print("Error: Invalid tenant ID")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
        if not tenant:
            print(f"Error: No tenant found with ID {tenant_id}")
            return
        
        # Check if tenant has a password field
        if not hasattr(tenant, 'hashed_password'):
            print("Error: Tenant model does not have a password field")
            return
        
        # Get new password
        new_password = getpass("New Password: ")
        confirm_password = getpass("Confirm New Password: ")
        
        if not new_password:
            print("Error: Password is required")
            return
        
        if new_password != confirm_password:
            print("Error: Passwords don't match")
            return
        
        # Update password
        tenant.hashed_password = get_password_hash(new_password)
        db.commit()
        
        print(f"Password reset successfully for tenant '{tenant.name}'")
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        db.rollback()
    finally:
        db.close()

def update_tenant_contact_email():
    """Update a tenant's contact email"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    
    print("=== Update Tenant Contact Email ===")
    
    # Get tenant ID
    tenant_id = input("Enter Tenant ID: ")
    if not tenant_id or not tenant_id.isdigit():
        print("Error: Invalid tenant ID")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
        if not tenant:
            print(f"Error: No tenant found with ID {tenant_id}")
            return
        
        # Check if tenant has a contact_email field
        if not hasattr(tenant, 'contact_email'):
            print("The tenant model does not have a contact_email field.")
            print("Let's add it to the database schema.")
            
            from sqlalchemy import text
            db.execute(text("ALTER TABLE tenants ADD COLUMN contact_email TEXT"))
            db.commit()
            print("Added contact_email column to tenants table")
            
            # Add the column to the model as well
            from sqlalchemy import Column, String
            Tenant.contact_email = Column(String)
        
        # Show current email if any
        current_email = tenant.contact_email if hasattr(tenant, 'contact_email') else None
        if current_email:
            print(f"Current contact email: {current_email}")
        else:
            print("No contact email currently set")
        
        # Get new email
        new_email = input("New Contact Email: ")
        
        if not new_email:
            print("Error: Contact email is required")
            return
        
        # Update email
        tenant.contact_email = new_email
        db.commit()
        
        print(f"Contact email updated successfully for tenant '{tenant.name}'")
        
    except Exception as e:
        print(f"Error updating contact email: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main menu"""
    while True:
        print("\n=== Tenant Management ===")
        print("1. Create new tenant with password")
        print("2. List all tenants")
        print("3. Test tenant authentication")
        print("4. Reset tenant password")
        print("5. Update tenant contact email")  # Added new option
        print("0. Exit")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            create_tenant_with_password()
        elif choice == "2":
            list_tenants()
        elif choice == "3":
            authenticate_tenant()
        elif choice == "4":
            reset_tenant_password()
        elif choice == "5":
            update_tenant_contact_email()  # Added new function
        elif choice == "0":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()