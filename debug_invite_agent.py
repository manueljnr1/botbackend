# Create this debug script: debug_invite_agent.py
import sys
import traceback
from app.database import SessionLocal
from app.tenants.models import Tenant

def debug_invite_agent():
    print("=== DEBUG: Agent Invitation Endpoint ===\n")
    
    # 1. Test database connection
    print("1. Testing database connection...")
    try:
        db = SessionLocal()
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).fetchone()
        print("✅ Database connection: OK")
        db.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # 2. Test model imports
    print("\n2. Testing model imports...")
    try:
        from app.live_chat.models import Agent, AgentStatus
        print("✅ Live chat models import: OK")
    except Exception as e:
        print(f"❌ Live chat models import failed: {e}")
        traceback.print_exc()
        return
    
    # 3. Test service import
    print("\n3. Testing service imports...")
    try:
        from app.live_chat.agent_service import AgentAuthService
        print("✅ Agent service import: OK")
    except Exception as e:
        print(f"❌ Agent service import failed: {e}")
        traceback.print_exc()
        return
    
    # 4. Test tenant lookup
    print("\n4. Testing tenant lookup...")
    try:
        db = SessionLocal()
        tenant = db.query(Tenant).first()
        if tenant:
            print(f"✅ Found tenant: {tenant.name} (ID: {tenant.id})")
            print(f"   API Key: {tenant.api_key[:10]}...")
        else:
            print("❌ No tenants found in database")
            return
        db.close()
    except Exception as e:
        print(f"❌ Tenant lookup failed: {e}")
        return
    
    # 5. Test email service
    print("\n5. Testing email service...")
    try:
        from app.email.resend_service import email_service
        print(f"✅ Email service import: OK")
        print(f"   Email enabled: {email_service.enabled}")
        if not email_service.enabled:
            print("⚠️  Email service disabled (RESEND_API_KEY not set)")
    except Exception as e:
        print(f"❌ Email service import failed: {e}")
        traceback.print_exc()
    
    # 6. Test agent invitation process
    print("\n6. Testing agent invitation process...")
    try:
        db = SessionLocal()
        service = AgentAuthService(db)
        
        # Use the first tenant for testing
        tenant = db.query(Tenant).first()
        
        print(f"   Testing with tenant: {tenant.name}")
        print("   Calling invite_agent method...")
        
        # This will fail if there are issues
        result = service.invite_agent(
            tenant_id=tenant.id,
            email="test-debug@example.com",
            full_name="Debug Test Agent",
            invited_by_id=tenant.id
        )
        
        print(f"✅ Agent invitation successful: {result}")
        
        # Clean up test agent
        test_agent = db.query(Agent).filter(Agent.email == "test-debug@example.com").first()
        if test_agent:
            db.delete(test_agent)
            db.commit()
            print("   Test agent cleaned up")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Agent invitation failed: {e}")
        traceback.print_exc()
        
        # Try to clean up
        try:
            db.rollback()
            test_agent = db.query(Agent).filter(Agent.email == "test-debug@example.com").first()
            if test_agent:
                db.delete(test_agent)
                db.commit()
            db.close()
        except:
            pass
        return
    
    print("\n🎉 All checks passed! The endpoint should work now.")

if __name__ == "__main__":
    debug_invite_agent()