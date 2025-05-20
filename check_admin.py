import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Adjust these imports to match your actual project structure
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import Base
from app.admin.models import Admin  # Adjust this import based on where your Admin model is defined
from app.config import settings

def check_admin(username_or_email):
    """Check if an admin exists and view its properties"""
    # Connect to database
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Find admin
        admin = db.query(Admin).filter(
            (Admin.username == username_or_email) | (Admin.email == username_or_email)
        ).first()
        
        if not admin:
            print(f"❌ No admin found with username or email: {username_or_email}")
            return
        
        # Print admin details
        print(f"✅ Admin found:")
        print(f"ID: {admin.id}")
        print(f"Username: {admin.username}")
        print(f"Email: {admin.email}")
        print(f"Name: {admin.name}")
        print(f"Is active: {admin.is_active}")
        
        # Check password hash (don't print the full hash for security)
        if hasattr(admin, 'hashed_password'):
            print(f"Has password hash: Yes ({admin.hashed_password[:10]}...)")
        elif hasattr(admin, 'password_hash'):
            print(f"Has password hash: Yes ({admin.password_hash[:10]}...)")
        else:
            print("Password field not found - check model structure")
            
        # Print all attributes for debugging
        print("\nAll admin attributes:")
        for attr in dir(admin):
            if not attr.startswith('_') and attr not in ('metadata', 'registry'):
                value = getattr(admin, attr)
                if not callable(value):
                    print(f"  {attr}: {value}")
        
    except Exception as e:
        print(f"❌ Error checking admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    username_or_email = input("Enter admin username or email to check: ")
    check_admin(username_or_email)