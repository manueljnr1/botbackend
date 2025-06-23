"""
Enhanced CLI Management Commands for Password-Protected API Key Operations
"""

import click
import logging
import asyncio
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.tenants.models import Tenant
from app.tenants.api_key_service import EnhancedAPIKeyResetService, get_enhanced_api_key_reset_service
from app.tenants.api_key_migration import APIKeyMigrationService, run_api_key_migration

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.group()
def enhanced_api_key_cli():
    """Enhanced API Key Management Commands with Password Support"""
    pass


@enhanced_api_key_cli.command()
@click.option('--tenant-id', type=int, required=True, help='Tenant ID to reset')
@click.option('--reason', type=str, help='Reason for the reset')
@click.option('--confirm', is_flag=True, help='Confirm the reset operation')
def admin_reset_key(tenant_id: int, reason: Optional[str], confirm: bool):
    """Reset API key for a specific tenant (Admin operation - bypasses password)"""
    
    if not confirm:
        click.echo("⚠️  This will reset the tenant's API key and invalidate the current one.")
        click.echo("   This is an ADMIN operation that bypasses password verification.")
        click.echo("   Use --confirm flag to proceed.")
        return
    
    db = SessionLocal()
    try:
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Get tenant info first
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            click.echo(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        click.echo(f"🔄 Admin resetting API key for tenant: {tenant.name} (ID: {tenant_id})")
        click.echo(f"   Email: {tenant.email}")
        
        # Perform the admin reset (bypasses password verification)
        async def reset_operation():
            return await api_service.admin_reset_tenant_api_key(
                tenant_id=tenant_id,
                reason=reason
            )
        
        result = asyncio.run(reset_operation())
        
        if result["success"]:
            click.echo(f"✅ API key reset successful!")
            click.echo(f"   Tenant: {result['tenant_name']}")
            click.echo(f"   Old key: {result['old_api_key_masked']}")
            click.echo(f"   New key: {result['new_api_key']}")
            click.echo(f"   Timestamp: {result['reset_timestamp']}")
            click.echo(f"   Verification: {result.get('verification_method', 'admin_override')}")
            
            # Audit the reset
            api_service.audit_api_key_reset(
                tenant_id=tenant_id,
                reset_by="cli_admin",
                reason=reason or "CLI-initiated admin reset",
                verification_method="admin_override"
            )
        else:
            click.echo(f"❌ Reset failed: {result.get('error')}")
            
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}")
    finally:
        db.close()


@enhanced_api_key_cli.command()
@click.option('--tenant-id', type=int, required=True, help='Tenant ID to test')
@click.option('--password', type=str, required=True, help='Password to verify')
@click.option('--show-methods', is_flag=True, help='Show available authentication methods')
def test_password(tenant_id: int, password: str, show_methods: bool):
    """Test password verification for a tenant (Admin diagnostic tool)"""
    
    db = SessionLocal()
    try:
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Get tenant info first
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            click.echo(f"❌ Tenant with ID {tenant_id} not found")
            return
        
        click.echo(f"🔐 Testing password verification for tenant: {tenant.name} (ID: {tenant_id})")
        
        if show_methods:
            # Show available authentication methods
            from app.auth.models import TenantCredentials
            has_supabase = bool(tenant.supabase_user_id)
            has_local_creds = bool(
                db.query(TenantCredentials).filter(
                    TenantCredentials.tenant_id == tenant_id
                ).first()
            )
            
            click.echo(f"   Authentication methods available:")
            click.echo(f"   - Supabase: {'✅' if has_supabase else '❌'} ({tenant.supabase_user_id or 'Not configured'})")
            click.echo(f"   - Local credentials: {'✅' if has_local_creds else '❌'}")
            click.echo("")
        
        # Test password verification
        async def verify_operation():
            return await api_service.verify_tenant_password(tenant_id, password)
        
        verification_result = asyncio.run(verify_operation())
        
        if verification_result["success"]:
            click.echo(f"✅ Password verification successful!")
            click.echo(f"   Method used: {verification_result.get('method')}")
            click.echo(f"   Email: {verification_result.get('tenant_email', tenant.email)}")
        else:
            click.echo(f"❌ Password verification failed")
            click.echo(f"   Method attempted: {verification_result.get('method')}")
            click.echo(f"   Error: {verification_result.get('error')}")
            
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}")
    finally:
        db.close()


