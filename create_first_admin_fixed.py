#!/usr/bin/env python3
"""
Fixed Create First Admin Script
Handles SQLAlchemy relationship issues and creates admin users safely
"""

import sys
import os
import getpass
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def create_admin_with_raw_sql():
    """Create admin using raw SQL to avoid relationship issues"""
    
    from sqlalchemy import create_engine, text
    from app.config import settings
    import bcrypt
    
    # Get user input
    print("🔧 Creating First Admin User")
    print("=" * 30)
    
    username = input("Enter admin username: ").strip()
    email = input("Enter admin email: ").strip()
    full_name = input("Enter admin name: ").strip()
    
    # Get password securely
    try:
        password = getpass.getpass("Enter admin password (hidden): ")
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return
    
    if not all([username, email, full_name, password]):
        print("❌ All fields are required")
        return
    
    # Validate email format
    if "@" not in email or "." not in email:
        print("❌ Invalid email format")
        return
    
    # Hash password
    try:
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    except Exception as e:
        print(f"❌ Error hashing password: {e}")
        return
    
    # Create database connection
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.begin() as conn:  # Use transaction
            # Check if user already exists
            check_user_query = text("""
                SELECT id, username, email FROM users 
                WHERE username = :username OR email = :email
            """)
            
            existing_user = conn.execute(check_user_query, {
                "username": username, 
                "email": email
            }).fetchone()
            
            if existing_user:
                print(f"❌ User already exists: {existing_user.username} ({existing_user.email})")
                
                # Ask if they want to promote existing user to admin
                promote = input("Would you like to promote this user to admin? (y/n): ").lower()
                if promote == 'y':
                    # Check if already admin
                    check_admin_query = text("""
                        SELECT id FROM admin_users WHERE user_id = :user_id
                    """)
                    existing_admin = conn.execute(check_admin_query, {
                        "user_id": existing_user.id
                    }).fetchone()
                    
                    if existing_admin:
                        print("✅ User is already an admin")
                    else:
                        # Promote to admin
                        insert_admin_query = text("""
                            INSERT INTO admin_users (user_id, created_at) 
                            VALUES (:user_id, :created_at)
                        """)
                        conn.execute(insert_admin_query, {
                            "user_id": existing_user.id,
                            "created_at": datetime.utcnow()
                        })
                        print(f"✅ User '{existing_user.username}' promoted to admin successfully!")
                return
            
            # Create new user
            insert_user_query = text("""
                INSERT INTO users (username, email, full_name, hashed_password, is_active, is_verified, created_at)
                VALUES (:username, :email, :full_name, :hashed_password, :is_active, :is_verified, :created_at)
                RETURNING id
            """)
            
            result = conn.execute(insert_user_query, {
                "username": username,
                "email": email,
                "full_name": full_name,
                "hashed_password": hashed_password,
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.utcnow()
            })
            
            user_id = result.fetchone().id
            print(f"✅ User created with ID: {user_id}")
            
            # Create admin record
            insert_admin_query = text("""
                INSERT INTO admin_users (user_id, created_at)
                VALUES (:user_id, :created_at)
                RETURNING id
            """)
            
            admin_result = conn.execute(insert_admin_query, {
                "user_id": user_id,
                "created_at": datetime.utcnow()
            })
            
            admin_id = admin_result.fetchone().id
            print(f"✅ Admin record created with ID: {admin_id}")
            
            print("\n🎉 First admin user created successfully!")
            print(f"   Username: {username}")
            print(f"   Email: {email}")
            print(f"   Name: {full_name}")
            print(f"   User ID: {user_id}")
            print(f"   Admin ID: {admin_id}")
            print("\n🔐 You can now log in with these credentials")
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        import traceback
        traceback.print_exc()

