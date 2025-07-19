import  json
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.knowledge_base.models import TenantIntentPattern, CentralIntentModel
from app.config import settings

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class EnhancedIntentClassifier:
    """Two-tier intent classification: Tenant-specific → Central patterns"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.2,
                openai_api_key=settings.OPENAI_API_KEY
            )
    
    def classify_intent(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """Two-tier classification: tenant-specific first, then central"""
        logger.info(f"🎯 ENHANCED CLASSIFIER CALLED: '{user_message[:30]}...' for tenant {tenant_id}")
        try:
            # TIER 1: Check tenant-specific patterns first
            tenant_result = self._classify_tenant_specific(user_message, tenant_id)
            if tenant_result['confidence'] > 0.7:
                logger.info(f"🎯 Tenant-specific match: {tenant_result['intent']} (confidence: {tenant_result['confidence']})")
                return tenant_result
            
            # TIER 2: Fallback to central classification
            central_result = self._classify_central(user_message)
            
            # Return best result
            if tenant_result['confidence'] > central_result['confidence']:
                return tenant_result
            else:
                return central_result
                
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return {"intent": "general", "confidence": 0.3, "source": "error_fallback"}
        




    
    def _classify_tenant_specific(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """LLM-powered semantic pattern matching"""
        try:
            # Get tenant patterns
            patterns = self.db.query(TenantIntentPattern).filter(
                TenantIntentPattern.tenant_id == tenant_id,
                TenantIntentPattern.is_active == True
            ).all()
            
            logger.info(f"🔍 Found {len(patterns)} tenant patterns for semantic analysis")
            
            if not patterns:
                logger.warning(f"⚠️ No tenant-specific patterns found for tenant {tenant_id}")
                return {"intent": "general", "confidence": 0.0, "source": "no_tenant_patterns"}
            
            # Use LLM for semantic matching
            return self._semantic_pattern_matching(user_message, patterns)
            
        except Exception as e:
            logger.error(f"Tenant semantic classification error: {e}")
            return {"intent": "general", "confidence": 0.0, "source": "tenant_error"}

    def _semantic_pattern_matching(self, user_message: str, patterns: List) -> Dict[str, Any]:
        """Use LLM to semantically match user message against extracted patterns"""
        try:
            if not self.llm_available:
                logger.warning("🤖 LLM not available, falling back to basic matching")
                return self._fallback_pattern_matching(user_message, patterns)
            
            # Prepare pattern data for LLM
            pattern_data = []
            for pattern in patterns:
                pattern_info = {
                    "pattern_id": pattern.id,
                    "document_id": pattern.document_id,
                    "intent_type": pattern.intent_type,
                    "confidence": pattern.confidence,
                    "extracted_patterns": pattern.pattern_data
                }
                pattern_data.append(pattern_info)
            
            # Create semantic matching prompt
            prompt = f"""Analyze this user message and determine which document pattern best matches their intent semantically.

    USER MESSAGE: "{user_message}"

    AVAILABLE DOCUMENT PATTERNS:
    {json.dumps(pattern_data, indent=2)}

    TASK:
    1. Understand the semantic meaning and intent behind the user's message
    2. Match it against the available document patterns based on meaning, not exact keywords
    3. Consider synonyms, different phrasings, and contextual understanding
    4. Determine the best matching document and confidence level

    EXAMPLES OF SEMANTIC MATCHING:
    - "card getting declined" matches "payment troubleshooting" patterns
    - "billing issue" matches "payment problems" patterns  
    - "how much does it cost" matches "pricing information" patterns
    - "contact hours" matches "support FAQ" patterns

    RESPONSE FORMAT (JSON only):
    {{
        "best_match_pattern_id": <pattern_id or null>,
        "document_id": <document_id or null>,
        "intent": "<intent_type>",
        "confidence": 0.0-1.0,
        "reasoning": "Brief explanation of semantic match",
        "semantic_match": true/false
    }}

    Respond with JSON only:"""

            logger.info(f"🤖 Sending semantic analysis request for: '{user_message[:50]}...'")
            
            # Get LLM response
            result = self.llm.invoke(prompt)
            response_text = result.content.strip()
            
            logger.info(f"🤖 LLM response: {response_text[:200]}...")
            
            # Parse JSON response
            try:
                # Extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_data = json.loads(json_match.group())
                else:
                    response_data = json.loads(response_text)
                
                # Validate response
                if self._validate_semantic_response(response_data):
                    confidence = response_data.get("confidence", 0.0)
                    
                    # Lower threshold for semantic matching since LLM is more intelligent
                    if response_data.get("best_match_pattern_id") and confidence > 0.6:
                        logger.info(f"✅ Semantic match found: {response_data['intent']} (confidence: {confidence:.2f})")
                        logger.info(f"💡 Reasoning: {response_data.get('reasoning', 'N/A')}")
                        
                        return {
                            "intent": response_data["intent"],
                            "confidence": confidence,
                            "source": "tenant_specific_semantic",
                            "document_id": response_data["document_id"],
                            "pattern_id": response_data["best_match_pattern_id"],
                            "reasoning": response_data.get("reasoning"),
                            "semantic_match": True
                        }
                    else:
                        logger.info(f"❌ Semantic analysis found no strong match (confidence: {confidence:.2f})")
                        return {"intent": "general", "confidence": 0.0, "source": "semantic_no_match"}
                else:
                    logger.error("❌ Invalid semantic response format")
                    return self._fallback_pattern_matching(user_message, patterns)
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON parsing failed: {e}")
                logger.error(f"Raw response: {response_text}")
                return self._fallback_pattern_matching(user_message, patterns)
                
        except Exception as e:
            logger.error(f"❌ Semantic matching error: {e}")
            return self._fallback_pattern_matching(user_message, patterns)

    def _validate_semantic_response(self, response_data: Dict) -> bool:
        """Validate LLM semantic response format"""
        required_fields = ["intent", "confidence"]
        return all(field in response_data for field in required_fields)

    def _fallback_pattern_matching(self, user_message: str, patterns: List) -> Dict[str, Any]:
        """Fallback to original pattern matching if LLM fails"""
        logger.info("🔄 Using fallback pattern matching")
        
        # Use the original scoring logic as fallback
        user_lower = user_message.lower()
        best_match = None
        best_score = 0.0
        
        for pattern in patterns:
            score = self._score_pattern_match(user_lower, pattern.pattern_data)
            if score > best_score:
                best_score = score
                best_match = pattern
        
        # Lower threshold for fallback
        if best_match and best_score > 0.4:
            return {
                "intent": best_match.intent_type,
                "confidence": min(best_score, 0.8),
                "source": "tenant_specific_fallback",
                "document_id": best_match.document_id,
                "pattern_id": best_match.id
            }
        
        return {"intent": "general", "confidence": 0.0, "source": "fallback_no_match"}
            




    
    def _score_pattern_match(self, user_message: str, pattern_data: Dict) -> float:
        """Score how well user message matches a pattern"""
        try:
            score = 0.0
            total_weight = 0.0
            
            # Keyword matching (weight: 0.3)
            keywords = pattern_data.get('keywords', [])
            if keywords:
                keyword_score = sum(1 for kw in keywords if kw.lower() in user_message) / len(keywords)
                score += keyword_score * 0.3
                total_weight += 0.3
            
            # Question pattern matching (weight: 0.25)
            question_patterns = pattern_data.get('question_patterns', [])
            if question_patterns:
                question_score = self._pattern_similarity(user_message, question_patterns)
                score += question_score * 0.25
                total_weight += 0.25
            
            # Problem pattern matching (weight: 0.35)
            problem_patterns = pattern_data.get('problem_patterns', [])
            if problem_patterns:
                problem_score = self._pattern_similarity(user_message, problem_patterns)
                score += problem_score * 0.35
                total_weight += 0.35
            
            # Trigger phrase matching (weight: 0.1)
            trigger_phrases = pattern_data.get('trigger_phrases', [])
            if trigger_phrases:
                trigger_score = sum(1 for phrase in trigger_phrases if phrase.lower() in user_message) / len(trigger_phrases)
                score += trigger_score * 0.1
                total_weight += 0.1
            
            return score / total_weight if total_weight > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Pattern scoring error: {e}")
            return 0.0
    
    def _pattern_similarity(self, user_message: str, patterns: List[str]) -> float:
        """Calculate similarity between user message and pattern templates"""
        try:
            # Simple similarity based on common words
            user_words = set(user_message.lower().split())
            best_similarity = 0.0
            
            for pattern in patterns:
                pattern_words = set(pattern.lower().split())
                common_words = user_words.intersection(pattern_words)
                similarity = len(common_words) / max(len(pattern_words), 1)
                best_similarity = max(best_similarity, similarity)
            
            return best_similarity
            
        except Exception as e:
            logger.error(f"Pattern similarity error: {e}")
            return 0.0
    
    def _classify_central(self, user_message: str) -> Dict[str, Any]:
        """Classify using central trained model"""
        if not self.llm_available:
            return {"intent": "general", "confidence": 0.5, "source": "central_fallback"}
        
        try:
            # Get active central model
            central_model = self.db.query(CentralIntentModel).filter(
                CentralIntentModel.is_active == True
            ).order_by(CentralIntentModel.trained_at.desc()).first()
            
            if not central_model:
                return self._basic_intent_classification(user_message)
            
            # Use central model for classification
            training_data = central_model.training_data
            
            prompt = PromptTemplate(
                input_variables=["message", "patterns"],
                template="""Classify user intent using trained patterns.