@enhanced_api_key_cli.command()
@click.option('--tenant-ids', type=str, required=True, help='Comma-separated tenant IDs')
@click.option('--reason', type=str, help='Reason for the bulk reset')
@click.option('--confirm', is_flag=True, help='Confirm the bulk reset operation')
@click.option('--show-progress', is_flag=True, help='Show detailed progress')
def bulk_admin_reset(tenant_ids: str, reason: Optional[str], confirm: bool, show_progress: bool):
    """Bulk reset API keys for multiple tenants (Admin operation)"""
    
    if not confirm:
        click.echo("⚠️  This will reset API keys for multiple tenants.")
        click.echo("   This is an ADMIN BULK operation that bypasses password verification.")
        click.echo("   Use --confirm flag to proceed.")
        return
    
    try:
        # Parse tenant IDs
        id_list = [int(id.strip()) for id in tenant_ids.split(',')]
    except ValueError:
        click.echo("❌ Invalid tenant IDs format. Use comma-separated integers.")
        return
    
    db = SessionLocal()
    try:
        api_service = get_enhanced_api_key_reset_service(db)
        
        click.echo(f"🔄 Bulk admin resetting API keys for {len(id_list)} tenants...")
        click.echo(f"   Reason: {reason or 'Not specified'}")
        click.echo("")
        
        successful = 0
        failed = 0
        
        for i, tenant_id in enumerate(id_list, 1):
            if show_progress:
                click.echo(f"   [{i}/{len(id_list)}] Processing tenant {tenant_id}...")
            
            async def reset_operation():
                return await api_service.admin_reset_tenant_api_key(
                    tenant_id=tenant_id,
                    reason=reason or "CLI bulk admin reset"
                )
            
            result = asyncio.run(reset_operation())
            
            if result["success"]:
                successful += 1
                click.echo(f"   ✅ Tenant {tenant_id} ({result['tenant_name']}): {result['old_api_key_masked']} → {result['new_api_key'][:12]}...")
                
                # Audit each reset
                api_service.audit_api_key_reset(
                    tenant_id=tenant_id,
                    reset_by="cli_admin_bulk",
                    reason=reason or "CLI bulk admin reset",
                    verification_method="admin_override"
                )
            else:
                failed += 1
                click.echo(f"   ❌ Tenant {tenant_id}: {result.get('error')}")
        
        click.echo(f"\n📊 Bulk admin reset completed: {successful} successful, {failed} failed")
        click.echo(f"   Security note: All resets bypassed password verification (admin override)")
        
    except Exception as e:
        click.echo(f"❌ Bulk reset error: {str(e)}")
    finally:
        db.close()


@enhanced_api_key_cli.command()
@click.option('--tenant-id', type=int, help='Specific tenant ID to check')
@click.option('--include-auth-methods', is_flag=True, help='Include authentication method analysis')
def security_audit(tenant_id: Optional[int], include_auth_methods: bool):
    """Enhanced security audit with authentication method analysis"""
    
    db = SessionLocal()
    try:
        api_service = get_enhanced_api_key_reset_service(db)
        
        if tenant_id:
            # Check specific tenant
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                click.echo(f"❌ Tenant {tenant_id} not found")
                return
            
            click.echo(f"🔍 Security audit for tenant {tenant_id} ({tenant.name}):")
            click.echo(f"   Email: {tenant.email}")
            click.echo(f"   Business: {tenant.business_name}")
            click.echo(f"   API Key: {tenant.api_key[:8]}...{tenant.api_key[-4:] if tenant.api_key else 'None'}")
            click.echo(f"   Active: {tenant.is_active}")
            
            if include_auth_methods:
                # Check authentication methods
                from app.auth.models import TenantCredentials
                has_supabase = bool(tenant.supabase_user_id)
                has_local_creds = bool(
                    db.query(TenantCredentials).filter(
                        TenantCredentials.tenant_id == tenant_id
                    ).first()
                )
                
                click.echo(f"   🔐 Authentication Methods:")
                click.echo(f"      Supabase: {'✅' if has_supabase else '❌'}")
                click.echo(f"      Local credentials: {'✅' if has_local_creds else '❌'}")
                click.echo(f"      Can reset API key: {'✅' if (has_supabase or has_local_creds) else '❌'}")
                
                # Security score
                score = 0
                if tenant.api_key:
                    score += 40
                if has_supabase and has_local_creds:
                    score += 60
                elif has_supabase or has_local_creds:
                    score += 40
                
                click.echo(f"      Security score: {score}/100")
            
        else:
            # Comprehensive audit
            click.echo("🔍 Running comprehensive security audit...")
            
            from app.auth.models import TenantCredentials
            tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
            
            # Security counters
            total_tenants = len(tenants)
            tenants_with_supabase = 0
            tenants_with_local = 0
            tenants_with_both = 0
            tenants_with_neither = 0
            tenants_missing_api_keys = 0
            
            click.echo(f"\n📊 Security Summary:")
            click.echo(f"   Total active tenants: {total_tenants}")
            
            for tenant in tenants:
                has_supabase = bool(tenant.supabase_user_id)
                has_local_creds = bool(
                    db.query(TenantCredentials).filter(
                        TenantCredentials.tenant_id == tenant.id
                    ).first()
                )
                
                if has_supabase:
                    tenants_with_supabase += 1
                if has_local_creds:
                    tenants_with_local += 1
                if has_supabase and has_local_creds:
                    tenants_with_both += 1
                if not has_supabase and not has_local_creds:
                    tenants_with_neither += 1
                if not tenant.api_key:
                    tenants_missing_api_keys += 1
            
            click.echo(f"   Tenants with Supabase auth: {tenants_with_supabase}")
            click.echo(f"   Tenants with local credentials: {tenants_with_local}")
            click.echo(f"   Tenants with both methods: {tenants_with_both}")
            click.echo(f"   Tenants with no auth methods: {tenants_with_neither}")
            click.echo(f"   Tenants missing API keys: {tenants_missing_api_keys}")
            
            # Security recommendations
            click.echo(f"\n💡 Security Recommendations:")
            if tenants_missing_api_keys > 0:
                click.echo(f"   🚨 {tenants_missing_api_keys} tenants missing API keys - run migration")
            if tenants_with_neither > 0:
                click.echo(f"   ⚠️ {tenants_with_neither} tenants have no auth methods - cannot reset keys safely")
            if tenants_with_both < total_tenants * 0.8:
                click.echo(f"   🔐 Consider enabling multiple auth methods for better security")
            
            click.echo(f"   🔄 Implement regular API key rotation (every 90 days)")
            click.echo(f"   📊 Consider dedicated audit log table for production")
                
    except Exception as e:
        click.echo(f"❌ Security audit error: {str(e)}")
    finally:
        db.close()