def create_admin_with_sqlalchemy():
    """Alternative method using SQLAlchemy with careful imports"""
    
    try:
        # Import models one by one to avoid relationship issues
        from app.database import SessionLocal
        
        # Import base models first
        from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
        from sqlalchemy.orm import declarative_base
        from app.database import Base
        
        # Create minimal User class to avoid relationship issues
        class User(Base):
            __tablename__ = "users"
            
            id = Column(Integer, primary_key=True, index=True)
            username = Column(String, unique=True, index=True)
            email = Column(String, unique=True, index=True)
            full_name = Column(String)
            hashed_password = Column(String)
            is_active = Column(Boolean, default=True)
            is_verified = Column(Boolean, default=False)
            created_at = Column(DateTime, default=datetime.utcnow)
        
        # Create minimal AdminUser class
        class AdminUser(Base):
            __tablename__ = "admin_users"
            
            id = Column(Integer, primary_key=True, index=True)
            user_id = Column(Integer, ForeignKey("users.id"))
            created_at = Column(DateTime, default=datetime.utcnow)
        
        # Now create admin
        print("🔧 Creating First Admin User (SQLAlchemy Method)")
        print("=" * 45)
        
        username = input("Enter admin username: ").strip()
        email = input("Enter admin email: ").strip()
        full_name = input("Enter admin name: ").strip()
        
        try:
            password = getpass.getpass("Enter admin password (hidden): ")
        except KeyboardInterrupt:
            print("\n❌ Operation cancelled")
            return
        
        if not all([username, email, full_name, password]):
            print("❌ All fields are required")
            return
        
        # Hash password
        import bcrypt
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        
        # Create database session
        db = SessionLocal()
        
        try:
            # Check if user exists
            existing = db.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing:
                print(f"❌ User already exists: {existing.username} ({existing.email})")
                
                # Check if already admin
                admin = db.query(AdminUser).filter(AdminUser.user_id == existing.id).first()
                if admin:
                    print("✅ User is already an admin")
                else:
                    promote = input("Promote to admin? (y/n): ").lower()
                    if promote == 'y':
                        new_admin = AdminUser(user_id=existing.id)
                        db.add(new_admin)
                        db.commit()
                        print(f"✅ User '{existing.username}' promoted to admin!")
                return
            
            # Create new user
            new_user = User(
                username=username,
                email=email,
                full_name=full_name,
                hashed_password=hashed_password,
                is_active=True,
                is_verified=True
            )
            
            db.add(new_user)
            db.flush()  # Get the ID
            
            # Create admin record
            new_admin = AdminUser(user_id=new_user.id)
            db.add(new_admin)
            
            db.commit()
            
            print("\n🎉 First admin user created successfully!")
            print(f"   Username: {username}")
            print(f"   Email: {email}")
            print(f"   User ID: {new_user.id}")
            print(f"   Admin ID: {new_admin.id}")
            
        except Exception as e:
            db.rollback()
            print(f"❌ Error: {e}")
            
        finally:
            db.close()
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Falling back to raw SQL method...")
        create_admin_with_raw_sql()

def main():
    """Main function with method selection"""
    
    print("🛠️ Admin User Creator - Fixed Version")
    print("Handles SQLAlchemy relationship issues")
    print("=" * 45)
    
    # Check if bcrypt is available
    try:
        import bcrypt
    except ImportError:
        print("❌ bcrypt library not found. Installing...")
        os.system("pip install bcrypt")
        try:
            import bcrypt
            print("✅ bcrypt installed successfully")
        except ImportError:
            print("❌ Failed to install bcrypt. Please install manually: pip install bcrypt")
            return
    
    print("\nChoose creation method:")
    print("1. Raw SQL method (recommended - avoids relationship issues)")
    print("2. SQLAlchemy method (may have relationship issues)")
    print("3. Auto-detect best method")
    
    choice = input("\nEnter choice (1-3, default=1): ").strip() or "1"
    
    if choice == "1":
        create_admin_with_raw_sql()
    elif choice == "2":
        create_admin_with_sqlalchemy()
    elif choice == "3":
        # Try SQLAlchemy first, fall back to raw SQL
        try:
            create_admin_with_sqlalchemy()
        except Exception as e:
            print(f"⚠️ SQLAlchemy method failed: {e}")
            print("🔄 Trying raw SQL method...")
            create_admin_with_raw_sql()
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()