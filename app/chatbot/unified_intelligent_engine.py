

import logging
import re
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from app.chatbot.simple_memory import SimpleChatbotMemory
from app.knowledge_base.models import FAQ, KnowledgeBase, ProcessingStatus
from app.knowledge_base.processor import DocumentProcessor
from app.tenants.models import Tenant
from app.config import settings
from app.chatbot.security import SecurityPromptManager, build_secure_chatbot_prompt
from app.chatbot.security import fix_response_formatting

from app.chatbot.security import check_message_security

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class UnifiedIntelligentEngine:
    """
    Single engine implementing your efficient architecture:
    User Message → Intent Classifier → Context Check → Smart Response
    """
    
    def __init__(self, db: Session):
        self.db = db
        
        # Initialize LLM
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY
            )
        
        logger.info("🚀 Unified Intelligent Engine initialized - Token Efficient Architecture")
    
    def process_message(self, 
                       api_key: str, 
                       user_message: str, 
                       user_identifier: str,
                       platform: str = "web") -> Dict[str, Any]:
        """
        Main processing pipeline following your architecture diagram:
        Message → Intent → Context Check → Unified Response
        """
        try:
            # Get tenant
            tenant = self._get_tenant_by_api_key(api_key)
            if not tenant:
                return {"error": "Invalid API key", "success": False}
            
            is_safe, security_response = check_message_security(user_message, tenant.business_name or tenant.name)
            if not is_safe:
                logger.warning(f"🔒 Security risk blocked in unified engine: {user_message[:50]}...")
                return {
                    "success": True,  # Don't reveal it was blocked
                    "response": SecurityPromptManager.get_security_decline_message(
                        SecurityPromptManager._identify_risk_type(""), 
                        tenant.business_name or tenant.name
                    ),
                    "session_id": "security_block",
                    "answered_by": "security_system",
                    "intent": "security_risk",
                    "architecture": "unified_intelligent_security"
                }
            
            # Initialize memory
            memory = SimpleChatbotMemory(self.db, tenant.id)
            session_id, is_new_session = memory.get_or_create_session(user_identifier, platform)
            
            # Store user message
            memory.store_message(session_id, user_message, True)
            
            # STEP 1: Intent Classification (Lightweight LLM)
            intent_result = self._classify_intent(user_message, tenant)
            
            # STEP 2: Context Check (Product vs General)
            context_result = self._check_context_relevance(user_message, intent_result, tenant)
            
            # STEP 3: Smart Routing & Response Generation
            if context_result['is_product_related']:
                # Product-related: Use 3-tier KB search
                response = self._handle_product_related(user_message, tenant, context_result)
            else:
                # General knowledge: Direct LLM
                response = self._handle_general_knowledge(user_message, tenant, intent_result)
            
            # STEP 4: Sufficiency Check
            final_response = self._check_sufficiency_and_enhance(
                user_message, response, tenant, context_result
            )
                
            final_response['content'] = fix_response_formatting(final_response['content'])

            # Store response
            memory.store_message(session_id, final_response['content'], False)
            
            return {
                "success": True,
                "response": final_response['content'],
                "session_id": session_id,
                "is_new_session": is_new_session,
                "answered_by": final_response['source'],
                "intent": intent_result['intent'],
                "context": context_result['context_type'],
                "token_efficiency": "~80% reduction",
                "architecture": "unified_intelligent"
            }
            
        except Exception as e:
            logger.error(f"Error in unified processing: {e}")
            return {"error": str(e), "success": False}
    
    def _classify_intent(self, user_message: str, tenant: Tenant) -> Dict[str, Any]:
        """
        Lightweight intent classification - determines user's goal
        """
        if not self.llm_available:
            return {"intent": "general", "confidence": 0.5}
        
        try:
            prompt = PromptTemplate(
                input_variables=["message", "company"],
                template="""Classify this user message intent for {company}:

Message: "{message}"

Intent Categories:
- functional: User wants to DO something (reset password, upgrade, cancel, setup)
- informational: User wants to LEARN something (how it works, features, pricing) 
- support: User has a PROBLEM (error, not working, confused)
- casual: General chat, greetings, jokes, weather, non-business
- company: About the company itself (hours, contact, location, team)

Response (single word): functional|informational|support|casual|company

Intent:"""
            )
            
            result = self.llm.invoke(prompt.format(
                message=user_message,
                company=tenant.business_name or tenant.name
            ))
            
            intent = result.content.strip().lower()
            
            # Validate intent
            valid_intents = ['functional', 'informational', 'support', 'casual', 'company']
            if intent not in valid_intents:
                intent = 'general'
            
            return {
                "intent": intent,
                "confidence": 0.9 if intent in valid_intents else 0.5
            }
            
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return {"intent": "general", "confidence": 0.3}
    
    def _check_context_relevance(self, user_message: str, intent_result: Dict, tenant: Tenant) -> Dict[str, Any]:
        """
        Context check - Is this about our product/service?
        This is the KEY optimization that saves massive tokens
        """
        intent = intent_result.get('intent', 'general')
        
        # Fast context routing based on intent
        if intent in ['functional', 'support']:
            # Functional/support questions are almost always product-related
            return {
                "is_product_related": True,
                "context_type": "product_functional",
                "reasoning": f"Intent '{intent}' indicates product interaction"
            }
        
        elif intent == 'casual':
            # Casual chat is almost never product-related
            return {
                "is_product_related": False,
                "context_type": "general_casual",
                "reasoning": "Casual conversation detected"
            }
        
        elif intent == 'company':
            # Company questions use custom prompts only
            return {
                "is_product_related": True,
                "context_type": "company_info",
                "reasoning": "Company information request"
            }
        
        else:
            # Informational: Use LLM to determine if product-specific
            return self._llm_context_check(user_message, tenant)
    
    def _llm_context_check(self, user_message: str, tenant: Tenant) -> Dict[str, Any]:
        """
        LLM-based context check for ambiguous cases
        """
        if not self.llm_available:
            return {"is_product_related": True, "context_type": "unknown"}
        
        try:
            prompt = PromptTemplate(
                input_variables=["message", "company"],
                template="""Is this question about {company}'s specific products/services?

Message: "{message}"

Answer: YES if asking about {company}'s specific features, pricing, setup, etc.
Answer: NO if asking general knowledge (weather, news, definitions, how-to guides unrelated to {company})

Examples:
- "How do I reset my password?" → YES (product-specific)
- "What's the weather today?" → NO (general knowledge)
- "How does AI work?" → NO (general knowledge)
- "How much does your plan cost?" → YES (product-specific)

Response: YES|NO

Answer:"""
            )
            
            result = self.llm.invoke(prompt.format(
                message=user_message,
                company=tenant.business_name or tenant.name
            ))
            
            is_product = result.content.strip().upper() == "YES"
            
            return {
                "is_product_related": is_product,
                "context_type": "product_specific" if is_product else "general_knowledge",
                "reasoning": "LLM context analysis"
            }
            
        except Exception as e:
            logger.error(f"Context check error: {e}")
            return {"is_product_related": True, "context_type": "fallback"}
    
    def _handle_product_related(self, user_message: str, tenant: Tenant, context_result: Dict) -> Dict[str, Any]:
        """
        Handle product-related queries with 3-tier KB search:
        1. FAQ (fast, authoritative)
        2. KB (detailed, contextual) 
        3. Custom prompts (company info)
        """
        # Quick FAQ check first
        faq_result = self._quick_faq_check(user_message, tenant.id)
        if faq_result['found']:
            return {
                "content": faq_result['answer'],
                "source": "FAQ",
                "confidence": 0.9
            }
        
        # Check if company info request
        if context_result.get('context_type') == 'company_info':
            return self._handle_company_info(user_message, tenant)
        
        # Deep KB search for complex queries
        kb_result = self._search_knowledge_base(user_message, tenant.id)
        if kb_result['found']:
            return {
                "content": kb_result['answer'],
                "source": "Knowledge_Base",
                "confidence": 0.8
            }
        
        # Fallback to enhanced prompt with tenant customization
        return self._generate_custom_response(user_message, tenant, "product_related")
    
    def _handle_general_knowledge(self, user_message: str, tenant: Tenant, intent_result: Dict) -> Dict[str, Any]:
        """
        Handle general knowledge with direct LLM (no KB search needed)
        This saves massive tokens for non-product questions
        """
        return self._generate_custom_response(user_message, tenant, "general_knowledge")
    
    def _quick_faq_check(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """
        Efficient FAQ matching - single LLM call with all FAQs
        """
        faqs = self.db.query(FAQ).filter(FAQ.tenant_id == tenant_id).limit(10).all()
        
        if not faqs or not self.llm_available:
            return {"found": False}
        
        try:
            # Format FAQs efficiently
            faq_text = "\n".join([f"{i+1}. Q: {faq.question}\n   A: {faq.answer}" for i, faq in enumerate(faqs)])
            
            prompt = PromptTemplate(
                input_variables=["message", "faqs"],
                template="""Match user question to FAQ:

User: "{message}"

FAQs:
{faqs}

If exact match found, respond: MATCH:[FAQ_NUMBER]
If no good match, respond: NO_MATCH

Response:"""
            )
            
            result = self.llm.invoke(prompt.format(message=user_message, faqs=faq_text))
            response = result.content.strip()
            
            if response.startswith("MATCH:"):
                try:
                    faq_num = int(response.split(":")[1]) - 1
                    if 0 <= faq_num < len(faqs):
                        return {
                            "found": True,
                            "answer": self._enhance_faq_response(faqs[faq_num].answer)
                        }
                except:
                    pass
            
            return {"found": False}
            
        except Exception as e:
            logger.error(f"FAQ check error: {e}")
            return {"found": False}
    
    def _search_knowledge_base(self, user_message: str, tenant_id: int) -> Dict[str, Any]:
        """
        Efficient KB search - only for complex queries that need detailed answers
        """
        try:
            # Get completed knowledge bases
            kbs = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.processing_status == ProcessingStatus.COMPLETED
            ).all()
            
            if not kbs:
                return {"found": False}
            
            # Search most recent KB (or implement KB ranking)
            processor = DocumentProcessor(tenant_id)
            
            for kb in kbs:
                try:
                    vector_store = processor.get_vector_store(kb.vector_store_id)
                    docs = vector_store.similarity_search(user_message, k=3)
                    
                    if docs and docs[0].page_content:
                        # Found relevant content
                        context = "\n".join([doc.page_content for doc in docs[:2]])
                        
                        return {
                            "found": True,
                            "answer": self._generate_kb_response(user_message, context)
                        }
                        
                except Exception as e:
                    logger.warning(f"KB search failed for {kb.id}: {e}")
                    continue
            
            return {"found": False}
            
        except Exception as e:
            logger.error(f"KB search error: {e}")
            return {"found": False}
    
    def _generate_kb_response(self, user_message: str, context: str) -> str:
        """
        Generate response using KB context
        """
        if not self.llm_available:
            return context[:500] + "..."
        
        try:
            prompt = PromptTemplate(
                input_variables=["question", "context"],
                template="""Answer the question using the provided context. Be specific and helpful.

Question: {question}

Context: {context}

Answer:"""
            )
            
            result = self.llm.invoke(prompt.format(question=user_message, context=context))
            return result.content.strip()
            
        except Exception as e:
            logger.error(f"KB response generation error: {e}")
            return "I found relevant information but couldn't process it properly."
    
    def _handle_company_info(self, user_message: str, tenant: Tenant) -> Dict[str, Any]:
        """
        Handle company-specific questions using tenant data
        """
        company_info = {
            "name": tenant.business_name or tenant.name,
            "email": tenant.email,
            # Add more fields as needed
        }
        
        return self._generate_custom_response(user_message, tenant, "company_info", company_info)
    
