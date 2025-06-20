# app/chatbot/smart_feedback.py
"""
Advanced Smart Feedback System - Supabase + Resend Integration
Efficient, trackable, and production-ready with 30-day email memory
"""

import logging
import uuid
import re
import json
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.chatbot.models import ChatSession
from app.knowledge_base.models import FAQ 
import os

# Supabase integration
try:
    from supabase import create_client, Client
except ImportError:
    raise ImportError("Please install: pip install supabase")

logger = logging.getLogger(__name__)

class PendingFeedback(Base):
    """Enhanced model to track pending feedback requests"""
    __tablename__ = "pending_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    session_id = Column(String, ForeignKey("chat_sessions.session_id"))
    user_email = Column(String)
    user_question = Column(Text)
    bot_response = Column(Text)
    conversation_context = Column(Text)  # JSON string of recent messages
    
    # Email tracking
    tenant_email_sent = Column(Boolean, default=False)
    tenant_email_id = Column(String, nullable=True)  # Resend email ID
    tenant_response = Column(Text, nullable=True)
    user_notified = Column(Boolean, default=False)
    user_email_id = Column(String, nullable=True)  # Follow-up email ID
    

    
    form_accessed = Column(Boolean, default=False)
    form_accessed_at = Column(DateTime, nullable=True)
    form_expired = Column(Boolean, default=False)
    
    
    add_to_faq = Column(Boolean, default=False)
    faq_question = Column(Text, nullable=True)
    faq_answer = Column(Text, nullable=True)
    faq_created = Column(Boolean, default=False)

    # Status tracking
    status = Column(String, default="pending")  # pending, tenant_notified, responded, resolved
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    tenant_notified_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    session = relationship("ChatSession")

