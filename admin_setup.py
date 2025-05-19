# admin_setup.py
import argparse
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.auth.models import User
from app.core.security import get_password_hash

def create_admin_user(username, email, password):
    db = SessionLocal()
    try:
        # Check if admin user already exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"User '{username}' already exists.")
            return
        
        # Create new admin user
        admin_user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            is_admin=True,
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        print(f"Admin user '{username}' created successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("username", help="Admin username")
    parser.add_argument("email", help="Admin email address")
    parser.add_argument("password", help="Admin password")
    
    args = parser.parse_args()
    create_admin_user(args.username, args.email, args.password)