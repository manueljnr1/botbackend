"""
Email service using SendGrid for sending emails
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"Loaded .env from: {env_path}")
else:
    # Try loading from current directory
    load_dotenv()
    print("Loaded .env from current directory or environment")

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails using SendGrid"""
    
    def __init__(self):
        """Initialize the email service with SendGrid configuration"""
        # SendGrid settings - these will be loaded from your .env file
        self.api_key = os.getenv("SENDGRID_API_KEY", "")
        self.default_sender = os.getenv("DEFAULT_SENDER_EMAIL", "")
        self.default_sender_name = os.getenv("DEFAULT_SENDER_NAME", "Your App")
        
        # For escalation emails
        self.default_recipient = os.getenv("DEFAULT_SUPPORT_EMAIL", "")
        
        # Debug info
        print(f"API Key present: {bool(self.api_key)}")
        print(f"Sender email: {self.default_sender}")
        print(f"Sender name: {self.default_sender_name}")
        
        # Check if configuration is valid
        self.is_configured = bool(self.api_key and self.default_sender)
        
        if not self.is_configured:
            logger.warning("SendGrid email service is not properly configured.")
            print("❌ Missing configuration:")
            if not self.api_key:
                print("  - SENDGRID_API_KEY")
            if not self.default_sender:
                print("  - DEFAULT_SENDER_EMAIL")
        else:
            try:
                self.sg = sendgrid.SendGridAPIClient(api_key=self.api_key)
                logger.info("SendGrid email service initialized successfully")
                print("✅ SendGrid initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize SendGrid: {e}")
                print(f"❌ SendGrid initialization failed: {e}")
                self.is_configured = False
    
    def send_email(self, to_email, subject, html_content, from_email=None, from_name=None):
        """
        Send a generic email using SendGrid
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            from_email: Sender email (defaults to DEFAULT_SENDER_EMAIL)
            from_name: Sender name (defaults to DEFAULT_SENDER_NAME)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.error("Cannot send email: SendGrid is not configured")
            return False
        
        try:
            # Create the email
            from_email_obj = Email(
                email=from_email or self.default_sender,
                name=from_name or self.default_sender_name
            )
            to_email_obj = To(to_email)
            content = Content("text/html", html_content)
            
            mail = Mail(from_email_obj, to_email_obj, subject, content)
            
            # Send the email
            response = self.sg.client.mail.send.post(request_body=mail.get())
            
            # Check if successful (SendGrid returns 202 for success)
            if response.status_code == 202:
                logger.info(f"Email sent successfully to {to_email}")
                print(f"✅ Email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send email. Status code: {response.status_code}")
                print(f"❌ SendGrid error: {response.status_code}")
                return False
        
        except Exception as e:
            logger.exception(f"Failed to send email via SendGrid: {e}")
            print(f"❌ Error sending email: {e}")
            return False
    
    def send_escalation_email(self, user_id, conversation_history, user_email=None):
        """
        Send an escalation email to support
        """
        if not self.is_configured or not self.default_recipient:
            logger.error("Cannot send escalation email: Email service or support email is not configured")
            return False
        
        # Build email body
        body = [
            "<html><body>",
            "<h2>Chatbot Conversation Escalation</h2>",
            f"<p><strong>User ID:</strong> {user_id}</p>"
        ]
        
        if user_email:
            body.append(f"<p><strong>User Email:</strong> {user_email}</p>")
        
        body.append("<h3>Conversation History:</h3>")
        body.append("<div style='border: 1px solid #ddd; padding: 10px; margin: 10px 0;'>")
        
        for message in conversation_history:
            sender = "User" if message.get("is_from_user", False) else "Bot"
            content = message.get("content", "")
            body.append(f"<p><strong>{sender}:</strong> {content}</p>")
        
        body.append("</div>")
        body.append("<p>Please review and respond to the user as soon as possible.</p>")
        body.append("</body></html>")
        
        html_content = "\n".join(body)
        
        return self.send_email(
            to_email=self.default_recipient,
            subject=f"Chatbot Escalation: User {user_id}",
            html_content=html_content
        )

# Create a singleton instance
email_service = EmailService()