class AdvancedSmartFeedbackManager:
    """
    Production-ready smart feedback system with:
    - Real-time email tracking via Supabase
    - Direct Resend integration for reliability
    - Automatic webhook processing
    - Advanced analytics and monitoring
    - 30-day email memory system
    """
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        
        # Email memory configuration
        self.EMAIL_MEMORY_DURATION = timedelta(days=30)  # 30-day memory
        
        # Initialize Supabase
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Initialize Resend
        self.resend_api_key = os.getenv("RESEND_API_KEY")
        if not self.resend_api_key:
            raise ValueError("RESEND_API_KEY must be set")
        
        self.from_email = os.getenv("FROM_EMAIL", "feedback@agentlyra.com")
        
        # Enhanced inadequate response patterns
        self.inadequate_response_patterns = [
            r"i don't have.*information",
            r"i'm not sure",
            r"i don't know",
            r"i can't find.*information",
            r"i'm sorry.*i don't have",
            r"i don't have access to",
            r"i'm unable to.*provide",
            r"i cannot.*answer",
            r"i'm not able to",
            r"please contact.*support",
            r"i'd recommend.*contacting",
            r"you may want to.*contact",
            r"for more information.*contact",
            r"sorry.*unable",
            r"sorry.*cannot",
            r"am unable to",
            r"i'm not familiar with",
            r"i don't understand",
            r"could you clarify",
            r"that's outside my knowledge"
        ]
        
        logger.info(f"✅ Advanced Smart Feedback Manager initialized for tenant {tenant_id} with 30-day email memory")
    
    def should_request_email(self, session_id: str, user_identifier: str) -> bool:
        """
        Check if we should ask for email with 30-day memory logic
        """
        try:
            from app.chatbot.simple_memory import SimpleChatbotMemory
            
            memory = SimpleChatbotMemory(self.db, self.tenant_id)
            conversation_history = memory.get_conversation_history(user_identifier, max_messages=5)
            
            # Check if we already have email for this session
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session and hasattr(session, 'user_email') and session.user_email:
                # Check if email has expired (30 days)
                if hasattr(session, 'email_captured_at') and session.email_captured_at:
                    email_age = datetime.utcnow() - session.email_captured_at
                    
                    if email_age > self.EMAIL_MEMORY_DURATION:
                        logger.info(f"📅 Email expired for session {session_id} (age: {email_age.days} days), requesting fresh email")
                        # Clear expired email
                        session.user_email = None
                        session.email_captured_at = None
                        if hasattr(session, 'email_expires_at'):
                            session.email_expires_at = None
                        self.db.commit()
                        
                        # Track email expiration in Supabase
                        self._track_email_expired(session_id, session.user_email, email_age.days)
                        
                        return True  # Request fresh email
                    else:
                        days_remaining = (self.EMAIL_MEMORY_DURATION - email_age).days
                        logger.debug(f"📧 Email still valid for session {session_id} ({days_remaining} days remaining)")
                        return False  # Email still valid
                else:
                    # Legacy session without capture timestamp - assume it's old and request fresh
                    logger.info(f"🔄 Legacy session {session_id} without timestamp, requesting fresh email")
                    session.user_email = None
                    self.db.commit()
                    return True
            
            # Check if conversation is new (no meaningful history)
            if len(conversation_history) <= 1:  # Only greeting or first message
                logger.info(f"🆕 New conversation for {user_identifier}, requesting email")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking email request: {e}")
            return False
    
    def generate_email_request_message(self, tenant_name: str) -> str:
        """Generate a natural, professional email request with memory context"""
        messages = [
            f"Hi! I'm {tenant_name}'s AI assistant. To provide you with the best possible support and follow-up, could you please share your email address?",
            f"Hello! Welcome to {tenant_name}. For quality service and follow-up support, may I have your email address?",
            f"Hi there! I'm here to help you with {tenant_name}. To ensure I can provide complete assistance, could you share your email with me?",
            f"Welcome! I'm {tenant_name}'s virtual assistant. For better service and support follow-up, would you mind sharing your email address?",
            f"Good to see you! I'm {tenant_name}'s AI assistant. For the best experience and follow-up support, could you please provide your email?"
        ]
        import random
        return random.choice(messages)
    
    def extract_email_from_message(self, message: str) -> Optional[str]:
        """Extract and validate email address from user message"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, message)
        return matches[0] if matches else None
    
    def store_user_email(self, session_id: str, email: str) -> bool:
        """
        Store user email with 30-day expiration tracking
        """
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session:
                # Store email with timestamp
                session.user_email = email.lower().strip()
                session.email_captured_at = datetime.utcnow()
                
                # Set expiration date
                if hasattr(session, 'email_expires_at'):
                    session.email_expires_at = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
                
                self.db.commit()
                
                # Track in Supabase for analytics
                self._track_email_capture(session_id, email)
                
                # Log memory duration
                expiry_date = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
                logger.info(f"✅ Stored email {email} for session {session_id} (expires: {expiry_date.strftime('%Y-%m-%d')})")
                return True
        except Exception as e:
            logger.error(f"❌ Error storing email: {e}")
            self.db.rollback()
        return False
    
    def get_email_memory_status(self, session_id: str) -> Dict[str, Any]:
        """Get email memory status for debugging"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                return {"status": "session_not_found"}
            
            if not session.user_email:
                return {"status": "no_email"}
            
            if hasattr(session, 'email_captured_at') and session.email_captured_at:
                email_age = datetime.utcnow() - session.email_captured_at
                days_remaining = (self.EMAIL_MEMORY_DURATION - email_age).days
                
                return {
                    "status": "active" if email_age <= self.EMAIL_MEMORY_DURATION else "expired",
                    "email": session.user_email,
                    "captured_at": session.email_captured_at.isoformat(),
                    "age_days": email_age.days,
                    "days_remaining": max(0, days_remaining),
                    "expires_at": (session.email_captured_at + self.EMAIL_MEMORY_DURATION).isoformat()
                }
            else:
                return {
                    "status": "legacy_no_timestamp",
                    "email": session.user_email
                }
                
        except Exception as e:
            logger.error(f"Error getting email memory status: {e}")
            return {"status": "error", "error": str(e)}
    
    def cleanup_expired_emails(self) -> int:
        """Clean up expired emails across all sessions for this tenant"""
        try:
            cutoff_date = datetime.utcnow() - self.EMAIL_MEMORY_DURATION
            
            # Find expired sessions
            expired_sessions = self.db.query(ChatSession).filter(
                ChatSession.tenant_id == self.tenant_id,
                ChatSession.user_email.isnot(None),
                ChatSession.email_captured_at < cutoff_date
            ).all()
            
            cleaned_count = 0
            for session in expired_sessions:
                old_email = session.user_email
                session.user_email = None
                session.email_captured_at = None
                if hasattr(session, 'email_expires_at'):
                    session.email_expires_at = None
                
                # Track cleanup in Supabase
                email_age = datetime.utcnow() - session.email_captured_at if session.email_captured_at else None
                self._track_email_expired(session.session_id, old_email, email_age.days if email_age else None)
                
                cleaned_count += 1
            
            self.db.commit()
            logger.info(f"🧹 Cleaned up {cleaned_count} expired emails for tenant {self.tenant_id}")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired emails: {e}")
            self.db.rollback()
            return 0
    
    def detect_inadequate_response(self, bot_response: str) -> bool:
        """
        Advanced inadequate response detection with scoring
        """
        response_lower = bot_response.lower().strip()
        
        logger.debug(f"🔍 Analyzing response: '{response_lower[:100]}...'")
        
        inadequate_score = 0
        matched_patterns = []
        
        # Pattern matching with scoring
        for pattern in self.inadequate_response_patterns:
            if re.search(pattern, response_lower):
                inadequate_score += 1
                matched_patterns.append(pattern)
        
        # Additional heuristics
        response_length = len(bot_response)
        word_count = len(bot_response.split())
        
        # Very short responses with uncertainty words
        if response_length < 50 and word_count < 10:
            uncertainty_words = ["sorry", "don't", "can't", "unable", "unclear", "unsure"]
            if any(word in response_lower for word in uncertainty_words):
                inadequate_score += 2
                matched_patterns.append("short_uncertain_response")
        
        # Question deflection patterns
        deflection_patterns = [
            r"you should.*contact",
            r"please.*reach out",
            r"i recommend.*speaking",
            r"you might want to.*call"
        ]
        
        for pattern in deflection_patterns:
            if re.search(pattern, response_lower):
                inadequate_score += 1
                matched_patterns.append(pattern)
        
        is_inadequate = inadequate_score >= 1
        
        if is_inadequate:
            logger.info(f"🔔 INADEQUATE RESPONSE DETECTED (score: {inadequate_score})")
            logger.info(f"📝 Matched patterns: {matched_patterns}")
        else:
            logger.debug(f"✅ Response appears adequate (score: {inadequate_score})")
        
        return is_inadequate
    
    def create_feedback_request(self, session_id: str, user_question: str, 
                              bot_response: str, conversation_context: List[Dict]) -> Optional[str]:
        """
        Create feedback request with advanced tracking and email sending
        """
        try:
            # Get session and validate
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                logger.error(f"❌ Session {session_id} not found")
                return None
            
            user_email = getattr(session, 'user_email', None)
            if not user_email:
                logger.warning(f"⚠️ No user email found for session {session_id}")
                return None
            
            # Check if email is still valid (not expired)
            if hasattr(session, 'email_captured_at') and session.email_captured_at:
                email_age = datetime.utcnow() - session.email_captured_at
                if email_age > self.EMAIL_MEMORY_DURATION:
                    logger.warning(f"⚠️ User email expired for session {session_id}, cannot create feedback request")
                    return None
            
            # Generate unique feedback ID
            feedback_id = str(uuid.uuid4())
            
            # Get tenant information
            tenant = self._get_tenant()
            if not tenant:
                logger.error(f"❌ Tenant {self.tenant_id} not found")
                return None
            
            # Create pending feedback record
            pending_feedback = PendingFeedback(
                feedback_id=feedback_id,
                tenant_id=self.tenant_id,
                session_id=session_id,
                user_email=user_email,
                user_question=user_question,
                bot_response=bot_response,
                conversation_context=json.dumps(conversation_context),
                status="pending"
            )
            
            self.db.add(pending_feedback)
            self.db.commit()
            
            # Send notification email to tenant
            email_sent, email_id = self._send_tenant_notification_advanced(
                feedback_id=feedback_id,
                tenant=tenant,
                user_question=user_question,
                bot_response=bot_response,
                conversation_context=conversation_context,
                user_email=user_email
            )
            
            if email_sent:
                # Update feedback record with email tracking
                pending_feedback.tenant_email_sent = True
                pending_feedback.tenant_email_id = email_id
                pending_feedback.tenant_notified_at = datetime.utcnow()
                pending_feedback.status = "tenant_notified"
                self.db.commit()
                
                logger.info(f"✅ Created feedback request {feedback_id} and sent notification")
                return feedback_id
            else:
                logger.error(f"❌ Failed to send tenant notification for {feedback_id}")
                # Don't delete the record, allow manual retry
                return None
                
        except Exception as e:
            logger.error(f"💥 Error creating feedback request: {e}")
            self.db.rollback()
            return None
    
    def _send_tenant_notification_advanced(self, feedback_id: str, tenant: Any, 
                                         user_question: str, bot_response: str,
                                         conversation_context: List[Dict], 
                                         user_email: str) -> tuple[bool, Optional[str]]:
        """
        Send advanced tenant notification with enhanced template and tracking
        """
        try:
            # Get tenant email configuration
            tenant_email = getattr(tenant, 'email', None)
            company_name = getattr(tenant, 'name', 'Your Company')
            
            if not tenant_email:
                logger.error(f"❌ No email configured for tenant {self.tenant_id}")
                return False, None
            
            # Build conversation context for email
            context_html = ""
            if conversation_context:
                context_items = []
                for msg in conversation_context[-5:]:  # Last 5 messages
                    role = "Customer" if msg.get("role") == "user" else "AI Assistant"
                    content = msg.get("content", "")[:200]  # Limit length
                    context_items.append(f"""
                        <div style="margin: 8px 0; padding: 8px; background: {'#f0f8ff' if role == 'Customer' else '#f8f8f8'}; border-radius: 4px;">
                            <strong>{role}:</strong> {content}
                        </div>
                    """)
                
                if context_items:
                    context_html = f"""
                    <div style="margin: 20px 0;">
                        <h3 style="color: #666; margin-bottom: 10px;">Recent Conversation:</h3>
                        <div style="border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: #fafafa;">
                            {''.join(context_items)}
                        </div>
                    </div>
                    """
            
            # Create reply-to address for tracking
           
            
            # Generate advanced email template
            email_html = self._generate_tenant_email_template(
                feedback_id=feedback_id,
                company_name=getattr(tenant, 'name', 'Your Company'), # Use company name instead of the whole tenant object
                user_question=user_question,
                bot_response=bot_response,
                context_html=context_html, # Assuming you create this variable
                user_email=user_email
            )
            
            # Send via Resend with enhanced configuration
            resend_payload = {
                "from": f"Lyra AI System <{self.from_email}>",
                "to": [tenant_email],
                "subject": f"🔔 Customer Feedback Needed - {company_name}",
                "html": email_html,
                "tags": [
                    {"name": "type", "value": "feedback_notification"},
                    {"name": "tenant_id", "value": str(self.tenant_id)},
                    {"name": "feedback_id", "value": feedback_id}
                ]
            }
            
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                },
                json=resend_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                email_id = result.get("id")
                
                # Track in Supabase for real-time monitoring
                self._track_email_sent(
                    feedback_id=feedback_id,
                    email_type="tenant_notification",
                    recipient=tenant_email,
                    provider_id=email_id,
                )
                
                logger.info(f"✅ Tenant notification sent successfully: {email_id}")
                return True, email_id
            else:
                error_msg = response.text
                logger.error(f"❌ Resend API error: {response.status_code} - {error_msg}")
                
                # Track failed email
                self._track_email_failed(
                    feedback_id=feedback_id,
                    email_type="tenant_notification",
                    error_message=error_msg
                )
                return False, None
                
        except Exception as e:
            logger.error(f"💥 Error sending tenant notification: {e}")
            return False, None
    
    def _generate_tenant_email_template(self, feedback_id: str, company_name: str,
                                    user_question: str, bot_response: str,
                                    context_html: str, user_email: str) -> str:
        """Generate enhanced email template with business name"""
        
        feedback_base_url = os.getenv("FEEDBACK_BASE_URL") or os.getenv("APP_BASE_URL", "https://botbackend-qtbf.onrender.com")
        feedback_url = f"{feedback_base_url}/chatbot/feedback/form/{feedback_id}"
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Customer Feedback Request - {company_name}</title>
            <style>
                .lyra-header {{
                    background: linear-gradient(135deg, #6B46C1, #9333EA);
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 12px 12px 0 0;
                }}
                .business-badge {{
                    background: rgba(255, 255, 255, 0.2);
                    padding: 8px 16px;
                    border-radius: 20px;
                    display: inline-block;
                    margin-top: 10px;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div class="lyra-header">
                    <h1 style="margin: 0; font-size: 28px;">LYRA AI</h1>
                    <div class="business-badge">{company_name}</div>
                </div>
                
                <div style="background: white; padding: 30px; border-radius: 0 0 12px 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                    <h2 style="color: #1a1a2e; margin-top: 0;">🔔 Customer Feedback Needed</h2>
                    <p>Hello <strong>{company_name}</strong>!</p>
                    <p>Your AI assistant was unable to answer a customer's question satisfactorily.</p>
                    
                    <h3 style="color: #3498db;">💬 Customer's Question:</h3>
                    <div style="background: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; border-radius: 8px;">"{user_question}"</div>
                    
                    <h3 style="color: #f39c12;">🤖 AI's Response:</h3>
                    <div style="background: #fff8e1; padding: 15px; border-left: 4px solid #ff9800; border-radius: 8px;">"{bot_response}"</div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{feedback_url}" style="background: linear-gradient(135deg, #6B46C1, #9333EA); color: white; padding: 16px 32px; text-align: center; text-decoration: none; display: inline-block; border-radius: 12px; font-size: 18px; font-weight: 600;">
                            Provide Improved Answer
                        </a>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; font-size: 14px; color: #666;">
                        <p><strong>✨ New Features:</strong></p>
                        <ul style="margin: 5px 0; padding-left: 20px;">
                            <li>Enhanced form with your business branding</li>
                            <li>Option to add responses to your FAQ automatically</li>
                            <li>Secure one-time use form that expires after submission</li>
                        </ul>
                    </div>
                    
                    <p style="font-size: 12px; color: #7f8c8d; margin-top: 20px;">
                        Feedback ID: {feedback_id} | Powered by Lyra AI
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _track_email_sent(self, feedback_id: str, email_type: str, 
                         recipient: str, provider_id: str, reply_to: str = None):
        """Track successful email in Supabase for real-time monitoring"""
        try:
            tracking_data = {
                "feedback_id": feedback_id,
                "email_type": email_type,
                "recipient": recipient,
                "status": "sent",
                "provider_id": provider_id,
                "reply_to_email": reply_to,
                "tenant_id": self.tenant_id,
                "sent_at": datetime.utcnow().isoformat()
            }
            
            self.supabase.table("email_tracking").insert(tracking_data).execute()
            logger.debug(f"✅ Email tracking recorded in Supabase: {provider_id}")
            
        except Exception as e:
            logger.error(f"⚠️ Failed to track email in Supabase: {e}")
    
    def _track_email_failed(self, feedback_id: str, email_type: str, error_message: str):
        """Track failed email in Supabase"""
        try:
            tracking_data = {
                "feedback_id": feedback_id,
                "email_type": email_type,
                "status": "failed",
                "error_message": error_message,
                "tenant_id": self.tenant_id,
                "sent_at": datetime.utcnow().isoformat()
            }
            
            self.supabase.table("email_tracking").insert(tracking_data).execute()
            
        except Exception as e:
            logger.error(f"⚠️ Failed to track email failure: {e}")
    
    def _track_email_capture(self, session_id: str, email: str):
        """Track when user provides email with 30-day expiration info"""
        try:
            expiry_date = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
            
            capture_data = {
                "session_id": session_id,
                "user_email": email,
                "tenant_id": self.tenant_id,
                "captured_at": datetime.utcnow().isoformat(),
                "expires_at": expiry_date.isoformat(),
                "memory_duration_days": self.EMAIL_MEMORY_DURATION.days
            }
            
            self.supabase.table("email_captures").insert(capture_data).execute()
            
        except Exception as e:
            logger.error(f"⚠️ Failed to track email capture: {e}")
    
    def _track_email_expired(self, session_id: str, email: str, age_days: Optional[int]):
        """Track when email expires for analytics"""
        try:
            expiry_data = {
                "session_id": session_id,
                "user_email": email,
                "tenant_id": self.tenant_id,
                "expired_at": datetime.utcnow().isoformat(),
                "age_days": age_days,
                "memory_duration_days": self.EMAIL_MEMORY_DURATION.days,
                "reason": "automatic_expiry"
            }
            
            self.supabase.table("email_expirations").insert(expiry_data).execute()
            
        except Exception as e:
            logger.error(f"⚠️ Failed to track email expiration: {e}")
    
    def process_tenant_response(self, feedback_id: str, tenant_response: str) -> bool:
        """
        Process tenant's email response and send follow-up to customer
        """
        try:
            # Get pending feedback
            pending = self.db.query(PendingFeedback).filter(
                PendingFeedback.feedback_id == feedback_id,
                PendingFeedback.tenant_id == self.tenant_id
            ).first()
            
            if not pending:
                logger.error(f"❌ Feedback request {feedback_id} not found")
                return False
            
            if pending.user_notified:
                logger.warning(f"⚠️ Feedback {feedback_id} already processed")
                return False
            
            # Store tenant response
            pending.tenant_response = tenant_response.strip()
            pending.status = "responded"
            
            # Send follow-up email to customer
            email_sent, email_id = self._send_customer_followup_advanced(pending)
            
            if email_sent:
                pending.user_notified = True
                pending.user_email_id = email_id
                pending.resolved_at = datetime.utcnow()
                pending.status = "resolved"
                self.db.commit()
                
                logger.info(f"✅ Processed tenant response for feedback {feedback_id}")
                return True
            else:
                logger.error(f"❌ Failed to send customer follow-up for {feedback_id}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Error processing tenant response: {e}")
            self.db.rollback()
            return False
    
    def _send_customer_followup_advanced(self, pending: PendingFeedback) -> tuple[bool, Optional[str]]:
        """Send professional follow-up email to customer"""
        try:
            tenant = self._get_tenant()
            if not tenant:
                return False, None
            
            company_name = getattr(tenant, 'business_name', 'Our Company')
            
            # Generate customer follow-up email
            email_html = self._generate_customer_followup_template(
                pending=pending,
                company_name=company_name
            )
            
            # Send from company's perspective
            from_name = f"{company_name} Support"
            
            resend_payload = {
                "from": f"{from_name} <{self.from_email}>",
                "to": [pending.user_email],
                "subject": f"Follow up from {company_name}",
                "html": email_html,
                "tags": [
                    {"name": "type", "value": "customer_followup"},
                    {"name": "feedback_id", "value": pending.feedback_id}
                ]
            }
            
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                },
                json=resend_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                email_id = result.get("id")
                
                # Track in Supabase
                self._track_email_sent(
                    feedback_id=pending.feedback_id,
                    email_type="customer_followup",
                    recipient=pending.user_email,
                    provider_id=email_id
                )
                
                logger.info(f"✅ Customer follow-up sent: {email_id}")
                return True, email_id
            else:
                logger.error(f"❌ Failed to send customer follow-up: {response.text}")
                return False, None
                
        except Exception as e:
            logger.error(f"💥 Error sending customer follow-up: {e}")
            return False, None
    
    def _generate_customer_followup_template(self, pending: PendingFeedback, company_name: str) -> str:
        """Generate professional customer follow-up email"""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Your Question Has Been Answered</title>
            <!-- ✅ ADDED EMAIL PREVIEW TEXT -->
            <meta name="description" content="Your question has been answered, thank you for reaching out">
            <style type="text/css">
                /* Email client preview text */
                .preheader {{
                    display: none !important;
                    visibility: hidden;
                    opacity: 0;
                    color: transparent;
                    height: 0;
                    width: 0;
                    line-height: 0;
                    font-size: 0;
                }}
            </style>
        </head>
        <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
            
            <!-- ✅ PREVIEW TEXT FOR EMAIL CLIENTS -->
            <div class="preheader">Your question has been answered, thank you for reaching out</div>
            
            <div style="background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                
                <!-- ✅ UPDATED HEADER: Business name bold and prominent, no green tick -->
                <div style="text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #e1e5e9;">
                    <h1 style="color: #2c3e50; margin: 0; font-size: 28px; font-weight: bold;">{company_name}</h1>
                    <h2 style="color: #27ae60; margin: 15px 0 0 0; font-size: 20px; font-weight: normal;">Your Question Has Been Answered</h2>
                </div>
                
                <!-- Greeting -->
                <div style="margin-bottom: 25px;">
                    <p style="font-size: 16px; margin: 0;">Hello,</p>
                    <p style="font-size: 16px;">Thank you for your recent question to <strong>{company_name}</strong>. We've reviewed your inquiry and wanted to provide you with a more comprehensive answer.</p>
                </div>
                
                <!-- Original Question -->
                <div style="margin-bottom: 25px;">
                    <h3 style="color: #3498db; margin-bottom: 12px; font-size: 18px;">💬 Your Original Question:</h3>
                    <div style="background: linear-gradient(135deg, #e3f2fd, #bbdefb); padding: 20px; border-left: 4px solid #2196f3; border-radius: 8px; font-size: 16px;">
                        "{pending.user_question}"
                    </div>
                </div>
                
                <!-- Improved Response -->
                <div style="margin-bottom: 30px;">
                    <h3 style="color: #27ae60; margin-bottom: 12px; font-size: 18px;">✨ Our Improved Response:</h3>
                    <div style="background: linear-gradient(135deg, #e8f5e8, #c8e6c8); padding: 25px; border-left: 4px solid #27ae60; border-radius: 8px; font-size: 16px; line-height: 1.7;">
                        {pending.tenant_response}
                    </div>
                </div>
                
                <!-- Call to Action -->
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 25px; text-align: center;">
                    <p style="margin: 0; font-size: 16px;">We appreciate your patience and hope this information is helpful.</p>
                    <p style="margin: 10px 0 0 0; font-size: 16px;"><strong>Please don't hesitate to reach out if you have any other questions!</strong></p>
                </div>
                
                <!-- Footer -->
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e1e5e9;">
                    <p style="margin: 0 0 10px 0; font-size: 16px;">Best regards,<br><strong>{company_name} Customer Support Team</strong></p>
                    <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #f1f1f1; color: #7f8c8d; font-size: 12px; text-align: center;">
                        <p style="margin: 0;">This message was sent in response to your conversation with our AI assistant.</p>
                        <p style="margin: 5px 0 0 0;">We're committed to providing you with the best possible support.</p>
                    </div>
                </div>
                
            </div>
        </body>
        </html>
        """
    
    def get_feedback_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive feedback analytics with email memory stats"""
        try:
            from datetime import timedelta
            
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get feedback statistics from main database
            total_requests = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.created_at >= start_date
            ).count()
            
            resolved_requests = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.created_at >= start_date,
                PendingFeedback.status == "resolved"
            ).count()
            
            pending_requests = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.status.in_(["pending", "tenant_notified", "responded"])
            ).count()
            
            # Get email analytics from Supabase
            try:
                supabase_analytics = self.supabase.table("email_tracking").select("*").gte(
                    "sent_at", start_date.isoformat()
                ).eq("tenant_id", self.tenant_id).execute()
                
                emails = supabase_analytics.data
                successful_emails = len([e for e in emails if e["status"] == "sent"])
                failed_emails = len([e for e in emails if e["status"] == "failed"])
                
                # Get email capture analytics
                capture_analytics = self.supabase.table("email_captures").select("*").gte(
                    "captured_at", start_date.isoformat()
                ).eq("tenant_id", self.tenant_id).execute()
                
                email_captures = len(capture_analytics.data)
                
                # Get expiration analytics
                expiry_analytics = self.supabase.table("email_expirations").select("*").gte(
                    "expired_at", start_date.isoformat()
                ).eq("tenant_id", self.tenant_id).execute()
                
                email_expirations = len(expiry_analytics.data)
                
            except Exception as e:
                logger.warning(f"Could not fetch Supabase analytics: {e}")
                emails = []
                successful_emails = 0
                failed_emails = 0
                email_captures = 0
                email_expirations = 0
            
            # Calculate metrics
            resolution_rate = (resolved_requests / total_requests * 100) if total_requests > 0 else 0
            email_success_rate = (successful_emails / len(emails) * 100) if emails else 0
            
            return {
                "success": True,
                "period_days": days,
                "email_memory_duration_days": self.EMAIL_MEMORY_DURATION.days,
                "feedback_requests": {
                    "total": total_requests,
                    "resolved": resolved_requests,
                    "pending": pending_requests,
                    "resolution_rate": round(resolution_rate, 2)
                },
                "email_performance": {
                    "total_sent": len(emails),
                    "successful": successful_emails,
                    "failed": failed_emails,
                    "success_rate": round(email_success_rate, 2)
                },
                "email_memory": {
                    "captures": email_captures,
                    "expirations": email_expirations,
                    "memory_duration_days": self.EMAIL_MEMORY_DURATION.days
                },
                "tenant_id": self.tenant_id
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback analytics: {e}")
            return {"success": False, "error": str(e)}
    
    def get_pending_feedback_list(self, limit: int = 20) -> List[Dict]:
        """Get list of pending feedback requests"""
        try:
            pending_requests = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.status.in_(["pending", "tenant_notified", "responded"])
            ).order_by(PendingFeedback.created_at.desc()).limit(limit).all()
            
            return [
                {
                    "feedback_id": req.feedback_id,
                    "user_question": req.user_question,
                    "bot_response": req.bot_response,
                    "user_email": req.user_email,
                    "status": req.status,
                    "created_at": req.created_at.isoformat(),
                    "tenant_email_sent": req.tenant_email_sent,
                    "tenant_notified_at": req.tenant_notified_at.isoformat() if req.tenant_notified_at else None
                }
                for req in pending_requests
            ]
            
        except Exception as e:
            logger.error(f"Error getting pending feedback list: {e}")
            return []
    
    def retry_failed_notification(self, feedback_id: str) -> bool:
        """Retry sending tenant notification for failed feedback"""
        try:
            pending = self.db.query(PendingFeedback).filter(
                PendingFeedback.feedback_id == feedback_id,
                PendingFeedback.tenant_id == self.tenant_id
            ).first()
            
            if not pending:
                logger.error(f"Feedback {feedback_id} not found")
                return False
            
            if pending.tenant_email_sent:
                logger.warning(f"Feedback {feedback_id} already sent")
                return False
            
            # Get tenant and conversation context
            tenant = self._get_tenant()
            if not tenant:
                return False
            
            try:
                conversation_context = json.loads(pending.conversation_context) if pending.conversation_context else []
            except:
                conversation_context = []
            
            # Retry sending notification
            email_sent, email_id = self._send_tenant_notification_advanced(
                feedback_id=feedback_id,
                tenant=tenant,
                user_question=pending.user_question,
                bot_response=pending.bot_response,
                conversation_context=conversation_context,
                user_email=pending.user_email
            )
            
            if email_sent:
                pending.tenant_email_sent = True
                pending.tenant_email_id = email_id
                pending.tenant_notified_at = datetime.utcnow()
                pending.status = "tenant_notified"
                self.db.commit()
                
                logger.info(f"✅ Retry successful for feedback {feedback_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error retrying notification: {e}")
            return False
    
    def _get_tenant(self):
        """Get tenant information"""
        try:
            from app.tenants.models import Tenant
            return self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
        except Exception as e:
            logger.error(f"Error getting tenant: {e}")
            return None