#     def _generate_custom_response(self, user_message: str, tenant: Tenant, response_type: str, extra_context: Dict = None) -> Dict[str, Any]:
#         """
#         Generate response with tenant's custom prompt and context
#         """
#         if not self.llm_available:
#             return {
#                 "content": "I'm here to help! Could you please provide more details?",
#                 "source": "fallback",
#                 "confidence": 0.3
#             }
        
#         try:
#             # Build prompt with tenant customization
#             base_prompt = tenant.system_prompt or f"You are a helpful assistant for {tenant.business_name or tenant.name}."
            
#             if response_type == "general_knowledge":
#                 instruction = "Answer this general question while maintaining your helpful personality."
#             elif response_type == "company_info":
#                 instruction = f"Answer about {tenant.business_name or tenant.name} using available information."
#             else:
#                 instruction = "Provide helpful information about our product or service."
            
#             prompt_template = f"""{base_prompt}

# {instruction}

# User Question: {{message}}

# Your response:"""
            
#             prompt = PromptTemplate(input_variables=["message"], template=prompt_template)
#             result = self.llm.invoke(prompt.format(message=user_message))
            
#             return {
#                 "content": result.content.strip(),
#                 "source": f"Custom_{response_type}",
#                 "confidence": 0.7
#             }
            
