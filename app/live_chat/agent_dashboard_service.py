# app/live_chat/agent_dashboard_service.py

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc, func
from dataclasses import dataclass
import traceback

from app.live_chat.customer_detection_service import CustomerDetectionService, CustomerProfile, CustomerSession, CustomerDevice
from app.live_chat.models import Agent, AgentSession, LiveChatConversation, ConversationStatus, AgentStatus, ChatQueue, LiveChatMessage

logger = logging.getLogger(__name__)


def make_naive(dt):
    """Convert timezone-aware datetime to naive"""
    if dt and dt.tzinfo:
        return dt.replace(tzinfo=None)
    return dt

def safe_subtract(dt1, dt2):
    """Safely subtract datetimes"""
    if not dt1 or not dt2:
        return timedelta(0)
    return make_naive(dt1) - make_naive(dt2)


@dataclass
class PreviewResult:
    """Result of text preview generation"""
    snippet: str
    contextual_preview: str
    detected_keywords: List[str]
    is_truncated: bool
    original_length: int
    preview_type: str  # 'snippet', 'contextual', 'full'


class TextPreviewService:
    """Service for generating customer message previews and contextual snippets"""
    
    # Priority keywords for contextual preview
    PRIORITY_KEYWORDS = {
        "urgent": ["urgent", "emergency", "asap", "immediately", "critical", "broken", "down", "not working"],
        "billing": ["bill", "billing", "charge", "payment", "invoice", "refund", "money", "cost"],
        "technical": ["bug", "error", "crash", "broken", "not working", "issue", "problem", "glitch"],
        "authentication": ["login", "password", "access", "account", "locked out", "forgot", "reset"],
        "sales": ["buy", "purchase", "order", "product", "demo", "trial", "upgrade", "pricing"],
        "account": ["account", "profile", "settings", "update", "change", "modify"],
        "general": ["help", "support", "question", "how to", "information"]
    }
    
    # Common sentence endings to help with smart truncation
    SENTENCE_ENDINGS = ['.', '!', '?', '\n']
    
    @classmethod
    def generate_message_preview(cls, text: str, 
                                max_snippet_length: int = 150,
                                max_contextual_length: int = 200,
                                context_window: int = 50) -> PreviewResult:
        """
        Generate both snippet and contextual preview for a message
        
        Args:
            text: Original message text
            max_snippet_length: Maximum length for simple snippet
            max_contextual_length: Maximum length for contextual preview
            context_window: Characters to show around important keywords
            
        Returns:
            PreviewResult with both preview types
        """
        if not text or not text.strip():
            return PreviewResult(
                snippet="",
                contextual_preview="",
                detected_keywords=[],
                is_truncated=False,
                original_length=0,
                preview_type="empty"
            )
        
        # Clean and normalize text
        cleaned_text = cls._clean_text(text)
        original_length = len(cleaned_text)
        
        # Detect important keywords
        detected_keywords = cls._detect_keywords(cleaned_text)
        
        # Generate snippet preview
        snippet = cls._generate_snippet(cleaned_text, max_snippet_length)
        
        # Generate contextual preview
        contextual_preview = cls._generate_contextual_preview(
            cleaned_text, detected_keywords, max_contextual_length, context_window
        )
        
        # Determine preview type
        preview_type = "full" if original_length <= max_snippet_length else "contextual" if detected_keywords else "snippet"
        
        return PreviewResult(
            snippet=snippet,
            contextual_preview=contextual_preview,
            detected_keywords=detected_keywords,
            is_truncated=original_length > max_snippet_length,
            original_length=original_length,
            preview_type=preview_type
        )
    
    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Clean and normalize text for processing"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common chat artifacts
        text = re.sub(r'^\s*-+\s*', '', text)  # Remove leading dashes
        text = re.sub(r'\s*-+\s*$', '', text)  # Remove trailing dashes
        
        return text
    
    @classmethod
    def _detect_keywords(cls, text: str) -> List[str]:
        """Detect important keywords in text for contextual preview"""
        text_lower = text.lower()
        detected = []
        
        for category, keywords in cls.PRIORITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    detected.append(keyword)
        
        return list(set(detected))  # Remove duplicates
    
    @classmethod
    def _generate_snippet(cls, text: str, max_length: int) -> str:
        """Generate simple snippet (first X characters with ellipsis)"""
        if len(text) <= max_length:
            return text
        
        # Try to break at a word boundary
        truncated = text[:max_length]
        
        # Find the last space to avoid cutting words
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:  # Only use word boundary if it's not too short
            truncated = truncated[:last_space]
        
        # Try to end at sentence boundary if possible
        for ending in cls.SENTENCE_ENDINGS:
            sentence_end = truncated.rfind(ending)
            if sentence_end > max_length * 0.6:  # Must be reasonably long
                truncated = truncated[:sentence_end + 1]
                break
        
        return truncated + "..." if len(text) > len(truncated) else truncated
    
    @classmethod
    def _generate_contextual_preview(cls, text: str, keywords: List[str], 
                                   max_length: int, context_window: int) -> str:
        """Generate contextual preview highlighting important parts"""
        if not keywords:
            # No keywords found, return smart snippet
            return cls._generate_snippet(text, max_length)
        
        text_lower = text.lower()
        
        # Find all keyword positions
        keyword_positions = []
        for keyword in keywords:
            start = 0
            while True:
                pos = text_lower.find(keyword.lower(), start)
                if pos == -1:
                    break
                keyword_positions.append((pos, pos + len(keyword), keyword))
                start = pos + 1
        
        if not keyword_positions:
            return cls._generate_snippet(text, max_length)
        
        # Sort by position
        keyword_positions.sort()
        
        # Create context segments around keywords
        segments = []
        used_ranges = []
        
        for start_pos, end_pos, keyword in keyword_positions:
            # Define context window around keyword
            context_start = max(0, start_pos - context_window)
            context_end = min(len(text), end_pos + context_window)
            
            # Check if this overlaps with already used ranges
            overlaps = False
            for used_start, used_end in used_ranges:
                if not (context_end < used_start or context_start > used_end):
                    overlaps = True
                    break
            
            if not overlaps:
                # Extract context
                context_text = text[context_start:context_end].strip()
                
                # Clean up the start and end
                if context_start > 0:
                    # Find word boundary at start
                    space_pos = context_text.find(' ')
                    if space_pos > 0 and space_pos < context_window // 2:
                        context_text = "..." + context_text[space_pos:]
                    else:
                        context_text = "..." + context_text
                
                if context_end < len(text):
                    # Find word boundary at end
                    last_space = context_text.rfind(' ')
                    if last_space > len(context_text) - context_window // 2:
                        context_text = context_text[:last_space] + "..."
                    else:
                        context_text = context_text + "..."
                
                segments.append(context_text)
                used_ranges.append((context_start, context_end))
                
                # Check if we're approaching max length
                current_length = sum(len(seg) for seg in segments) + len(segments) * 3  # Account for separators
                if current_length > max_length * 0.8:
                    break
        
        if not segments:
            return cls._generate_snippet(text, max_length)
        
        # Combine segments
        contextual_preview = " | ".join(segments)
        
        # Ensure we don't exceed max length
        if len(contextual_preview) > max_length:
            contextual_preview = contextual_preview[:max_length - 3] + "..."
        
        return contextual_preview
    
    @classmethod
    def analyze_urgency(cls, text: str) -> Dict[str, Any]:
        """Analyze text for urgency indicators"""
        urgency_indicators = [
            "urgent", "emergency", "asap", "immediate", "critical", "help",
            "broken", "not working", "error", "problem", "issue",
            "frustrated", "angry", "stuck", "can't", "won't"
        ]
        
        text_lower = text.lower()
        found_indicators = [indicator for indicator in urgency_indicators if indicator in text_lower]
        
        urgency_score = len(found_indicators)
        urgency_level = "low"
        
        if urgency_score >= 3:
            urgency_level = "high"
        elif urgency_score >= 1:
            urgency_level = "medium"
        
        return {
            "urgency_level": urgency_level,
            "urgency_score": urgency_score,
            "indicators": found_indicators
        }
    
    @classmethod
    def extract_entities(cls, text: str) -> Dict[str, List[str]]:
        """Extract entities like emails, phone numbers, order IDs"""
        entities = {
            "emails": [],
            "phone_numbers": [],
            "order_ids": [],
            "account_numbers": []
        }
        
        # Email regex
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        entities["emails"] = re.findall(email_pattern, text)
        
        # Phone number regex (simple)
        phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b'
        entities["phone_numbers"] = re.findall(phone_pattern, text)
        
        # Order ID pattern (common formats)
        order_pattern = r'\b(?:order|order#|order id|ref|reference)[\s#:]*([A-Z0-9]{6,})\b'
        entities["order_ids"] = re.findall(order_pattern, text, re.IGNORECASE)
        
        # Account number pattern
        account_pattern = r'\b(?:account|account#|account number)[\s#:]*([A-Z0-9]{4,})\b'
        entities["account_numbers"] = re.findall(account_pattern, text, re.IGNORECASE)
        
        return entities


