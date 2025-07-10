# app/email/resend_service.py - UPDATED with Dynamic FROM_NAME

import os
import logging
from typing import Dict, Optional, List
import httpx
from datetime import datetime
import resend
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

logger = logging.getLogger(__name__)

class ResendEmailService:
    """Email service using Resend for sending transactional emails"""
    
    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@yourdomain.com")
        self.default_from_name = os.getenv("FROM_NAME", "Support Team")  # Fallback name
        
        if not self.api_key:
            logger.warning("RESEND_API_KEY not set - email sending will be disabled")
            self.enabled = False
        else:
            resend.api_key = self.api_key
            self.enabled = True
        
        # Initialize Jinja2 for email templates
        template_dir = Path(__file__).parent / "templates"
        template_dir.mkdir(exist_ok=True)
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
    
    async def send_agent_invitation(self, to_email: str, agent_name: str, 
                                  business_name: str, invite_url: str) -> Dict:
        """Send agent invitation email with dynamic FROM_NAME"""
        try:
            if not self.enabled:
                logger.warning("Email service disabled - cannot send invitation")
                return {
                    "success": False,
                    "error": "Email service not configured"
                }
            
            # 🎯 DYNAMIC FROM_NAME - Use tenant's business name
            dynamic_from_name = f"{business_name} Support" if business_name else self.default_from_name
            
            # Render email template
            html_content = self._render_agent_invitation_template(
                agent_name=agent_name,
                business_name=business_name,
                invite_url=invite_url
            )
            
            # Send email via Resend with dynamic FROM_NAME
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": f"Join {business_name}'s Support Team - Set Up Your Agent Account",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "agent_invitation"},
                    {"name": "business", "value": self._sanitize_tag_value(business_name)}  # ← FIX THIS
                ]
            }
            
            response = resend.Emails.send(params)
            
            logger.info(f"✅ Agent invitation sent to {to_email} from '{dynamic_from_name}', ID: {response.get('id')}")
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email,
                "from_name": dynamic_from_name,  # Include in response
                "message": "Invitation sent successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send agent invitation to {to_email}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "to_email": to_email
            }
    
    async def send_password_reset_notification(self, to_email: str, agent_name: str, 
                                             business_name: str) -> Dict:
        """Send notification when agent password is reset with dynamic FROM_NAME"""
        try:
            if not self.enabled:
                return {"success": False, "error": "Email service not configured"}
            
            # 🎯 DYNAMIC FROM_NAME - Use tenant's business name
            dynamic_from_name = f"{business_name} Support" if business_name else self.default_from_name
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Account Activated - {business_name}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .success {{ background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; color: #155724; }}
                    .logo {{ background: linear-gradient(135deg, #6d28d9, #9333ea); color: white; width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px; font-size: 24px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="logo">🎧</div>
                        <h2>✅ Welcome to {business_name}!</h2>
                    </div>
                    
                    <p>Hi {agent_name},</p>
                    
                    <div class="success">
                        <strong>Great news!</strong> Your agent account for {business_name} has been successfully activated.
                    </div>
                    
                    <p>You can now log in to the agent dashboard and start helping customers. Here's what you can do next:</p>
                    
                    <ul>
                        <li>Log in to your agent dashboard</li>
                        <li>Complete your profile setup</li>
                        <li>Review the training materials</li>
                        <li>Start accepting customer chats</li>
                    </ul>
                    
                    <p>Welcome to the {business_name} support team!</p>
                    
                    <p>Best regards,<br>The {business_name} Team</p>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": f"{dynamic_from_name} <{self.from_email}>",  # 🎯 Dynamic name here
                "to": [to_email],
                "subject": f"Welcome to {business_name} - Account Activated!",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "account_activation"},
                    {"name": "business", "value": business_name}
                ]
            }
            
            response = resend.Emails.send(params)
            
            logger.info(f"✅ Account activation email sent to {to_email} from '{dynamic_from_name}'")
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email,
                "from_name": dynamic_from_name
            }
            
        except Exception as e:
            logger.error(f"Failed to send activation email: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def send_agent_revoked_notification(self, to_email: str, agent_name: str, 
                                            business_name: str) -> Dict:
        """Send notification when agent access is revoked with dynamic FROM_NAME"""
        try:
            if not self.enabled:
                return {"success": False, "error": "Email service not configured"}
            
            # 🎯 DYNAMIC FROM_NAME - Use tenant's business name
            dynamic_from_name = f"{business_name} Support" if business_name else self.default_from_name
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Account Access Update - {business_name}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; color: #856404; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Account Access Update - {business_name}</h2>
                    
                    <p>Hi {agent_name},</p>
                    
                    <div class="warning">
                        <strong>Important:</strong> Your agent access for {business_name} has been updated.
                    </div>
                    
                    <p>Your agent account access has been revoked. You will no longer be able to access the agent dashboard or handle customer chats.</p>
                    
                    <p>If you believe this was done in error or have questions about this change, please contact your administrator.</p>
                    
                    <p>Thank you for your service to {business_name}.</p>
                    
                    <p>Best regards,<br>The {business_name} Team</p>
                </div>
            </body>
            </html>
            """
            
            params = {
                "from": f"{dynamic_from_name} <{self.from_email}>",  # 🎯 Dynamic name here
                "to": [to_email],
                "subject": f"Account Access Update - {business_name}",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "account_revoked"},
                    {"name": "business", "value": business_name}
                ]
            }
            
            response = resend.Emails.send(params)
            
            logger.info(f"✅ Account revocation email sent to {to_email} from '{dynamic_from_name}'")
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email,
                "from_name": dynamic_from_name
            }
            
        except Exception as e:
            logger.error(f"Failed to send revocation email: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def test_email_connection(self) -> Dict:
        """Test if email service is working"""
        try:
            if not self.enabled:
                return {
                    "success": False,
                    "error": "Email service not configured - RESEND_API_KEY missing"
                }
            
            # Use default name for test emails
            test_from_name = self.default_from_name
            
            # Try to send a test email to verify connection
            test_params = {
                "from": f"{test_from_name} <{self.from_email}>",
                "to": [self.from_email],  # Send to self
                "subject": "Live Chat Email Service Test",
                "html": "<h1>✅ Email service is working!</h1><p>This is a test email from your live chat system.</p>",
                "tags": [{"name": "type", "value": "test"}]
            }
            
            response = resend.Emails.send(test_params)
            
            return {
                "success": True,
                "message": "Email service is working correctly",
                "test_email_id": response.get("id"),
                "from_name": test_from_name
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Email service test failed: {str(e)}"
            }
    
    def _render_agent_invitation_template(self, agent_name: str, business_name: str, 
                                        invite_url: str) -> str:
        """Render the agent invitation email template"""
        
        # Try to load custom template first, fall back to default
        try:
            template = self.jinja_env.get_template("agent_invitation.html")
            return template.render(
                agent_name=agent_name,
                business_name=business_name,
                invite_url=invite_url,
                expires_in="7 days",
                support_email=self.from_email
            )
        except Exception:
            # Fallback to inline template
            return self._get_default_invitation_template(
                agent_name, business_name, invite_url
            )
    
    def _get_default_invitation_template(self, agent_name: str, business_name: str, 
                                       invite_url: str) -> str:
        """Default agent invitation email template with business name"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Join {business_name} Support Team</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .container {{
                    background-color: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .logo {{
                    background: linear-gradient(135deg, #6d28d9, #9333ea);
                    color: white;
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 20px;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #6d28d9, #9333ea);
                    color: white;
                    text-decoration: none;
                    padding: 16px 32px;
                    border-radius: 8px;
                    font-weight: 600;
                    margin: 20px 0;
                    text-align: center;
                }}
                .info-box {{
                    background-color: #f3f4f6;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #6d28d9;
                }}
                .warning {{
                    background-color: #fef3c7;
                    border: 1px solid #f59e0b;
                    padding: 15px;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">🎧</div>
                    <h1>Welcome to {business_name}!</h1>
                    <p>You've been invited to join our customer support team</p>
                </div>
                
                <p>Hi {agent_name},</p>
                
                <p>Great news! You've been invited to join <strong>{business_name}</strong> as a customer support agent.</p>
                
                <div class="info-box">
                    <h3>🚀 What you'll be doing:</h3>
                    <ul>
                        <li>Respond to customer inquiries in real-time</li>
                        <li>Help resolve customer issues and questions</li>
                        <li>Work with a modern, easy-to-use chat interface</li>
                        <li>Make a real difference in customer satisfaction</li>
                    </ul>
                </div>
                
                <p><strong>To get started, click the button below:</strong></p>
                
                <div style="text-align: center;">
                    <a href="{invite_url}" class="button">Accept Invitation & Set Password</a>
                </div>
                
                <div class="warning">
                    <strong>⏰ Important:</strong> This invitation will expire in 7 days. Please complete your setup soon!
                </div>
                
                <p>If you have any questions, please don't hesitate to reach out.</p>
                
                <p>We're excited to have you on the team!</p>
                
                <p>Best regards,<br>The {business_name} Team</p>
            </div>
        </body>
        </html>
        """


    async def send_conversation_transcript(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: str,
        conversation_id: int,
        agent_name: str,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None
    ) -> Dict[str, any]:
        """
        Send conversation transcript email
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML version of transcript
            plain_content: Plain text version of transcript
            conversation_id: ID of the conversation
            agent_name: Name of agent sending the transcript
            cc_emails: Optional CC recipients
            bcc_emails: Optional BCC recipients
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "Email service not configured"
            }
        
        try:
            # Prepare email payload
            email_data = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": plain_content,
                "tags": [
                    {"name": "type", "value": "conversation_transcript"},
                    {"name": "conversation_id", "value": str(conversation_id)},
                    {"name": "agent", "value": agent_name}
                ]
            }
            
            # Add CC/BCC if provided
            if cc_emails:
                email_data["cc"] = cc_emails
            
            if bcc_emails:
                email_data["bcc"] = bcc_emails
            
            # Send email via Resend API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/emails",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=email_data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Transcript email sent successfully to {to_email}, ID: {result.get('id')}")
                    
                    return {
                        "success": True,
                        "email_id": result.get("id"),
                        "to_email": to_email,
                        "subject": subject,
                        "conversation_id": conversation_id,
                        "sent_at": datetime.utcnow().isoformat()
                    }
                else:
                    error_detail = response.text
                    logger.error(f"❌ Failed to send transcript email: {response.status_code} - {error_detail}")
                    
                    return {
                        "success": False,
                        "error": f"Email send failed: {response.status_code}",
                        "details": error_detail
                    }
                    
        except httpx.TimeoutException:
            logger.error("❌ Email send timeout")
            return {
                "success": False,
                "error": "Email send timeout"
            }
        except httpx.RequestError as e:
            logger.error(f"❌ Email send request error: {str(e)}")
            return {
                "success": False,
                "error": f"Request error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error sending transcript email: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }



    def _sanitize_tag_value(self, value: str) -> str:
        """Sanitize tag values to only contain ASCII letters, numbers, underscores, or dashes"""
        if not value:
            return "unknown"
        
        # Replace spaces and special characters with underscores
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', value)
        
        # Remove multiple consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        
        # Ensure it's not empty and not too long
        if not sanitized:
            return "unknown"
        
        return sanitized[:50]  # Limit length to 50 characters


# Create the email service instance
email_service = ResendEmailService()