import os
import logging
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class EmailProvider(ABC):
    @abstractmethod
    def send_email(self, to_email: str, subject: str, html_content: str, from_email: str = None) -> bool:
        pass

class SendGridProvider(EmailProvider):
    def __init__(self):
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            self.sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
            self.Mail = Mail
        except ImportError:
            logger.error("SendGrid not installed. Run: pip install sendgrid")
            raise
    
    def send_email(self, to_email: str, subject: str, html_content: str, from_email: str = None) -> bool:
        try:
            from_email = from_email or os.getenv('EMAIL_FROM_ADDRESS')
            from_name = os.getenv('EMAIL_FROM_NAME', 'Customer Support')
            
            message = self.Mail(
                from_email=f"{from_name} <{from_email}>",
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            
            response = self.sg.send(message)
            logger.info(f"✅ Email sent via SendGrid to {to_email} (Status: {response.status_code})")
            return response.status_code in [200, 201, 202]
            
        except Exception as e:
            logger.error(f"❌ SendGrid email failed: {e}")
            return False

class SMTPProvider(EmailProvider):

     

    def send_email(self, to_email: str, subject: str, html_content: str, from_email: str = None) -> bool:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # ... (your other code to get config and create the message is fine) ...
            smtp_server = os.getenv('SMTP_SERVER')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            smtp_username = os.getenv('SMTP_USERNAME')
            smtp_password = os.getenv('SMTP_PASSWORD')

            if not all([smtp_server, smtp_username, smtp_password]):
                # ...
                return False
            
            from_email = from_email or os.getenv('EMAIL_FROM_ADDRESS')
            from_name = os.getenv('EMAIL_FROM_NAME', 'Customer Support')
            
            logger.info(f"📧 Attempting to send email via SMTP:")
            # ... (your logging is fine) ...
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{from_name} <{from_email}>"
            msg['To'] = to_email
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Choose SMTP connection type based on port
            if smtp_port == 465:
                logger.info("🔐 Using SMTP_SSL connection (port 465)...")
                with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                    server.set_debuglevel(1)  # <--- THIS IS THE CRUCIAL LINE TO ADD
                    
                    logger.info("🔑 Authenticating with SMTP server (SSL)...")
                    server.login(smtp_username, smtp_password)
                    
                    logger.info("📤 Sending email...")
                    server.send_message(msg)
            
            logger.info(f"✅ Email sent successfully via SMTP to {to_email}")
            return True
                
        except Exception as e:
            logger.error(f"❌ SMTP email failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    # def send_email(self, to_email: str, subject: str, html_content: str, from_email: str = None) -> bool:
    #     try:
    #         import smtplib
    #         from email.mime.text import MIMEText
    #         from email.mime.multipart import MIMEMultipart
            
    #         # Get SMTP configuration
    #         smtp_server = os.getenv('SMTP_SERVER')
    #         smtp_port = int(os.getenv('SMTP_PORT', 587))
    #         smtp_username = os.getenv('SMTP_USERNAME')
    #         smtp_password = os.getenv('SMTP_PASSWORD')
            
    #         # Validate SMTP configuration
    #         if not all([smtp_server, smtp_username, smtp_password]):
    #             missing = []
    #             if not smtp_server: missing.append('SMTP_SERVER')
    #             if not smtp_username: missing.append('SMTP_USERNAME')
    #             if not smtp_password: missing.append('SMTP_PASSWORD')
    #             logger.error(f"❌ SMTP configuration incomplete. Missing: {', '.join(missing)}")
    #             return False
            
    #         from_email = from_email or os.getenv('EMAIL_FROM_ADDRESS')
    #         from_name = os.getenv('EMAIL_FROM_NAME', 'Customer Support')
            
    #         logger.info(f"📧 Attempting to send email via SMTP:")
    #         logger.info(f"   Server: {smtp_server}:{smtp_port}")
    #         logger.info(f"   From: {from_name} <{from_email}>")
    #         logger.info(f"   To: {to_email}")
    #         logger.info(f"   Subject: {subject}")
            
    #         # Create message
    #         msg = MIMEMultipart('alternative')
    #         msg['Subject'] = subject
    #         msg['From'] = f"{from_name} <{from_email}>"
    #         msg['To'] = to_email
            
    #         # Add HTML content
    #         html_part = MIMEText(html_content, 'html')
    #         msg.attach(html_part)
            
    #         # Choose SMTP connection type based on port
    #         if smtp_port == 465:
    #             # Use SMTP_SSL for port 465 (Gmail SSL)
    #             logger.info("🔐 Using SMTP_SSL connection (port 465)...")
    #             with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
    #                 logger.info("🔑 Authenticating with SMTP server (SSL)...")
    #                 server.login(smtp_username, smtp_password)
                    
    #                 logger.info("📤 Sending email...")
    #                 server.send_message(msg)
    #         # else:
    #         #     # Use regular SMTP with STARTTLS for port 587
    #         #     logger.info("🔐 Using SMTP connection with STARTTLS (port 587)...")
    #         #     with smtplib.SMTP(smtp_server, smtp_port) as server:
    #         #         logger.info("🔐 Starting TLS connection...")
    #         #         server.starttls()
                    
    #         #         logger.info("🔑 Authenticating with SMTP server...")
    #         #         server.login(smtp_username, smtp_password)
                    
    #         #         logger.info("📤 Sending email...")
    #         #         server.send_message(msg)
            
    #         logger.info(f"✅ Email sent successfully via SMTP to {to_email}")
    #         return True
            
    #     except Exception as e:
    #         logger.error(f"❌ SMTP email failed: {e}")
    #         import traceback
    #         logger.error(traceback.format_exc())
    #         return False
        

        
class EmailService:
    def __init__(self):
        self.provider = self._get_provider()
    
    def _get_provider(self) -> Optional[EmailProvider]:
        
        print("--- DEBUGGING ENVIRONMENT VARIABLES ---")
        print(f"EMAIL_PROVIDER: {os.getenv('EMAIL_PROVIDER')}")
        print(f"SMTP_SERVER: {os.getenv('SMTP_SERVER')}")
        print(f"SMTP_PORT: {os.getenv('SMTP_PORT')}")
        print(f"SMTP_USE_SSL: {os.getenv('SMTP_USE_SSL')}")
        print("------------------------------------")
        # --- END TEMPORARY DEBUG CODE ---

        provider_name = os.getenv('EMAIL_PROVIDER', '').lower()
        
        try:
            if provider_name == 'sendgrid':
                return SendGridProvider()
            elif provider_name == 'smtp':
                return SMTPProvider()
            else:
                logger.warning(f"No email provider configured or unknown provider: {provider_name}")
                return None
        except Exception as e:
            logger.error(f"Failed to initialize email provider: {e}")
            return None
            
    

    def send_tenant_email(self, tenant_from_email: str, tenant_to_email: str,
                     subject: str, body: str) -> bool:
        """Send email to tenant for feedback notifications"""
        if not self.provider:
            logger.error("❌ No email provider available")
            return False

        # --- STARTING A SIMPLE, DIRECT TEST ---
        print("--- RUNNING A SIMPLE, DIRECT TEST ---")
        my_actual_gmail = os.getenv('SMTP_USERNAME') # Use the same email you log in with

        if not my_actual_gmail:
            logger.error("❌ SMTP_USERNAME is not set in your .env file!")
            return False

        test_subject = "Simple Internal Test From Python"
        test_body = "This is a test message to confirm the core sending function is working."

        return self.provider.send_email(
            to_email=my_actual_gmail,      # Sending TO yourself
            subject=test_subject,
            html_content=test_body,
            from_email=my_actual_gmail   # Sending FROM yourself
    )

    # def send_tenant_email(self, tenant_from_email: str, tenant_to_email: str, 
    #                      subject: str, body: str) -> bool:
    #     """Send email to tenant for feedback notifications"""
    #     if not self.provider:
    #         logger.error("❌ No email provider available")
    #         return False
        
    #     return self.provider.send_email(
    #         to_email=tenant_to_email,
    #         subject=subject,
    #         html_content=body,
    #         from_email=tenant_from_email
    #     )
    
    def send_user_followup(self, tenant_from_email: str, user_email: str, 
                          subject: str, body: str) -> bool:
        """Send follow-up email to user with tenant's response"""
        if not self.provider:
            logger.error("❌ No email provider available")
            return False
        
        return self.provider.send_email(
            to_email=user_email,
            subject=subject,
            html_content=body,
            from_email=tenant_from_email
        )

# Create global instance
email_service = EmailService()