class AgentDashboardService:
    """Enhanced agent dashboard with customer intelligence and text preview"""
    
    def __init__(self, db: Session):
        self.db = db
        self.detection_service = CustomerDetectionService(db)
        self.text_preview_service = TextPreviewService()
    
    async def get_enhanced_queue_for_agent(self, agent: Agent) -> Dict[str, Any]:
        """Get queue with enhanced customer intelligence for agent dashboard"""
        try:
            # Get queued conversations for this tenant
            queued_conversations = self.db.query(LiveChatConversation).filter(
                and_(
                    LiveChatConversation.tenant_id == agent.tenant_id,
                    LiveChatConversation.status.in_([
                        ConversationStatus.QUEUED,
                        ConversationStatus.ASSIGNED
                    ])
                )
            ).order_by(LiveChatConversation.queue_position.asc()).all()
            
            enhanced_queue = []
            
            for conversation in queued_conversations:
                # Get customer intelligence
                customer_intel = await self._get_customer_intelligence(
                    conversation.customer_identifier,
                    agent.tenant_id
                )
                
                # Get enhanced conversation preview with text preview service
                preview = await self._get_enhanced_conversation_preview(conversation.id)
                
                # Calculate urgency score
                urgency_score = self._calculate_urgency_score(conversation, customer_intel)
                
                # Get routing recommendations
                routing_rec = await self._get_routing_recommendation(
                    conversation, customer_intel, agent
                )
                
                enhanced_queue.append({
                    "conversation_id": conversation.id,
                    "queue_position": conversation.queue_position,
                    "customer_identifier": conversation.customer_identifier,
                    "customer_name": conversation.customer_name,
                    "status": conversation.status,
                    "created_at": conversation.created_at.isoformat(),
                    "wait_time_minutes": self._calculate_wait_time(conversation),
                    
                    # Enhanced customer intelligence
                    "customer_intelligence": customer_intel,
                    "conversation_preview": preview,
                    "urgency_score": urgency_score,
                    "routing_recommendation": routing_rec,
                    
                    # Visual indicators for agent dashboard
                    "indicators": self._get_visual_indicators(conversation, customer_intel),
                    
                    # Suggested actions
                    "suggested_actions": self._get_suggested_actions(
                        conversation, customer_intel, agent
                    )
                })
            
            # Sort by urgency and queue position
            enhanced_queue.sort(key=lambda x: (x["urgency_score"], x["queue_position"]), reverse=True)
            
            return {
                "success": True,
                "total_in_queue": len(enhanced_queue),
                "agent_recommendations": self._get_agent_specific_recommendations(agent, enhanced_queue),
                "queue": enhanced_queue,
                "queue_statistics": self._get_queue_statistics(enhanced_queue),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting enhanced queue: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}
    
    async def _get_enhanced_conversation_preview(self, conversation_id: int) -> Dict[str, Any]:
        """Get enhanced conversation preview with text preview service"""
        try:
            # Get conversation and first customer message
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                return {"has_messages": False, "error": "Conversation not found"}
            
            # Get first customer message
            first_message = self.db.query(LiveChatMessage).filter(
                and_(
                    LiveChatMessage.conversation_id == conversation_id,
                    LiveChatMessage.sender_type == "customer"
                )
            ).order_by(LiveChatMessage.sent_at.asc()).first()
            
            preview = {
                "has_messages": False,
                "preview_text": "Customer is waiting to start conversation",
                "message_count": 0,
                "urgency_keywords": [],
                "sentiment": "neutral"
            }
            
            # Use original question if no messages yet
            message_text = None
            if first_message:
                message_text = first_message.content
                preview["sent_at"] = first_message.sent_at.isoformat()
            elif conversation.original_question:
                message_text = conversation.original_question
                preview["sent_at"] = conversation.created_at.isoformat()
            
            if message_text:
                # Generate enhanced preview using TextPreviewService
                preview_result = self.text_preview_service.generate_message_preview(
                    text=message_text,
                    max_snippet_length=120,
                    max_contextual_length=180,
                    context_window=40
                )
                
                # Analyze urgency and extract entities
                urgency_analysis = self.text_preview_service.analyze_urgency(message_text)
                entities = self.text_preview_service.extract_entities(message_text)
                
                preview.update({
                    "has_messages": True,
                    "message_count": self.db.query(LiveChatMessage).filter(
                        LiveChatMessage.conversation_id == conversation_id
                    ).count(),
                    
                    # Text preview results
                    "snippet": preview_result.snippet,
                    "contextual_preview": preview_result.contextual_preview,
                    "preview_type": preview_result.preview_type,
                    "is_truncated": preview_result.is_truncated,
                    "original_length": preview_result.original_length,
                    "detected_keywords": preview_result.detected_keywords,
                    
                    # Full message for agent reference
                    "full_message": message_text,
                    
                    # Urgency analysis
                    "urgency_analysis": urgency_analysis,
                    
                    # Extracted entities
                    "entities": entities,
                    
                    # Legacy fields for backward compatibility
                    "preview_text": preview_result.contextual_preview or preview_result.snippet,
                    "urgency_keywords": urgency_analysis["indicators"],
                    "sentiment": self._analyze_sentiment(message_text)
                })
            
            return preview
            
        except Exception as e:
            logger.error(f"Error getting enhanced conversation preview: {str(e)}")
            return {"has_messages": False, "error": str(e)}
    
    async def _get_customer_intelligence(self, customer_identifier: str, tenant_id: int) -> Dict[str, Any]:
        """Get comprehensive customer intelligence"""
        try:
            # Get customer profile
            customer_profile = self.db.query(CustomerProfile).filter(
                and_(
                    CustomerProfile.tenant_id == tenant_id,
                    CustomerProfile.customer_identifier == customer_identifier
                )
            ).first()
            
            if not customer_profile:
                return {
                    "profile_status": "new_customer",
                    "is_returning": False,
                    "risk_level": "unknown",
                    "value_tier": "standard"
                }
            
            # Get recent sessions
            recent_sessions = self.db.query(CustomerSession).filter(
                CustomerSession.customer_profile_id == customer_profile.id
            ).order_by(desc(CustomerSession.started_at)).limit(5).all()
            
            # Get conversation history
            conversation_history = self.db.query(LiveChatConversation).filter(
                and_(
                    LiveChatConversation.tenant_id == tenant_id,
                    LiveChatConversation.customer_identifier == customer_identifier
                )
            ).order_by(desc(LiveChatConversation.created_at)).limit(10).all()
            
            # Analyze customer patterns
            patterns = self._analyze_customer_patterns(
                customer_profile, recent_sessions, conversation_history
            )
            
            # Calculate customer value and risk
            value_assessment = self._assess_customer_value(conversation_history)
            risk_assessment = self._assess_customer_risk(customer_profile, conversation_history)
            
            return {
                "profile_status": "returning_customer",
                "is_returning": True,
                "customer_since": customer_profile.first_seen.isoformat() if customer_profile.first_seen else None,
                "last_interaction": customer_profile.last_seen.isoformat() if customer_profile.last_seen else None,
                "total_conversations": customer_profile.total_conversations,
                "satisfaction_average": customer_profile.customer_satisfaction_avg,
                "preferred_language": customer_profile.preferred_language,
                "timezone": customer_profile.time_zone,
                
                # Behavioral patterns
                "patterns": patterns,
                
                # Value and risk assessment
                "value_tier": value_assessment["tier"],
                "risk_level": risk_assessment["level"],
                
                # Geographic context
                "location_context": self._get_location_context(recent_sessions),
                
                # Device context
                "device_context": self._get_device_context(customer_profile.id),
                
                # Conversation insights
                "conversation_insights": self._get_conversation_insights(conversation_history)
            }
            
        except Exception as e:
            logger.error(f"Error getting customer intelligence: {str(e)}")
            return {"profile_status": "error", "error": str(e)}
    
    def _analyze_customer_patterns(self, profile: CustomerProfile, 
                                 sessions: List[CustomerSession], 
                                 conversations: List[LiveChatConversation]) -> Dict[str, Any]:
        """Analyze customer behavioral patterns"""
        patterns = {
            "communication_frequency": "unknown",
            "preferred_times": [],
            "escalation_tendency": "low",
            "resolution_preference": "quick",
            "common_issues": [],
            "seasonal_patterns": {}
        }
        
        if not conversations:
            return patterns
        
        # Analyze communication frequency
        if len(conversations) > 5:
            patterns["communication_frequency"] = "high"
        elif len(conversations) > 2:
            patterns["communication_frequency"] = "medium"
        else:
            patterns["communication_frequency"] = "low"
        
        # Analyze preferred contact times
        contact_hours = [conv.created_at.hour for conv in conversations if conv.created_at]
        if contact_hours:
            from collections import Counter
            hour_counts = Counter(contact_hours)
            most_common_hours = [hour for hour, count in hour_counts.most_common(3)]
            patterns["preferred_times"] = most_common_hours
        
        # Analyze escalation tendency
        abandoned_count = sum(1 for conv in conversations if conv.status == ConversationStatus.ABANDONED)
        if abandoned_count > len(conversations) * 0.3:
            patterns["escalation_tendency"] = "high"
        elif abandoned_count > len(conversations) * 0.1:
            patterns["escalation_tendency"] = "medium"
        
        # Analyze conversation duration preferences
        durations = [conv.conversation_duration_seconds for conv in conversations 
                    if conv.conversation_duration_seconds]
        if durations:
            avg_duration = sum(durations) / len(durations)
            if avg_duration < 300:  # 5 minutes
                patterns["resolution_preference"] = "quick"
            elif avg_duration > 1800:  # 30 minutes
                patterns["resolution_preference"] = "thorough"
            else:
                patterns["resolution_preference"] = "standard"
        
        return patterns
    
    def _assess_customer_value(self, conversations: List[LiveChatConversation]) -> Dict[str, Any]:
        """Assess customer value tier"""
        value_score = 0
        
        # Frequency bonus
        if len(conversations) > 10:
            value_score += 3
        elif len(conversations) > 5:
            value_score += 2
        elif len(conversations) > 2:
            value_score += 1
        
        # Satisfaction bonus
        satisfaction_scores = [conv.customer_satisfaction for conv in conversations 
                             if conv.customer_satisfaction]
        if satisfaction_scores:
            avg_satisfaction = sum(satisfaction_scores) / len(satisfaction_scores)
            if avg_satisfaction >= 4.5:
                value_score += 2
            elif avg_satisfaction >= 4.0:
                value_score += 1
        
        # Determine tier
        if value_score >= 5:
            tier = "premium"
        elif value_score >= 3:
            tier = "valued"
        else:
            tier = "standard"
        
        return {
            "tier": tier,
            "score": value_score,
            "factors": {
                "conversation_frequency": len(conversations),
                "average_satisfaction": sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
            }
        }
    
    def _assess_customer_risk(self, profile: CustomerProfile, 
                            conversations: List[LiveChatConversation]) -> Dict[str, Any]:
        """Assess customer risk level"""
        risk_score = 0
        risk_factors = []
        
        # High abandonment rate
        if conversations:
            abandoned_rate = sum(1 for conv in conversations 
                               if conv.status == ConversationStatus.ABANDONED) / len(conversations)
            if abandoned_rate > 0.4:
                risk_score += 3
                risk_factors.append("High abandonment rate")
            elif abandoned_rate > 0.2:
                risk_score += 1
                risk_factors.append("Moderate abandonment rate")
        
        # Low satisfaction scores
        satisfaction_scores = [conv.customer_satisfaction for conv in conversations 
                             if conv.customer_satisfaction]
        if satisfaction_scores:
            avg_satisfaction = sum(satisfaction_scores) / len(satisfaction_scores)
            if avg_satisfaction < 2.5:
                risk_score += 3
                risk_factors.append("Low satisfaction scores")
            elif avg_satisfaction < 3.5:
                risk_score += 1
                risk_factors.append("Below average satisfaction")
        
        # Frequent recent contacts (potential escalation)
        recent_conversations = [conv for conv in conversations 
                      if make_naive(conv.created_at) > make_naive(datetime.utcnow()) - timedelta(days=7)]
        if len(recent_conversations) > 3:
            risk_score += 2
            risk_factors.append("High recent contact frequency")
        
        # Determine risk level
        if risk_score >= 5:
            level = "high"
        elif risk_score >= 3:
            level = "medium"
        else:
            level = "low"
        
        return {
            "level": level,
            "score": risk_score,
            "factors": risk_factors
        }
    
    def _get_location_context(self, sessions: List[CustomerSession]) -> Dict[str, Any]:
        """Get customer location context from recent sessions"""
        if not sessions:
            return {"status": "unknown"}
        
        latest_session = sessions[0]
        
        context = {
            "current_location": {
                "country": latest_session.country,
                "region": latest_session.region,
                "city": latest_session.city
            },
            "location_consistency": "unknown"
        }
        
        # Check location consistency
        if len(sessions) > 1:
            countries = [s.country for s in sessions if s.country]
            if len(set(countries)) == 1:
                context["location_consistency"] = "consistent"
            else:
                context["location_consistency"] = "variable"
                context["recent_locations"] = list(set(countries))
        
        return context
    
    def _get_device_context(self, customer_profile_id: int) -> Dict[str, Any]:
        """Get customer device context"""
        devices = self.db.query(CustomerDevice).filter(
            CustomerDevice.customer_profile_id == customer_profile_id
        ).order_by(desc(CustomerDevice.last_seen)).all()
        
        if not devices:
            return {"status": "unknown"}
        
        primary_device = devices[0]
        
        return {
            "primary_device": {
                "type": primary_device.device_type,
                "browser": primary_device.browser_name,
                "os": primary_device.operating_system
            },
            "device_count": len(devices),
            "capabilities": {
                "websockets": primary_device.supports_websockets,
                "file_upload": primary_device.supports_file_upload,
                "notifications": primary_device.supports_notifications
            },
            "compatibility_notes": self._get_compatibility_notes(primary_device)
        }
    
    def _get_compatibility_notes(self, device: CustomerDevice) -> List[str]:
        """Get device compatibility notes for agents"""
        notes = []
        
        if not device.supports_websockets:
            notes.append("Limited real-time messaging support")
        
        if not device.supports_file_upload:
            notes.append("Cannot upload files")
        
        if not device.supports_notifications:
            notes.append("Browser notifications disabled")
        
        if device.device_type == "mobile":
            notes.append("Mobile user - use concise messages")
        
        return notes
    
    def _get_conversation_insights(self, conversations: List[LiveChatConversation]) -> Dict[str, Any]:
        """Get insights from conversation history"""
        if not conversations:
            return {"status": "no_history"}
        
        insights = {
            "most_recent_topic": None,
            "common_resolution_types": [],
            "typical_duration": None,
            "success_rate": 0,
            "preferred_agents": []
        }
        
        # Get most recent conversation topic/context
        latest_conv = conversations[0]
        if latest_conv.handoff_context:
            try:
                import json
                context = json.loads(latest_conv.handoff_context)
                insights["most_recent_topic"] = context.get("topic", "General inquiry")
            except:
                pass
        
        # Analyze resolution patterns
        resolution_types = [conv.resolution_status for conv in conversations 
                          if conv.resolution_status]
        if resolution_types:
            from collections import Counter
            common_resolutions = Counter(resolution_types).most_common(3)
            insights["common_resolution_types"] = [res for res, count in common_resolutions]
        
        # Calculate success rate
        completed_conversations = [conv for conv in conversations 
                                 if conv.status == ConversationStatus.CLOSED]
        if conversations:
            insights["success_rate"] = len(completed_conversations) / len(conversations)
        
        # Find preferred agents
        agent_interactions = {}
        for conv in conversations:
            if conv.assigned_agent_id:
                if conv.assigned_agent_id not in agent_interactions:
                    agent_interactions[conv.assigned_agent_id] = {
                        "count": 0,
                        "satisfaction_scores": [],
                        "resolution_rate": 0
                    }
                
                agent_interactions[conv.assigned_agent_id]["count"] += 1
                
                if conv.customer_satisfaction:
                    agent_interactions[conv.assigned_agent_id]["satisfaction_scores"].append(
                        conv.customer_satisfaction
                    )
                
                if conv.resolution_status == "resolved":
                    agent_interactions[conv.assigned_agent_id]["resolution_rate"] += 1
        
        # Calculate agent preferences
        preferred_agents = []
        for agent_id, data in agent_interactions.items():
            if data["count"] >= 2:  # At least 2 interactions
                avg_satisfaction = (
                    sum(data["satisfaction_scores"]) / len(data["satisfaction_scores"])
                    if data["satisfaction_scores"] else 0
                )
                resolution_rate = data["resolution_rate"] / data["count"]
                
                if avg_satisfaction >= 4.0 or resolution_rate >= 0.8:
                    agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                    if agent:
                        preferred_agents.append({
                            "agent_id": agent_id,
                            "agent_name": agent.display_name,
                            "interaction_count": data["count"],
                            "avg_satisfaction": round(avg_satisfaction, 2),
                            "resolution_rate": round(resolution_rate, 2)
                        })
        
        insights["preferred_agents"] = sorted(
            preferred_agents, 
            key=lambda x: (x["avg_satisfaction"], x["resolution_rate"]), 
            reverse=True
        )[:3]
        
        return insights
    
    def _analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis"""
        if not text:
            return "neutral"
        
        positive_words = [
            "good", "great", "excellent", "amazing", "wonderful", "perfect",
            "love", "like", "satisfied", "happy", "pleased", "thank"
        ]
        
        negative_words = [
            "bad", "terrible", "awful", "horrible", "hate", "dislike",
            "frustrated", "angry", "disappointed", "upset", "annoyed",
            "problem", "issue", "broken", "wrong", "error"
        ]
        
        text_lower = text.lower()
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if negative_count > positive_count:
            return "negative"
        elif positive_count > negative_count:
            return "positive"
        else:
            return "neutral"
    
    def _calculate_urgency_score(self, conversation: LiveChatConversation, 
                                customer_intel: Dict[str, Any]) -> float:
        """Calculate urgency score for prioritization"""
        score = 0.0
        
        # Base urgency from wait time
        wait_minutes = self._calculate_wait_time(conversation)
        if wait_minutes > 30:
            score += 0.4
        elif wait_minutes > 15:
            score += 0.2
        elif wait_minutes > 5:
            score += 0.1
        
        # Customer value tier
        value_tier = customer_intel.get("value_tier", "standard")
        if value_tier == "premium":
            score += 0.3
        elif value_tier == "valued":
            score += 0.2
        
        # Risk level
        risk_level = customer_intel.get("risk_level", "low")
        if risk_level == "high":
            score += 0.3
        elif risk_level == "medium":
            score += 0.1
        
        # Previous abandonment history
        patterns = customer_intel.get("patterns", {})
        if patterns.get("escalation_tendency") == "high":
            score += 0.2
        
        # Recent activity frequency
        if customer_intel.get("patterns", {}).get("communication_frequency") == "high":
            score += 0.1
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _calculate_wait_time(self, conversation: LiveChatConversation) -> int:
        """Calculate wait time in minutes"""
        if conversation.queue_entry_time:
            delta = safe_subtract(datetime.utcnow(), conversation.queue_entry_time)
            return int(delta.total_seconds() / 60)
        return 0
    
    async def _get_routing_recommendation(self, conversation: LiveChatConversation,
                                        customer_intel: Dict[str, Any], 
                                        current_agent: Agent) -> Dict[str, Any]:
        """Get routing recommendation for this conversation"""
        recommendation = {
            "recommended_agent": None,
            "confidence": 0.0,
            "reasoning": [],
            "alternative_agents": []
        }
        
        # Check for preferred agents from customer history
        preferred_agents = customer_intel.get("conversation_insights", {}).get("preferred_agents", [])
        if preferred_agents:
            top_preference = preferred_agents[0]
            
            # Check if preferred agent is available
            preferred_agent = self.db.query(Agent).filter(
                and_(
                    Agent.id == top_preference["agent_id"],
                    Agent.tenant_id == current_agent.tenant_id,
                    Agent.is_online == True,
                    Agent.status == "active"
                )
            ).first()
            
            if preferred_agent:
                session = self.db.query(AgentSession).filter(
                    and_(
                        AgentSession.agent_id == preferred_agent.id,
                        AgentSession.logout_at.is_(None),
                        AgentSession.active_conversations < AgentSession.max_concurrent_chats
                    )
                ).first()
                
                if session:
                    recommendation.update({
                        "recommended_agent": {
                            "agent_id": preferred_agent.id,
                            "agent_name": preferred_agent.display_name,
                            "current_load": session.active_conversations,
                            "max_capacity": session.max_concurrent_chats
                        },
                        "confidence": 0.9,
                        "reasoning": [
                            f"Customer has positive history with {preferred_agent.display_name}",
                            f"Previous satisfaction: {top_preference['avg_satisfaction']}/5.0",
                            f"Resolution rate: {top_preference['resolution_rate']*100:.0f}%"
                        ]
                    })
        
        # If no preferred agent available, suggest based on other factors
        if not recommendation["recommended_agent"]:
            # Get available agents for this tenant
            available_agents = self.db.query(Agent).join(
                AgentSession, Agent.id == AgentSession.agent_id
            ).filter(
                and_(
                    Agent.tenant_id == current_agent.tenant_id,
                    Agent.is_online == True,
                    Agent.status == "active",
                    AgentSession.logout_at.is_(None),
                    AgentSession.active_conversations < AgentSession.max_concurrent_chats
                )
            ).all()
            
            if available_agents:
                # Simple load balancing - choose least busy agent
                least_busy = min(
                    available_agents, 
                    key=lambda a: a.sessions[0].active_conversations if a.sessions else 0
                )
                
                session = least_busy.sessions[0] if least_busy.sessions else None
                
                recommendation.update({
                    "recommended_agent": {
                        "agent_id": least_busy.id,
                        "agent_name": least_busy.display_name,
                        "current_load": session.active_conversations if session else 0,
                        "max_capacity": session.max_concurrent_chats if session else 3
                    },
                    "confidence": 0.6,
                    "reasoning": [
                        "Available agent with lowest current workload",
                        "No specific agent preference from customer history"
                    ]
                })
        
        return recommendation
    
    def _get_visual_indicators(self, conversation: LiveChatConversation, 
                             customer_intel: Dict[str, Any]) -> Dict[str, Any]:
        """Get visual indicators for agent dashboard"""
        indicators = {
            "priority": "normal",
            "customer_type": "new",
            "risk_level": "low",
            "flags": [],
            "badges": []
        }
        
        # Priority indicator
        urgency_score = self._calculate_urgency_score(conversation, customer_intel)
        if urgency_score >= 0.7:
            indicators["priority"] = "high"
        elif urgency_score >= 0.4:
            indicators["priority"] = "medium"
        
        # Customer type
        if customer_intel.get("is_returning"):
            indicators["customer_type"] = "returning"
            if customer_intel.get("value_tier") == "premium":
                indicators["customer_type"] = "premium"
        
        # Risk level
        indicators["risk_level"] = customer_intel.get("risk_level", "low")
        
        # Flags
        patterns = customer_intel.get("patterns", {})
        if patterns.get("escalation_tendency") == "high":
            indicators["flags"].append("escalation_risk")
        
        if customer_intel.get("conversation_insights", {}).get("success_rate", 1.0) < 0.5:
            indicators["flags"].append("resolution_challenges")
        
        wait_time = self._calculate_wait_time(conversation)
        if wait_time > 20:
            indicators["flags"].append("long_wait")
        
        # Badges
        if customer_intel.get("is_returning"):
            indicators["badges"].append("returning_customer")
        
        if customer_intel.get("value_tier") == "premium":
            indicators["badges"].append("premium_customer")
        
        if customer_intel.get("total_conversations", 0) > 10:
            indicators["badges"].append("frequent_customer")
        
        location = customer_intel.get("location_context", {}).get("current_location", {})
        if location.get("country") and location["country"] != "Unknown":
            indicators["badges"].append(f"location_{location['country'].lower()}")
        
        return indicators
    
    def _get_suggested_actions(self, conversation: LiveChatConversation,
                             customer_intel: Dict[str, Any], 
                             agent: Agent) -> List[Dict[str, Any]]:
        """Get suggested actions for agents"""
        actions = []
        
        # High priority assignment
        urgency_score = self._calculate_urgency_score(conversation, customer_intel)
        if urgency_score >= 0.7:
            actions.append({
                "type": "assign_immediately",
                "priority": "high",
                "title": "Assign Immediately",
                "description": "High priority customer - assign to available agent now",
                "action_data": {"conversation_id": conversation.id}
            })
        
        # Preferred agent recommendation
        preferred_agents = customer_intel.get("conversation_insights", {}).get("preferred_agents", [])
        if preferred_agents:
            actions.append({
                "type": "assign_to_preferred",
                "priority": "medium",
                "title": f"Assign to {preferred_agents[0]['agent_name']}",
                "description": f"Customer has positive history with this agent (avg satisfaction: {preferred_agents[0]['avg_satisfaction']}/5.0)",
                "action_data": {
                    "conversation_id": conversation.id,
                    "agent_id": preferred_agents[0]["agent_id"]
                }
            })
        
        # Risk mitigation
        if customer_intel.get("risk_level") == "high":
            actions.append({
                "type": "escalate_to_senior",
                "priority": "high",
                "title": "Consider Senior Agent",
                "description": "Customer has history of escalation - consider assigning to experienced agent",
                "action_data": {"conversation_id": conversation.id}
            })
        
        # Language/location specific
        preferred_language = customer_intel.get("preferred_language")
        if preferred_language and preferred_language != "en":
            actions.append({
                "type": "language_specific",
                "priority": "medium",
                "title": f"Assign {preferred_language.title()}-speaking Agent",
                "description": f"Customer's preferred language is {preferred_language}",
                "action_data": {
                    "conversation_id": conversation.id,
                    "required_language": preferred_language
                }
            })
        
        return actions
    
    def _get_agent_specific_recommendations(self, agent: Agent, 
                                          queue: List[Dict]) -> Dict[str, Any]:
        """Get recommendations specific to this agent"""
        recommendations = {
            "suggested_picks": [],
            "workload_advice": "",
            "skill_matches": []
        }
        
        # Find conversations this agent would be good for
        for conv in queue[:5]:  # Check top 5 in queue
            customer_intel = conv["customer_intelligence"]
            
            # Check if agent has history with this customer
            preferred_agents = customer_intel.get("conversation_insights", {}).get("preferred_agents", [])
            for pref_agent in preferred_agents:
                if pref_agent["agent_id"] == agent.id:
                    recommendations["suggested_picks"].append({
                        "conversation_id": conv["conversation_id"],
                        "reason": "You have positive history with this customer",
                        "confidence": 0.9,
                        "customer_name": conv.get("customer_name", "Customer"),
                        "previous_satisfaction": pref_agent["avg_satisfaction"]
                    })
                    break
        
        # Workload advice
        current_conversations = 0  # Would get from agent session
        if current_conversations == 0:
            recommendations["workload_advice"] = "You're available to take new conversations"
        elif current_conversations < 2:
            recommendations["workload_advice"] = "Light workload - good time to help colleagues"
        else:
            recommendations["workload_advice"] = "Moderate workload - focus on current conversations"
        
        return recommendations
    
    def _get_queue_statistics(self, queue: List[Dict]) -> Dict[str, Any]:
        """Get queue statistics for dashboard"""
        if not queue:
            return {"total": 0}
        
        stats = {
            "total": len(queue),
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "by_customer_type": {"new": 0, "returning": 0, "premium": 0},
            "by_risk": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
            "average_wait_time": 0,
            "longest_waiting": 0
        }
        
        wait_times = []
        
        for conv in queue:
            # Priority breakdown
            priority = conv["indicators"]["priority"]
            stats["by_priority"][priority] += 1
            
            # Customer type breakdown
            customer_type = conv["indicators"]["customer_type"]
            if customer_type in stats["by_customer_type"]:
                stats["by_customer_type"][customer_type] += 1
            else:
                stats["by_customer_type"]["returning"] += 1
            
            # Risk breakdown
            risk_level = conv["indicators"]["risk_level"]
            stats["by_risk"][risk_level] += 1
            
            # Wait times
            wait_time = conv["wait_time_minutes"]
            wait_times.append(wait_time)
        
        if wait_times:
            stats["average_wait_time"] = sum(wait_times) / len(wait_times)
            stats["longest_waiting"] = max(wait_times)
        
        return stats


class SharedDashboardService:
    """Shared service layer for dashboard operations - used by both admin and agent endpoints"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    def get_assignable_agents(self) -> Dict[str, Any]:
        """Get agents available for assignment"""
        try:
            agents = self.db.query(Agent).filter(
                Agent.tenant_id == self.tenant_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True
            ).all()
            
            assignable_agents = []
            for agent in agents:
                session = self.db.query(AgentSession).filter(
                    AgentSession.agent_id == agent.id,
                    AgentSession.logout_at.is_(None)
                ).first()
                
                is_online = session is not None
                current_load = session.active_conversations if session else 0
                max_capacity = session.max_concurrent_chats if session else agent.max_concurrent_chats
                is_available = is_online and (current_load < max_capacity) and (session.is_accepting_chats if session else True)
                
                assignable_agents.append({
                    "agent_id": agent.id,
                    "display_name": agent.display_name,
                    "email": agent.email,
                    "is_online": is_online,
                    "is_available": is_available,
                    "current_conversations": current_load,
                    "max_concurrent_chats": max_capacity,
                    "utilization_percent": round((current_load / max_capacity * 100) if max_capacity > 0 else 0, 1)
                })
            
            assignable_agents.sort(key=lambda x: (not x["is_available"], x["utilization_percent"]))
            
            return {
                "success": True,
                "tenant_id": self.tenant_id,
                "total_agents": len(assignable_agents),
                "available_agents": sum(1 for a in assignable_agents if a["is_available"]),
                "agents": assignable_agents
            }
            
        except Exception as e:
            logger.error(f"Error getting assignable agents: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_active_conversations(self, requesting_agent_id: Optional[int] = None) -> Dict[str, Any]:
        """Get active conversations - can filter by requesting agent"""
        try:
            query = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.status.in_([
                    ConversationStatus.QUEUED,
                    ConversationStatus.ASSIGNED,
                    ConversationStatus.ACTIVE
                ])
            )
            
            # If requesting agent provided, show their conversations first
            if requesting_agent_id:
                query = query.order_by(
                    (LiveChatConversation.assigned_agent_id == requesting_agent_id).desc(),
                    LiveChatConversation.created_at.desc()
                )
            else:
                query = query.order_by(LiveChatConversation.created_at.desc())
            
            conversations = query.all()
            
            conversation_list = []
            current_time = datetime.utcnow()
            
            for conv in conversations:
                agent_name = None
                if conv.assigned_agent_id:
                    agent = self.db.query(Agent).filter(Agent.id == conv.assigned_agent_id).first()
                    agent_name = agent.display_name if agent else "Unknown Agent"
                
                wait_time = None
                if conv.queue_entry_time:
                    if conv.assigned_at:
                        time_diff = safe_subtract(conv.assigned_at, conv.queue_entry_time)
                        wait_time = int(time_diff.total_seconds() / 60)
                    else:
                        time_diff = safe_subtract(current_time, conv.queue_entry_time)
                        wait_time = int(time_diff.total_seconds() / 60)
                
                conversation_list.append({
                    "conversation_id": conv.id,
                    "customer_identifier": conv.customer_identifier,
                    "customer_name": conv.customer_name,
                    "customer_email": conv.customer_email,
                    "status": conv.status,
                    "assigned_agent_id": conv.assigned_agent_id,
                    "agent_name": agent_name,
                    "created_at": conv.created_at.isoformat() if conv.created_at else None,
                    "last_activity_at": conv.last_activity_at.isoformat() if conv.last_activity_at else None,
                    "message_count": conv.message_count,
                    "wait_time_minutes": wait_time,
                    "queue_position": conv.queue_position,
                    "is_mine": conv.assigned_agent_id == requesting_agent_id if requesting_agent_id else False
                })
            
            return {
                "success": True,
                "conversations": conversation_list,
                "total_count": len(conversation_list),
                "my_conversations": len([c for c in conversation_list if c.get("is_mine")]) if requesting_agent_id else None
            }
            
        except Exception as e:
            logger.error(f"Error getting active conversations: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_analytics_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get analytics summary for tenant"""
        try:
            from_date = datetime.utcnow() - timedelta(days=days)
            
            # Basic conversation stats
            total_conversations = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date
            ).count()
            
            completed_conversations = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.status == ConversationStatus.CLOSED
            ).count()
            
            abandoned_conversations = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.status == ConversationStatus.ABANDONED
            ).count()
            
            # Calculate averages
            avg_wait_time = self.db.query(func.avg(LiveChatConversation.wait_time_seconds)).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.wait_time_seconds.isnot(None)
            ).scalar() or 0
            
            avg_duration = self.db.query(func.avg(LiveChatConversation.conversation_duration_seconds)).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.conversation_duration_seconds.isnot(None)
            ).scalar() or 0
            
            avg_satisfaction = self.db.query(func.avg(LiveChatConversation.customer_satisfaction)).filter(
                LiveChatConversation.tenant_id == self.tenant_id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.customer_satisfaction.isnot(None)
            ).scalar() or 0
            
            return {
                "success": True,
                "period_days": days,
                "summary": {
                    "total_conversations": total_conversations,
                    "completed_conversations": completed_conversations,
                    "abandoned_conversations": abandoned_conversations,
                    "completion_rate": round((completed_conversations / total_conversations * 100) if total_conversations > 0 else 0, 2),
                    "abandonment_rate": round((abandoned_conversations / total_conversations * 100) if total_conversations > 0 else 0, 2),
                    "avg_wait_time_minutes": round(avg_wait_time / 60, 2),
                    "avg_conversation_duration_minutes": round(avg_duration / 60, 2),
                    "avg_customer_satisfaction": round(avg_satisfaction, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            waiting_count = self.db.query(ChatQueue).filter(
                ChatQueue.status == "waiting",
                ChatQueue.tenant_id == self.tenant_id
            ).count()

            assigned_count = self.db.query(ChatQueue).filter(
                ChatQueue.status == "assigned",
                ChatQueue.tenant_id == self.tenant_id
            ).count()

            return {
                "success": True,
                "waiting": waiting_count,
                "assigned": assigned_count,
                "tenant_id": self.tenant_id
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {"success": False, "error": str(e)}