User Message: "{message}"

Trained Patterns:
{patterns}

Intent Categories:
- troubleshooting: User has a problem/issue that needs solving
- sales: User interested in purchasing/pricing/plans
- enquiry: User wants information about features/capabilities
- faq: User asking basic questions about company/service
- general: Casual conversation or unclear intent

Response: intent_type (confidence: 0.0-1.0)

Classification:"""
            )
            
            result = self.llm.invoke(prompt.format(
                message=user_message,
                patterns=str(training_data)[:2000]  # Limit size
            ))
            
            # Parse result
            response = result.content.strip()
            if '(' in response:
                intent = response.split('(')[0].strip()
                confidence_str = response.split('confidence: ')[1].split(')')[0] if 'confidence:' in response else '0.7'
                try:
                    confidence = float(confidence_str)
                except:
                    confidence = 0.7
            else:
                intent = response.strip()
                confidence = 0.7
            
            return {
                "intent": intent,
                "confidence": min(confidence, 0.9),  # Cap central confidence
                "source": "central_model",
                "model_version": central_model.model_version
            }
            
        except Exception as e:
            logger.error(f"Central classification error: {e}")
            return self._basic_intent_classification(user_message)
    
    def _basic_intent_classification(self, user_message: str) -> Dict[str, Any]:
        """Fallback basic classification"""
        user_lower = user_message.lower()
        
        # Simple keyword-based classification
        if any(word in user_lower for word in ['problem', 'issue', 'error', 'not working', 'broken', 'help']):
            return {"intent": "troubleshooting", "confidence": 0.6, "source": "basic_keywords"}
        elif any(word in user_lower for word in ['price', 'cost', 'buy', 'purchase', 'plan', 'upgrade']):
            return {"intent": "sales", "confidence": 0.6, "source": "basic_keywords"}
        elif any(word in user_lower for word in ['how', 'what', 'can', 'does', 'features']):
            return {"intent": "enquiry", "confidence": 0.6, "source": "basic_keywords"}
        else:
            return {"intent": "general", "confidence": 0.5, "source": "basic_fallback"}

def get_enhanced_intent_classifier(db: Session) -> EnhancedIntentClassifier:
    """Factory function"""
    return EnhancedIntentClassifier(db)