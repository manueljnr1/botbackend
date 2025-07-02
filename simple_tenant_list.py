#!/usr/bin/env python3
"""
Simple Tenant List Script - Minimal dependencies version
Works around SQLAlchemy relationship issues by using direct queries
"""

import sys
import os
import uuid
import secrets
import random
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
import click

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import only essential configurations
try:
    from app.config import settings
    DATABASE_URL = settings.DATABASE_URL
except ImportError:
    # Fallback to environment variable
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("❌ Database URL not found. Set DATABASE_URL environment variable.")
        sys.exit(1)

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SimpleTenantService:
    """Simple service using raw SQL queries to avoid relationship issues"""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def get_tenants_raw(self, active_only: bool = False) -> List[Dict]:
        """Get tenants using raw SQL query"""
        base_query = """
        SELECT 
            id,
            name,
            business_name,
            email,
            api_key,
            is_active,
            supabase_user_id,
            created_at,
            updated_at,
            primary_color,
            logo_image_url,
            logo_text,
            discord_enabled,
            slack_enabled,
            telegram_enabled,
            feedback_email,
            enable_feedback_system,
            system_prompt,
            security_level,
            is_super_tenant
        FROM tenants
        """
        
        if active_only:
            base_query += " WHERE is_active = true"
        
        base_query += " ORDER BY id"
        
        result = self.db.execute(text(base_query))
        
        tenants = []
        for row in result:
            tenants.append(dict(row._mapping))
        
        return tenants
    
    def get_tenant_credentials(self, tenant_id: int) -> bool:
        """Check if tenant has local credentials"""
        query = text("SELECT COUNT(*) as count FROM tenant_credentials WHERE tenant_id = :tenant_id")
        result = self.db.execute(query, {"tenant_id": tenant_id}).fetchone()
        return result.count > 0 if result else False
    
    def get_tenant_by_id(self, tenant_id: int) -> Optional[Dict]:
        """Get specific tenant by ID"""
        query = text("""
        SELECT 
            id,
            name,
            business_name,
            email,
            api_key,
            is_active,
            supabase_user_id,
            created_at,
            updated_at,
            description,
            primary_color,
            secondary_color,
            text_color,
            background_color,
            user_bubble_color,
            bot_bubble_color,
            border_color,
            logo_image_url,
            logo_text,
            border_radius,
            widget_position,
            font_family,
            custom_css,
            discord_enabled,
            discord_bot_token,
            slack_enabled,
            slack_bot_token,
            telegram_enabled,
            telegram_bot_token,
            feedback_email,
            enable_feedback_system,
            system_prompt,
            security_level,
            allow_custom_prompts,
            is_super_tenant,
            can_impersonate
        FROM tenants 
        WHERE id = :tenant_id
        """)
        
        result = self.db.execute(query, {"tenant_id": tenant_id}).fetchone()
        return dict(result._mapping) if result else None
    
    def search_tenants(self, name: str = None, email: str = None, business: str = None) -> List[Dict]:
        """Search tenants with filters"""
        conditions = []
        params = {}
        
        if name:
            conditions.append("name ILIKE :name")
            params["name"] = f"%{name}%"
        
        if email:
            conditions.append("email ILIKE :email")
            params["email"] = f"%{email}%"
        
        if business:
            conditions.append("business_name ILIKE :business")
            params["business"] = f"%{business}%"
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = text(f"""
        SELECT 
            id, name, business_name, email, api_key, is_active, 
            supabase_user_id, created_at, updated_at
        FROM tenants{where_clause}
        ORDER BY id
        """)
        
        result = self.db.execute(query, params)
        
        tenants = []
        for row in result:
            tenants.append(dict(row._mapping))
        
        return tenants
    
    def get_tenant_stats(self) -> Dict[str, Any]:
        """Get tenant statistics"""
        stats = {}
        
        # Basic counts
        result = self.db.execute(text("SELECT COUNT(*) as total FROM tenants")).fetchone()
        stats["total"] = result.total
        
        result = self.db.execute(text("SELECT COUNT(*) as active FROM tenants WHERE is_active = true")).fetchone()
        stats["active"] = result.active
        stats["inactive"] = stats["total"] - stats["active"]
        
        # Auth method counts
        result = self.db.execute(text("SELECT COUNT(*) as supabase FROM tenants WHERE supabase_user_id IS NOT NULL")).fetchone()
        stats["supabase_auth"] = result.supabase
        
        result = self.db.execute(text("SELECT COUNT(*) as local FROM tenant_credentials")).fetchone()
        stats["local_auth"] = result.local if result else 0
        
        # API key counts
        result = self.db.execute(text("SELECT COUNT(*) as with_keys FROM tenants WHERE api_key IS NOT NULL AND api_key != ''")).fetchone()
        stats["with_api_keys"] = result.with_keys
        stats["without_api_keys"] = stats["total"] - stats["with_api_keys"]
        
        # Integration counts
        result = self.db.execute(text("SELECT COUNT(*) as discord FROM tenants WHERE discord_enabled = true")).fetchone()
        stats["discord_enabled"] = result.discord if result else 0
        
        result = self.db.execute(text("SELECT COUNT(*) as slack FROM tenants WHERE slack_enabled = true")).fetchone()
        stats["slack_enabled"] = result.slack if result else 0
        
        result = self.db.execute(text("SELECT COUNT(*) as telegram FROM tenants WHERE telegram_enabled = true")).fetchone()
        stats["telegram_enabled"] = result.telegram if result else 0
        
        return stats
    
    def generate_secure_tenant_id(self) -> int:
        """Generate a secure random 9-digit tenant ID"""
        max_attempts = 100
        for attempt in range(max_attempts):
            # Generate random 9-digit ID
            new_id = random.randint(100000000, 999999999)
            
            # Check if ID is available
            result = self.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE id = :id"), {"id": new_id}).fetchone()
            if result.count == 0:
                return new_id
        
        raise ValueError(f"Could not generate unique tenant ID after {max_attempts} attempts")
    
    def generate_api_key(self) -> str:
        """Generate a secure API key"""
        random_part = secrets.token_urlsafe(32)
        clean_key = random_part.replace('=', '').replace('+', '').replace('/', '')[:32]
        return f"sk-{clean_key}"
    
    def check_tenant_exists(self, name: str = None, email: str = None) -> Dict[str, bool]:
        """Check if tenant name or email already exists"""
        results = {"name_exists": False, "email_exists": False}
        
        if name:
            result = self.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE name = :name"), {"name": name}).fetchone()
            results["name_exists"] = result.count > 0
        
        if email:
            result = self.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE LOWER(email) = LOWER(:email)"), {"email": email}).fetchone()
            results["email_exists"] = result.count > 0
        
        return results
    
    def create_tenant(self, name: str, business_name: str, email: str, password: str = None, description: str = None) -> Dict[str, Any]:
        """Create a new tenant"""
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Check if tenant already exists
            existing = self.check_tenant_exists(name=name, email=email)
            if existing["name_exists"]:
                return {"success": False, "error": f"Tenant name '{name}' already exists"}
            if existing["email_exists"]:
                return {"success": False, "error": f"Email '{email}' already registered"}
            
            # Generate secure tenant ID and API key
            tenant_id = self.generate_secure_tenant_id()
            api_key = self.generate_api_key()
            
            # Ensure API key is unique
            max_attempts = 10
            for attempt in range(max_attempts):
                result = self.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE api_key = :api_key"), {"api_key": api_key}).fetchone()
                if result.count == 0:
                    break
                api_key = self.generate_api_key()
            else:
                return {"success": False, "error": "Could not generate unique API key"}
            
            # Create tenant record
            insert_query = text("""
                INSERT INTO tenants (
                    id, name, business_name, email, api_key, is_active, 
                    description, created_at, updated_at
                ) VALUES (
                    :id, :name, :business_name, :email, :api_key, :is_active,
                    :description, :created_at, :updated_at
                )
            """)
            
            now = datetime.utcnow()
            self.db.execute(insert_query, {
                "id": tenant_id,
                "name": name,
                "business_name": business_name,
                "email": email,
                "api_key": api_key,
                "is_active": True,
                "description": description,
                "created_at": now,
                "updated_at": now
            })
            
            # Create local credentials if password provided
            if password:
                hashed_password = pwd_context.hash(password)
                credentials_query = text("""
                    INSERT INTO tenant_credentials (tenant_id, hashed_password)
                    VALUES (:tenant_id, :hashed_password)
                """)
                
                self.db.execute(credentials_query, {
                    "tenant_id": tenant_id,
                    "hashed_password": hashed_password
                })
            
            # Commit the transaction
            self.db.commit()
            
            return {
                "success": True,
                "tenant_id": tenant_id,
                "name": name,
                "business_name": business_name,
                "email": email,
                "api_key": api_key,
                "has_password": bool(password),
                "created_at": now.isoformat()
            }
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": f"Failed to create tenant: {str(e)}"}
    
    def update_tenant(self, tenant_id: int, **updates) -> Dict[str, Any]:
        """Update tenant fields"""
        try:
            # Check if tenant exists
            result = self.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE id = :id"), {"id": tenant_id}).fetchone()
            if result.count == 0:
                return {"success": False, "error": f"Tenant with ID {tenant_id} not found"}
            
            # Build update query dynamically
            allowed_fields = [
                'name', 'business_name', 'email', 'description', 'is_active',
                'primary_color', 'secondary_color', 'logo_text', 'feedback_email',
                'enable_feedback_system', 'system_prompt'
            ]
            
            update_fields = []
            params = {"tenant_id": tenant_id, "updated_at": datetime.utcnow()}
            
            for field, value in updates.items():
                if field in allowed_fields and value is not None:
                    update_fields.append(f"{field} = :{field}")
                    params[field] = value
            
            if not update_fields:
                return {"success": False, "error": "No valid fields to update"}
            
            # Add updated_at
            update_fields.append("updated_at = :updated_at")
            
            update_query = text(f"""
                UPDATE tenants 
                SET {', '.join(update_fields)}
                WHERE id = :tenant_id
            """)
            
            self.db.execute(update_query, params)
            self.db.commit()
            
            return {"success": True, "message": f"Tenant {tenant_id} updated successfully"}
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": f"Failed to update tenant: {str(e)}"}
    
    def delete_tenant(self, tenant_id: int, confirm: bool = False) -> Dict[str, Any]:
        """Delete a tenant (with confirmation)"""
        try:
            if not confirm:
                return {"success": False, "error": "Deletion requires confirmation flag"}
            
            # Check if tenant exists
            tenant = self.get_tenant_by_id(tenant_id)
            if not tenant:
                return {"success": False, "error": f"Tenant with ID {tenant_id} not found"}
            
            # Delete related records first (tenant_credentials)
            self.db.execute(text("DELETE FROM tenant_credentials WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
            
            # Delete the tenant
            self.db.execute(text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": tenant_id})
            
            self.db.commit()
            
            return {
                "success": True, 
                "message": f"Tenant '{tenant['name']}' (ID: {tenant_id}) deleted successfully"
            }
            
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": f"Failed to delete tenant: {str(e)}"}


def format_table_data(tenants: List[Dict]) -> List[Dict[str, Any]]:
    """Format tenant data for table display"""
    formatted_data = []
    service = SimpleTenantService()
    
    for tenant in tenants:
        # Check auth methods
        has_supabase = bool(tenant.get('supabase_user_id'))
        has_local = service.get_tenant_credentials(tenant['id'])
        
        auth_indicator = ""
        if has_supabase:
            auth_indicator += "S"
        if has_local:
            auth_indicator += "L"
        if not auth_indicator:
            auth_indicator = "❌"
        
        # Format API key
        api_key = tenant.get('api_key')
        api_key_masked = f"{api_key[:8]}...{api_key[-4:]}" if api_key else "None"
        
        # Format dates
        created_at = tenant.get('created_at')
        created_str = created_at.strftime("%Y-%m-%d") if created_at else "Unknown"
        
        formatted_data.append({
            "ID": tenant['id'],
            "Name": (tenant['name'][:20] + "...") if len(tenant['name']) > 20 else tenant['name'],
            "Business": (tenant['business_name'][:25] + "...") if len(tenant['business_name']) > 25 else tenant['business_name'],
            "Email": (tenant['email'][:30] + "...") if len(tenant['email']) > 30 else tenant['email'],
            "API Key": api_key_masked,
            "Active": "✅" if tenant['is_active'] else "❌",
            "Auth": auth_indicator,
            "Created": created_str
        })
    
    return formatted_data


def display_tenant_details(tenant: Dict) -> None:
    """Display detailed information for a single tenant"""
    service = SimpleTenantService()
    has_local_creds = service.get_tenant_credentials(tenant['id'])
    
    print(f"\n{'='*80}")
    print(f"🏢 TENANT DETAILS: {tenant['name']} (ID: {tenant['id']})")
    print(f"{'='*80}")
    
    # Basic Information
    print(f"📋 Basic Information:")
    print(f"   Name: {tenant['name']}")
    print(f"   Business: {tenant['business_name']}")
    print(f"   Email: {tenant['email']}")
    print(f"   Description: {tenant.get('description') or 'None'}")
    print(f"   Active: {'✅ Yes' if tenant['is_active'] else '❌ No'}")
    print(f"   Super Tenant: {'✅ Yes' if tenant.get('is_super_tenant') else '❌ No'}")
    
    # API Key Information
    print(f"\n🔑 API Key:")
    api_key = tenant.get('api_key')
    if api_key:
        print(f"   Key: {api_key[:12]}...{api_key[-8:]}")
    else:
        print(f"   Key: ❌ No API key set")
    
    # Authentication Methods
    print(f"\n🔐 Authentication:")
    has_supabase = bool(tenant.get('supabase_user_id'))
    print(f"   Supabase: {'✅ Configured' if has_supabase else '❌ Not configured'}")
    if tenant.get('supabase_user_id'):
        print(f"   Supabase ID: {tenant['supabase_user_id']}")
    print(f"   Local Credentials: {'✅ Available' if has_local_creds else '❌ Not available'}")
    
    # Branding Information
    print(f"\n🎨 Branding:")
    print(f"   Primary Color: {tenant.get('primary_color', '#007bff')}")
    print(f"   Secondary Color: {tenant.get('secondary_color', '#f0f4ff')}")
    print(f"   Logo Image: {'✅ Set' if tenant.get('logo_image_url') else '❌ None'}")
    print(f"   Logo Text: {tenant.get('logo_text', 'None')}")
    print(f"   Custom CSS: {'✅ Set' if tenant.get('custom_css') else '❌ None'}")
    print(f"   Widget Position: {tenant.get('widget_position', 'bottom-right')}")
    print(f"   Font Family: {tenant.get('font_family', 'Inter, sans-serif')}")
    
    # Integration Information
    print(f"\n🔗 Integrations:")
    print(f"   Discord: {'✅ Enabled' if tenant.get('discord_enabled') else '❌ Disabled'}")
    if tenant.get('discord_bot_token'):
        print(f"   Discord Token: {tenant['discord_bot_token'][:10]}...{tenant['discord_bot_token'][-4:]}")
    
    print(f"   Slack: {'✅ Enabled' if tenant.get('slack_enabled') else '❌ Disabled'}")
    if tenant.get('slack_bot_token'):
        print(f"   Slack Token: {tenant['slack_bot_token'][:10]}...{tenant['slack_bot_token'][-4:]}")
    
    print(f"   Telegram: {'✅ Enabled' if tenant.get('telegram_enabled') else '❌ Disabled'}")
    if tenant.get('telegram_bot_token'):
        print(f"   Telegram Token: {tenant['telegram_bot_token'][:10]}...{tenant['telegram_bot_token'][-4:]}")
    
    # Email Configuration
    print(f"\n📧 Email Settings:")
    print(f"   Feedback Email: {tenant.get('feedback_email', 'Not set')}")
    print(f"   Feedback System: {'✅ Enabled' if tenant.get('enable_feedback_system', True) else '❌ Disabled'}")
    
    # Timestamps
    print(f"\n📅 Timestamps:")
    created_at = tenant.get('created_at')
    updated_at = tenant.get('updated_at')
    print(f"   Created: {created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if created_at else 'Unknown'}")
    print(f"   Updated: {updated_at.strftime('%Y-%m-%d %H:%M:%S UTC') if updated_at else 'Unknown'}")
    
    # Security Information
    print(f"\n🛡️ Security:")
    print(f"   Security Level: {tenant.get('security_level', 'standard')}")
    print(f"   Custom Prompts: {'✅ Allowed' if tenant.get('allow_custom_prompts', True) else '❌ Blocked'}")
    print(f"   System Prompt: {'✅ Set' if tenant.get('system_prompt') else '❌ Default'}")
    print(f"   Can Impersonate: {'✅ Yes' if tenant.get('can_impersonate') else '❌ No'}")


@click.group()
def cli():
    """Simple Tenant Management CLI Tool"""
    pass


@cli.command()
@click.option('--active-only', is_flag=True, help='Show only active tenants')
@click.option('--format', 'output_format', type=click.Choice(['table', 'simple', 'detailed']), default='table', help='Output format')
@click.option('--limit', type=int, help='Limit number of tenants shown')
def list_tenants(active_only: bool, output_format: str, limit: Optional[int]):
    """List all tenants with their details"""
    
    try:
        service = SimpleTenantService()
        tenants = service.get_tenants_raw(active_only=active_only)
        
        if limit:
            tenants = tenants[:limit]
        
        if not tenants:
            print("❌ No tenants found")
            return
        
        print(f"\n🏢 Found {len(tenants)} tenant(s)")
        
        if output_format == 'detailed':
            # Show detailed information for each tenant
            for tenant in tenants:
                # Get full details for each tenant
                full_tenant = service.get_tenant_by_id(tenant['id'])
                if full_tenant:
                    display_tenant_details(full_tenant)
        
        elif output_format == 'simple':
            # Simple list format
            print(f"\n{'ID':<10} {'Name':<20} {'Business':<25} {'Active':<8} {'Email'}")
            print("-" * 80)
            for tenant in tenants:
                active_status = "✅ Yes" if tenant['is_active'] else "❌ No"
                name = tenant['name'][:19] if len(tenant['name']) > 19 else tenant['name']
                business = tenant['business_name'][:24] if len(tenant['business_name']) > 24 else tenant['business_name']
                print(f"{tenant['id']:<10} {name:<20} {business:<25} {active_status:<8} {tenant['email']}")
        
        else:
            # Table format (default)
            try:
                from tabulate import tabulate
                formatted_data = format_table_data(tenants)
                
                print(f"\n📊 Tenant Summary:")
                print("Auth Legend: S=Supabase, L=Local, ❌=None")
                print("\n" + tabulate(formatted_data, headers="keys", tablefmt="grid"))
            except ImportError:
                print("📊 Tenant Summary (tabulate not available, using simple format):")
                print("Auth Legend: S=Supabase, L=Local, ❌=None")
                print(f"\n{'ID':<10} {'Name':<20} {'Business':<25} {'Active':<8} {'Auth':<6}")
                print("-" * 75)
                for tenant in tenants:
                    service_local = SimpleTenantService()
                    has_supabase = bool(tenant.get('supabase_user_id'))
                    has_local = service_local.get_tenant_credentials(tenant['id'])
                    
                    auth_indicator = ""
                    if has_supabase:
                        auth_indicator += "S"
                    if has_local:
                        auth_indicator += "L"
                    if not auth_indicator:
                        auth_indicator = "❌"
                    
                    active_status = "✅" if tenant['is_active'] else "❌"
                    name = tenant['name'][:19] if len(tenant['name']) > 19 else tenant['name']
                    business = tenant['business_name'][:24] if len(tenant['business_name']) > 24 else tenant['business_name']
                    print(f"{tenant['id']:<10} {name:<20} {business:<25} {active_status:<8} {auth_indicator:<6}")
        
        # Summary statistics
        active_count = sum(1 for t in tenants if t['is_active'])
        inactive_count = len(tenants) - active_count
        
        print(f"\n📈 Statistics:")
        print(f"   Total: {len(tenants)}")
        print(f"   Active: {active_count}")
        print(f"   Inactive: {inactive_count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument('tenant_id', type=int)
def show_tenant(tenant_id: int):
    """Show detailed information for a specific tenant"""
    
    try:
        service = SimpleTenantService()
        tenant = service.get_tenant_by_id(tenant_id)
        
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        display_tenant_details(tenant)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
@click.option('--name', help='Search by tenant name')
@click.option('--email', help='Search by email')
@click.option('--business', help='Search by business name')
def search_tenants(name: Optional[str], email: Optional[str], business: Optional[str]):
    """Search for tenants by various criteria"""
    
    if not any([name, email, business]):
        print("❌ Please provide at least one search criteria")
        return
    
    try:
        service = SimpleTenantService()
        tenants = service.search_tenants(name=name, email=email, business=business)
        
        if not tenants:
            print("❌ No tenants found matching the search criteria")
            return
        
        print(f"\n🔍 Found {len(tenants)} tenant(s) matching search criteria:")
        
        try:
            from tabulate import tabulate
            formatted_data = format_table_data(tenants)
            print("\n" + tabulate(formatted_data, headers="keys", tablefmt="grid"))
        except ImportError:
            print(f"\n{'ID':<10} {'Name':<20} {'Business':<25} {'Email'}")
            print("-" * 70)
            for tenant in tenants:
                name_str = tenant['name'][:19] if len(tenant['name']) > 19 else tenant['name']
                business_str = tenant['business_name'][:24] if len(tenant['business_name']) > 24 else tenant['business_name']
                print(f"{tenant['id']:<10} {name_str:<20} {business_str:<25} {tenant['email']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
def stats():
    """Show tenant statistics"""
    
    try:
        service = SimpleTenantService()
        stats = service.get_tenant_stats()
        
        print(f"\n📊 Tenant Statistics")
        print(f"{'='*50}")
        
        print(f"\n🏢 General:")
        print(f"   Total Tenants: {stats['total']}")
        print(f"   Active: {stats['active']}")
        print(f"   Inactive: {stats['inactive']}")
        
        print(f"\n🔐 Authentication:")
        print(f"   Supabase Auth: {stats['supabase_auth']}")
        print(f"   Local Credentials: {stats['local_auth']}")
        
        print(f"\n🔑 API Keys:")
        print(f"   With API Key: {stats['with_api_keys']}")
        print(f"   Missing API Key: {stats['without_api_keys']}")
        
        print(f"\n🔗 Integrations:")
        print(f"   Discord Enabled: {stats['discord_enabled']}")
        print(f"   Slack Enabled: {stats['slack_enabled']}")
        print(f"   Telegram Enabled: {stats['telegram_enabled']}")
        
        # Security recommendations
        print(f"\n💡 Recommendations:")
        if stats['without_api_keys'] > 0:
            print(f"   ⚠️ {stats['without_api_keys']} tenants missing API keys")
        if stats['inactive'] > 0:
            print(f"   📋 {stats['inactive']} inactive tenants (consider cleanup)")
        
        if stats['without_api_keys'] == 0:
            print(f"   ✅ All tenants have API keys")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
def test_connection():
    """Test database connection"""
    try:
        service = SimpleTenantService()
        result = service.db.execute(text("SELECT COUNT(*) as count FROM tenants")).fetchone()
        print(f"✅ Database connection successful!")
        print(f"📊 Found {result.count} tenants in database")
        
        # Test if tables exist
        tables_query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('tenants', 'tenant_credentials')
        ORDER BY table_name
        """)
        
        tables = service.db.execute(tables_query).fetchall()
        print(f"📋 Available tables: {[table.table_name for table in tables]}")
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


@cli.command()
@click.option('--name', prompt='Tenant name', help='Unique tenant name/username')
@click.option('--business-name', prompt='Business name', help='Business or company name')
@click.option('--email', prompt='Email address', help='Tenant email address')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password for local authentication')
@click.option('--description', help='Optional description')
@click.option('--dry-run', is_flag=True, help='Show what would be created without actually creating')
def create_tenant(name: str, business_name: str, email: str, password: str, description: Optional[str], dry_run: bool):
    """Create a new tenant with local credentials"""
    
    try:
        service = SimpleTenantService()
        
        # Validate inputs
        if not name or not business_name or not email:
            print("❌ Name, business name, and email are required")
            return
        
        if len(password) < 6:
            print("❌ Password must be at least 6 characters long")
            return
        
        # Check if tenant already exists
        existing = service.check_tenant_exists(name=name, email=email)
        if existing["name_exists"]:
            print(f"❌ Tenant name '{name}' already exists")
            return
        if existing["email_exists"]:
            print(f"❌ Email '{email}' already registered")
            return
        
        if dry_run:
            print(f"\n🔍 DRY RUN - Would create tenant:")
            print(f"   Name: {name}")
            print(f"   Business: {business_name}")
            print(f"   Email: {email}")
            print(f"   Password: {'*' * len(password)}")
            print(f"   Description: {description or 'None'}")
            print(f"   Will generate: Secure tenant ID and API key")
            print(f"   Will create: Local password credentials")
            return
        
        # Create the tenant
        print(f"🔄 Creating tenant '{name}'...")
        result = service.create_tenant(
            name=name,
            business_name=business_name,
            email=email,
            password=password,
            description=description
        )
        
        if result["success"]:
            print(f"✅ Tenant created successfully!")
            print(f"\n📋 Tenant Details:")
            print(f"   ID: {result['tenant_id']}")
            print(f"   Name: {result['name']}")
            print(f"   Business: {result['business_name']}")
            print(f"   Email: {result['email']}")
            print(f"   API Key: {result['api_key']}")
            print(f"   Password: {'✅ Set' if result['has_password'] else '❌ Not set'}")
            print(f"   Created: {result['created_at']}")
            
            print(f"\n💡 Next steps:")
            print(f"   1. Save the API key: {result['api_key']}")
            print(f"   2. Test login with email and password")
            print(f"   3. Configure tenant settings as needed")
            
        else:
            print(f"❌ Failed to create tenant: {result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('tenant_id', type=int)
@click.option('--name', help='Update tenant name')
@click.option('--business-name', help='Update business name')
@click.option('--email', help='Update email address')
@click.option('--description', help='Update description')
@click.option('--active/--inactive', help='Set active status')
@click.option('--feedback-email', help='Update feedback email')
@click.option('--system-prompt', help='Update system prompt')
@click.option('--primary-color', help='Update primary color (hex format)')
def update_tenant(tenant_id: int, **updates):
    """Update an existing tenant"""
    
    try:
        service = SimpleTenantService()
        
        # Filter out None values
        filtered_updates = {k.replace('_', '_'): v for k, v in updates.items() if v is not None}
        
        if not filtered_updates:
            print("❌ No update fields provided")
            return
        
        # Show current tenant info
        tenant = service.get_tenant_by_id(tenant_id)
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        print(f"🔄 Updating tenant '{tenant['name']}' (ID: {tenant_id})...")
        
        # Perform update
        result = service.update_tenant(tenant_id, **filtered_updates)
        
        if result["success"]:
            print(f"✅ {result['message']}")
            
            # Show updated tenant
            updated_tenant = service.get_tenant_by_id(tenant_id)
            print(f"\n📋 Updated Tenant Details:")
            print(f"   Name: {updated_tenant['name']}")
            print(f"   Business: {updated_tenant['business_name']}")
            print(f"   Email: {updated_tenant['email']}")
            print(f"   Active: {'✅' if updated_tenant['is_active'] else '❌'}")
            print(f"   Updated: {updated_tenant['updated_at']}")
            
        else:
            print(f"❌ {result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('tenant_id', type=int)
@click.option('--confirm', is_flag=True, help='Confirm deletion')
@click.option('--force', is_flag=True, help='Force deletion without interactive confirmation')
def delete_tenant(tenant_id: int, confirm: bool, force: bool):
    """Delete a tenant (requires confirmation)"""
    
    try:
        service = SimpleTenantService()
        
        # Get tenant info first
        tenant = service.get_tenant_by_id(tenant_id)
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        print(f"🗑️  About to delete tenant:")
        print(f"   ID: {tenant['id']}")
        print(f"   Name: {tenant['name']}")
        print(f"   Business: {tenant['business_name']}")
        print(f"   Email: {tenant['email']}")
        print(f"   Active: {'✅' if tenant['is_active'] else '❌'}")
        
        if not force and not confirm:
            response = input(f"\n⚠️  Are you sure you want to delete this tenant? This action cannot be undone. (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("❌ Deletion cancelled")
                return
            confirm = True
        
        # Perform deletion
        result = service.delete_tenant(tenant_id, confirm=confirm)
        
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ {result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('tenant_id', type=int)
def regenerate_api_key(tenant_id: int):
    """Regenerate API key for a tenant"""
    
    try:
        service = SimpleTenantService()
        
        # Get tenant info first
        tenant = service.get_tenant_by_id(tenant_id)
        if not tenant:
            print(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        old_api_key = tenant.get('api_key', 'None')
        old_masked = f"{old_api_key[:8]}...{old_api_key[-4:]}" if old_api_key and old_api_key != 'None' else 'None'
        
        print(f"🔄 Regenerating API key for tenant '{tenant['name']}' (ID: {tenant_id})")
        print(f"   Current API key: {old_masked}")
        
        # Generate new API key
        new_api_key = service.generate_api_key()
        
        # Ensure uniqueness
        max_attempts = 10
        for attempt in range(max_attempts):
            result = service.db.execute(text("SELECT COUNT(*) as count FROM tenants WHERE api_key = :api_key"), {"api_key": new_api_key}).fetchone()
            if result.count == 0:
                break
            new_api_key = service.generate_api_key()
        else:
            print("❌ Could not generate unique API key")
            return
        
        # Update the tenant
        update_result = service.update_tenant(tenant_id, api_key=new_api_key)
        
        if update_result["success"]:
            print(f"✅ API key regenerated successfully!")
            print(f"   Old key: {old_masked}")
            print(f"   New key: {new_api_key}")
            print(f"   ⚠️  Update your applications with the new API key")
        else:
            print(f"❌ {update_result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Check dependencies
    missing_deps = []
    
    try:
        import passlib
    except ImportError:
        missing_deps.append("passlib[bcrypt]")
    
    if missing_deps:
        print("❌ Missing required dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print(f"\nInstall with: pip install {' '.join(missing_deps)}")
        sys.exit(1)
    
    # Optional dependency check
    try:
        import tabulate
    except ImportError:
        print("ℹ️  Note: Install 'tabulate' for better table formatting: pip install tabulate")
    
    # Run the CLI
    cli()