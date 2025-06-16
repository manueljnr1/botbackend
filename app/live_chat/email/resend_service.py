import os
import logging
from typing import Dict, Optional, List
import resend
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

logger = logging.getLogger(__name__)

class ResendEmailService:
    """Email service using Resend for sending transactional emails"""
    
    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@yourdomain.com")
        self.from_name = os.getenv("FROM_NAME", "Your Company")
        
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
        """Send agent invitation email"""
        try:
            if not self.enabled:
                logger.warning("Email service disabled - cannot send invitation")
                return {
                    "success": False,
                    "error": "Email service not configured"
                }
            
            # Render email template
            html_content = self._render_agent_invitation_template(
                agent_name=agent_name,
                business_name=business_name,
                invite_url=invite_url
            )
            
            # Send email via Resend
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": f"Join {business_name}'s Support Team - Set Up Your Agent Account",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "agent_invitation"},
                    {"name": "business", "value": business_name}
                ]
            }
            
            response = resend.Emails.send(params)
            
            logger.info(f"✅ Agent invitation sent to {to_email}, ID: {response.get('id')}")
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email,
                "message": "Invitation sent successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send agent invitation to {to_email}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "to_email": to_email
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
        """Default agent invitation email template"""
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
                .button:hover {{
                    background: linear-gradient(135deg, #5b21b6, #7c3aed);
                }}
                .info-box {{
                    background-color: #f3f4f6;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #6d28d9;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #6b7280;
                    font-size: 14px;
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
                
                <p>Great news! You've been invited to join <strong>{business_name}</strong> as a customer support agent. You'll be helping customers through our live chat system.</p>
                
                <div class="info-box">
                    <h3>🚀 What you'll be doing:</h3>
                    <ul>
                        <li>Respond to customer inquiries in real-time</li>
                        <li>Help resolve customer issues and questions</li>
                        <li>Work with a modern, easy-to-use chat interface</li>
                        <li>Make a real difference in customer satisfaction</li>
                    </ul>
                </div>
                
                <p><strong>To get started, click the button below to set up your account:</strong></p>
                
                <div style="text-align: center;">
                    <a href="{invite_url}" class="button">Accept Invitation & Set Password</a>
                </div>
                
                <div class="warning">
                    <strong>⏰ Important:</strong> This invitation will expire in 7 days. Please complete your setup soon!
                </div>
                
                <p>Once you've set up your account, you'll be able to:</p>
                <ul>
                    <li>Log into the agent dashboard</li>
                    <li>Start helping customers right away</li>
                    <li>Access training materials and documentation</li>
                    <li>Customize your profile and preferences</li>
                </ul>
                
                <p>If you have any questions about this invitation or need help getting started, please don't hesitate to reach out to us.</p>
                
                <p>We're excited to have you on the team!</p>
                
                <p>Best regards,<br>
                The {business_name} Team</p>
                
                <div class="footer">
                    <p>This invitation was sent to {agent_name} for {business_name}</p>
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                    <p>The invitation link will expire automatically.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    async def send_password_reset_notification(self, to_email: str, agent_name: str, 
                                             business_name: str) -> Dict:
        """Send notification when agent password is reset"""
        try:
            if not self.enabled:
                return {"success": False, "error": "Email service not configured"}
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Password Reset Confirmation</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .success {{ background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; color: #155724; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>✅ Account Activated Successfully</h2>
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
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": f"Welcome to {business_name} - Account Activated!",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "account_activation"},
                    {"name": "business", "value": business_name}
                ]
            }
            
            response = resend.Emails.send(params)
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email
            }
            
        except Exception as e:
            logger.error(f"Failed to send activation email: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def send_agent_revoked_notification(self, to_email: str, agent_name: str, 
                                            business_name: str) -> Dict:
        """Send notification when agent access is revoked"""
        try:
            if not self.enabled:
                return {"success": False, "error": "Email service not configured"}
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Account Access Update</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; color: #856404; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Account Access Update</h2>
                    
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
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": f"Account Access Update - {business_name}",
                "html": html_content,
                "tags": [
                    {"name": "type", "value": "account_revoked"},
                    {"name": "business", "value": business_name}
                ]
            }
            
            response = resend.Emails.send(params)
            
            return {
                "success": True,
                "email_id": response.get("id"),
                "to_email": to_email
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
            
            # Try to send a test email to verify connection
            test_params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [self.from_email],  # Send to self
                "subject": "Live Chat Email Service Test",
                "html": "<h1>✅ Email service is working!</h1><p>This is a test email from your live chat system.</p>",
                "tags": [{"name": "type", "value": "test"}]
            }
            
            response = resend.Emails.send(test_params)
            
            return {
                "success": True,
                "message": "Email service is working correctly",
                "test_email_id": response.get("id")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Email service test failed: {str(e)}"
            }