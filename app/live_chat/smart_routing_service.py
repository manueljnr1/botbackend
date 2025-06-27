# app/live_chat/smart_routing_service.py

import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
from collections import defaultdict, Counter

from app.live_chat.models import (
    LiveChatConversation, Agent, AgentSession, LiveChatMessage,
    ConversationStatus, AgentStatus
)
# Import the new models (these would be added to models.py)
from app.live_chat.models import (
    AgentTag, ConversationTagging, AgentTagPerformance, 
    SmartRoutingLog, agent_tags_association
)

logger = logging.getLogger(__name__)


class MessageAnalyzer:
    """Analyzes customer messages to detect intent and required skills"""
    
    # Predefined keyword patterns for different categories
    KEYWORD_PATTERNS = {
        "billing": {
            "keywords": [
                "bill", "billing", "charge", "payment", "invoice", "refund", 
                "money", "cost", "price", "fee", "subscription", "plan",
                "credit card", "debit", "bank", "transaction", "receipt"
            ],
            "phrases": [
                "billing issue", "payment problem", "refund request",
                "wrong charge", "unexpected fee", "billing error"
            ]
        },
        "refunds": {
            "keywords": [
                "refund", "money back", "return", "cancel", "cancellation",
                "dispute", "chargeback", "reimburse", "compensation"
            ],
            "phrases": [
                "want my money back", "request a refund", "cancel my order",
                "return my purchase", "dispute this charge"
            ]
        },
        "authentication": {
            "keywords": [
                "login", "password", "access", "account", "username",
                "signin", "sign in", "authenticate", "verification", "verify",
                "locked out", "forgot", "reset", "2fa", "two factor"
            ],
            "phrases": [
                "can't login", "forgot password", "account locked",
                "login problem", "access denied", "verification code"
            ]
        },
        "technical": {
            "keywords": [
                "bug", "error", "crash", "broken", "not working", "issue",
                "problem", "glitch", "malfunction", "loading", "slow",
                "API", "integration", "sync", "connection"
            ],
            "phrases": [
                "technical issue", "something is broken", "not working properly",
                "app crashed", "page won't load", "connection error"
            ]
        },
        "account": {
            "keywords": [
                "account", "profile", "settings", "preferences", "data",
                "information", "details", "update", "change", "modify"
            ],
            "phrases": [
                "update my account", "change my information", "account settings",
                "profile update", "personal information"
            ]
        },
        "sales": {
            "keywords": [
                "buy", "purchase", "order", "product", "service", "demo",
                "trial", "upgrade", "downgrade", "features", "pricing"
            ],
            "phrases": [
                "want to buy", "interested in", "pricing information",
                "product demo", "upgrade my plan"
            ]
        },
        "general": {
            "keywords": [
                "help", "support", "question", "how to", "information",
                "guide", "tutorial", "documentation"
            ],
            "phrases": [
                "need help", "have a question", "how do I", "can you help"
            ]
        }
    }
    
    @classmethod
    def analyze_message(cls, message_content: str) -> List[Dict[str, Any]]:
        """
        Analyze message content and return detected tags with confidence scores
        
        Returns:
            List of dicts with tag_name, confidence, detected_keywords
        """
        if not message_content:
            return []
        
        message_lower = message_content.lower()
        detected_tags = []
        
        for category, patterns in cls.KEYWORD_PATTERNS.items():
            confidence = 0.0
            detected_keywords = []
            
            # Check individual keywords
            keyword_matches = 0
            for keyword in patterns["keywords"]:
                if keyword in message_lower:
                    keyword_matches += 1
                    detected_keywords.append(keyword)
            
            # Check phrases (higher weight)
            phrase_matches = 0
            for phrase in patterns.get("phrases", []):
                if phrase in message_lower:
                    phrase_matches += 1
                    detected_keywords.append(phrase)
                    confidence += 0.3  # Phrases are more specific
            
            # Calculate confidence based on matches
            if keyword_matches > 0:
                confidence += min(keyword_matches * 0.1, 0.5)
            
            # Boost confidence for multiple matches
            if keyword_matches >= 3:
                confidence += 0.2
            
            # Cap confidence at 1.0
            confidence = min(confidence, 1.0)
            
            if confidence > 0.1:  # Only include if we have reasonable confidence
                detected_tags.append({
                    "tag_name": category,
                    "confidence": round(confidence, 3),
                    "detected_keywords": detected_keywords,
                    "keyword_count": keyword_matches,
                    "phrase_count": phrase_matches
                })
        
        # Sort by confidence descending
        detected_tags.sort(key=lambda x: x["confidence"], reverse=True)
        return detected_tags
    
    @classmethod
    def analyze_conversation_context(cls, conversation: LiveChatConversation, 
                                   db: Session) -> Dict[str, Any]:
        """Analyze full conversation context for better routing"""
        context = {
            "customer_history": cls._get_customer_history(conversation, db),
            "urgency_indicators": cls._detect_urgency(conversation),
            "complexity_score": cls._assess_complexity(conversation),
            "customer_sentiment": cls._analyze_sentiment(conversation)
        }
        return context
    
    @classmethod
    def _get_customer_history(cls, conversation: LiveChatConversation, db: Session) -> Dict:
        """Get customer's conversation history for context"""
        if not conversation.customer_identifier:
            return {"is_new": True, "previous_tags": [], "satisfaction_history": []}
        
        # Get previous conversations
        previous_convs = db.query(LiveChatConversation).filter(
            and_(
                LiveChatConversation.tenant_id == conversation.tenant_id,
                LiveChatConversation.customer_identifier == conversation.customer_identifier,
                LiveChatConversation.id != conversation.id
            )
        ).order_by(desc(LiveChatConversation.created_at)).limit(5).all()
        
        if not previous_convs:
            return {"is_new": True, "previous_tags": [], "satisfaction_history": []}
        
        # Get tags from previous conversations
        previous_tags = []
        satisfaction_scores = []
        
        for conv in previous_convs:
            if conv.customer_satisfaction:
                satisfaction_scores.append(conv.customer_satisfaction)
            
            # Get conversation tags
            conv_tags = db.query(ConversationTagging).filter(
                ConversationTagging.conversation_id == conv.id
            ).all()
            
            for tag_record in conv_tags:
                previous_tags.append(tag_record.tag.name)
        
        return {
            "is_new": False,
            "previous_conversations": len(previous_convs),
            "previous_tags": list(set(previous_tags)),
            "satisfaction_history": satisfaction_scores,
            "avg_satisfaction": sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else None
        }
    
    @classmethod
    def _detect_urgency(cls, conversation: LiveChatConversation) -> Dict:
        """Detect urgency indicators"""
        urgency_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "broken", "down", "not working", "stopped", "error",
            "frustrated", "angry", "disappointed", "terrible"
        ]
        
        # Analyze first message if available
        urgency_score = 0
        detected_indicators = []
        
        if conversation.original_question:
            message_lower = conversation.original_question.lower()
            for keyword in urgency_keywords:
                if keyword in message_lower:
                    urgency_score += 1
                    detected_indicators.append(keyword)
        
        return {
            "urgency_score": min(urgency_score, 5),  # Cap at 5
            "indicators": detected_indicators,
            "is_urgent": urgency_score >= 2
        }
    
    @classmethod
    def _assess_complexity(cls, conversation: LiveChatConversation) -> int:
        """Assess conversation complexity (1-5 scale)"""
        complexity = 1
        
        # Check message length
        if conversation.original_question:
            msg_len = len(conversation.original_question)
            if msg_len > 500:
                complexity += 2
            elif msg_len > 200:
                complexity += 1
        
        # Check for technical terms
        technical_terms = [
            "api", "integration", "webhook", "database", "server",
            "ssl", "certificate", "domain", "dns", "endpoint"
        ]
        
        if conversation.original_question:
            msg_lower = conversation.original_question.lower()
            tech_count = sum(1 for term in technical_terms if term in msg_lower)
            complexity += min(tech_count, 2)
        
        return min(complexity, 5)
    
    @classmethod
    def _analyze_sentiment(cls, conversation: LiveChatConversation) -> str:
        """Simple sentiment analysis"""
        if not conversation.original_question:
            return "neutral"
        
        positive_words = ["good", "great", "excellent", "happy", "satisfied", "love", "perfect"]
        negative_words = ["bad", "terrible", "awful", "hate", "frustrated", "angry", "disappointed"]
        
        msg_lower = conversation.original_question.lower()
        
        positive_count = sum(1 for word in positive_words if word in msg_lower)
        negative_count = sum(1 for word in negative_words if word in msg_lower)
        
        if negative_count > positive_count:
            return "negative"
        elif positive_count > negative_count:
            return "positive"
        else:
            return "neutral"


