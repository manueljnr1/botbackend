#!/usr/bin/env python3
"""
Complete Tenant Creator with Password Support
Creates both tenant record AND tenant credentials (password)
"""

import sys
import os
import getpass
import secrets
import string
from datetime import datetime, timezone

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def generate_api_key():
    """Generate a secure API key"""
    return f"sk-{str(__import__('uuid').uuid4()).replace('-', '')}"

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    import bcrypt
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

def create_admin_user():
    """Create admin user using your exact schema"""
    
    from sqlalchemy import create_engine, text
    from app.config import settings
    
    print("🔧 Create Admin User")
    print("=" * 30)
    
    # Get user input
    username = input("Enter admin username: ").strip()
    email = input("Enter admin email: ").strip()
    
    try:
        password = getpass.getpass("Enter admin password (hidden): ")
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return None
    
    if not all([username, email, password]):
        print("❌ Username, email, and password are required")
        return None
    
    # Hash password
    try:
        hashed_password = hash_password(password)
    except Exception as e:
        print(f"❌ Error hashing password: {e}")
        return None
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.begin() as conn:
            # Check if user already exists
            check_query = text("""
                SELECT id, username, email, is_admin 
                FROM users 
                WHERE username = :username OR email = :email
            """)
            
            existing = conn.execute(check_query, {
                "username": username, 
                "email": email
            }).fetchone()
            
            if existing:
                print(f"❌ User already exists: {existing.username} ({existing.email})")
                
                if existing.is_admin:
                    print("✅ User is already an admin")
                    return existing.id
                else:
                    promote = input("Would you like to promote this user to admin? (y/n): ").lower()
                    if promote == 'y':
                        update_query = text("""
                            UPDATE users 
                            SET is_admin = :is_admin 
                            WHERE id = :user_id
                        """)
                        
                        conn.execute(update_query, {
                            "is_admin": True,
                            "user_id": existing.id
                        })
                        
                        print(f"✅ User '{existing.username}' promoted to admin!")
                        return existing.id
                    else:
                        return None
            
            # Create new admin user
            insert_query = text("""
                INSERT INTO users (username, email, hashed_password, is_active, is_admin, created_at)
                VALUES (:username, :email, :hashed_password, :is_active, :is_admin, :created_at)
                RETURNING id
            """)
            
            result = conn.execute(insert_query, {
                "username": username,
                "email": email,
                "hashed_password": hashed_password,
                "is_active": True,
                "is_admin": True,
                "created_at": datetime.now(timezone.utc)
            })
            
            user_id = result.fetchone().id
            
            print("\n🎉 Admin user created successfully!")
            print(f"   Username: {username}")
            print(f"   Email: {email}")
            print(f"   User ID: {user_id}")
            
            return user_id
            
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_complete_tenant(admin_user_id=None):
    """Create tenant with BOTH tenant record AND password credentials"""
    
    from sqlalchemy import create_engine, text
    from app.config import settings
    
    print("\n🏢 Create Complete Tenant (with Password)")
    print("=" * 45)
    
    # Get tenant input
    name = input("Enter tenant name/username: ").strip()
    description = input("Enter description (optional): ").strip() or None
    company_name = input("Enter company name: ").strip() or name
    contact_email = input("Enter contact email: ").strip()
    
    try:
        password = getpass.getpass("Enter tenant password (hidden): ")
        confirm_password = getpass.getpass("Confirm password (hidden): ")
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        return None
    
    if password != confirm_password:
        print("❌ Passwords don't match!")
        return None
    
    if not all([name, contact_email, password]):
        print("❌ Tenant name, contact email, and password are required")
        return None
    
    # Generate API key and hash password
    api_key = generate_api_key()
    
    try:
        hashed_password = hash_password(password)
    except Exception as e:
        print(f"❌ Error hashing password: {e}")
        return None
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.begin() as conn:
            # Check if tenant already exists
            check_query = text("""
                SELECT id, name, api_key FROM tenants 
                WHERE name = :name
            """)
            
            existing = conn.execute(check_query, {"name": name}).fetchone()
            
            if existing:
                print(f"❌ Tenant already exists: {existing.name}")
                return existing.id
            
            # Create new tenant
            tenant_insert_query = text("""
                INSERT INTO tenants (
                    name, description, api_key, is_active, contact_email, 
                    company_name, enable_feedback_system, feedback_notification_enabled,
                    discord_enabled, slack_enabled, created_at, updated_at
                )
                VALUES (
                    :name, :description, :api_key, :is_active, :contact_email,
                    :company_name, :enable_feedback_system, :feedback_notification_enabled,
                    :discord_enabled, :slack_enabled, :created_at, :updated_at
                )
                RETURNING id
            """)
            
            tenant_result = conn.execute(tenant_insert_query, {
                "name": name,
                "description": description,
                "api_key": api_key,
                "is_active": True,
                "contact_email": contact_email,
                "company_name": company_name,
                "enable_feedback_system": True,
                "feedback_notification_enabled": True,
                "discord_enabled": False,
                "slack_enabled": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            })
            
            tenant_id = tenant_result.fetchone().id
            
            print(f"✅ Tenant created with ID: {tenant_id}")
            
            # Create tenant credentials (PASSWORD)
            credentials_insert_query = text("""
                INSERT INTO tenant_credentials (tenant_id, hashed_password, created_at)
                VALUES (:tenant_id, :hashed_password, :created_at)
                RETURNING id
            """)
            
            credentials_result = conn.execute(credentials_insert_query, {
                "tenant_id": tenant_id,
                "hashed_password": hashed_password,
                "created_at": datetime.now(timezone.utc)
            })
            
            credentials_id = credentials_result.fetchone().id
            
            print(f"✅ Tenant credentials created with ID: {credentials_id}")
            
            print("\n🎉 Complete tenant created successfully!")
            print(f"   🏢 Name: {name}")
            print(f"   🏭 Company: {company_name}")
            print(f"   📧 Contact: {contact_email}")
            print(f"   🆔 Tenant ID: {tenant_id}")
            print(f"   🔑 API Key: {api_key}")
            print(f"   🔐 Password: ✅ Set and hashed")
            print(f"   🔵 Status: Active")
            
            # Optionally link admin user to tenant
            if admin_user_id:
                link = input(f"\nWould you like to link the admin user to this tenant? (y/n): ").lower()
                if link == 'y':
                    update_user_query = text("""
                        UPDATE users 
                        SET tenant_id = :tenant_id 
                        WHERE id = :user_id
                    """)
                    
                    conn.execute(update_user_query, {
                        "tenant_id": tenant_id,
                        "user_id": admin_user_id
                    })
                    
                    print(f"✅ Admin user linked to tenant {name}")
            
            print(f"\n🔐 IMPORTANT - SAVE THESE CREDENTIALS:")
            print(f"   Username: {name}")
            print(f"   Password: {password}")
            print(f"   API Key: {api_key}")
            print("\n   You'll need these for:")
            print("   • 🔑 JWT Login (dashboard access)")
            print("   • 🤖 API Key (chatbot requests)")
            
            return tenant_id
            
    except Exception as e:
        print(f"❌ Error creating tenant: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_tenant_authentication(tenant_name: str, password: str):
    """Test that tenant authentication works"""
    
    from sqlalchemy import create_engine, text
    from app.config import settings
    import bcrypt
    
    print(f"\n🧪 Testing Authentication for: {tenant_name}")
    print("-" * 40)
    
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Get tenant and credentials
            test_query = text("""
                SELECT t.id, t.name, t.api_key, t.is_active, tc.hashed_password
                FROM tenants t
                LEFT JOIN tenant_credentials tc ON t.id = tc.tenant_id
                WHERE t.name = :name
            """)
            
            result = conn.execute(test_query, {"name": tenant_name}).fetchone()
            
            if not result:
                print("❌ Tenant not found")
                return False
            
            print(f"✅ Tenant found: {result.name} (ID: {result.id})")
            print(f"✅ API Key: {result.api_key[:10]}...")
            print(f"✅ Active: {result.is_active}")
            
            if not result.hashed_password:
                print("❌ No password credentials found!")
                return False
            
            # Test password verification
            try:
                password_bytes = password.encode('utf-8')
                hashed_bytes = result.hashed_password.encode('utf-8')
                password_valid = bcrypt.checkpw(password_bytes, hashed_bytes)
                
                if password_valid:
                    print("✅ Password verification: SUCCESS")
                    print(f"✅ Ready for login at: /tenants/login")
                    return True
                else:
                    print("❌ Password verification: FAILED")
                    return False
                    
            except Exception as e:
                print(f"❌ Password verification error: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Authentication test error: {e}")
        return False

def main():
    """Main function"""
    
    # Check dependencies
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
    
    print("🛠️ COMPLETE ADMIN & TENANT CREATOR")
    print("Creates admin user AND tenant with password")
    print("=" * 55)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "admin":
            create_admin_user()
        elif command == "tenant":
            create_complete_tenant()
        elif command == "both":
            admin_id = create_admin_user()
            if admin_id:
                tenant_id = create_complete_tenant(admin_id)
                if tenant_id:
                    # Test authentication
                    tenant_name = input("\nTest authentication? Enter tenant name (or press Enter to skip): ").strip()
                    if tenant_name:
                        password = getpass.getpass("Enter password to test: ")
                        test_tenant_authentication(tenant_name, password)
        elif command == "test":
            tenant_name = input("Enter tenant name to test: ").strip()
            password = getpass.getpass("Enter password: ")
            test_tenant_authentication(tenant_name, password)
        else:
            print("Usage:")
            print("  python script.py admin     - Create admin user only")
            print("  python script.py tenant    - Create tenant only") 
            print("  python script.py both      - Create admin + tenant")
            print("  python script.py test      - Test tenant authentication")
    else:
        # Interactive mode
        print("\nWhat would you like to create?")
        print("1. Admin user only")
        print("2. Complete tenant (with password)")
        print("3. Both admin user and tenant (recommended)")
        print("4. Test tenant authentication")
        
        choice = input("\nEnter choice (1-4, default=3): ").strip() or "3"
        
        if choice == "1":
            create_admin_user()
        elif choice == "2":
            create_complete_tenant()
        elif choice == "3":
            admin_id = create_admin_user()
            if admin_id:
                tenant_id = create_complete_tenant(admin_id)
                if tenant_id:
                    print("\n🧪 Would you like to test the authentication?")
                    test_choice = input("Test now? (y/n): ").lower()
                    if test_choice == 'y':
                        tenant_name = input("Enter tenant name: ").strip()
                        password = getpass.getpass("Enter password: ")
                        test_tenant_authentication(tenant_name, password)
        elif choice == "4":
            tenant_name = input("Enter tenant name to test: ").strip()
            password = getpass.getpass("Enter password: ")
            test_tenant_authentication(tenant_name, password)
        else:
            print("❌ Invalid choice")
    
    print("\n✅ Complete setup finished!")
    print("\nYour tenant now has:")
    print("🔑 JWT Authentication (username + password)")
    print("🤖 API Key Authentication (for chatbot)")
    print("📊 Both methods work with your existing system!")

if __name__ == "__main__":
    main()