# Webhook handler for processing email replies
class FeedbackWebhookHandler:
    """Handle incoming email replies from Resend webhooks"""
    
    def __init__(self, db: Session):
        self.db = db
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    def process_email_reply(self, webhook_data: Dict) -> bool:
        """Process incoming email reply webhook"""
        try:
            # Extract email data
            email_from = webhook_data.get("from", "")
            email_to = webhook_data.get("to", "")
            email_subject = webhook_data.get("subject", "")
            email_text = webhook_data.get("text", "")
            email_html = webhook_data.get("html", "")
            
            # Extract feedback ID from reply-to or to address
            feedback_id = self._extract_feedback_id(email_to)
            if not feedback_id:
                logger.warning(f"Could not extract feedback ID from email: {email_to}")
                return False
            
            # Clean email content
            clean_response = self._clean_email_content(email_text or email_html)
            if not clean_response.strip():
                logger.warning(f"Empty response content for feedback {feedback_id}")
                return False
            
            # Store response in Supabase for tracking
            self._store_email_response(feedback_id, email_from, clean_response, webhook_data)
            
            # Get tenant from feedback record
            pending = self.db.query(PendingFeedback).filter(
                PendingFeedback.feedback_id == feedback_id
            ).first()
            
            if not pending:
                logger.error(f"Pending feedback {feedback_id} not found")
                return False
            
            # Process with feedback manager
            feedback_manager = AdvancedSmartFeedbackManager(self.db, pending.tenant_id)
            success = feedback_manager.process_tenant_response(feedback_id, clean_response)
            
            if success:
                logger.info(f"✅ Successfully processed email reply for feedback {feedback_id}")
            else:
                logger.error(f"❌ Failed to process email reply for feedback {feedback_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing email reply: {e}")
            return False
    
    def _extract_feedback_id(self, email_address: str) -> Optional[str]:
        """Extract feedback ID from email address"""
        import re
        match = re.search(r'feedback-([a-f0-9\-]+)@', email_address)
        return match.group(1) if match else None
    
    def _clean_email_content(self, content: str) -> str:
        """Clean email content removing quotes and signatures"""
        if not content:
            return ""
        
        import re
        
        # Remove HTML tags if present
        content = re.sub(r'<[^>]+>', '', content)
        
        # Remove common email reply markers
        patterns = [
            r'On.*wrote:.*',
            r'From:.*\n.*\n.*',
            r'-----Original Message-----.*',
            r'>.*',
            r'\n\n.*\n.*wrote:.*',
            r'Sent from my.*',
            r'Get Outlook for.*'
        ]
        
        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        content = content.strip()
        
        return content
    
    def _store_email_response(self, feedback_id: str, sender: str, content: str, raw_data: Dict):
        """Store email response in Supabase"""
        try:
            response_data = {
                "feedback_id": feedback_id,
                "sender_email": sender,
                "response_content": content,
                "raw_email_data": json.dumps(raw_data),
                "received_at": datetime.utcnow().isoformat(),
                "status": "received"
            }
            
            self.supabase.table("email_responses").insert(response_data).execute()
            
        except Exception as e:
            logger.error(f"Failed to store email response: {e}")