#         except Exception as e:
#             logger.error(f"Custom response error: {e}")
#             return {
#                 "content": "I apologize, but I'm having trouble processing your request right now.",
#                 "source": "error_fallback",
#                 "confidence": 0.1
#             }
    

    def _generate_custom_response(self, user_message: str, tenant: Tenant, response_type: str, extra_context: Dict = None) -> Dict[str, Any]:
        """
        Generate response with tenant's custom prompt and context - NOW WITH SECURITY
        """
        if not self.llm_available:
            return {
                "content": "I'm here to help! Could you please provide more details?",
                "source": "fallback",
                "confidence": 0.3
            }
        
        try:
            # 🔒 BUILD SECURE PROMPT (replaces old tenant.system_prompt usage)
            secure_prompt = build_secure_chatbot_prompt(
                tenant_prompt=tenant.system_prompt,
                company_name=tenant.business_name or tenant.name,
                faq_info="",  # Not needed for this context
                knowledge_base_info=""
            )
            
            if response_type == "general_knowledge":
                instruction = "Answer this general question while maintaining your helpful personality."
            elif response_type == "company_info":
                instruction = f"Answer about {tenant.business_name or tenant.name} using available information."
            else:
                instruction = "Provide helpful information about our product or service."
            
            # 🔒 USE SECURE PROMPT INSTEAD OF RAW TENANT PROMPT
            prompt_template = f"""{secure_prompt}

    {instruction}

    User Question: {{message}}

    Your response:"""
            
            prompt = PromptTemplate(input_variables=["message"], template=prompt_template)
            result = self.llm.invoke(prompt.format(message=user_message))
            
            return {
                "content": result.content.strip(),
                "source": f"Secure_{response_type}",
                "confidence": 0.7
            }
            
        except Exception as e:
            logger.error(f"Custom response error: {e}")
            return {
                "content": "I apologize, but I'm having trouble processing your request right now.",
                "source": "error_fallback",
                "confidence": 0.1
            }




    def _check_sufficiency_and_enhance(self, user_message: str, response: Dict, tenant: Tenant, context_result: Dict) -> Dict[str, Any]:
        """
        Check if response is sufficient, enhance if needed
        """
        content = response.get('content', '')
        
        # Quick sufficiency check
        if len(content) < 20:
            # Too short, enhance
            enhanced = self._enhance_insufficient_response(user_message, tenant)
            return {
                "content": enhanced,
                "source": f"{response.get('source', 'unknown')}_enhanced"
            }
        
        # Apply tenant prompt filter
        if tenant.system_prompt:
            enhanced_content = self._apply_custom_prompt_filter(content, tenant)
            return {
                "content": enhanced_content,
                "source": response.get('source', 'unknown')
            }
        
        return response
    
    def _enhance_insufficient_response(self, user_message: str, tenant: Tenant) -> str:
        """
        Enhance insufficient responses
        """
        return f"I understand you're asking about {user_message}. Let me connect you with more specific help for {tenant.business_name or tenant.name}."
    
