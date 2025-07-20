# app/chatbot/smart_feedback.py
"""
Advanced Smart Feedback System - Supabase + Resend Integration
Efficient, trackable, and production-ready with 30-day email memory
Now integrated with Email Scraper Engine for automatic email capture
"""

import logging
import uuid
import re
import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.chatbot.models import ChatSession
from app.knowledge_base.models import FAQ 
from app.tenants.models import Tenant
import os
from app.config import settings
from app.chatbot.email_scraper_engine import EmailScraperEngine, ScrapedEmail
from jinja2 import Environment, FileSystemLoader


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
    - Template-based email rendering
    - Integrated Email Scraper Engine for automatic email capture
    """
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        
        # Email memory configuration
        self.EMAIL_MEMORY_DURATION = timedelta(days=30)  # 30-day memory
        
        # Initialize email scraper engine
        self.email_scraper = EmailScraperEngine(db)
        
        # Initialize Supabase
        self.supabase_url = os.getenv("SUPABASE_URL")
        # self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Initialize Resend
        self.resend_api_key = os.getenv("RESEND_API_KEY")
        if not self.resend_api_key:
            raise ValueError("RESEND_API_KEY must be set")
        
        self.from_email = os.getenv("FROM_EMAIL", "feedback@agentlyra.com")
        
        # Initialize Jinja2 template environment
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        
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
        
        logger.info(f"✅ Advanced Smart Feedback Manager initialized for tenant {tenant_id} with 30-day email memory and email scraping")

        # Check LLM availability properly
        try:
            from langchain_openai import ChatOpenAI
            LLM_AVAILABLE = True
        except ImportError:
            LLM_AVAILABLE = False

        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        logger.info(f"🔍 LLM available: {self.llm_available}, OpenAI key exists: {bool(settings.OPENAI_API_KEY)}")

    def _load_template(self, template_name: str) -> str:
        """Load HTML template from file"""
        try:
            template = self.jinja_env.get_template(template_name)
            return template
        except Exception as e:
            logger.error(f"❌ Error loading template {template_name}: {e}")
            raise

    def attempt_email_scraping(self, session_id: str, scraping_data: Dict) -> Optional[str]:
        """
        Attempt to scrape email from various sources
        Returns first valid email found, None if no email scraped
        """
        try:
            if not scraping_data:
                return None
            
            logger.info(f"🔍 Attempting email scraping for session {session_id}")
            
            # Use bulk processing from email scraper
            result = self.email_scraper.bulk_process_scraping_data(
                tenant_id=self.tenant_id,
                scraping_data={
                    **scraping_data,
                    'session_id': session_id,
                    'metadata': scraping_data.get('metadata', {})
                }
            )
            
            if result.get('success') and result.get('total_emails_captured', 0) > 0:
                # Get the most recent scraped email for this session
                scraped_emails = self.email_scraper.get_scraped_emails_for_tenant(
                    tenant_id=self.tenant_id, 
                    limit=10
                )
                
                # Find email from this session
                for email_record in scraped_emails:
                    if email_record.get('session_id') == session_id:
                        scraped_email = email_record.get('email')
                        if scraped_email:
                            logger.info(f"✅ Successfully scraped email {scraped_email} for session {session_id} via {email_record.get('source')}")
                            return scraped_email
                
                # If no session-specific email, return first recent email
                if scraped_emails:
                    scraped_email = scraped_emails[0].get('email')
                    logger.info(f"✅ Using recent scraped email {scraped_email} for session {session_id}")
                    return scraped_email
            
            logger.info(f"📭 No emails scraped for session {session_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error during email scraping: {e}")
            return None
            
    def should_request_email(self, session_id: str, user_identifier: str, scraping_data: Dict = None) -> bool:
        """
        Check if we should ask for email with 30-day memory logic + LOOP PREVENTION
        Now includes automatic email scraping attempt
        """
        try:
            # FIRST: Attempt email scraping if data provided
            if scraping_data:
                scraped_email = self.attempt_email_scraping(session_id, scraping_data)
                if scraped_email:
                    # Store scraped email automatically
                    if self.store_user_email(session_id, scraped_email, source="scraped"):
                        logger.info(f"🎯 Email scraping successful - skipping manual request for session {session_id}")
                        return False  # Skip manual email request
                    else:
                        logger.warning(f"⚠️ Failed to store scraped email, falling back to manual request")
            
            # FALLBACK: Continue with existing logic if scraping failed or no data
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
                    # 🔥 FIX: Handle timezone properly
                    email_captured = session.email_captured_at
                    if email_captured.tzinfo is None:
                        email_captured = email_captured.replace(tzinfo=timezone.utc)
                    
                    current_time = datetime.now(timezone.utc)
                    email_age = current_time - email_captured
                    
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
            
            # 🔥 CRITICAL FIX: Check if we already asked for email in this conversation
            if conversation_history and len(conversation_history) > 1:
                # Look for recent email requests in conversation
                recent_messages = conversation_history[-4:]  # Last 4 messages
                for msg in recent_messages:
                    if not msg.get('is_from_user', True):  # Bot message
                        content = msg.get('content', '').lower()
                        email_request_indicators = [
                            'email address', 'your email', 'share your email', 
                            'provide your email', 'email for', 'may i have your email',
                            'could you share', 'kindly provide', 'email address for'
                        ]
                        
                        # If we recently asked for email, don't ask again
                        if any(indicator in content for indicator in email_request_indicators):
                            logger.info(f"📧 Recently asked for email in conversation, not asking again")
                            return False
            
            # Check if conversation is truly new (no meaningful history)
            if len(conversation_history) <= 1:  # Only greeting or first message
                logger.info(f"🆕 New conversation for {user_identifier}, requesting email")
                return True
            else:
                # Has conversation history but no email request detected - this might be a returning user
                # Only ask for email if it's been a while since last conversation
                logger.info(f"📧 Existing conversation for {user_identifier}, skipping email request")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error checking email request: {e}")
            return False
        


    def generate_email_request_message(self, business_name: str, conversation_context: List[Dict] = None) -> str:
        """
        Generate email request message - FIXED OPTION 2: Corrected validation logic
        """
        # Simple fallback templates
        simple_requests = [
                "Hi, to provide better support, could you share your email address?",
                f"Hello, for quality {business_name} service, may I have your email?",
                "Hi there, to ensure we assist you fully, could you share your email?",
                "Welcome, for better service and follow-up, would you mind sharing your email?",
                f"Hello, to give you the best {business_name} experience, could you provide your email?",
                "Could you let me know your email so we can follow up if needed?",
                "To keep in touch and assist you better, would you be open to sharing your email?",
                "Mind dropping your email so we can make sure everything goes smoothly?",
                "Just so we can support you properly, could you share your email?",
                "If you're comfortable, could you leave your email so we can help further?"
        ]
        
        import random
        selected_request = random.choice(simple_requests)
        
        if not self.llm_available:
            logger.info(f"📧 LLM unavailable, using simple email request for {business_name}")
            return selected_request
        
        try:
            from langchain_openai import ChatOpenAI
            from langchain.prompts import PromptTemplate
            
            prompt = PromptTemplate(
                input_variables=["business_name"],
                template='''You are a customer service assistant for {business_name}. Generate a brief, friendly message asking a new customer for their email address.

    Requirements:
    - Ask for email address politely
    - Maximum 15 words
    - Professional but casual tone
    - No exclamation marks
    - Don't mention any previous conversation

    Examples:
    "Hi, To provide better support, could you share your email address?"
    "Hello, For quality service, may I have your email?"
    "Hi there... Could you share your email for better assistance?"

    Your email request:'''
            )
            
            llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY,
            )
            
            result = llm.invoke(prompt.format(business_name=business_name))
            email_message = result.content.strip()
            
            # FIXED: More targeted validation - only block actual problems
            serious_issues = [
                # Debug leak indicators (keep these)
                "user provided", "extracted", "detected", "system", "backend", 
                "debug", "log", "conversation_context", "in response to", "assistant's request",
                
                # Specific business context leakage (only if it appears with business context)
                "test lyra local", "testing lyra", "lyra local",  # Full phrases only
                "thank you in advance",  # Full phrase that indicates echoing
                
                # Clear non-email-request responses
                "how can i help you", "what can i do for you", "how may i assist"
            ]
            
            # Check if response is actually asking for email
            email_request_indicators = ["email", "e-mail", "contact information", "contact details"]
            has_email_request = any(indicator in email_message.lower() for indicator in email_request_indicators)
            
            # Check for serious issues only
            for issue in serious_issues:
                if issue.lower() in email_message.lower():
                    logger.warning(f"🚨 Serious issue detected (contains '{issue}'), using fallback")
                    return selected_request
            
            # Must actually ask for email
            if not has_email_request:
                logger.warning(f"🚨 Response doesn't ask for email: '{email_message}', using fallback")
                return selected_request
            
            # Length validation (more generous)
            if len(email_message) > 100 or len(email_message) < 5:
                logger.warning(f"🚨 Email request length out of bounds ({len(email_message)} chars), using fallback")
                return selected_request
            
            # SUCCESS: Valid email request generated
            logger.info(f"📧 Generated valid LLM email request for {business_name}: '{email_message}'")
            return email_message
            
        except Exception as e:
            logger.error(f"❌ LLM email request generation failed: {e}")
            return selected_request

    def extract_email_from_message(self, message: str) -> Optional[str]:
        """Extract and validate email address from user message - CLEAN VERSION"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, message)
        
        if matches:
            email = matches[0].lower().strip()
            logger.info(f"📧 Email extracted: {email}")
            return email
        
        return None
    
    def store_user_email(self, session_id: str, email: str, source: str = "manual") -> bool:
        """
        Store user email with 30-day expiration tracking - FIXED TO PREVENT LEAKS
        Now supports both manual and scraped email sources
        """
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if session:
                # Store email with timestamp and source tracking
                session.user_email = email.lower().strip()
                session.email_captured_at = datetime.utcnow()
                
                # Set expiration date
                if hasattr(session, 'email_expires_at'):
                    session.email_expires_at = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
                
                # Track email source for analytics
                if hasattr(session, 'email_source'):
                    session.email_source = source
                
                self.db.commit()
                
                # Track in Supabase for analytics (backend only)
                self._track_email_capture(session_id, email, source)
                
                # Log for debugging (backend only)
                expiry_date = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
                logger.info(f"✅ Stored email {email} for session {session_id} via {source} (expires: {expiry_date.strftime('%Y-%m-%d')})")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error storing email: {e}")
            self.db.rollback()
        
        return False
    
    def generate_clean_email_acknowledgment(self, email: str, business_name: str) -> str:
        """
        Generate a clean email acknowledgment WITHOUT any debug information
        This replaces the LLM-based generation that was leaking debug info
        """
        # Use simple, predefined responses to avoid any debug leakage
        acknowledgment_templates = [
            "Perfect... I've noted your email as email. How can I assist you today?",
            "Great, I have noted your email. Let's rock and roll?",
            "Thanks, I've saved your email as email. What can I help you with?",
            "Great... I have your email as email. What will I be helping you with today?",
            "Cool, your email has been saved. What would you like to know?",
            "Got it! I've recorded your email as email. How may I assist you?",
            "Awesome, email is in. What do you need help with today?",
            "Email saved. What would you like us to sort out?",
            "Alright, email locked in. What's next on your mind?",
            "Noted your email. How can I be of help right now?"
        ]
        
        # Simple rotation to add variety without LLM complexity
        import random
        selected_template = random.choice(acknowledgment_templates)
        
        logger.info(f"📧 Generated clean email acknowledgment for {email}")
        return selected_template

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
                    "expires_at": (session.email_captured_at + self.EMAIL_MEMORY_DURATION).isoformat(),
                    "email_source": getattr(session, 'email_source', 'unknown')
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
            
            # Generate feedback URL
            feedback_base_url = os.getenv("FEEDBACK_BASE_URL") or os.getenv("APP_BASE_URL", "https://chatbot-api-production-2de6.up.railway.app")
            feedback_url = f"{feedback_base_url}/chatbot/feedback/form/{feedback_id}"
            
            # Load and render template
            template = self._load_template("tenant_notification_email.html")
            email_html = template.render(
                feedback_id=feedback_id,
                company_name=company_name,
                user_question=user_question,
                bot_response=bot_response,
                context_html=context_html,
                user_email=user_email,
                feedback_url=feedback_url
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
    
    def _track_email_capture(self, session_id: str, email: str, source: str = "manual"):
        """Track when user provides email with 30-day expiration info and source"""
        try:
            expiry_date = datetime.utcnow() + self.EMAIL_MEMORY_DURATION
            
            capture_data = {
                "session_id": session_id,
                "user_email": email,
                "tenant_id": self.tenant_id,
                "captured_at": datetime.utcnow().isoformat(),
                "expires_at": expiry_date.isoformat(),
                "memory_duration_days": self.EMAIL_MEMORY_DURATION.days,
                "email_source": source  # Track if manual vs scraped
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
            
            # Load and render template
            template = self._load_template("customer_followup_email.html")
            email_html = template.render(
                company_name=company_name,
                user_question=pending.user_question,
                tenant_response=pending.tenant_response
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
                scraped_captures = len([c for c in capture_analytics.data if c.get("email_source") == "scraped"])
                manual_captures = len([c for c in capture_analytics.data if c.get("email_source") == "manual"])
                
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
                scraped_captures = 0
                manual_captures = 0
                email_expirations = 0
            
            # Calculate metrics
            resolution_rate = (resolved_requests / total_requests * 100) if total_requests > 0 else 0
            email_success_rate = (successful_emails / len(emails) * 100) if emails else 0
            scraping_success_rate = (scraped_captures / email_captures * 100) if email_captures > 0 else 0
            
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
                "email_scraping": {
                    "scraped_captures": scraped_captures,
                    "manual_captures": manual_captures,
                    "scraping_success_rate": round(scraping_success_rate, 2)
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