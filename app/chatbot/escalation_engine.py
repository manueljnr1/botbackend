import logging
import uuid
import json
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from app.chatbot.models import Escalation, EscalationMessage
from app.chatbot.simple_memory import SimpleChatbotMemory
from app.config import settings
import os

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class EscalationEngine:
    """Complete escalation system - trigger detection + management"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.memory = SimpleChatbotMemory(db, tenant_id)
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.2,
                openai_api_key=settings.OPENAI_API_KEY
            )
        
        # Email config
        self.resend_api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "support@agentlyra.com")
    
    # ============ TRIGGER DETECTION ============
    
    def should_escalate(self, user_message: str, bot_response: str, 
                       conversation_history: List[Dict]) -> Tuple[bool, str, Dict]:
        """Detect if escalation should be offered"""
        if not self.llm_available:
            return self._basic_escalation_check(user_message)
        
        try:
            context_text = self._build_context(conversation_history)
            
            prompt = PromptTemplate(
                input_variables=["user_message", "bot_response", "context"],
                template="""Analyze if this customer needs human assistance.

USER: "{user_message}"
BOT: "{bot_response}"
CONTEXT: {context}

ESCALATE IF:
- User explicitly asks for human help
- User shows frustration ("not helpful", "doesn't work")
- Bot unable to solve after multiple attempts
- Technical issue beyond bot capability

RESPONSE (JSON):
{{
    "should_escalate": true/false,
    "confidence": 0.0-1.0,
    "reason": "user_requested|frustrated|bot_unable|technical_issue",
    "escalation_type": "technical|general|urgent"
}}

