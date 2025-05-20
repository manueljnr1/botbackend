import sys
import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

# Adjust these imports to match your actual project structure
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import Base
from app.admin.models import Admin  # Adjust this import based on where your Admin model is defined
from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin(username, email, name, password):
    # Connect to database
    # Change DATABASE_URI to DATABASE_URL as per the error message
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(Admin).filter(
            (Admin.username == username) | (Admin.email == email)
        ).first()
        
        if existing_admin:
            print(f"❌ Admin with username '{username}' or email '{email}' already exists.")
            return
        
        # Create new admin
        admin_id = uuid.uuid4()
        hashed_password = pwd_context.hash(password)
        
        new_admin = Admin(
            id=admin_id,
            username=username,
            email=email,
            name=name,
            hashed_password=hashed_password,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(new_admin)
        db.commit()
        
        print(f"✅ Admin created successfully!")
        print(f"ID: {admin_id}")
        print(f"Username: {username}")
        print(f"Email: {email}")
        print(f"Name: {name}")
        
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    username = input("Enter admin username: ")
    email = input("Enter admin email: ")
    name = input("Enter admin name: ")
    password = input("Enter admin password (visible): ")
    
    if not username or not email or not password:
        print("❌ All fields are required")
        sys.exit(1)
        
    create_admin(username, email, name, password)