class SmartRoutingService:
    """Advanced routing service using agent tags and AI-powered matching"""
    
    def __init__(self, db: Session):
        self.db = db
        self.message_analyzer = MessageAnalyzer()
    
    async def find_best_agent(self, conversation_id: int) -> Dict[str, Any]:
        """
        Find the best agent for a conversation using smart routing
        
        Returns:
            {
                "agent_id": int,
                "confidence": float,
                "reasoning": list,
                "detected_tags": list,
                "routing_method": str
            }
        """
        try:
            # Get conversation details
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
            
            # Analyze conversation content
            detected_tags = await self._analyze_conversation_tags(conversation)
            
            # Get conversation context
            context = self.message_analyzer.analyze_conversation_context(conversation, self.db)
            
            # Get available agents
            available_agents = await self._get_available_agents(conversation.tenant_id)
            
            if not available_agents:
                return {
                    "success": False,
                    "error": "No agents available",
                    "routing_method": "failed"
                }
            
            # Score agents based on tags and context
            scored_agents = await self._score_agents(
                available_agents, detected_tags, context, conversation
            )
            
            if not scored_agents:
                # Fallback to round-robin or least busy
                best_agent = min(available_agents, key=lambda a: a["current_load"])
                return {
                    "success": True,
                    "agent_id": best_agent["agent_id"],
                    "confidence": 0.3,
                    "reasoning": ["No specialized agents available", "Assigned to least busy agent"],
                    "detected_tags": detected_tags,
                    "routing_method": "fallback_load_balancing"
                }
            
            # Select best agent
            best_match = scored_agents[0]
            
            # Log routing decision
            await self._log_routing_decision(
                conversation, best_match, detected_tags, context, available_agents
            )
            
            return {
                "success": True,
                "agent_id": best_match["agent_id"],
                "confidence": best_match["total_score"],
                "reasoning": best_match["reasoning"],
                "detected_tags": detected_tags,
                "routing_method": "smart_tags",
                "alternative_agents": scored_agents[1:3] if len(scored_agents) > 1 else []
            }
            
        except Exception as e:
            logger.error(f"Error in smart routing: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "routing_method": "error"
            }
    
    async def _analyze_conversation_tags(self, conversation: LiveChatConversation) -> List[Dict]:
        """Analyze conversation and detect relevant tags"""
        detected_tags = []
        
        # Analyze initial message
        if conversation.original_question:
            message_tags = self.message_analyzer.analyze_message(conversation.original_question)
            
            for tag_data in message_tags:
                # Get tag from database
                tag = self.db.query(AgentTag).filter(
                    and_(
                        AgentTag.tenant_id == conversation.tenant_id,
                        AgentTag.name == tag_data["tag_name"],
                        AgentTag.is_active == True
                    )
                ).first()
                
                if tag:
                    # Store tag detection in database
                    tag_detection = ConversationTagging(
                        conversation_id=conversation.id,
                        tag_id=tag.id,
                        confidence_score=tag_data["confidence"],
                        detection_method="keyword_analysis",
                        detected_keywords=tag_data["detected_keywords"],
                        message_text=conversation.original_question[:500]  # Truncate if too long
                    )
                    
                    self.db.add(tag_detection)
                    
                    detected_tags.append({
                        "tag_id": tag.id,
                        "tag_name": tag.name,
                        "display_name": tag.display_name,
                        "category": tag.category,
                        "confidence": tag_data["confidence"],
                        "priority_weight": tag.priority_weight,
                        "keywords": tag_data["detected_keywords"]
                    })
        
        # Analyze handoff context if available
        if conversation.handoff_context:
            try:
                handoff_data = json.loads(conversation.handoff_context)
                if "intent" in handoff_data or "category" in handoff_data:
                    # Use chatbot-provided intent/category
                    chatbot_intent = handoff_data.get("intent") or handoff_data.get("category")
                    
                    # Find matching tag
                    tag = self.db.query(AgentTag).filter(
                        and_(
                            AgentTag.tenant_id == conversation.tenant_id,
                            or_(
                                AgentTag.name.ilike(f"%{chatbot_intent}%"),
                                AgentTag.display_name.ilike(f"%{chatbot_intent}%")
                            ),
                            AgentTag.is_active == True
                        )
                    ).first()
                    
                    if tag:
                        detected_tags.append({
                            "tag_id": tag.id,
                            "tag_name": tag.name,
                            "display_name": tag.display_name,
                            "category": tag.category,
                            "confidence": 0.8,  # High confidence from chatbot
                            "priority_weight": tag.priority_weight,
                            "keywords": ["chatbot_intent"]
                        })
            except json.JSONDecodeError:
                pass
        
        self.db.commit()
        return detected_tags
    
    async def _get_available_agents(self, tenant_id: int) -> List[Dict]:
        """Get all available agents with their current load and tag information"""
        available_agents = []
        
        # Get active agent sessions
        agent_sessions = self.db.query(AgentSession).join(Agent).filter(
            and_(
                Agent.tenant_id == tenant_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True,
                AgentSession.logout_at.is_(None),
                AgentSession.status.in_([AgentStatus.ACTIVE, AgentStatus.BUSY]),
                AgentSession.is_accepting_chats == True,
                AgentSession.active_conversations < AgentSession.max_concurrent_chats
            )
        ).options(joinedload(AgentSession.agent)).all()
        
        for session in agent_sessions:
            agent = session.agent
            
            # Get agent tags and performance
            agent_tags = self.db.query(AgentTag).join(agent_tags_association).filter(
                agent_tags_association.c.agent_id == agent.id
            ).all()
            
            # Get tag performance data
            tag_performances = self.db.query(AgentTagPerformance).filter(
                AgentTagPerformance.agent_id == agent.id
            ).all()
            
            performance_by_tag = {perf.tag_id: perf for perf in tag_performances}
            
            agent_data = {
                "agent_id": agent.id,
                "display_name": agent.display_name,
                "current_load": session.active_conversations,
                "max_capacity": session.max_concurrent_chats,
                "total_conversations": agent.total_conversations,
                "avg_satisfaction": agent.customer_satisfaction_avg or 0.0,
                "avg_response_time": agent.average_response_time or 300,  # 5 minutes default
                "tags": [],
                "specializations": []
            }
            
            # Process agent tags
            for tag in agent_tags:
                performance = performance_by_tag.get(tag.id)
                tag_info = {
                    "tag_id": tag.id,
                    "name": tag.name,
                    "display_name": tag.display_name,
                    "category": tag.category,
                    "priority_weight": tag.priority_weight,
                    "proficiency_level": 3,  # Default
                    "conversations_handled": 0,
                    "success_rate": 0.0,
                    "avg_satisfaction": 0.0,
                    "is_available": True
                }
                
                if performance:
                    tag_info.update({
                        "proficiency_level": performance.proficiency_level,
                        "conversations_handled": performance.total_conversations,
                        "success_rate": (performance.successful_resolutions / 
                                       performance.total_conversations if performance.total_conversations > 0 else 0),
                        "avg_satisfaction": performance.customer_satisfaction_avg,
                        "is_available": performance.is_available_for_tag and 
                                      performance.current_active_conversations < performance.max_concurrent_for_tag
                    })
                
                agent_data["tags"].append(tag_info)
                
                # Add to specializations if high proficiency
                if tag_info["proficiency_level"] >= 4:
                    agent_data["specializations"].append(tag.name)
            
            available_agents.append(agent_data)
        
        return available_agents
    
    async def _score_agents(self, available_agents: List[Dict], detected_tags: List[Dict],
                          context: Dict, conversation: LiveChatConversation) -> List[Dict]:
        """Score agents based on detected tags, performance, and context"""
        scored_agents = []
        
        for agent in available_agents:
            score_breakdown = {
                "tag_match_score": 0.0,
                "performance_score": 0.0,
                "availability_score": 0.0,
                "experience_score": 0.0,
                "customer_history_score": 0.0
            }
            
            reasoning = []
            
            # 1. Tag Matching Score (40% weight)
            tag_scores = []
            for detected_tag in detected_tags:
                best_tag_match = 0.0
                matching_agent_tag = None
                
                for agent_tag in agent["tags"]:
                    if agent_tag["tag_id"] == detected_tag["tag_id"] and agent_tag["is_available"]:
                        # Calculate match score based on proficiency and performance
                        proficiency_score = agent_tag["proficiency_level"] / 5.0  # Normalize to 0-1
                        performance_score = min(agent_tag["success_rate"], 1.0)
                        satisfaction_score = agent_tag["avg_satisfaction"] / 5.0 if agent_tag["avg_satisfaction"] else 0.5
                        
                        # Weight by tag confidence and priority
                        tag_match_score = (
                            proficiency_score * 0.4 +
                            performance_score * 0.3 +
                            satisfaction_score * 0.3
                        ) * detected_tag["confidence"] * detected_tag["priority_weight"]
                        
                        if tag_match_score > best_tag_match:
                            best_tag_match = tag_match_score
                            matching_agent_tag = agent_tag
                
                if best_tag_match > 0:
                    tag_scores.append(best_tag_match)
                    reasoning.append(f"Has {matching_agent_tag['display_name']} expertise (Level {matching_agent_tag['proficiency_level']}/5)")
            
            # Calculate weighted tag match score
            if tag_scores:
                score_breakdown["tag_match_score"] = sum(tag_scores) / len(detected_tags)
            else:
                # No matching tags - check if agent accepts overflow
                if agent.get("accepts_overflow", True):
                    score_breakdown["tag_match_score"] = 0.2  # Low but not zero
                    reasoning.append("No specialized skills but accepts general inquiries")
            
            # 2. Performance Score (25% weight)
            if agent["total_conversations"] > 0:
                satisfaction_factor = agent["avg_satisfaction"] / 5.0 if agent["avg_satisfaction"] else 0.5
                experience_factor = min(agent["total_conversations"] / 100, 1.0)  # Cap at 100 conversations
                response_factor = max(0.1, 1.0 - (agent["avg_response_time"] / 600))  # Penalize slow response (10min+)
                
                score_breakdown["performance_score"] = (
                    satisfaction_factor * 0.5 +
                    experience_factor * 0.3 +
                    response_factor * 0.2
                )
                
                if agent["avg_satisfaction"] >= 4.5:
                    reasoning.append(f"Excellent customer satisfaction ({agent['avg_satisfaction']:.1f}/5.0)")
                elif agent["avg_satisfaction"] >= 4.0:
                    reasoning.append(f"Good customer satisfaction ({agent['avg_satisfaction']:.1f}/5.0)")
            else:
                score_breakdown["performance_score"] = 0.5  # Neutral for new agents
                reasoning.append("New agent - no performance history")
            
            # 3. Availability Score (20% weight)
            load_factor = 1.0 - (agent["current_load"] / agent["max_capacity"])
            score_breakdown["availability_score"] = load_factor
            
            if agent["current_load"] == 0:
                reasoning.append("Fully available")
            elif load_factor > 0.5:
                reasoning.append("Good availability")
            else:
                reasoning.append("Limited availability")
            
            # 4. Experience Score (10% weight)
            if len(agent["specializations"]) > 0:
                score_breakdown["experience_score"] = min(len(agent["specializations"]) / 3, 1.0)
                reasoning.append(f"Specializes in: {', '.join(agent['specializations'])}")
            else:
                score_breakdown["experience_score"] = 0.3
            
            # 5. Customer History Score (5% weight)
            customer_history = context.get("customer_history", {})
            if not customer_history.get("is_new", True):
                # Check if agent has handled this customer before
                previous_tags = customer_history.get("previous_tags", [])
                agent_tag_names = [tag["name"] for tag in agent["tags"]]
                
                matching_history = len(set(previous_tags) & set(agent_tag_names))
                if matching_history > 0:
                    score_breakdown["customer_history_score"] = 0.8
                    reasoning.append("Has handled similar issues for this customer")
                else:
                    score_breakdown["customer_history_score"] = 0.4
            else:
                score_breakdown["customer_history_score"] = 0.5  # Neutral for new customers
            
            # Calculate total weighted score
            total_score = (
                score_breakdown["tag_match_score"] * 0.40 +
                score_breakdown["performance_score"] * 0.25 +
                score_breakdown["availability_score"] * 0.20 +
                score_breakdown["experience_score"] * 0.10 +
                score_breakdown["customer_history_score"] * 0.05
            )
            
            # Apply urgency boost
            urgency_info = context.get("urgency_indicators", {})
            if urgency_info.get("is_urgent", False):
                # Boost agents with high performance for urgent issues
                if score_breakdown["performance_score"] > 0.7:
                    total_score += 0.1
                    reasoning.append("Prioritized for urgent issue")
            
            # Apply complexity adjustment
            complexity_score = context.get("complexity_score", 1)
            if complexity_score >= 4:
                # Prefer experienced agents for complex issues
                if len(agent["specializations"]) >= 2:
                    total_score += 0.05
                    reasoning.append("Selected for complex issue handling")
            
            scored_agents.append({
                "agent_id": agent["agent_id"],
                "agent_name": agent["display_name"],
                "total_score": round(total_score, 3),
                "score_breakdown": score_breakdown,
                "reasoning": reasoning,
                "current_load": agent["current_load"],
                "matching_tags": [tag["name"] for tag in agent["tags"] 
                                 if any(dt["tag_id"] == tag["tag_id"] for dt in detected_tags)]
            })
        
        # Sort by total score descending
        scored_agents.sort(key=lambda x: x["total_score"], reverse=True)
        
        # Filter out agents with very low scores unless no good options
        if scored_agents and scored_agents[0]["total_score"] >= 0.3:
            scored_agents = [agent for agent in scored_agents if agent["total_score"] >= 0.2]
        
        return scored_agents
    
    async def _log_routing_decision(self, conversation: LiveChatConversation, 
                                  best_match: Dict, detected_tags: List[Dict],
                                  context: Dict, available_agents: List[Dict]):
        """Log routing decision for analysis and improvement"""
        try:
            routing_log = SmartRoutingLog(
                conversation_id=conversation.id,
                tenant_id=conversation.tenant_id,
                assigned_agent_id=best_match["agent_id"],
                routing_method="smart_tags",
                confidence_score=best_match["total_score"],
                detected_tags=[{
                    "tag_id": tag["tag_id"],
                    "tag_name": tag["tag_name"],
                    "confidence": tag["confidence"],
                    "keywords": tag["keywords"]
                } for tag in detected_tags],
                customer_context=context,
                available_agents=[{
                    "agent_id": agent["agent_id"],
                    "load": agent["current_load"],
                    "tags": [tag["name"] for tag in agent["tags"]]
                } for agent in available_agents],
                scoring_breakdown=best_match["score_breakdown"],
                alternative_agents=[{
                    "agent_id": agent["agent_id"],
                    "score": agent["total_score"],
                    "reasoning": agent["reasoning"][:3]  # Limit for storage
                } for agent in available_agents[1:3]]
            )
            
            self.db.add(routing_log)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error logging routing decision: {str(e)}")
    
    async def update_tag_performance(self, conversation_id: int, 
                                   satisfaction_rating: Optional[int] = None,
                                   resolution_status: str = "resolved"):
        """Update agent tag performance after conversation completion"""
        try:
            # Get conversation and routing log
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation or not conversation.assigned_agent_id:
                return
            
            routing_log = self.db.query(SmartRoutingLog).filter(
                SmartRoutingLog.conversation_id == conversation_id
            ).first()
            
            # Get conversation tags
            conversation_tags = self.db.query(ConversationTagging).filter(
                ConversationTagging.conversation_id == conversation_id
            ).all()
            
            # Update performance for each relevant tag
            for tag_record in conversation_tags:
                performance = self.db.query(AgentTagPerformance).filter(
                    and_(
                        AgentTagPerformance.agent_id == conversation.assigned_agent_id,
                        AgentTagPerformance.tag_id == tag_record.tag_id
                    )
                ).first()
                
                if not performance:
                    # Create new performance record
                    performance = AgentTagPerformance(
                        agent_id=conversation.assigned_agent_id,
                        tag_id=tag_record.tag_id
                    )
                    self.db.add(performance)
                
                # Update metrics
                performance.total_conversations += 1
                
                if resolution_status == "resolved":
                    performance.successful_resolutions += 1
                
                if satisfaction_rating:
                    # Update rolling average
                    if performance.customer_satisfaction_avg:
                        performance.customer_satisfaction_avg = (
                            (performance.customer_satisfaction_avg * (performance.total_conversations - 1) + satisfaction_rating) /
                            performance.total_conversations
                        )
                    else:
                        performance.customer_satisfaction_avg = satisfaction_rating
                
                # Update resolution time
                if conversation.conversation_duration_seconds:
                    duration_minutes = conversation.conversation_duration_seconds / 60
                    if performance.average_resolution_time:
                        performance.average_resolution_time = (
                            (performance.average_resolution_time * (performance.total_conversations - 1) + duration_minutes) /
                            performance.total_conversations
                        )
                    else:
                        performance.average_resolution_time = duration_minutes
                
                performance.last_conversation_date = datetime.utcnow()
                performance.last_updated = datetime.utcnow()
            
            # Update routing log with outcome
            if routing_log:
                routing_log.customer_satisfaction = satisfaction_rating
                if conversation.conversation_duration_seconds:
                    routing_log.resolution_time_minutes = conversation.conversation_duration_seconds // 60
                routing_log.conversation_ended_at = datetime.utcnow()
                
                # Calculate routing accuracy (simplified)
                if satisfaction_rating and satisfaction_rating >= 4:
                    routing_log.routing_accuracy = min(1.0, routing_log.confidence_score + 0.2)
                elif satisfaction_rating and satisfaction_rating <= 2:
                    routing_log.routing_accuracy = max(0.0, routing_log.confidence_score - 0.3)
                else:
                    routing_log.routing_accuracy = routing_log.confidence_score
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating tag performance: {str(e)}")
            self.db.rollback()
    
    def get_routing_analytics(self, tenant_id: int, days: int = 30) -> Dict[str, Any]:
        """Get routing analytics and performance insights"""
        try:
            from_date = datetime.utcnow() - timedelta(days=days)
            
            # Get routing logs
            routing_logs = self.db.query(SmartRoutingLog).filter(
                and_(
                    SmartRoutingLog.tenant_id == tenant_id,
                    SmartRoutingLog.routed_at >= from_date
                )
            ).all()
            
            if not routing_logs:
                return {"message": "No routing data available for the specified period"}
            
            # Calculate metrics
            total_routes = len(routing_logs)
            smart_routes = len([log for log in routing_logs if log.routing_method == "smart_tags"])
            avg_confidence = sum(log.confidence_score for log in routing_logs) / total_routes
            
            # Satisfaction analysis
            satisfaction_scores = [log.customer_satisfaction for log in routing_logs 
                                 if log.customer_satisfaction]
            avg_satisfaction = sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
            
            # Tag effectiveness
            tag_stats = defaultdict(lambda: {"routes": 0, "satisfaction": [], "accuracy": []})
            
            for log in routing_logs:
                if log.detected_tags:
                    for tag_data in log.detected_tags:
                        tag_name = tag_data["tag_name"]
                        tag_stats[tag_name]["routes"] += 1
                        
                        if log.customer_satisfaction:
                            tag_stats[tag_name]["satisfaction"].append(log.customer_satisfaction)
                        
                        if log.routing_accuracy:
                            tag_stats[tag_name]["accuracy"].append(log.routing_accuracy)
            
            # Format tag statistics
            tag_effectiveness = []
            for tag_name, stats in tag_stats.items():
                tag_effectiveness.append({
                    "tag_name": tag_name,
                    "total_routes": stats["routes"],
                    "avg_satisfaction": sum(stats["satisfaction"]) / len(stats["satisfaction"]) if stats["satisfaction"] else 0,
                    "avg_accuracy": sum(stats["accuracy"]) / len(stats["accuracy"]) if stats["accuracy"] else 0,
                    "sample_size": len(stats["satisfaction"])
                })
            
            tag_effectiveness.sort(key=lambda x: x["avg_satisfaction"], reverse=True)
            
            return {
                "period_days": days,
                "total_conversations_routed": total_routes,
                "smart_routing_usage": f"{(smart_routes/total_routes*100):.1f}%",
                "average_routing_confidence": round(avg_confidence, 3),
                "average_customer_satisfaction": round(avg_satisfaction, 2),
                "tag_effectiveness": tag_effectiveness,
                "routing_methods": {
                    "smart_tags": smart_routes,
                    "fallback": total_routes - smart_routes
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting routing analytics: {str(e)}")
            return {"error": str(e)}