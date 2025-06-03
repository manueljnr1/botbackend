import logging

logger = logging.getLogger(__name__)

class MockEmailService:
    """Mock email service that logs emails instead of sending them"""
    
    def send_tenant_email(self, tenant_from_email: str, tenant_to_email: str, 
                         subject: str, body: str) -> bool:
        """Mock tenant notification email"""
        
        print("\n" + "="*80)
        print("📧 TENANT NOTIFICATION EMAIL")
        print("="*80)
        print(f"From: {tenant_from_email}")
        print(f"To: {tenant_to_email}")
        print(f"Subject: {subject}")
        print("-" * 80)
        print("EMAIL CONTENT:")
        print(body)
        print("="*80)
        print("✅ [MOCK] Email would be sent to tenant for feedback")
        print("="*80 + "\n")
        
        logger.info(f"📧 [MOCK] Tenant notification would be sent to {tenant_to_email}")
        return True
    
    def send_user_followup(self, tenant_from_email: str, user_email: str, 
                          subject: str, body: str) -> bool:
        """Mock user follow-up email"""
        
        print("\n" + "="*80)
        print("📧 USER FOLLOW-UP EMAIL")
        print("="*80)
        print(f"From: {tenant_from_email}")
        print(f"To: {user_email}")
        print(f"Subject: {subject}")
        print("-" * 80)
        print("EMAIL CONTENT:")
        print(body)
        print("="*80)
        print("✅ [MOCK] Follow-up email would be sent to user")
        print("="*80 + "\n")
        
        logger.info(f"📧 [MOCK] User follow-up would be sent to {user_email}")
        return True

# Global instance
email_service = MockEmailService()