@enhanced_api_key_cli.command()
@click.option('--tenant-name', type=str, help='Tenant name to search for')
@click.option('--email', type=str, help='Tenant email to search for')
@click.option('--show-auth', is_flag=True, help='Show authentication method details')
@click.option('--limit', type=int, default=10, help='Maximum results to show')
def find_tenant_enhanced(tenant_name: Optional[str], email: Optional[str], show_auth: bool, limit: int):
    """Enhanced tenant search with authentication method details"""
    
    if not tenant_name and not email:
        click.echo("❌ Please provide either --tenant-name or --email")
        return
    
    db = SessionLocal()
    try:
        query = db.query(Tenant)
        
        if tenant_name:
            query = query.filter(Tenant.name.ilike(f"%{tenant_name}%"))
        
        if email:
            query = query.filter(Tenant.email.ilike(f"%{email}%"))
        
        tenants = query.limit(limit).all()
        
        if not tenants:
            click.echo("❌ No tenants found")
            return
        
        click.echo(f"🔍 Found {len(tenants)} tenant(s):")
        
        for tenant in tenants:
            api_key_masked = f"{tenant.api_key[:8]}...{tenant.api_key[-4:]}" if tenant.api_key else "None"
            click.echo(f"\n   📋 Tenant Details:")
            click.echo(f"      ID: {tenant.id}")
            click.echo(f"      Name: {tenant.name}")
            click.echo(f"      Business: {tenant.business_name}")
            click.echo(f"      Email: {tenant.email}")
            click.echo(f"      API Key: {api_key_masked}")
            click.echo(f"      Active: {tenant.is_active}")
            
            if show_auth:
                # Show authentication details
                from app.auth.models import TenantCredentials
                has_supabase = bool(tenant.supabase_user_id)
                has_local_creds = bool(
                    db.query(TenantCredentials).filter(
                        TenantCredentials.tenant_id == tenant.id
                    ).first()
                )
                
                click.echo(f"      🔐 Authentication:")
                click.echo(f"         Supabase: {'✅' if has_supabase else '❌'} ({tenant.supabase_user_id or 'Not configured'})")
                click.echo(f"         Local credentials: {'✅' if has_local_creds else '❌'}")
                click.echo(f"         Can reset key safely: {'✅' if (has_supabase or has_local_creds) else '❌'}")
            
    except Exception as e:
        click.echo(f"❌ Search error: {str(e)}")
    finally:
        db.close()


if __name__ == '__main__':
    enhanced_api_key_cli()