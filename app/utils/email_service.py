"""
Email service for sending escalation emails
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending emails"""
    
    def __init__(self):
        """Initialize the email service with configuration from environment variables"""
        # Email server settings
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        
        # Default sender and recipient
        self.default_sender = os.getenv("DEFAULT_SENDER_EMAIL", "")
        self.default_recipient = os.getenv("DEFAULT_SUPPORT_EMAIL", "")
        
        # Check if configuration is valid
        self.is_configured = (
            self.smtp_username and self.smtp_password and
            self.default_sender and self.default_recipient
        )
        
        if not self.is_configured:
            logger.warning("Email service is not properly configured. Check environment variables.")
    
    def send_escalation_email(self, user_id, conversation_history, user_email=None):
        """
        Send an escalation email to support
        
        Args:
            user_id: Identifier for the user (phone number, email, etc.)
            conversation_history: List of message dictionaries with 'content' and 'is_from_user' keys
            user_email: Optional email of the user for reply
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.error("Cannot send email: Email service is not configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.default_sender
            msg['To'] = self.default_recipient
            msg['Subject'] = f"Chatbot Escalation: User {user_id}"
            
            # Build email body
            body = [
                "<html><body>",
                "<h2>Chatbot Conversation Escalation</h2>",
                f"<p><strong>User ID:</strong> {user_id}</p>"
            ]
            
            # Add user email if available
            if user_email:
                body.append(f"<p><strong>User Email:</strong> {user_email}</p>")
            
            # Add conversation history
            body.append("<h3>Conversation History:</h3>")
            body.append("<div style='border: 1px solid #ddd; padding: 10px; margin: 10px 0;'>")
            
            for message in conversation_history:
                sender = "User" if message.get("is_from_user", False) else "Bot"
                content = message.get("content", "")
                body.append(f"<p><strong>{sender}:</strong> {content}</p>")
            
            body.append("</div>")
            body.append("<p>Please review and respond to the user as soon as possible.</p>")
            body.append("</body></html>")
            
            # Set email content
            msg.attach(MIMEText("\n".join(body), "html"))
            
            # Connect to SMTP server and send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Escalation email sent successfully for user {user_id}")
            return True
        
        except Exception as e:
            logger.exception(f"Failed to send escalation email: {e}")
            return False

# Create a singleton instance
email_service = EmailService()