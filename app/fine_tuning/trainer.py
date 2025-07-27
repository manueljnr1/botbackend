
import logging
import asyncio
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from collections import defaultdict, Counter

from app.database import SessionLocal
from app.chatbot.models import ChatMessage, ChatSession, Escalation
from app.chatbot.smart_feedback import PendingFeedback
from app.knowledge_base.models import FAQ, KnowledgeBase
from app.tenants.models import Tenant
from app.fine_tuning.models import LearningPattern, TrainingMetrics, AutoImprovement
from app.fine_tuning.models import LearningPattern, TrainingMetrics, AutoImprovement, ConversationAnalysis, ResponseConfidence, ProactiveLearning

# LLM Integration
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

from app.config import settings

logger = logging.getLogger(__name__)

class BackgroundTrainer:
    """
    Autonomous learning system that continuously improves chatbot responses
    Runs every 30 minutes, learns from failures, auto-updates responses
    """
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        self.training_interval = 30 * 60  # 30 minutes in seconds
        self.is_running = False
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        
        # Initialize LLM first
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.2,
                openai_api_key=settings.OPENAI_API_KEY
            )
        else:
            self.llm = None
        
        # Now initialize analyzers (after self.llm is set)
        self.semantic_analyzer = SemanticAnalyzer(self.llm if self.llm_available else None)
        self.confidence_analyzer = ConfidenceAnalyzer(self.llm if self.llm_available else None)
        self.proactive_learner = ProactiveLearner(self.db)
        
        logger.info("🧠 Background Trainer initialized - Autonomous learning enabled")
    
    async def start_continuous_learning(self):
        """Start the continuous learning background task"""
        if self.is_running:
            logger.warning("Background trainer already running")
            return
        
        self.is_running = True
        logger.info("🚀 Starting continuous learning - 30-minute cycles")
        
        while self.is_running:
            try:
                await self._training_cycle()
                await asyncio.sleep(self.training_interval)
            except Exception as e:
                logger.error(f"💥 Training cycle error: {e}")
                await asyncio.sleep(300)  # 5-minute recovery delay
    
    def stop_learning(self):
        """Stop the continuous learning process"""
        self.is_running = False
        logger.info("🛑 Background training stopped")
    
    async def _training_cycle(self):
        """Complete training cycle - analyze, learn, improve"""
        cycle_start = datetime.utcnow()
        logger.info("🔄 Starting training cycle")
        
        try:
            # Get all active tenants
            tenants = self.db.query(Tenant).filter(Tenant.is_active == True).all()
            
            total_patterns = 0
            total_improvements = 0
            
            for tenant in tenants:
                try:
                    tenant_patterns, tenant_improvements = await self._train_tenant(tenant)
                    total_patterns += tenant_patterns
                    total_improvements += tenant_improvements
                except Exception as e:
                    logger.error(f"❌ Tenant {tenant.id} training failed: {e}")
            
            cycle_time = (datetime.utcnow() - cycle_start).total_seconds()
            logger.info(f"✅ Training cycle complete: {total_patterns} patterns, {total_improvements} improvements, {cycle_time:.2f}s")
            
        except Exception as e:
            logger.error(f"💥 Training cycle failed: {e}")
    
    async def _train_tenant(self, tenant: Tenant) -> Tuple[int, int]:
        """Train a specific tenant's chatbot"""
        logger.info(f"🎯 Training tenant: {tenant.name} (ID: {tenant.id})")
        
        patterns_learned = 0
        improvements_made = 0
        
        try:
            # 1. Analyze recent conversations
            failed_conversations = self._get_failed_conversations(tenant.id)
            successful_conversations = self._get_successful_conversations(tenant.id)
            
            # 2. Learn from failures
            failure_patterns = await self._learn_from_failures(tenant.id, failed_conversations)
            patterns_learned += len(failure_patterns)
            
            # 3. Learn from successes
            success_patterns = await self._learn_from_successes(tenant.id, successful_conversations)
            patterns_learned += len(success_patterns)
            
            # 4. Auto-improve responses
            improvements = await self._auto_improve_responses(tenant.id, failure_patterns)
            improvements_made += len(improvements)
            
            # 5. Update knowledge base
            kb_updates = await self._update_knowledge_base(tenant.id, failure_patterns, success_patterns)
            improvements_made += len(kb_updates)
            
            # 6. Record training metrics
            self._record_training_metrics(tenant.id, patterns_learned, improvements_made)
            
            logger.info(f"✅ Tenant {tenant.id}: {patterns_learned} patterns, {improvements_made} improvements")
            
        except Exception as e:
            logger.error(f"❌ Tenant {tenant.id} training error: {e}")
        
        return patterns_learned, improvements_made
    
    def _get_failed_conversations(self, tenant_id: int) -> List[Dict]:
        """Get conversations that failed (escalated or negative feedback)"""
        cutoff_time = datetime.utcnow() - timedelta(hours=2)  # Last 2 hours
        
        failed_conversations = []
        
        # Get escalated conversations
        escalations = self.db.query(Escalation).filter(
            Escalation.tenant_id == tenant_id,
            Escalation.created_at >= cutoff_time
        ).all()
        
        for escalation in escalations:
            # Get conversation context
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == escalation.session_id
            ).first()
            
            if session:
                messages = self.db.query(ChatMessage).filter(
                    ChatMessage.session_id == session.id
                ).order_by(ChatMessage.created_at).all()
                
                failed_conversations.append({
                    'type': 'escalation',
                    'session_id': session.session_id,
                    'user_message': escalation.original_issue,
                    'conversation': [{'content': m.content, 'is_user': m.is_from_user} for m in messages],
                    'failure_reason': escalation.reason
                })
        
        # Get negative feedback conversations
        negative_feedback = self.db.query(PendingFeedback).filter(
            PendingFeedback.tenant_id == tenant_id,
            PendingFeedback.created_at >= cutoff_time,
            PendingFeedback.status.in_(['responded', 'pending'])
        ).all()
        
        for feedback in negative_feedback:
            failed_conversations.append({
                'type': 'negative_feedback',
                'session_id': feedback.session_id,
                'user_message': feedback.user_question,
                'bot_response': feedback.bot_response,
                'failure_reason': 'inadequate_response'
            })
        
        return failed_conversations
    
    def _get_successful_conversations(self, tenant_id: int) -> List[Dict]:
        """Get conversations that succeeded (no escalation, completed naturally)"""
        cutoff_time = datetime.utcnow() - timedelta(hours=2)
        
        # Get sessions with no escalations
        successful_sessions = self.db.query(ChatSession).filter(
            ChatSession.tenant_id == tenant_id,
            ChatSession.created_at >= cutoff_time,
            ChatSession.is_active == False  # Completed sessions
        ).all()
        
        successful_conversations = []
        
        for session in successful_sessions:
            # Check if no escalation occurred
            escalation_exists = self.db.query(Escalation).filter(
                Escalation.session_id == session.session_id
            ).first()
            
            if not escalation_exists:
                messages = self.db.query(ChatMessage).filter(
                    ChatMessage.session_id == session.id
                ).order_by(ChatMessage.created_at).all()
                
                if len(messages) >= 2:  # At least one exchange
                    successful_conversations.append({
                        'session_id': session.session_id,
                        'conversation': [{'content': m.content, 'is_user': m.is_from_user} for m in messages]
                    })
        
        return successful_conversations[:20]  # Limit to prevent overload
    
    async def _learn_from_failures(self, tenant_id: int, failed_conversations: List[Dict]) -> List[Dict]:
        """Analyze failed conversations and learn patterns"""
        if not failed_conversations or not self.llm_available:
            return []
        
        learned_patterns = []
        
        for conversation in failed_conversations:
            try:
                pattern = await self._extract_failure_pattern(tenant_id, conversation)
                if pattern:
                    learned_patterns.append(pattern)
                    self._store_learning_pattern(tenant_id, pattern)
            except Exception as e:
                logger.error(f"❌ Failed to learn from conversation: {e}")
        
        return learned_patterns
    
    async def _extract_failure_pattern(self, tenant_id: int, conversation: Dict) -> Optional[Dict]:
        """Extract what went wrong in a failed conversation"""
        if not self.llm_available:
            return None
        
        prompt = PromptTemplate(
            input_variables=["user_message", "bot_response", "failure_reason"],
            template="""Analyze this failed conversation and identify what went wrong:

USER MESSAGE: "{user_message}"
BOT RESPONSE: "{bot_response}"
FAILURE REASON: {failure_reason}

TASK: Identify the core issue and suggest a better response.

ANALYSIS:
1. What specific aspect of the user's need was not addressed?
2. What would be a more helpful, specific response?
3. What pattern should the bot learn to handle similar cases?

RESPONSE FORMAT (JSON):
{{
    "user_pattern": "specific pattern in user message",
    "failure_cause": "why current response failed",
    "improved_response": "better response that would work",
    "pattern_type": "payment_issue|technical_problem|account_question|general_inquiry",
    "confidence": 0.95
}}

JSON Response:"""
        )
        
        try:
            user_msg = conversation.get('user_message', '')
            bot_response = ''
            
            # Extract bot response from conversation
            conv_messages = conversation.get('conversation', [])
            for msg in conv_messages:
                if not msg.get('is_user', True):
                    bot_response = msg.get('content', '')
                    break
            
            result = self.llm.invoke(prompt.format(
                user_message=user_msg,
                bot_response=bot_response,
                failure_reason=conversation.get('failure_reason', 'unknown')
            ))
            
            response_text = result.content.strip()
            
            # Parse JSON response
            import json
            pattern_data = json.loads(response_text)
            
            if pattern_data.get('confidence', 0) > 0.7:
                return {
                    'user_pattern': pattern_data['user_pattern'],
                    'old_response': bot_response,
                    'improved_response': pattern_data['improved_response'],
                    'pattern_type': pattern_data.get('pattern_type', 'general_inquiry'),
                    'confidence': pattern_data['confidence'],
                    'source': 'failure_analysis'
                }
        
        except Exception as e:
            logger.error(f"❌ Pattern extraction failed: {e}")
        
        return None
    
    async def _learn_from_successes(self, tenant_id: int, successful_conversations: List[Dict]) -> List[Dict]:
        """Learn what works well from successful conversations"""
        success_patterns = []
        
        # Analyze response patterns that led to successful completions
        for conversation in successful_conversations[:10]:  # Limit processing
            try:
                conv_messages = conversation.get('conversation', [])
                
                # Find patterns in successful resolutions
                for i in range(len(conv_messages) - 1):
                    if conv_messages[i].get('is_user', True):  # User message
                        user_msg = conv_messages[i]['content']
                        
                        if i + 1 < len(conv_messages) and not conv_messages[i + 1].get('is_user', True):
                            bot_response = conv_messages[i + 1]['content']
                            
                            # Store successful pattern
                            pattern = {
                                'user_pattern': user_msg,
                                'successful_response': bot_response,
                                'pattern_type': 'successful_resolution',
                                'confidence': 0.8,
                                'source': 'success_analysis'
                            }
                            
                            success_patterns.append(pattern)
                            self._store_learning_pattern(tenant_id, pattern)
            
            except Exception as e:
                logger.error(f"❌ Success pattern extraction failed: {e}")
        
        return success_patterns
    
    def _store_learning_pattern(self, tenant_id: int, pattern: Dict):
        """Store learned pattern in database"""
        try:
            learning_pattern = LearningPattern(
                tenant_id=tenant_id,
                pattern_type=pattern.get('source', 'unknown'),
                user_message_pattern=pattern.get('user_pattern', ''),
                bot_response_pattern=pattern.get('old_response', ''),
                improved_response=pattern.get('improved_response') or pattern.get('successful_response', ''),
                confidence_score=pattern.get('confidence', 0.0)
            )
            
            self.db.add(learning_pattern)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ Failed to store pattern: {e}")
            self.db.rollback()
    
    async def _auto_improve_responses(self, tenant_id: int, failure_patterns: List[Dict]) -> List[Dict]:
        """Automatically improve responses based on learned patterns"""
        improvements = []
        
        for pattern in failure_patterns:
            try:
                if pattern.get('confidence', 0) > 0.8:
                    # Check if this pattern already exists
                    existing = self.db.query(LearningPattern).filter(
                        LearningPattern.tenant_id == tenant_id,
                        LearningPattern.user_message_pattern.contains(pattern['user_pattern'][:50])
                    ).first()
                    
                    if not existing:
                        # Create new improvement
                        improvement = AutoImprovement(
                            tenant_id=tenant_id,
                            improvement_type='response_updated',
                            trigger_pattern=pattern['user_pattern'],
                            old_response=pattern.get('old_response', ''),
                            new_response=pattern['improved_response'],
                            effectiveness_score=pattern['confidence']
                        )
                        
                        self.db.add(improvement)
                        improvements.append(pattern)
            
            except Exception as e:
                logger.error(f"❌ Auto-improvement failed: {e}")
        
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"❌ Failed to save improvements: {e}")
            self.db.rollback()
        
        return improvements
    
    async def _update_knowledge_base(self, tenant_id: int, failure_patterns: List[Dict], success_patterns: List[Dict]) -> List[Dict]:
        """Auto-update knowledge base with learned responses"""
        kb_updates = []
        
        # Create new FAQs from failure patterns
        for pattern in failure_patterns:
            try:
                if pattern.get('confidence', 0) > 0.85:
                    user_pattern = pattern['user_pattern']
                    improved_response = pattern['improved_response']
                    
                    # Check if similar FAQ exists
                    existing_faq = self.db.query(FAQ).filter(
                        FAQ.tenant_id == tenant_id,
                        FAQ.question.contains(user_pattern[:30])
                    ).first()
                    
                    if not existing_faq and len(user_pattern) > 10:
                        # Create new FAQ
                        new_faq = FAQ(
                            tenant_id=tenant_id,
                            question=self._clean_user_message(user_pattern),
                            answer=improved_response
                        )
                        
                        self.db.add(new_faq)
                        kb_updates.append({
                            'type': 'faq_created',
                            'question': user_pattern,
                            'answer': improved_response
                        })
            
            except Exception as e:
                logger.error(f"❌ KB update failed: {e}")
        
        try:
            self.db.commit()
            logger.info(f"✅ Created {len(kb_updates)} new FAQs for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"❌ Failed to save KB updates: {e}")
            self.db.rollback()
        
        return kb_updates
    
    def _clean_user_message(self, message: str) -> str:
        """Clean user message to create proper FAQ question"""
        # Remove personal information
        cleaned = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD NUMBER]', message)
        cleaned = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', cleaned)
        cleaned = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', cleaned)
        
        # Capitalize first letter
        cleaned = cleaned.strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        
        # Add question mark if not present
        if not cleaned.endswith('?'):
            cleaned += '?'
        
        return cleaned
    
    def _record_training_metrics(self, tenant_id: int, patterns_learned: int, improvements_made: int):
        """Record training cycle metrics"""
        try:
            metrics = TrainingMetrics(
                tenant_id=tenant_id,
                patterns_learned=patterns_learned,
                responses_improved=improvements_made,
                processing_time_seconds=0.0  # Could be calculated if needed
            )
            
            self.db.add(metrics)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ Failed to record metrics: {e}")
            self.db.rollback()
    
    def get_training_status(self, tenant_id: int = None) -> Dict:
        """Get current training status and metrics"""
        try:
            if tenant_id:
                # Tenant-specific metrics
                latest_metrics = self.db.query(TrainingMetrics).filter(
                    TrainingMetrics.tenant_id == tenant_id
                ).order_by(desc(TrainingMetrics.training_cycle)).first()
                
                total_patterns = self.db.query(LearningPattern).filter(
                    LearningPattern.tenant_id == tenant_id,
                    LearningPattern.is_active == True
                ).count()
                
                total_improvements = self.db.query(AutoImprovement).filter(
                    AutoImprovement.tenant_id == tenant_id,
                    AutoImprovement.is_active == True
                ).count()
                
                return {
                    'tenant_id': tenant_id,
                    'is_running': self.is_running,
                    'latest_training': latest_metrics.training_cycle.isoformat() if latest_metrics else None,
                    'total_patterns_learned': total_patterns,
                    'total_improvements_made': total_improvements,
                    'patterns_last_cycle': latest_metrics.patterns_learned if latest_metrics else 0,
                    'improvements_last_cycle': latest_metrics.responses_improved if latest_metrics else 0
                }
            else:
                # Global metrics
                total_tenants = self.db.query(Tenant).filter(Tenant.is_active == True).count()
                total_patterns = self.db.query(LearningPattern).filter(LearningPattern.is_active == True).count()
                total_improvements = self.db.query(AutoImprovement).filter(AutoImprovement.is_active == True).count()
                
                return {
                    'is_running': self.is_running,
                    'total_tenants': total_tenants,
                    'total_patterns_learned': total_patterns,
                    'total_improvements_made': total_improvements,
                    'training_interval_minutes': self.training_interval // 60
                }
        
        except Exception as e:
            logger.error(f"❌ Failed to get training status: {e}")
            return {'error': str(e)}





    async def _enhanced_conversation_analysis(self, tenant_id: int, conversations: List[Dict]) -> List[Dict]:
        """Enhanced analysis using semantic and confidence analysis"""
        enhanced_failures = []
        
        for conv in conversations:
            try:
                # Semantic analysis
                messages = conv.get('conversation', [])
                sentiment_analysis = self.semantic_analyzer.analyze_sentiment_progression(messages)
                
                # Check each user message for confusion
                confusion_signals = []
                for msg in messages:
                    if msg.get('is_user', True):
                        confusion = self.semantic_analyzer.detect_confusion_signals(msg['content'])
                        if confusion['confusion_detected']:
                            confusion_signals.append(confusion)
                
                # Store conversation analysis
                self._store_conversation_analysis(tenant_id, conv, sentiment_analysis, confusion_signals)
                
                # Flag as failure if semantic indicators present
                if sentiment_analysis.get('failure_detected') or confusion_signals:
                    enhanced_failures.append({
                        **conv,
                        'semantic_failure': True,
                        'sentiment_trend': sentiment_analysis['trend'],
                        'confusion_count': len(confusion_signals)
                    })
                    
            except Exception as e:
                logger.error(f"❌ Enhanced analysis failed: {e}")
        
        return enhanced_failures

    async def _analyze_response_confidence(self, tenant_id: int):
        """Analyze bot response confidence and flag improvements"""
        cutoff_time = datetime.utcnow() - timedelta(hours=2)
        
        # Get recent bot responses through ChatSession relationship
        recent_messages = self.db.query(ChatMessage).join(ChatSession).filter(
            ChatSession.tenant_id == tenant_id,  # Use session's tenant_id
            ChatMessage.is_from_user == False,
            ChatMessage.created_at >= cutoff_time
        ).all()
        
        low_confidence_responses = []
        
        for message in recent_messages:
            try:
                # Get corresponding user message
                user_message = self.db.query(ChatMessage).filter(
                    ChatMessage.session_id == message.session_id,
                    ChatMessage.is_from_user == True,
                    ChatMessage.created_at < message.created_at
                ).order_by(desc(ChatMessage.created_at)).first()
                
                if not user_message:
                    continue
                
                # Get session to get tenant_id
                session = self.db.query(ChatSession).filter(
                    ChatSession.id == message.session_id
                ).first()
                
                if not session or session.tenant_id != tenant_id:
                    continue
                
                # Analyze confidence
                confidence_analysis = self.confidence_analyzer.score_response_confidence(
                    message.content, 
                    user_message.content
                )
                
                # Store confidence analysis
                self._store_response_confidence(session.tenant_id, message, confidence_analysis)
                
                # Flag for improvement if low confidence
                if confidence_analysis['needs_improvement']:
                    improved_response = await self.confidence_analyzer.generate_improved_response(
                        message.content, user_message.content, confidence_analysis
                    )
                    
                    # Update stored confidence record with improvement
                    self._update_confidence_with_improvement(
                        session.tenant_id, message.id, improved_response
                    )
                    
                    low_confidence_responses.append({
                        'original_response': message.content,
                        'improved_response': improved_response,
                        'confidence_score': confidence_analysis['confidence_score'],
                        'user_message': user_message.content
                    })
            
            except Exception as e:
                logger.error(f"❌ Confidence analysis failed: {e}")
        
        return low_confidence_responses

    def _store_conversation_analysis(self, tenant_id: int, conversation: Dict, sentiment_analysis: Dict, confusion_signals: List):
        """Store conversation semantic analysis"""
        try:
            analysis = ConversationAnalysis(
                tenant_id=tenant_id,
                session_id=conversation.get('session_id', ''),
                sentiment_score=sentiment_analysis.get('final_sentiment', 0),
                confusion_detected=len(confusion_signals) > 0,
                satisfaction_level='negative' if sentiment_analysis.get('failure_detected') else 'neutral',
                confidence_signals={
                    'sentiment_trend': sentiment_analysis.get('trend', 0),
                    'confusion_patterns': confusion_signals
                }
            )
            
            self.db.add(analysis)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ Failed to store conversation analysis: {e}")
            self.db.rollback()

    def _store_response_confidence(self, tenant_id: int, message, confidence_analysis: Dict):
        """Store response confidence analysis"""
        try:
            confidence_record = ResponseConfidence(
                tenant_id=tenant_id,
                session_id=message.session_id,
                message_id=message.id,
                bot_response=message.content,
                confidence_score=confidence_analysis['confidence_score'],
                uncertainty_reasons=confidence_analysis.get('factors', []),
                needs_improvement=confidence_analysis['needs_improvement']
            )
            
            self.db.add(confidence_record)
            self.db.commit()
            return confidence_record.id
            
        except Exception as e:
            logger.error(f"❌ Failed to store confidence analysis: {e}")
            self.db.rollback()
            return None

    def _update_confidence_with_improvement(self, tenant_id: int, message_id: int, improved_response: str):
        """Update confidence record with improved response"""
        try:
            confidence_record = self.db.query(ResponseConfidence).filter(
                ResponseConfidence.message_id == message_id,
                ResponseConfidence.tenant_id == tenant_id
            ).first()
            
            if confidence_record:
                confidence_record.improved_response = improved_response
                confidence_record.improvement_applied = True
                self.db.commit()
                
        except Exception as e:
            logger.error(f"❌ Failed to update confidence record: {e}")
            self.db.rollback()

    async def _train_tenant(self, tenant: Tenant) -> Tuple[int, int]:
        """Enhanced tenant training with semantic and confidence analysis"""
        logger.info(f"🎯 Enhanced training for tenant: {tenant.name} (ID: {tenant.id})")
        
        patterns_learned = 0
        improvements_made = 0
        
        try:
            # 1. Get conversations
            failed_conversations = self._get_failed_conversations(tenant.id)
            successful_conversations = self._get_successful_conversations(tenant.id)
            
            # 2. Enhanced semantic analysis
            semantic_failures = await self._enhanced_conversation_analysis(tenant.id, failed_conversations + successful_conversations)
            failed_conversations.extend(semantic_failures)
            
            # 3. Confidence analysis
            low_confidence_responses = await self._analyze_response_confidence(tenant.id)
            improvements_made += len(low_confidence_responses)
            
            # 4. Original learning process
            failure_patterns = await self._learn_from_failures(tenant.id, failed_conversations)
            patterns_learned += len(failure_patterns)
            
            success_patterns = await self._learn_from_successes(tenant.id, successful_conversations)
            patterns_learned += len(success_patterns)
            
            # 5. Auto-improve responses
            improvements = await self._auto_improve_responses(tenant.id, failure_patterns)
            improvements_made += len(improvements)
            
            # 6. Update knowledge base
            kb_updates = await self._update_knowledge_base(tenant.id, failure_patterns, success_patterns)
            improvements_made += len(kb_updates)
            
            # 7. Record metrics
            self._record_training_metrics(tenant.id, patterns_learned, improvements_made)
            
            logger.info(f"✅ Enhanced training complete for tenant {tenant.id}: {patterns_learned} patterns, {improvements_made} improvements")
            
        except Exception as e:
            logger.error(f"❌ Enhanced training failed for tenant {tenant.id}: {e}")
        
        return patterns_learned, improvements_made




