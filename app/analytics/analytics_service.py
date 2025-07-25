import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from collections import Counter

from app.analytics.models import ConversationAnalytics
from app.chatbot.models import ChatSession, ChatMessage
from app.live_chat.customer_detection_service import CustomerDetectionService
from app.config import settings


try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Comprehensive analytics service for all 7 features"""
    
    def __init__(self, db: Session):
        self.db = db
        if LLM_AVAILABLE and settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY
            )
        else:
            self.llm = None

    
    def get_filtered_conversations(self, tenant_id: int, filters: Dict[str, Any]) -> List[Dict]:
        """Get conversations with date/time/session filters"""
        query = self.db.query(ChatSession).filter(ChatSession.tenant_id == tenant_id)
        
        if filters.get('start_date'):
            query = query.filter(ChatSession.created_at >= filters['start_date'])
        if filters.get('end_date'):
            query = query.filter(ChatSession.created_at <= filters['end_date'])
        if filters.get('session_id'):
            query = query.filter(ChatSession.session_id == filters['session_id'])
            
        sessions = query.order_by(ChatSession.created_at.desc()).limit(100).all()
        
        results = []
        for session in sessions:
            
            msg_count = self.db.query(func.count(ChatMessage.id)).filter(
                ChatMessage.session_id == session.id
            ).scalar()
            
            
            analytics = self.db.query(ConversationAnalytics).filter(
                ConversationAnalytics.session_id == session.session_id
            ).first()
            
            results.append({
                "session_id": session.session_id,
                "user_identifier": session.user_identifier,
                "created_at": session.created_at.isoformat(),
                "message_count": msg_count,
                "category": analytics.conversation_category if analytics else None,
                "sentiment": analytics.conversation_sentiment if analytics else None,
                "rating": analytics.user_rating if analytics else None,
                "location": {
                    "country": getattr(session, 'user_country', None),
                    "city": getattr(session, 'user_city', None),
                    "region": getattr(session, 'user_region', None)
                }
            })
        
        return results

   
    def get_location_analytics(self, tenant_id: int, days: int = 30) -> Dict[str, Any]:
        """Analyze user locations using existing detection service"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get sessions with location data
        sessions = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == tenant_id,
            ChatSession.created_at >= start_date
        ).all()
        
        # Extract location data from sessions or use detection service
        location_data = []
        for session in sessions:
            country = getattr(session, 'user_country', None)
            city = getattr(session, 'user_city', None)
            region = getattr(session, 'user_region', None)
            
            # If no location in session, try to detect from session metadata
            if not country and hasattr(session, 'session_metadata') and session.session_metadata:
                metadata = session.session_metadata
                country = metadata.get('country')
                city = metadata.get('city')
                region = metadata.get('region')
            
            if country:  # Only include if we have location data
                location_data.append({
                    "country": country,
                    "city": city or "Unknown",
                    "region": region or "Unknown"
                })
        
        
        country_counts = Counter(item['country'] for item in location_data)
        city_counts = Counter(f"{item['city']}, {item['country']}" for item in location_data)
        
        total_sessions = len(location_data)
        
        return {
            "total_sessions_with_location": total_sessions,
            "country_distribution": [
                {"country": country, "count": count, "percentage": (count/total_sessions)*100}
                for country, count in country_counts.most_common(10)
            ],
            "city_distribution": [
                {"location": city, "count": count, "percentage": (count/total_sessions)*100}
                for city, count in city_counts.most_common(15)
            ],
            "coverage_percentage": (total_sessions / len(sessions) * 100) if sessions else 0
        }

    
    def extract_conversation_topics(self, session_id: str) -> List[str]:
        """Extract topics from conversation using LLM"""
        if not self.llm:
            return ["general_inquiry"]
        
        try:
            # Get conversation messages
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                return []
            
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).order_by(ChatMessage.created_at).all()
            
            # Build conversation text
            conversation_text = ""
            for msg in messages:
                role = "User" if msg.is_from_user else "Assistant"
                conversation_text += f"{role}: {msg.content[:200]}\n"
            
            if len(conversation_text) < 50:
                return ["short_conversation"]
            
            # LLM topic extraction
            prompt = PromptTemplate(
                input_variables=["conversation"],
                template="""Extract 2-4 main topics from this conversation. Focus on what the user is asking about or discussing.

Conversation:
{conversation}

Return topics as a comma-separated list. Examples:
- pricing, features, setup
- login_issues, password_reset
- product_inquiry, demo_request
- billing, subscription, payment

Topics:"""
            )
            
            result = self.llm.invoke(prompt.format(conversation=conversation_text))
            topics_text = result.content.strip()
            
            # Parse and clean topics
            topics = [topic.strip().lower().replace(' ', '_') for topic in topics_text.split(',')]
            return [topic for topic in topics if len(topic) > 2][:4]  # Max 4 topics
            
        except Exception as e:
            logger.error(f"Topic extraction error: {e}")
            return ["extraction_error"]

    # 4. CHAT CATEGORIES
    def categorize_conversation(self, session_id: str) -> str:
        """Categorize conversation using LLM + keywords"""
        try:
            # Get conversation text
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                return "unknown"
            
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).all()
            
            user_messages = [msg.content for msg in messages if msg.is_from_user]
            conversation_text = " ".join(user_messages).lower()
            
            # Quick keyword categorization
            if any(word in conversation_text for word in ['price', 'cost', 'buy', 'purchase', 'plan', 'upgrade']):
                return "sales"
            elif any(word in conversation_text for word in ['problem', 'error', 'issue', 'broken', 'fix', 'help']):
                return "support"
            elif any(word in conversation_text for word in ['how', 'what', 'features', 'demo', 'info']):
                return "informational"
            elif any(word in conversation_text for word in ['billing', 'payment', 'invoice', 'refund']):
                return "billing"
            elif any(word in conversation_text for word in ['account', 'login', 'password', 'access']):
                return "account"
            else:
                return "general"
                
        except Exception as e:
            logger.error(f"Categorization error: {e}")
            return "error"

    # 5. CONVERSATION RATINGS
    def submit_conversation_rating(self, session_id: str, rating: int, feedback: str = None) -> bool:
        """Submit rating for conversation"""
        try:
            # Get or create analytics record
            analytics = self.db.query(ConversationAnalytics).filter(
                ConversationAnalytics.session_id == session_id
            ).first()
            
            if not analytics:
                session = self.db.query(ChatSession).filter(
                    ChatSession.session_id == session_id
                ).first()
                
                if not session:
                    return False
                
                analytics = ConversationAnalytics(
                    session_id=session_id,
                    tenant_id=session.tenant_id
                )
                self.db.add(analytics)
            
            analytics.user_rating = rating
            analytics.user_feedback = feedback
            self.db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Rating submission error: {e}")
            return False

    # 6. CUSTOMER JOURNEY MAPPING
    def analyze_customer_journey(self, user_identifier: str, tenant_id: int) -> Dict[str, Any]:
        """Analyze customer journey across sessions"""
        try:
            # Get all sessions for user
            sessions = self.db.query(ChatSession).filter(
                ChatSession.tenant_id == tenant_id,
                ChatSession.user_identifier == user_identifier
            ).order_by(ChatSession.created_at).all()
            
            journey_stages = []
            for i, session in enumerate(sessions):
                # Determine journey stage
                msg_count = self.db.query(func.count(ChatMessage.id)).filter(
                    ChatMessage.session_id == session.id
                ).scalar()
                
                analytics = self.db.query(ConversationAnalytics).filter(
                    ConversationAnalytics.session_id == session.session_id
                ).first()
                
                category = analytics.conversation_category if analytics else "unknown"
                
                # Map to journey stages
                if i == 0:
                    stage = "discovery"
                elif category == "informational":
                    stage = "consideration"
                elif category == "sales":
                    stage = "evaluation"
                elif category == "account":
                    stage = "onboarding"
                elif category == "support":
                    stage = "usage"
                else:
                    stage = "engagement"
                
                journey_stages.append({
                    "session_id": session.session_id,
                    "stage": stage,
                    "timestamp": session.created_at.isoformat(),
                    "category": category,
                    "message_count": msg_count,
                    "rating": analytics.user_rating if analytics else None
                })
            
            return {
                "user_identifier": user_identifier,
                "total_sessions": len(sessions),
                "journey_stages": journey_stages,
                "current_stage": journey_stages[-1]["stage"] if journey_stages else "unknown",
                "engagement_score": self._calculate_engagement_score(journey_stages)
            }
            
        except Exception as e:
            logger.error(f"Journey analysis error: {e}")
            return {"error": str(e)}

    # 7. SENTIMENT ANALYSIS
    def analyze_conversation_sentiment(self, session_id: str) -> Dict[str, Any]:
        """Analyze sentiment of conversation"""
        if not self.llm:
            return {"sentiment": "neutral", "confidence": 0.5}
        
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == session_id
            ).first()
            
            if not session:
                return {"sentiment": "unknown", "confidence": 0.0}
            
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id,
                ChatMessage.is_from_user == True
            ).order_by(ChatMessage.created_at).all()
            
            user_messages = [msg.content for msg in messages]
            conversation_text = " ".join(user_messages)
            
            if len(conversation_text) < 20:
                return {"sentiment": "neutral", "confidence": 0.3}
            
            # LLM sentiment analysis
            prompt = PromptTemplate(
                input_variables=["text"],
                template="""Analyze the sentiment of this customer conversation. Focus on the customer's overall mood and satisfaction.

Customer messages: {text}

Classify as one of: positive, negative, neutral, frustrated, satisfied

Response format: SENTIMENT|CONFIDENCE
Example: positive|0.8

Analysis:"""
            )
            
            result = self.llm.invoke(prompt.format(text=conversation_text))
            response = result.content.strip()
            
            if '|' in response:
                sentiment, confidence_str = response.split('|', 1) # Split only once
                # Extract only the numeric part before any newline or extra text
                confidence = float(confidence_str.strip().split('\n')[0]) 
            else:
                sentiment = response.lower()
                confidence = 0.7 # Fallback confidence
            
            return {
                "sentiment": sentiment.strip(),
                "confidence": confidence,
                "message_count": len(user_messages)
            }
            
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {"sentiment": "error", "confidence": 0.0}

    # UTILITY METHODS
    def _calculate_engagement_score(self, journey_stages: List[Dict]) -> float:
        """Calculate engagement score from journey stages"""
        if not journey_stages:
            return 0.0
        
        score = 0.0
        for stage in journey_stages:
            # Base score for each session
            score += 1.0
            
            # Bonus for message count
            msg_count = stage.get('message_count', 0)
            score += min(msg_count * 0.1, 2.0)  # Max 2 bonus points
            
            # Bonus for positive rating
            rating = stage.get('rating')
            if rating and rating >= 4:
                score += 1.0
        
        # Normalize to 0-10 scale
        return min(score / len(journey_stages) * 2, 10.0)

    def analyze_all_sessions(self, tenant_id: int, limit: int = 50) -> None:
        """Batch analyze sessions that don't have analytics"""
        try:
            # Get sessions without analytics
            sessions = self.db.query(ChatSession).outerjoin(
                ConversationAnalytics,
                ChatSession.session_id == ConversationAnalytics.session_id
            ).filter(
                ChatSession.tenant_id == tenant_id,
                ConversationAnalytics.id.is_(None)
            ).limit(limit).all()
            
            for session in sessions:
                try:
                    # Extract topics, categorize, analyze sentiment
                    topics = self.extract_conversation_topics(session.session_id)
                    category = self.categorize_conversation(session.session_id)
                    sentiment = self.analyze_conversation_sentiment(session.session_id)
                    
                    # Create analytics record
                    analytics = ConversationAnalytics(
                        session_id=session.session_id,
                        tenant_id=session.tenant_id,
                        conversation_category=category,
                        conversation_sentiment=sentiment.get('sentiment'),
                        conversation_topics=json.dumps(topics)
                    )
                    
                    self.db.add(analytics)
                    
                except Exception as e:
                    logger.error(f"Error analyzing session {session.session_id}: {e}")
                    continue
            
            self.db.commit()
            logger.info(f"Analyzed {len(sessions)} sessions for tenant {tenant_id}")
            
        except Exception as e:
            logger.error(f"Batch analysis error: {e}")