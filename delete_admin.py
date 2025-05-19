# delete_admin.py

import argparse
import sys
from sqlalchemy.orm import Session
from sqlalchemy import or_

# Import your models and database settings
# Adjust import paths as needed based on your project structure
from app.database import get_db, SessionLocal
from app.auth.models import User

def get_db_session():
    """Create and return a database session"""
    return SessionLocal()

def find_admin(db: Session, identifier: str):
    """
    Find an admin user by username, email, or ID
    """
    # Check if identifier is an ID (integer)
    try:
        if identifier.isdigit():
            user = db.query(User).filter(
                User.id == int(identifier),
                User.is_admin == True
            ).first()
            if user:
                return user
    except:
        pass
    
    # Try to find by username or email
    user = db.query(User).filter(
        or_(User.username == identifier, User.email == identifier),
        User.is_admin == True
    ).first()
    
    return user

def list_admins(db: Session):
    """List all admin users in the system"""
    admins = db.query(User).filter(User.is_admin == True).all()
    
    if not admins:
        print("No admin users found in the system.")
        return
    
    print("\nList of admin users:")
    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Active':<10}")
    print("-" * 65)
    
    for admin in admins:
        status = "Active" if admin.is_active else "Inactive"
        print(f"{admin.id:<5} {admin.username:<20} {admin.email:<30} {status:<10}")
    
    print()

def delete_admin(db: Session, identifier: str, force: bool = False):
    """Delete an admin user by username, email, or ID"""
    admin = find_admin(db, identifier)
    
    if not admin:
        print(f"Error: No admin user found matching '{identifier}'")
        return False
    
    # Show admin details
    print(f"Found admin user:")
    print(f"ID: {admin.id}")
    print(f"Username: {admin.username}")
    print(f"Email: {admin.email}")
    print(f"Status: {'Active' if admin.is_active else 'Inactive'}")
    
    # Check if this is the last admin
    admin_count = db.query(User).filter(User.is_admin == True).count()
    if admin_count <= 1:
        print("\nWARNING: This appears to be the last admin user in the system.")
        print("Deleting this user will leave the system without any administrators.")
        print("It's recommended to create another admin user before proceeding.")
        
        if not force:
            extra_confirm = input("Are you REALLY sure you want to delete the last admin? Type 'CONFIRM' to proceed: ")
            if extra_confirm != "CONFIRM":
                print("Operation cancelled.")
                return False
    
    # Get confirmation unless force flag is set
    if not force:
        confirm = input(f"\nAre you sure you want to delete admin '{admin.username}'? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return False
    
    # Decide between permanent deletion and deactivation
    if not force:
        delete_type = input("Permanently delete user or just deactivate? (delete/deactivate): ")
        
        if delete_type.lower() == 'deactivate':
            # Just deactivate the user
            admin.is_active = False
            db.commit()
            print(f"Admin user '{admin.username}' has been deactivated.")
            return True
        elif delete_type.lower() != 'delete':
            print("Invalid option. Operation cancelled.")
            return False
    
    # Permanently delete the user
    db.delete(admin)
    db.commit()
    print(f"Admin user '{admin.username}' has been permanently deleted.")
    return True

def main():
    parser = argparse.ArgumentParser(description='Admin User Management Script')
    parser.add_argument('action', choices=['list', 'delete'], 
                        help='Action to perform: list or delete')
    parser.add_argument('--identifier', type=str,
                        help='Username, email, or ID of the admin to delete')
    parser.add_argument('--force', action='store_true', 
                        help='Force deletion without confirmation')
    
    args = parser.parse_args()
    
    db = get_db_session()
    
    try:
        if args.action == 'list':
            list_admins(db)
        
        elif args.action == 'delete':
            if not args.identifier:
                print("Error: --identifier is required for delete action")
                parser.print_help()
                return 1
            
            delete_admin(db, args.identifier, args.force)
        
    finally:
        db.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())