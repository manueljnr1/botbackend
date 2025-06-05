#!/usr/bin/env python3
"""
Working Tenant Management Script
Compatible with your exact database structure
"""
import os
import sys
import uuid
import logging
from getpass import getpass
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def get_password_hash(password):
    """Hash password using bcrypt"""
    try:
        import bcrypt
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    except ImportError:
        print("❌ bcrypt not found. Installing...")
        os.system("pip install bcrypt")
        import bcrypt
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

def verify_password(plain_password, hashed_password):
    """Verify password against hash"""
    try:
        import bcrypt
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except ImportError:
        print("❌ bcrypt not available for password verification")
        return False

def create_tenant_with_password():
    """Create a new tenant with password stored in tenant_credentials"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running this from the project root directory")
        return
    
    print("🏢 === Tenant Creation Tool ===")
    
    # Get tenant information
    name = input("Tenant Name: ").strip()
    description = input("Description (optional): ").strip() or None
    email = input("Contact Email: ").strip()
    company_name = input("Company Name (optional, defaults to tenant name): ").strip() or name
    password = getpass("Password: ")
    confirm_password = getpass("Confirm Password: ")
    
    if not name:
        print("❌ Error: Tenant name is required")
        return
    
    if not password:
        print("❌ Error: Password is required")
        return
    
    if password != confirm_password:
        print("❌ Error: Passwords don't match")
        return
    
    if not email:
        print("⚠️ Warning: No contact email provided. It's recommended to add one for password recovery.")
        proceed = input("Do you want to proceed without a contact email? (y/n): ")
        if proceed.lower() != 'y':
            return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if tenant with this name already exists
        check_query = text("SELECT id, name FROM tenants WHERE name = :name")
        existing = db.execute(check_query, {"name": name}).fetchone()
        
        if existing:
            print(f"❌ Error: A tenant with the name '{name}' already exists (ID: {existing.id})")
            return
        
        # Generate API key
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        print("🔄 Creating tenant with correct schema...")
        
        # Create tenant using raw SQL to ensure compatibility
        tenant_insert = text("""
            INSERT INTO tenants (
                name, description, api_key, is_active, email, company_name,
                enable_feedback_system, feedback_notification_enabled,
                discord_enabled, slack_enabled, created_at, updated_at
            )
            VALUES (
                :name, :description, :api_key, :is_active, :email, :company_name,
                :enable_feedback_system, :feedback_notification_enabled,
                :discord_enabled, :slack_enabled, :created_at, :updated_at
            )
            RETURNING id
        """)
        
        tenant_result = db.execute(tenant_insert, {
            "name": name,
            "description": description,
            "api_key": api_key,
            "is_active": True,
            "email": email,
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
        
        # Create tenant credentials using the correct column names
        print("🔄 Creating credentials with correct schema...")
        credentials_insert = text("""
            INSERT INTO tenant_credentials (tenant_id, hashed_password, password_updated_at)
            VALUES (:tenant_id, :hashed_password, :password_updated_at)
        """)
        
        db.execute(credentials_insert, {
            "tenant_id": tenant_id,
            "hashed_password": hashed_password,
            "password_updated_at": datetime.now(timezone.utc)
        })
        
        print(f"✅ Credentials created successfully")
        
        db.commit()
        
        print("\n🎉 === Tenant created successfully ===")
        print(f"Tenant ID: {tenant_id}")
        print(f"Tenant Name: {name}")
        print(f"Company Name: {company_name}")
        print(f"Contact Email: {email if email else 'Not provided'}")
        print(f"API Key: {api_key}")
        print(f"Password: ✅ Set and encrypted")
        print(f"Password Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n🔐 SAVE THESE CREDENTIALS:")
        print(f"   Username: {name}")
        print(f"   Password: {password}")
        print(f"   API Key: {api_key}")
        print("\n🔑 You can now:")
        print("   • Login via JWT: POST /tenants/login")
        print("   • Use API: X-API-Key header")
        print("   • Test with webchatbot interface")
        
    except Exception as e:
        print(f"❌ Error creating tenant: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def authenticate_tenant():
    """Test tenant authentication with password"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    print("🔐 === Tenant Authentication Test ===")
    
    # Get authentication details
    name = input("Tenant Name: ").strip()
    password = getpass("Password: ")
    
    if not name or not password:
        print("❌ Error: Tenant name and password are required")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Get tenant and credentials in one query
        auth_query = text("""
            SELECT t.id, t.name, t.api_key, t.is_active, tc.hashed_password
            FROM tenants t
            LEFT JOIN tenant_credentials tc ON t.id = tc.tenant_id
            WHERE t.name = :name
        """)
        
        result = db.execute(auth_query, {"name": name}).fetchone()
        
        if not result:
            print("❌ Error: Tenant not found")
            return
        
        if not result.is_active:
            print("❌ Error: Tenant account is inactive")
            return
        
        if not result.hashed_password:
            print("❌ Error: Tenant does not have password credentials set")
            return
        
        # Verify password
        if verify_password(password, result.hashed_password):
            print(f"✅ Authentication successful for tenant: {result.name}")
            print(f"✅ Tenant ID: {result.id}")
            print(f"✅ API Key: {result.api_key}")
            print(f"✅ Status: Active")
            print("\n🔑 This tenant can now:")
            print("   • Login to admin dashboard")
            print("   • Use chatbot API")
            print("   • Access all tenant features")
        else:
            print("❌ Error: Invalid password")
        
    except Exception as e:
        print(f"❌ Error during authentication: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def list_tenants():
    """List all tenants in the system"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        from datetime import datetime
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    print("📋 === Tenant List ===")
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Get all tenants with credential info
        tenants_query = text("""
            SELECT t.id, t.name, t.company_name, t.email, t.api_key, 
                   t.is_active, t.description, t.created_at,
                   CASE WHEN tc.hashed_password IS NOT NULL THEN 1 ELSE 0 END as has_password
            FROM tenants t
            LEFT JOIN tenant_credentials tc ON t.id = tc.tenant_id
            ORDER BY t.created_at DESC
        """)
        
        tenants = db.execute(tenants_query).fetchall()
        
        if not tenants:
            print("❌ No tenants found in the system")
            print("💡 Use option 1 to create your first tenant")
            return
        
        print(f"Found {len(tenants)} tenant(s):\n")
        
        for i, tenant in enumerate(tenants, 1):
            status = "🟢 Active" if tenant.is_active else "🔴 Inactive"
            password_status = "✅ Set" if tenant.has_password else "❌ Missing"
            
            # Handle created_at safely (could be string or datetime)
            try:
                if tenant.created_at:
                    if isinstance(tenant.created_at, str):
                        # Try to parse the string date
                        try:
                            parsed_date = datetime.fromisoformat(tenant.created_at.replace('Z', '+00:00'))
                            created = parsed_date.strftime("%Y-%m-%d %H:%M")
                        except:
                            created = tenant.created_at[:16]  # Just take first 16 chars
                    else:
                        created = tenant.created_at.strftime("%Y-%m-%d %H:%M")
                else:
                    created = "Unknown"
            except:
                created = "Unknown"
            
            print(f"{i}. {tenant.name}")
            print(f"   🏭 Company: {tenant.company_name or 'Not set'}")
            print(f"   🆔 ID: {tenant.id}")
            print(f"   🔵 Status: {status}")
            print(f"   🔐 Password: {password_status}")
            print(f"   📧 Email: {tenant.email or 'Not provided'}")
            print(f"   🔑 API Key: {tenant.api_key[:10]}...")
            print(f"   📅 Created: {created}")
            
            if tenant.description:
                print(f"   📝 Description: {tenant.description}")
            
            print()
        
    except Exception as e:
        print(f"❌ Error listing tenants: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def reset_tenant_password():
    """Reset a tenant's password"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text, create_engine
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    print("🔄 === Reset Tenant Password ===")
    
    # Get tenant identifier (can be ID or name)
    identifier = input("Enter Tenant ID or Tenant Name: ").strip()
    if not identifier:
        print("❌ Error: Tenant ID or name is required")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Find tenant by ID or name
        if identifier.isdigit():
            tenant_query = text("SELECT id, name FROM tenants WHERE id = :identifier")
        else:
            tenant_query = text("SELECT id, name FROM tenants WHERE name = :identifier")
        
        tenant = db.execute(tenant_query, {"identifier": identifier}).fetchone()
        
        if not tenant:
            print(f"❌ Error: No tenant found with identifier '{identifier}'")
            return
        
        print(f"Found tenant: {tenant.name} (ID: {tenant.id})")
        
        # Get new password
        new_password = getpass("New Password: ")
        confirm_password = getpass("Confirm New Password: ")
        
        if not new_password:
            print("❌ Error: Password is required")
            return
        
        if new_password != confirm_password:
            print("❌ Error: Passwords don't match")
            return
        
        # Hash new password
        hashed_password = get_password_hash(new_password)
        
        # Use the correct column names for your table
        print("🔄 Updating password with correct schema...")
        
        try:
            # Try INSERT OR REPLACE first (works with your schema)
            sqlite_query = text("""
                INSERT OR REPLACE INTO tenant_credentials (tenant_id, hashed_password, password_updated_at)
                VALUES (:tenant_id, :hashed_password, :password_updated_at)
            """)
            
            db.execute(sqlite_query, {
                "tenant_id": tenant.id,
                "hashed_password": hashed_password,
                "password_updated_at": datetime.now(timezone.utc)
            })
            
            db.commit()
            print(f"✅ Password reset successfully for tenant '{tenant.name}'")
            
        except Exception as e:
            print(f"❌ Error with INSERT OR REPLACE: {e}")
            print("🔄 Trying alternative approach...")
            
            # Alternative: Delete then insert
            try:
                # First check if credentials exist
                check_query = text("SELECT tenant_id FROM tenant_credentials WHERE tenant_id = :tenant_id")
                existing = db.execute(check_query, {"tenant_id": tenant.id}).fetchone()
                
                if existing:
                    # Update existing record
                    update_query = text("""
                        UPDATE tenant_credentials 
                        SET hashed_password = :hashed_password, password_updated_at = :password_updated_at
                        WHERE tenant_id = :tenant_id
                    """)
                    db.execute(update_query, {
                        "tenant_id": tenant.id,
                        "hashed_password": hashed_password,
                        "password_updated_at": datetime.now(timezone.utc)
                    })
                    print("✅ Updated existing credentials")
                else:
                    # Insert new record
                    insert_query = text("""
                        INSERT INTO tenant_credentials (tenant_id, hashed_password, password_updated_at)
                        VALUES (:tenant_id, :hashed_password, :password_updated_at)
                    """)
                    db.execute(insert_query, {
                        "tenant_id": tenant.id,
                        "hashed_password": hashed_password,
                        "password_updated_at": datetime.now(timezone.utc)
                    })
                    print("✅ Created new credentials")
                
                db.commit()
                print(f"✅ Password reset successfully for tenant '{tenant.name}' (using alternative method)")
                
            except Exception as e2:
                print(f"❌ Alternative method also failed: {e2}")
                db.rollback()
                return
        
        print(f"\n🔑 New credentials:")
        print(f"   Username: {tenant.name}")
        print(f"   Password: {new_password}")
        print(f"   Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def update_tenant_email():
    """Update a tenant's contact email"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    print("📧 === Update Tenant Contact Email ===")
    
    # Get tenant identifier
    identifier = input("Enter Tenant ID or Tenant Name: ").strip()
    if not identifier:
        print("❌ Error: Tenant ID or name is required")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Find tenant
        if identifier.isdigit():
            tenant_query = text("SELECT id, name, email FROM tenants WHERE id = :identifier")
        else:
            tenant_query = text("SELECT id, name, email FROM tenants WHERE name = :identifier")
        
        tenant = db.execute(tenant_query, {"identifier": identifier}).fetchone()
        
        if not tenant:
            print(f"❌ Error: No tenant found with identifier '{identifier}'")
            return
        
        print(f"Found tenant: {tenant.name} (ID: {tenant.id})")
        
        # Show current email
        if tenant.email:
            print(f"Current contact email: {tenant.email}")
        else:
            print("No contact email currently set")
        
        # Get new email
        new_email = input("New Contact Email (or press Enter to clear): ").strip()
        
        # Update email
        update_query = text("UPDATE tenants SET email = :email WHERE id = :tenant_id")
        db.execute(update_query, {
            "email": new_email if new_email else None,
            "tenant_id": tenant.id
        })
        
        db.commit()
        
        if new_email:
            print(f"✅ Contact email updated to '{new_email}' for tenant '{tenant.name}'")
        else:
            print(f"✅ Contact email cleared for tenant '{tenant.name}'")
        
    except Exception as e:
        print(f"❌ Error updating contact email: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def show_tenant_details():
    """Show detailed information about a specific tenant"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        from datetime import datetime
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    print("🔍 === Tenant Details ===")
    
    identifier = input("Enter Tenant ID or Tenant Name: ").strip()
    if not identifier:
        print("❌ Error: Tenant ID or name is required")
        return
    
    db = SessionLocal()
    
    def safe_format_date(date_value):
        """Safely format date regardless of type"""
        try:
            if not date_value:
                return "Unknown"
            if isinstance(date_value, str):
                try:
                    parsed_date = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    return parsed_date.strftime("%Y-%m-%d %H:%M")
                except:
                    return date_value[:16] if len(date_value) > 16 else date_value
            else:
                return date_value.strftime("%Y-%m-%d %H:%M")
        except:
            return "Unknown"
    
    try:
        # Get detailed tenant info using correct column names
        if identifier.isdigit():
            detail_query = text("""
                SELECT t.*, 
                       CASE WHEN tc.hashed_password IS NOT NULL THEN 1 ELSE 0 END as has_password,
                       tc.password_updated_at as password_created_at
                FROM tenants t
                LEFT JOIN tenant_credentials tc ON t.id = tc.tenant_id
                WHERE t.id = :identifier
            """)
        else:
            detail_query = text("""
                SELECT t.*, 
                       CASE WHEN tc.hashed_password IS NOT NULL THEN 1 ELSE 0 END as has_password,
                       tc.password_updated_at as password_created_at
                FROM tenants t
                LEFT JOIN tenant_credentials tc ON t.id = tc.tenant_id
                WHERE t.name = :identifier
            """)
        
        tenant = db.execute(detail_query, {"identifier": identifier}).fetchone()
        
        if not tenant:
            print(f"❌ No tenant found with identifier '{identifier}'")
            return
        
        print(f"\n📊 Tenant Details for: {tenant.name}")
        print("=" * 50)
        print(f"🆔 ID: {tenant.id}")
        print(f"🏢 Name: {tenant.name}")
        print(f"🏭 Company: {tenant.company_name or 'Not set'}")
        print(f"📧 Contact Email: {tenant.email or 'Not set'}")
        print(f"📝 Description: {tenant.description or 'Not set'}")
        print(f"🔑 API Key: {tenant.api_key}")
        print(f"🔵 Status: {'🟢 Active' if tenant.is_active else '🔴 Inactive'}")
        print(f"🔐 Password: {'✅ Set' if tenant.has_password else '❌ Not set'}")
        
        if tenant.password_created_at:
            pwd_updated = safe_format_date(tenant.password_created_at)
            print(f"🔐 Password Last Updated: {pwd_updated}")
        
        print(f"📅 Created: {safe_format_date(tenant.created_at)}")
        print(f"📅 Updated: {safe_format_date(tenant.updated_at)}")
        
        # Integration settings
        print(f"\n🔌 Integrations:")
        print(f"   📧 Feedback System: {'✅ Enabled' if tenant.enable_feedback_system else '❌ Disabled'}")
        print(f"   🔔 Notifications: {'✅ Enabled' if tenant.feedback_notification_enabled else '❌ Disabled'}")
        print(f"   🎮 Discord: {'✅ Enabled' if tenant.discord_enabled else '❌ Disabled'}")
        print(f"   💬 Slack: {'✅ Enabled' if tenant.slack_enabled else '❌ Disabled'}")
        
        # Get usage stats
        try:
            stats_queries = [
                ("📊 Chat Sessions", "SELECT COUNT(*) as count FROM chat_sessions WHERE tenant_id = :tenant_id"),
                ("💬 Messages", "SELECT COUNT(*) as count FROM chat_messages cm JOIN chat_sessions cs ON cm.session_id = cs.id WHERE cs.tenant_id = :tenant_id"),
                ("📚 Knowledge Bases", "SELECT COUNT(*) as count FROM knowledge_bases WHERE tenant_id = :tenant_id"),
                ("❓ FAQs", "SELECT COUNT(*) as count FROM faqs WHERE tenant_id = :tenant_id")
            ]
            
            print(f"\n📈 Usage Statistics:")
            for label, query in stats_queries:
                try:
                    result = db.execute(text(query), {"tenant_id": tenant.id}).fetchone()
                    print(f"   {label}: {result.count}")
                except:
                    print(f"   {label}: ❌ Error")
                    
        except Exception as e:
            print(f"   📈 Usage stats: ❌ Error retrieving")
        
    except Exception as e:
        print(f"❌ Error getting tenant details: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def main():
    """Main menu"""
    print("🛠️ TENANT MANAGEMENT SYSTEM")
    print("Compatible with your database structure")
    print("=" * 50)
    
    while True:
        print("\n📋 === Main Menu ===")
        print("1. 🏢 Create new tenant with password")
        print("2. 📋 List all tenants")
        print("3. 🔐 Test tenant authentication")
        print("4. 🔄 Reset tenant password")
        print("5. 📧 Update tenant contact email")
        print("6. 🔍 Show tenant details")
        print("0. 🚪 Exit")
        
        choice = input("\nEnter your choice (0-6): ").strip()
        
        if choice == "1":
            create_tenant_with_password()
        elif choice == "2":
            list_tenants()
        elif choice == "3":
            authenticate_tenant()
        elif choice == "4":
            reset_tenant_password()
        elif choice == "5":
            update_tenant_email()
        elif choice == "6":
            show_tenant_details()
        elif choice == "0":
            print("👋 Exiting...")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()