Analysis:"""
            )
            
            result = self.llm.invoke(prompt.format(
                user_message=user_message,
                bot_response=bot_response,
                context=context_text
            ))
            
            import re
            json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                should_escalate = analysis.get('should_escalate', False)
                confidence = analysis.get('confidence', 0.0)
                
                if should_escalate and confidence > 0.7:
                    logger.info(f"🚨 Escalation trigger: {analysis.get('reason')}")
                    return True, analysis.get('reason'), analysis
                
                return False, "confidence_low", analysis
            
        except Exception as e:
            logger.error(f"Escalation trigger error: {e}")
        
        return self._basic_escalation_check(user_message)
    
    def _basic_escalation_check(self, user_message: str) -> Tuple[bool, str, Dict]:
        """Fallback keyword detection"""
        user_lower = user_message.lower()
        escalation_phrases = [
            "speak to human", "talk to human", "human agent", "customer service",
            "not helpful", "doesn't work", "frustrated", "speak to someone"
        ]
        
        for phrase in escalation_phrases:
            if phrase in user_lower:
                return True, "keyword_match", {"escalation_type": "general", "confidence": 0.8}
        
        return False, "no_triggers", {}
    
    def _build_context(self, conversation_history: List[Dict]) -> str:
        """Build conversation context"""
        if not conversation_history:
            return "No previous conversation"
        
        context_items = []
        for msg in conversation_history[-6:]:
            role = "User" if msg.get('role') == 'user' else "Bot"
            content = msg.get('content', '')[:100]
            context_items.append(f"{role}: {content}")
        
        return "\n".join(context_items)
    
    # ============ ESCALATION MANAGEMENT ============
    
    def create_escalation(self, session_id: str, user_identifier: str, 
                         escalation_data: Dict, user_message: str) -> Optional[str]:
        """Create escalation and notify team"""
        try:
            escalation_id = str(uuid.uuid4())
            
            # Get conversation summary
            conversation_history = self.memory.get_conversation_history(user_identifier, 10)
            summary = self._generate_summary(conversation_history, user_message)
            
            # Create escalation
            escalation = Escalation(
                escalation_id=escalation_id,
                tenant_id=self.tenant_id,
                session_id=session_id,
                user_identifier=user_identifier,
                reason=escalation_data.get('reason', 'unknown'),
                original_issue=user_message,
                conversation_summary=summary,
                status="pending"
            )
            
            self.db.add(escalation)
            self.db.commit()
            self.db.refresh(escalation)
            
            # Notify team
            if self._send_team_notification(escalation):
                escalation.team_notified = True
                escalation.status = "active"
                self.db.commit()
                logger.info(f"✅ Escalation {escalation_id} created")
                return escalation_id
            
            return None
                
        except Exception as e:
            logger.error(f"Error creating escalation: {e}")
            self.db.rollback()
            return None
    
    def offer_escalation(self, escalation_data: Dict, company_name: str) -> str:
        """Generate escalation offer message"""
        escalation_type = escalation_data.get('escalation_type', 'general')
        
        if escalation_type == 'technical':
            return f"I understand this is a technical issue. Would you like me to connect you with our {company_name} technical team?"
        elif escalation_type == 'urgent':
            return f"This seems urgent. Let me escalate this to our {company_name} team right away."
        else:
            return f"Would you like me to escalate this to our {company_name} team for more personalized assistance?"
    
    def process_team_response(self, escalation_id: str, team_message: str) -> bool:
        """Process team response and prepare for bot delivery"""
        try:
            escalation = self.db.query(Escalation).filter(
                Escalation.escalation_id == escalation_id,
                Escalation.tenant_id == self.tenant_id
            ).first()
            
            if not escalation:
                return False
            
            # Store team message
            message = EscalationMessage(
                escalation_id=escalation.id,
                content=team_message,
                from_team=True,
                sent_to_customer=False
            )
            
            self.db.add(message)
            self.db.commit()
            
            logger.info(f"✅ Team response stored for escalation {escalation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing team response: {e}")
            return False
    
    def get_pending_team_message(self, session_id: str) -> Optional[str]:
        """Get pending team message for bot to deliver"""
        try:
            escalation = self.db.query(Escalation).filter(
                Escalation.session_id == session_id,
                Escalation.tenant_id == self.tenant_id,
                Escalation.status == "active"
            ).first()
            
            if not escalation:
                return None
            
            # Get undelivered team message
            message = self.db.query(EscalationMessage).filter(
                EscalationMessage.escalation_id == escalation.id,
                EscalationMessage.from_team == True,
                EscalationMessage.sent_to_customer == False
            ).first()
            
            if message:
                # Mark as sent
                message.sent_to_customer = True
                self.db.commit()
                
                # Format for bot delivery
                return f"Message from our team: {message.content}"
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting team message: {e}")
            return None
    
    def resolve_escalation(self, escalation_id: str) -> bool:
        """Mark escalation as resolved"""
        try:
            escalation = self.db.query(Escalation).filter(
                Escalation.escalation_id == escalation_id,
                Escalation.tenant_id == self.tenant_id
            ).first()
            
            if escalation:
                escalation.status = "resolved"
                escalation.resolved_at = datetime.utcnow()
                self.db.commit()
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error resolving escalation: {e}")
            return False
    
    # ============ TEAM COMMUNICATION ============
    
    def _send_team_notification(self, escalation: Escalation) -> bool:
        """Send email notification to team"""
        if not self.resend_api_key:
            logger.warning("No Resend API key configured")
            return False
        
        try:
            # Get tenant info
            from app.tenants.models import Tenant
            tenant = self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
            if not tenant or not tenant.email:
                return False
            
            company_name = tenant.business_name or tenant.name
            feedback_base_url = os.getenv("FEEDBACK_BASE_URL", "https://agentlyra.up.railway.app")
            response_url = f"{feedback_base_url}/chatbot/escalation/respond/{escalation.escalation_id}"
            
            email_html = f"""
            <h3>🚨 Customer Escalation - {company_name}</h3>
            
            <p><strong>Customer:</strong> {escalation.user_identifier}</p>
            <p><strong>Issue:</strong> {escalation.original_issue}</p>
            <p><strong>Reason:</strong> {escalation.reason}</p>
            
            <h4>Conversation Summary:</h4>
            <p>{escalation.conversation_summary}</p>
            
            <p><a href="{response_url}" style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Respond to Customer</a></p>
            """
            
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": f"Escalation System <{self.from_email}>",
                    "to": [tenant.email],
                    "subject": f"🚨 Customer Escalation - {company_name}",
                    "html": email_html
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                escalation.team_email_id = result.get("id")
                self.db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending team notification: {e}")
            return False
    
    def _generate_summary(self, conversation_history: List[Dict], current_issue: str) -> str:
        """Generate conversation summary"""
        if not conversation_history:
            return f"Customer issue: {current_issue}"
        
        # Simple summary for now
        user_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'user']
        recent_issues = user_messages[-3:] if len(user_messages) > 3 else user_messages
        
        summary = f"Customer tried: {' → '.join(recent_issues)}"
        return f"{summary}\n\nCurrent issue: {current_issue}"
