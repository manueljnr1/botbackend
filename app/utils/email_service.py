# app/utils/email_service.py - Updated for multi-tenant
"""
Tenant-Aware Email Service for Smart Feedback System
Each tenant uses their own from/to emails via your SMTP system
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Multi-tenant email service using tenant-specific email addresses"""
    
    def __init__(self):
        # Your system's SMTP credentials (used to send emails on behalf of tenants)
        self.smtp_server = getattr(settings, 'SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_username = getattr(settings, 'SMTP_USERNAME', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
    
    def send_tenant_email(self, tenant_from_email: str, tenant_to_email: str, 
                         subject: str, body: str) -> bool:
        """
        Send email on behalf of a tenant using their configured email addresses
        
        Args:
            tenant_from_email: The tenant's "from" email (what user sees)
            tenant_to_email: The tenant's feedback email (where they receive emails)
            subject: Email subject
            body: Email body
        """
        try:
            if not self.smtp_username or not self.smtp_password:
                logger.error("System SMTP credentials not configured")
                return False
            
            if not tenant_from_email or not tenant_to_email:
                logger.error("Tenant email addresses not provided")
                return False
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = tenant_from_email        # User sees this as sender
            msg['To'] = tenant_to_email           # Tenant receives at this address
            msg['Subject'] = subject
            
            # Add reply-to for tenant responses
            msg['Reply-To'] = tenant_from_email
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Send using your system's SMTP credentials
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            
            # Send from your system but with tenant's "from" address
            server.sendmail(self.smtp_username, tenant_to_email, text)
            server.quit()
            
            logger.info(f"Email sent successfully from {tenant_from_email} to {tenant_to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending tenant email: {e}")
            return False
    
    def send_user_followup(self, tenant_from_email: str, user_email: str, 
                          subject: str, body: str) -> bool:
        """
        Send follow-up email to user from tenant
        
        Args:
            tenant_from_email: Tenant's email (what user sees as sender)
            user_email: User's email address
            subject: Email subject
            body: Email body
        """
        try:
            if not self.smtp_username or not self.smtp_password:
                logger.error("System SMTP credentials not configured")
                return False
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = tenant_from_email
            msg['To'] = user_email
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            server.sendmail(self.smtp_username, user_email, text)
            server.quit()
            
            logger.info(f"Follow-up email sent from {tenant_from_email} to {user_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending follow-up email: {e}")
            return False