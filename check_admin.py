# DATABASE ADMIN DETAILS CHECKER SCRIPT
# ======================================
# This script checks your database for admin details and provides useful debugging info

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import logging

# Add your app directory to the path (adjust as needed)
sys.path.append('/Users/mac/Downloads/chatbot')  # Update this path

try:
    from app.config import settings
    from app.admin.models import Admin
    from app.tenants.models import Tenant
    from app.database import get_db, SessionLocal, engine
    from app.core.security import get_password_hash, verify_password
    print("✅ Successfully imported app modules")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please update the sys.path.append() line with your correct project path")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_database_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def check_admin_table_exists():
    """Check if admin table exists"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if 'admins' in tables:
            print("✅ 'admins' table exists")
            
            # Get column info
            columns = inspector.get_columns('admins')
            print("📋 Admin table columns:")
            for col in columns:
                print(f"   - {col['name']}: {col['type']}")
            return True
        else:
            print("❌ 'admins' table does not exist")
            print(f"📋 Available tables: {tables}")
            return False
    except Exception as e:
        print(f"❌ Error checking admin table: {e}")
        return False

def list_all_admins():
    """List all admins in the database"""
    try:
        db = SessionLocal()
        admins = db.query(Admin).all()
        
        if not admins:
            print("📭 No admins found in database")
            return []
        
        print(f"👥 Found {len(admins)} admin(s):")
        print("-" * 80)
        
        for admin in admins:
            print(f"ID: {admin.id}")
            print(f"Username: {admin.username}")
            print(f"Email: {admin.email}")
            print(f"Name: {getattr(admin, 'name', 'N/A')}")
            print(f"Is Active: {admin.is_active}")
            print(f"Created At: {getattr(admin, 'created_at', 'N/A')}")
            print(f"Password Hash: {admin.hashed_password[:20]}..." if admin.hashed_password else "No password")
            print("-" * 40)
        
        db.close()
        return admins
        
    except Exception as e:
        print(f"❌ Error listing admins: {e}")
        return []

def test_admin_password(admin_email, test_password):
    """Test if a password works for an admin"""
    try:
        db = SessionLocal()
        admin = db.query(Admin).filter(Admin.email == admin_email).first()
        
        if not admin:
            print(f"❌ Admin with email {admin_email} not found")
            return False
        
        if verify_password(test_password, admin.hashed_password):
            print(f"✅ Password '{test_password}' is correct for {admin_email}")
            return True
        else:
            print(f"❌ Password '{test_password}' is incorrect for {admin_email}")
            return False
            
        db.close()
    except Exception as e:
        print(f"❌ Error testing password: {e}")
        return False

def create_test_admin():
    """Create a test admin if none exists"""
    try:
        db = SessionLocal()
        
        # Check if test admin already exists
        existing_admin = db.query(Admin).filter(Admin.email == "admin@test.com").first()
        if existing_admin:
            print("ℹ️ Test admin already exists")
            return existing_admin
        
        # Create new test admin
        test_admin = Admin(
            username="testadmin",
            email="admin@test.com",
            name="Test Admin",
            hashed_password=get_password_hash("admin123"),
            is_active=True
        )
        
        db.add(test_admin)
        db.commit()
        db.refresh(test_admin)
        
        print("✅ Test admin created successfully!")
        print(f"   Email: admin@test.com")
        print(f"   Password: admin123")
        
        db.close()
        return test_admin
        
    except Exception as e:
        print(f"❌ Error creating test admin: {e}")
        if 'db' in locals():
            db.rollback()
            db.close()
        return None

def check_tenants_summary():
    """Quick summary of tenants table"""
    try:
        db = SessionLocal()
        tenant_count = db.query(Tenant).count()
        active_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
        
        print(f"🏢 Tenants Summary:")
        print(f"   Total tenants: {tenant_count}")
        print(f"   Active tenants: {active_tenants}")
        
        if tenant_count > 0:
            recent_tenants = db.query(Tenant).order_by(Tenant.id.desc()).limit(3).all()
            print(f"   Recent tenants:")
            for tenant in recent_tenants:
                print(f"     - {tenant.name} ({tenant.email})")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error checking tenants: {e}")

def run_full_database_check():
    """Run complete database diagnostic"""
    print("🔍 STARTING DATABASE ADMIN CHECK")
    print("=" * 50)
    
    # 1. Test database connection
    if not check_database_connection():
        return
    
    # 2. Check if admin table exists
    if not check_admin_table_exists():
        print("\n💡 Admin table doesn't exist. You may need to run database migrations.")
        return
    
    # 3. List all admins
    print("\n👥 CHECKING ADMIN ACCOUNTS")
    print("-" * 30)
    admins = list_all_admins()
    
    # 4. Create test admin if no admins exist
    if not admins:
        print("\n🔧 CREATING TEST ADMIN")
        print("-" * 25)
        create_test_admin()
        admins = list_all_admins()  # Refresh list
    
    # 5. Test login credentials for existing admins
    if admins:
        print("\n🔐 TESTING ADMIN PASSWORDS")
        print("-" * 30)
        
        # Test common passwords for existing admins
        test_passwords = ["admin123", "password", "admin", "test123"]
        
        for admin in admins[:2]:  # Test first 2 admins only
            print(f"\nTesting passwords for {admin.email}:")
            for pwd in test_passwords:
                if test_admin_password(admin.email, pwd):
                    break
            else:
                print(f"   None of the common passwords worked for {admin.email}")
    
    # 6. Check tenants summary
    print("\n🏢 TENANT SUMMARY")
    print("-" * 20)
    check_tenants_summary()
    
    # 7. Print curl test command
    print("\n🧪 QUICK TEST COMMAND")
    print("-" * 25)
    if admins:
        test_admin = next((a for a in admins if a.email == "admin@test.com"), admins[0])
        print(f"Test this admin login with curl:")
        print(f'curl -X POST "http://localhost:8000/tenants/login" \\')
        print(f'  -H "Content-Type: application/json" \\')
        print(f'  -d \'{{"email": "{test_admin.email}", "password": "admin123"}}\'')
    
    print("\n✅ DATABASE CHECK COMPLETE")

def interactive_admin_manager():
    """Interactive admin management"""
    while True:
        print("\n🛠️ ADMIN MANAGER")
        print("1. List all admins")
        print("2. Create test admin")
        print("3. Test admin password")
        print("4. Check database tables")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            list_all_admins()
        elif choice == "2":
            create_test_admin()
        elif choice == "3":
            email = input("Enter admin email: ").strip()
            password = input("Enter password to test: ").strip()
            test_admin_password(email, password)
        elif choice == "4":
            check_admin_table_exists()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Admin Checker")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("--create-admin", "-c", action="store_true", help="Create test admin only")
    parser.add_argument("--list", "-l", action="store_true", help="List admins only")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_admin_manager()
    elif args.create_admin:
        create_test_admin()
    elif args.list:
        list_all_admins()
    else:
        run_full_database_check()


# QUICK STANDALONE ADMIN CREATOR
# ==============================

def quick_create_admin():
    """Standalone function to quickly create an admin"""
    try:
        # Update this path to match your project
        sys.path.append('/Users/mac/Downloads/chatbot')
        
        from app.database import SessionLocal
        from app.admin.models import Admin
        from app.core.security import get_password_hash
        
        db = SessionLocal()
        
        # Check if admin exists
        existing = db.query(Admin).filter(Admin.email == "admin@test.com").first()
        if existing:
            print("Admin already exists!")
            return
        
        # Create admin
        admin = Admin(
            username="testadmin",
            email="admin@test.com", 
            name="Test Admin",
            hashed_password=get_password_hash("admin123"),
            is_active=True
        )
        
        db.add(admin)
        db.commit()
        
        print("✅ Test admin created!")
        print("Email: admin@test.com")
        print("Password: admin123")
        
        db.close()
        
    except Exception as e:
        print(f"Error: {e}")

# Uncomment this line to quickly create an admin:
# quick_create_admin()


# USAGE INSTRUCTIONS
print("""
📖 USAGE INSTRUCTIONS:

1. QUICK RUN (full check):
   python check_admin.py

2. INTERACTIVE MODE:
   python check_admin.py --interactive

3. CREATE ADMIN ONLY:
   python check_admin.py --create-admin

4. LIST ADMINS ONLY:
   python check_admin.py --list

BEFORE RUNNING:
- Update the sys.path.append() line with your project path
- Make sure your database is running
- Ensure your .env file is configured

COMMON ISSUES:
- Import errors: Check your project path
- Database errors: Ensure database is running and accessible
- No admins found: Script will create a test admin automatically
""")