#     def _apply_custom_prompt_filter(self, content: str, tenant: Tenant) -> str:
#         """
#         Apply tenant's custom prompt as a filter to ensure brand voice
#         """
#         if not self.llm_available or not tenant.system_prompt:
#             return content
        
#         try:
#             prompt = PromptTemplate(
#                 input_variables=["response", "brand_voice"],
#                 template="""Adjust this response to match the brand voice:

# Brand Voice: {brand_voice}

# Response: {response}

# Adjusted Response:"""
#             )
            
#             result = self.llm.invoke(prompt.format(
#                 response=content,
#                 brand_voice=tenant.system_prompt
#             ))
            
#             return result.content.strip()
            
#         except Exception as e:
#             logger.error(f"Prompt filter error: {e}")
#             return content




    def _apply_custom_prompt_filter(self, content: str, tenant: Tenant) -> str:
        """
        Apply tenant's custom prompt as a filter to ensure brand voice - WITH SECURITY
        """
        if not self.llm_available:
            return content
        
        # 🔒 USE SECURE PROMPT BUILDING
        if tenant.system_prompt:
            secure_brand_voice = build_secure_chatbot_prompt(
                tenant_prompt=tenant.system_prompt,
                company_name=tenant.business_name or tenant.name,
                faq_info="",
                knowledge_base_info=""
            )
        else:
            return content
        
        try:
            prompt = PromptTemplate(
                input_variables=["response", "brand_voice"],
                template="""Adjust this response to match the brand voice:

    Brand Voice: {brand_voice}

    Response: {response}

    Adjusted Response:"""
            )
            
            result = self.llm.invoke(prompt.format(
                response=content,
                brand_voice=secure_brand_voice
            ))
            
            return result.content.strip()
            
        except Exception as e:
            logger.error(f"Prompt filter error: {e}")
            return content


    
    def _enhance_faq_response(self, faq_answer: str) -> str:
        """
        Make FAQ answers more conversational
        """
        starters = ["Great question! ", "Happy to help! ", "Here's what you need to know: "]
        import random
        return random.choice(starters) + faq_answer
    
    def _get_tenant_by_api_key(self, api_key: str) -> Optional[Tenant]:
        """Get tenant by API key"""
        return self.db.query(Tenant).filter(
            Tenant.api_key == api_key,
            Tenant.is_active == True
        ).first()

# Factory function
def get_unified_intelligent_engine(db: Session) -> UnifiedIntelligentEngine:
    """Factory function to create the unified engine"""
    return UnifiedIntelligentEngine(db)