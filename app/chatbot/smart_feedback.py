# app/chatbot/smart_feedback.py
"""
Smart Feedback System - Human-in-the-loop for better responses
"""



import logging
import uuid
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.email_service import EmailService


from app.chatbot.models import ChatSession
import re

logger = logging.getLogger(__name__)

class PendingFeedback(Base):
    """Model to track pending feedback requests"""
    __tablename__ = "pending_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(String, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    session_id = Column(String, ForeignKey("chat_sessions.session_id"))
    user_email = Column(String)
    user_question = Column(Text)
    bot_response = Column(Text)
    conversation_context = Column(Text)  # JSON string of recent messages
    tenant_email_sent = Column(Boolean, default=False)
    tenant_response = Column(Text, nullable=True)
    user_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    session = relationship("ChatSession")

class SmartFeedbackManager:
    """Manages the smart feedback system"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.email_service = EmailService()
        
        # Patterns that indicate the bot doesn't have a good answer
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
            r"for more information.*contact"
            r"sorry.*unable",
            r"sorry.*cannot",
            r"am unable to",
        ]
    
    def should_request_email(self, session_id: str, user_identifier: str) -> bool:
        """
        Check if we should ask for email at the start of conversation
        Returns True for new conversations without memory
        """
        from app.chatbot.simple_memory import SimpleChatbotMemory
        
        memory = SimpleChatbotMemory(self.db, self.tenant_id)
        conversation_history = memory.get_conversation_history(user_identifier, max_messages=5)
        
        # Check if we already have email for this session
        session = self.db.query(ChatSession).filter(
            ChatSession.session_id == session_id
        ).first()
        
        if session and hasattr(session, 'user_email') and session.user_email:
            return False  # Already have email
        
        # Check if conversation is new (no meaningful history)
        if len(conversation_history) <= 1:  # Only greeting or first message
            return True
        
        return False
    
    def generate_email_request_message(self, tenant_name: str) -> str:
        """Generate a natural email request message"""
        messages = [
            f"Hi there! I'm {tenant_name}'s AI assistant. To ensure I can provide you with the best follow-up support if needed, could you please share your email address?",
            f"Hello! Welcome to {tenant_name}. For feedback and follow-up purposes, may I have your email address before we start?",
            f"Hi! I'm here to help you with {tenant_name}. To provide better service and follow-up, could you share your email with me?",
            f"Welcome! I'm {tenant_name}'s virtual assistant. For quality assurance and follow-up, would you mind sharing your email address?"
        ]
        import random
        return random.choice(messages)
    
    def extract_email_from_message(self, message: str) -> Optional[str]:
        """Extract email address from user message"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, message)
        return matches[0] if matches else None
    
    def store_user_email(self, session_id: str, email: str) -> bool:
        """Store user email in session"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session:
                # Add user_email field to ChatSession model if not exists
                if not hasattr(session, 'user_email'):
                    # You'll need to add this field to your ChatSession model
                    logger.warning("user_email field not found in ChatSession model")
                    return False
                
                session.user_email = email
                self.db.commit()
                logger.info(f"Stored email {email} for session {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing email: {e}")
            self.db.rollback()
            
        return False
    
    def detect_inadequate_response(self, bot_response: str) -> bool:
        """
        Detect if the bot's response indicates it doesn't have adequate information
        """
        response_lower = bot_response.lower()
        
        logger.info(f"🔍 Checking response: '{response_lower[:100]}...'")
        
        for pattern in self.inadequate_response_patterns:
            if re.search(pattern, response_lower):
                logger.info(f"✅ MATCHED inadequate response pattern: {pattern}")
                return True
            else:
                logger.debug(f"❌ Pattern '{pattern}' did not match")
        
        # Additional checks
        if len(bot_response) < 30:
            if any(word in response_lower for word in ["sorry", "don't", "can't", "unable"]):
                logger.info(f"✅ MATCHED short inadequate response with trigger words")
                return True
        
        logger.info(f"❌ No inadequate patterns detected")
        return False
    
    def create_feedback_request(self, session_id: str, user_question: str, 
                              bot_response: str, conversation_context: List[Dict]) -> str:
        """
        Create a pending feedback request and send email to tenant
        Returns feedback_id for tracking
        """
        try:
            # Get session info
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                logger.error(f"Session {session_id} not found")
                return None
            
            user_email = getattr(session, 'user_email', None)
            if not user_email:
                logger.warning(f"No user email found for session {session_id}")
                return None
            
            # Generate unique feedback ID
            feedback_id = str(uuid.uuid4())
            
            # Create pending feedback record
            pending_feedback = PendingFeedback(
                feedback_id=feedback_id,
                tenant_id=self.tenant_id,
                session_id=session_id,
                user_email=user_email,
                user_question=user_question,
                bot_response=bot_response,
                conversation_context=str(conversation_context)  # Convert to JSON string
            )
            
            self.db.add(pending_feedback)
            self.db.commit()
            
            # Send email to tenant
            if self._send_tenant_notification_email(feedback_id, user_question, bot_response, conversation_context):
                pending_feedback.tenant_email_sent = True
                self.db.commit()
                logger.info(f"Created feedback request {feedback_id} and sent tenant notification")
                return feedback_id
            
        except Exception as e:
            logger.error(f"Error creating feedback request: {e}")
            self.db.rollback()
        
        return None
    
    def _send_tenant_notification_email(self, feedback_id: str, user_question: str, 
                                  bot_response: str, conversation_context: List[Dict]) -> bool:
        """Send notification email to tenant with feedback request"""
        try:
            # Get tenant info
            from app.tenants.models import Tenant
            tenant = self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
            
            if not tenant:
                logger.error(f"Tenant {self.tenant_id} not found")
                return False
            
            # Check if tenant has feedback system enabled
            if not getattr(tenant, 'enable_feedback_system', True):
                logger.info(f"Feedback system disabled for tenant {self.tenant_id}")
                return False
            
            # Get tenant email configuration
            feedback_email = getattr(tenant, 'feedback_email', None)
            from_email = getattr(tenant, 'from_email', None)
            company_name = getattr(tenant, 'company_name', tenant.name)
            
            if not feedback_email:
                logger.warning(f"No feedback email configured for tenant {self.tenant_id}")
                return False
            
            if not from_email:
                # Fallback to a default format
                from_email = f"assistant@{tenant.name.lower().replace(' ', '')}.com"
            
            # Build conversation context
            context_text = ""
            if conversation_context:
                context_text = "\n".join([
                    f"{'User' if msg.get('role') == 'user' else 'Bot'}: {msg.get('content', '')}"
                    for msg in conversation_context[-5:]  # Last 5 messages
                ])
            
            # Email content with tenant branding
            subject = f"Feedback Needed - Question from {company_name} Customer"
            
            body = f"""
    Hello {company_name} Team,

    A customer asked a question that your AI assistant couldn't answer adequately. Your help is needed to provide a better response.

    FEEDBACK ID: {feedback_id}

    CUSTOMER QUESTION:
    "{user_question}"

    AI ASSISTANT'S RESPONSE:
    "{bot_response}"

    RECENT CONVERSATION CONTEXT:
    {context_text}

    TO RESPOND:
    Simply reply to this email with your improved answer. The system will automatically format and send your response to the customer as a follow-up message.

    This helps improve your AI assistant's knowledge base and provides better customer service.

    Best regards,
    {company_name} AI Assistant System
    """
            
            # Send email using tenant's email configuration
            return self.email_service.send_tenant_email(
                tenant_from_email=from_email,
                tenant_to_email=feedback_email,
                subject=subject,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Error sending tenant notification email: {e}")
            return False
        
        
    def process_tenant_response(self, feedback_id: str, tenant_response: str) -> bool:
        """
        Process tenant's email response and send follow-up to user
        """
        try:
            # Get pending feedback
            pending = self.db.query(PendingFeedback).filter(
                PendingFeedback.feedback_id == feedback_id,
                PendingFeedback.tenant_id == self.tenant_id
            ).first()
            
            if not pending:
                logger.error(f"Feedback request {feedback_id} not found")
                return False
            
            if pending.user_notified:
                logger.warning(f"Feedback {feedback_id} already processed")
                return False
            
            # Store tenant response
            pending.tenant_response = tenant_response
            pending.resolved_at = datetime.utcnow()
            
            # Send follow-up email to user
            if self._send_user_followup_email(pending):
                pending.user_notified = True
                self.db.commit()
                logger.info(f"Processed tenant response for feedback {feedback_id}")
                return True
            
        except Exception as e:
            logger.error(f"Error processing tenant response: {e}")
            self.db.rollback()
        
        return False
    
    def _send_user_followup_email(self, pending: PendingFeedback) -> bool:
        """Send follow-up email to user with tenant's improved response"""
        try:
            from app.tenants.models import Tenant
            tenant = self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
            
            if not tenant:
                return False
            
            # Get tenant email configuration
            from_email = getattr(tenant, 'from_email', f"support@{tenant.name.lower()}.com")
            company_name = getattr(tenant, 'company_name', tenant.name)
            
            subject = f"Follow-up from {company_name} - Your Question Answered"
            
            body = f"""
    Hello,

    Thank you for your recent question to {company_name}. We've reviewed your inquiry and wanted to provide you with a more comprehensive answer.

    YOUR ORIGINAL QUESTION:
    "{pending.user_question}"

    OUR IMPROVED RESPONSE:
    {pending.tenant_response}

    We appreciate your patience and hope this information is helpful. Please don't hesitate to reach out if you have any other questions.

    Best regards,
    {company_name} Customer Support Team

    ---
    This message was sent in response to your conversation with our AI assistant.
    """
            
            # Send follow-up email to user
            return self.email_service.send_user_followup(
                tenant_from_email=from_email,
                user_email=pending.user_email,
                subject=subject,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Error sending user follow-up email: {e}")
        return False
    
    
    def get_pending_feedback_stats(self) -> Dict[str, Any]:
        """Get statistics about pending feedback requests"""
        try:
            total_pending = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.user_notified == False
            ).count()
            
            total_resolved = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.user_notified == True
            ).count()
            
            recent_requests = self.db.query(PendingFeedback).filter(
                PendingFeedback.tenant_id == self.tenant_id,
                PendingFeedback.created_at > datetime.utcnow() - timedelta(days=7)
            ).count()
            
            return {
                "total_pending": total_pending,
                "total_resolved": total_resolved,
                "recent_requests_7_days": recent_requests
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback stats: {e}")
            return {"error": str(e)}