class SemanticAnalyzer:
    """Analyzes conversation semantics and sentiment"""
    
    def __init__(self, llm=None):
        self.llm = llm
        self.confusion_patterns = [
            "i don't understand", "what do you mean", "that's not right",
            "that doesn't help", "i'm confused", "what?", "huh?",
            "that's not what i asked", "you're not listening"
        ]
        self.satisfaction_positive = ["thanks", "perfect", "great", "exactly", "solved"]
        self.satisfaction_negative = ["never mind", "forget it", "useless", "waste of time"]
    
    def analyze_sentiment_progression(self, messages: List[Dict]) -> Dict:
        """Track sentiment changes throughout conversation"""
        sentiments = []
        
        for msg in messages:
            if msg.get('is_user', True):
                sentiment = self._calculate_sentiment(msg['content'])
                sentiments.append(sentiment)
        
        if len(sentiments) < 2:
            return {'progression': 'insufficient_data', 'trend': 0}
        
        # Calculate trend: positive slope = improving, negative = deteriorating
        trend = (sentiments[-1] - sentiments[0]) / len(sentiments)
        
        return {
            'progression': sentiments,
            'trend': trend,
            'final_sentiment': sentiments[-1],
            'failure_detected': trend < -0.3 and sentiments[-1] < -0.2
        }
    
    def detect_confusion_signals(self, user_message: str) -> Dict:
        """Detect confusion indicators in user message"""
        message_lower = user_message.lower()
        
        confusion_found = []
        for pattern in self.confusion_patterns:
            if pattern in message_lower:
                confusion_found.append(pattern)
        
        # Additional signals
        question_marks = user_message.count('?')
        repeated_words = len(user_message.split()) != len(set(user_message.split()))
        
        return {
            'confusion_detected': len(confusion_found) > 0,
            'confusion_patterns': confusion_found,
            'excessive_questions': question_marks > 2,
            'repeated_words': repeated_words,
            'confidence_score': max(0, 1 - (len(confusion_found) * 0.3))
        }
    
    def extract_satisfaction_indicators(self, message: str) -> str:
        """Extract satisfaction level from message"""
        message_lower = message.lower()
        
        positive_count = sum(1 for word in self.satisfaction_positive if word in message_lower)
        negative_count = sum(1 for word in self.satisfaction_negative if word in message_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _calculate_sentiment(self, text: str) -> float:
        """Simple sentiment calculation (-1 to 1)"""
        positive_words = ['good', 'great', 'thanks', 'perfect', 'helpful', 'solved', 'yes']
        negative_words = ['bad', 'terrible', 'useless', 'wrong', 'no', 'not', 'can\'t', 'won\'t']
        
        words = text.lower().split()
        positive_score = sum(1 for word in words if word in positive_words)
        negative_score = sum(1 for word in words if word in negative_words)
        
        total_words = len(words)
        if total_words == 0:
            return 0
        
        return (positive_score - negative_score) / total_words

class ConfidenceAnalyzer:
    """Analyzes and scores bot response confidence"""
    
    def __init__(self, llm=None):
        self.llm = llm
        self.uncertainty_phrases = [
            "i think", "maybe", "possibly", "i'm not sure", "let me check",
            "it might be", "probably", "i believe", "it could be"
        ]
    
    def score_response_confidence(self, response: str, user_message: str, context: Dict = None) -> Dict:
        """Score confidence of bot response"""
        confidence_factors = []
        
        # 1. Check for uncertainty phrases
        uncertainty_count = sum(1 for phrase in self.uncertainty_phrases if phrase in response.lower())
        uncertainty_penalty = min(uncertainty_count * 0.2, 0.6)
        confidence_factors.append(('uncertainty_phrases', 1 - uncertainty_penalty))
        
        # 2. Response length appropriateness
        response_length = len(response.split())
        if response_length < 5:
            confidence_factors.append(('too_short', 0.5))
        elif response_length > 100:
            confidence_factors.append(('too_long', 0.8))
        else:
            confidence_factors.append(('length_appropriate', 1.0))
        
        # 3. Specificity check
        generic_responses = ['i can help', 'let me assist', 'i understand', 'thank you for']
        is_generic = any(phrase in response.lower() for phrase in generic_responses)
        confidence_factors.append(('specificity', 0.6 if is_generic else 0.9))
        
        # 4. Question answering completeness
        user_questions = user_message.count('?')
        if user_questions > 0 and '?' not in response:
            confidence_factors.append(('answers_questions', 0.7))
        else:
            confidence_factors.append(('answers_questions', 1.0))
        
        # Calculate overall confidence
        weights = [factor[1] for factor in confidence_factors]
        overall_confidence = sum(weights) / len(weights)
        
        return {
            'confidence_score': round(overall_confidence, 2),
            'factors': confidence_factors,
            'needs_improvement': overall_confidence < 0.7,
            'uncertainty_detected': uncertainty_count > 0
        }
    
    async def generate_improved_response(self, original_response: str, user_message: str, confidence_analysis: Dict) -> str:
        """Generate improved response for low-confidence cases"""
        if not self.llm:
            return original_response
        
        prompt = f"""
Improve this bot response to be more confident and helpful:

USER: "{user_message}"
BOT: "{original_response}"

ISSUES: {confidence_analysis.get('factors', [])}

Generate a more confident, specific, and helpful response:
"""
        
        try:
            result = self.llm.invoke(prompt)
            return result.content.strip()
        except:
            return original_response

class ProactiveLearner:
    """Handles A/B testing and proactive improvements"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def should_ab_test(self, user_pattern: str, tenant_id: int) -> bool:
        """Determine if pattern should be A/B tested"""
        # Check if already being tested
        existing_test = self.db.query(ProactiveLearning).filter(
            ProactiveLearning.tenant_id == tenant_id,
            ProactiveLearning.pattern_trigger.contains(user_pattern[:30]),
            ProactiveLearning.test_status == 'active'
        ).first()
        
        return existing_test is None
    
    def create_ab_test(self, tenant_id: int, pattern: str, response_a: str, response_b: str):
        """Create new A/B test"""
        ab_test = ProactiveLearning(
            tenant_id=tenant_id,
            pattern_trigger=pattern,
            response_a=response_a,
            response_b=response_b
        )
        
        self.db.add(ab_test)
        self.db.commit()
        return ab_test
    
    def record_ab_result(self, test_id: int, variant: str, success: bool):
        """Record A/B test result"""
        test = self.db.query(ProactiveLearning).filter(ProactiveLearning.id == test_id).first()
        if not test:
            return
        
        if variant == 'a':
            if success:
                test.a_success_count += 1
            else:
                test.a_failure_count += 1
        else:
            if success:
                test.b_success_count += 1
            else:
                test.b_failure_count += 1
        
        # Check if test should conclude
        total_tests = test.a_success_count + test.a_failure_count + test.b_success_count + test.b_failure_count
        if total_tests >= 20:  # Minimum sample size
            self._conclude_ab_test(test)
        
        self.db.commit()
    
    def _conclude_ab_test(self, test: ProactiveLearning):
        """Conclude A/B test and select winner"""
        a_success_rate = test.a_success_count / max(test.a_success_count + test.a_failure_count, 1)
        b_success_rate = test.b_success_count / max(test.b_success_count + test.b_failure_count, 1)
        
        if b_success_rate > a_success_rate * 1.1:  # B needs to be 10% better
            test.winner_response = test.response_b
        else:
            test.winner_response = test.response_a
        
        test.test_status = 'completed'
        test.completed_at = datetime.utcnow()



# Global trainer instance
_global_trainer = None

def get_background_trainer() -> BackgroundTrainer:
    """Get the global background trainer instance"""
    global _global_trainer
    if _global_trainer is None:
        _global_trainer = BackgroundTrainer()
    return _global_trainer

async def start_background_training():
    """Start background training - called from main.py startup"""
    trainer = get_background_trainer()
    await trainer.start_continuous_learning()

def stop_background_training():
    """Stop background training"""
    global _global_trainer
    if _global_trainer:
        _global_trainer.stop_learning()