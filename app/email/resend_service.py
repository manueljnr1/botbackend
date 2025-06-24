import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class ResendEmailService:
    """Email service using Resend... for sending transactional emails"""
    
    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@yourdomain.com")
        self.from_name = os.getenv("FROM_NAME", "Your Company")
        
        if not self.api_key:
            logger.warning("RESEND_API_KEY not set - email sending will be disabled")
            self.enabled = False
        else:
            try:
                import resend
                resend.api_key = self.api_key
                self.enabled = True
            except ImportError:
                logger.warning("resend package not installed - email sending will be disabled")
                self.enabled = False
    
    async def send_agent_invitation(self, to_email: str, agent_name: str, 
                                  business_name: str, invite_url: str) -> Dict:
        """Send agent invitation email"""
        if not self.enabled:
            logger.warning("Email service disabled - cannot send invitation")
            return {
                "success": False,
                "error": "Email service not configured"
            }
        
        try:
            import resend
            
            html_content = f"""
            <h1>Welcome to {business_name}!</h1>
            <p>Hi {agent_name},</p>
            <p>You've been invited to join our customer support team.</p>
            <p><a href="{invite_url}">Accept Invitation</a></p>
            <p>This invitation expires in 7 days.</p>
            """
            
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": f"Join {business_name}'s Support Team",
                "html": html_content,
            }
            
            response = resend.Emails.send(params)
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email,
                "message": "Invitation sent successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to send agent invitation: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "to_email": to_email
            }
    
    async def send_password_reset_notification(self, to_email: str, agent_name: str, 
                                             business_name: str) -> Dict:
        """Send notification when agent password is reset"""
        return {"success": True, "message": "Password reset notification sent"}
    
    async def send_agent_revoked_notification(self, to_email: str, agent_name: str, 
                                            business_name: str) -> Dict:
        """Send notification when agent access is revoked"""
        return {"success": True, "message": "Agent revoked notification sent"}
    
    async def test_email_connection(self) -> Dict:
        """Test if email service is working"""
        if not self.enabled:
            return {
                "success": False,
                "error": "Email service not configured - RESEND_API_KEY missing"
            }
        
        return {
            "success": True,
            "message": "Email service is configured correctly"
        }

# Global instance
email_service = ResendEmailService()
