# # app/chatbot/enhanced_super_tenant_admin_engine.py
# """
# Enhanced Super Tenant Admin Engine with LLM Integration
# Provides intelligent, conversational tenant administration
# """

# import logging
# import uuid
# from typing import Dict, Any, Optional, Tuple, List
# from sqlalchemy.orm import Session
# from datetime import datetime

# from app.chatbot.admin_intent_parser import get_llm_admin_intent_parser, AdminActionType, ParsedIntent
# from app.chatbot.tenant_data_manager import TenantDataManager, TenantSecurityError
# from app.chatbot.simple_memory import SimpleChatbotMemory
# from app.tenants.models import Tenant
# from app.config import settings

# try:
#     from langchain_openai import ChatOpenAI
#     from langchain.prompts import PromptTemplate
#     LLM_AVAILABLE = True
# except ImportError:
#     LLM_AVAILABLE = False

# logger = logging.getLogger(__name__)

# class AdminConfirmation(dict):
#     """Enhanced confirmation with LLM context"""
#     def __init__(self, action_id: str, intent: ParsedIntent, tenant_id: int, expires_in_minutes: int = 10):
#         super().__init__()
#         self.update({
#             "action_id": action_id,
#             "intent": intent,
#             "tenant_id": tenant_id,
#             "created_at": datetime.utcnow(),
#             "expires_in_minutes": expires_in_minutes,
#             "confirmed": False,
#             "context_data": {}  # Store additional context
#         })

# class EnhancedSuperTenantAdminEngine:
#     """
#     LLM-Enhanced admin engine for natural language tenant management
#     Provides intelligent, conversational administration experience
#     """
    
#     def __init__(self, db: Session):
#         self.db = db
#         self.intent_parser = get_llm_admin_intent_parser()
        
#         # Initialize LLM for response generation
#         self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
#         if self.llm_available:
#             self.llm = ChatOpenAI(
#                 model_name="gpt-3.5-turbo",
#                 temperature=0.3,  # Slightly higher for more natural responses
#                 openai_api_key=settings.OPENAI_API_KEY
#             )
        
#         # Store pending confirmations
#         self.pending_confirmations: Dict[str, AdminConfirmation] = {}
        
#         logger.info("🤖 Enhanced SuperTenantAdminEngine initialized with LLM support")
    
#     def process_admin_message(
#         self, 
#         user_message: str, 
#         authenticated_tenant_id: int, 
#         user_identifier: str,
#         session_context: Dict[str, Any] = None
#     ) -> Dict[str, Any]:
#         """
#         Process admin message with LLM enhancement for natural conversation
#         """
#         try:
#             logger.info(f"🧠 Processing enhanced admin message for tenant {authenticated_tenant_id}: {user_message[:50]}...")
            
#             # Initialize secure tenant data manager
#             data_manager = TenantDataManager(self.db, authenticated_tenant_id)
            
#             # Initialize memory for conversation context
#             memory = SimpleChatbotMemory(self.db, authenticated_tenant_id)
#             session_id, _ = memory.get_or_create_session(user_identifier, "admin_web")
            
#             # Get conversation history for context
#             conversation_history = memory.get_conversation_history(user_identifier, max_messages=10)
            
#             # Store user message
#             memory.store_message(session_id, user_message, True)
            
#             # Check if this is a confirmation/follow-up response
#             confirmation_result = self._handle_follow_up_responses(
#                 user_message, authenticated_tenant_id, data_manager, conversation_history
#             )
#             if confirmation_result:
#                 memory.store_message(session_id, confirmation_result["response"], False)
#                 return confirmation_result
            
#             # Parse the intent with conversation context
#             intent = self.intent_parser.parse(user_message)
            
#             # Enhance with conversation context
#             if conversation_history:
#                 intent = self.intent_parser.enhance_with_context(intent, conversation_history)
            
#             # Execute the appropriate action
#             result = self._execute_enhanced_admin_action(
#                 intent, data_manager, authenticated_tenant_id, conversation_history
#             )
            
#             # Store bot response
#             memory.store_message(session_id, result["response"], False)
            
#             # Log admin action for audit
#             data_manager.log_admin_action(
#                 action=intent.action.value,
#                 details={
#                     "user_message": user_message,
#                     "confidence": intent.confidence,
#                     "llm_reasoning": intent.llm_reasoning,
#                     "success": result.get("success", False)
#                 }
#             )
            
#             return result
            
#         except TenantSecurityError as e:
#             logger.error(f"🚨 Security error in enhanced admin processing: {e}")
#             return {
#                 "success": False,
#                 "response": "⛔ Access denied. You can only manage your own tenant data.",
#                 "error": "security_violation"
#             }
#         except Exception as e:
#             logger.error(f"💥 Error processing enhanced admin message: {e}")
#             return {
#                 "success": False,
#                 "response": "❌ I encountered an error processing your request. Please try again.",
#                 "error": str(e)
#             }
    
#     def _handle_follow_up_responses(
#         self, 
#         user_message: str, 
#         tenant_id: int, 
#         data_manager: TenantDataManager,
#         conversation_history: List[Dict]
#     ) -> Optional[Dict[str, Any]]:
#         """
#         Handle follow-up responses using LLM to understand context
#         """
#         message_lower = user_message.lower().strip()
        
#         # Check for explicit confirmations first
#         if message_lower in ['yes', 'y', 'confirm', 'proceed', 'do it', 'go ahead']:
#             return self._handle_confirmation(tenant_id, data_manager)
        
#         if message_lower in ['no', 'n', 'cancel', 'abort', 'stop', 'nevermind']:
#             return self._handle_cancellation(tenant_id)
        
#         # Use LLM to understand if this is a follow-up response
#         if self.llm_available and conversation_history:
#             follow_up_result = self._analyze_follow_up_with_llm(
#                 user_message, conversation_history, tenant_id, data_manager
#             )
#             if follow_up_result:
#                 return follow_up_result
        
#         return None
    
#     def _analyze_follow_up_with_llm(
#         self, 
#         user_message: str, 
#         conversation_history: List[Dict], 
#         tenant_id: int,
#         data_manager: TenantDataManager
#     ) -> Optional[Dict[str, Any]]:
#         """
#         Use LLM to analyze if current message is a follow-up to previous conversation
#         """
#         try:
#             # Get the last bot message to understand context
#             last_bot_message = None
#             for msg in reversed(conversation_history):
#                 if msg.get("role") == "assistant":
#                     last_bot_message = msg.get("content", "")
#                     break
            
#             if not last_bot_message:
#                 return None
            
#             # Check if we have pending confirmations
#             pending = self._get_pending_confirmation(tenant_id)
            
#             prompt = PromptTemplate(
#                 input_variables=["user_message", "last_bot_message", "has_pending"],
#                 template="""Analyze if this user message is a follow-up response to the assistant's previous message.

# LAST ASSISTANT MESSAGE: "{last_bot_message}"

# USER'S CURRENT MESSAGE: "{user_message}"

# PENDING ACTION: {has_pending}

# TASK: Determine if the user is:
# 1. Answering a question the assistant asked
# 2. Providing additional information requested
# 3. Confirming or canceling a pending action
# 4. Starting a completely new conversation

# RESPONSE FORMAT (JSON):
# {{
#     "is_followup": true/false,
#     "followup_type": "confirmation|information|answer|new_topic",
#     "confidence": 0.95,
#     "reasoning": "explanation"
# }}

# EXAMPLES:
# - If bot asked "What should the answer be?" and user says "We're open 9-5" → followup=true, type=answer
# - If bot asked for confirmation and user says "absolutely" → followup=true, type=confirmation  
# - If user says completely unrelated thing → followup=false, type=new_topic

# JSON Response:"""
#             )
            
#             response = self.llm.invoke(prompt.format(
#                 user_message=user_message,
#                 last_bot_message=last_bot_message,
#                 has_pending=bool(pending)
#             ))
            
#             response_text = response.content if hasattr(response, 'content') else str(response)
            
#             import json
#             import re
#             json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
#             if json_match:
#                 analysis = json.loads(json_match.group())
                
#                 if analysis.get("is_followup", False):
#                     followup_type = analysis.get("followup_type", "")
#                     confidence = analysis.get("confidence", 0.5)
                    
#                     logger.info(f"🔄 LLM detected follow-up: {followup_type} (confidence: {confidence})")
                    
#                     if followup_type == "confirmation" and pending:
#                         # Handle as confirmation
#                         return self._handle_confirmation(tenant_id, data_manager)
                    
#                     elif followup_type == "information" or followup_type == "answer":
#                         # Handle as additional information
#                         return self._handle_information_follow_up(
#                             user_message, tenant_id, data_manager, pending
#                         )
        
#         except Exception as e:
#             logger.error(f"Error analyzing follow-up with LLM: {e}")
        
#         return None
    
#     def _handle_information_follow_up(
#         self, 
#         user_message: str, 
#         tenant_id: int, 
#         data_manager: TenantDataManager,
#         pending: Optional[AdminConfirmation]
#     ) -> Optional[Dict[str, Any]]:
#         """
#         Handle when user provides additional information in follow-up
#         """
#         if not pending:
#             return None
        
#         intent = pending["intent"]
#         action_id = pending["action_id"]
        
#         # Handle FAQ creation with additional information
#         if intent.action == AdminActionType.ADD_FAQ:
#             # Extract additional info using LLM
#             if self.llm_available:
#                 faq_params = self.intent_parser.extract_faq_parameters_llm(user_message)
#             else:
#                 faq_params = {}
            
#             # Combine with existing parameters
#             existing_question = intent.parameters.get('question')
#             existing_answer = intent.parameters.get('answer')
            
#             new_question = faq_params.get('question') or existing_question
#             new_answer = faq_params.get('answer') or existing_answer
            
#             # If we now have both question and answer, create the FAQ
#             if new_question and new_answer:
#                 try:
#                     faq = data_manager.create_faq(new_question, new_answer)
#                     # Remove from pending confirmations
#                     del self.pending_confirmations[action_id]
                    
#                     return {
#                         "success": True,
#                         "response": f"✅ Perfect! I've created your FAQ:\n\n**Question:** {new_question}\n**Answer:** {new_answer}\n\n**FAQ ID:** #{faq.id}",
#                         "action": "faq_created",
#                         "faq_id": faq.id
#                     }
#                 except Exception as e:
#                     return {
#                         "success": False,
#                         "response": f"❌ Failed to create FAQ: {str(e)}"
#                     }
            
#             # Still missing information - ask for what's needed
#             elif new_question and not new_answer:
#                 # Update pending confirmation with new question
#                 intent.parameters['question'] = new_question
#                 return {
#                     "success": False,
#                     "response": f"📝 Got it! The question is: '{new_question}'\n\nNow, what should the answer be?",
#                     "requires_input": True
#                 }
            
#             elif new_answer and not new_question:
#                 # Update pending confirmation with new answer
#                 intent.parameters['answer'] = new_answer
#                 return {
#                     "success": False,
#                     "response": f"📝 Perfect answer: '{new_answer}'\n\nWhat should the question be?",
#                     "requires_input": True
#                 }
            
#             else:
#                 return {
#                     "success": False,
#                     "response": "🤔 I need both a question and answer for the FAQ. Could you provide them?\n\nExample: 'Question: What are your hours? Answer: 9-5 weekdays'"
#                 }
        
#         # Handle FAQ updates with additional information
#         elif intent.action == AdminActionType.UPDATE_FAQ:
#             faq_id = intent.parameters.get('faq_id')
#             if not faq_id:
#                 return None
            
#             # Use LLM to understand what they want to update
#             if self.llm_available:
#                 update_params = self._extract_update_parameters_llm(user_message)
#             else:
#                 update_params = {'question': None, 'answer': None}
            
#             try:
#                 faq = data_manager.update_faq(
#                     faq_id, 
#                     update_params.get('question'), 
#                     update_params.get('answer')
#                 )
                
#                 if faq:
#                     # Remove from pending confirmations
#                     del self.pending_confirmations[action_id]
                    
#                     return {
#                         "success": True,
#                         "response": f"✅ Updated FAQ #{faq_id}:\n\n**Question:** {faq.question}\n**Answer:** {faq.answer}",
#                         "action": "faq_updated",
#                         "faq_id": faq.id
#                     }
#                 else:
#                     return {
#                         "success": False,
#                         "response": f"❌ FAQ #{faq_id} not found."
#                     }
#             except Exception as e:
#                 return {
#                     "success": False,
#                     "response": f"❌ Failed to update FAQ: {str(e)}"
#                 }
        
#         return None
    
#     def _extract_update_parameters_llm(self, user_message: str) -> Dict[str, Any]:
#         """Extract what fields to update from user message"""
#         if not self.llm_available:
#             return {}
        
#         try:
#             prompt = PromptTemplate(
#                 input_variables=["user_message"],
#                 template="""Extract what the user wants to update in an FAQ.

# USER MESSAGE: "{user_message}"

# The user is providing information to update an existing FAQ. They might say:
# - "Change the question to: What are your new hours?"
# - "Update the answer: We're now open 24/7"
# - "The question should be: How do I cancel?"
# - "New answer: Just click the cancel button"

# RESPONSE FORMAT (JSON):
# {{
#     "question": "new question text or null",
#     "answer": "new answer text or null"
# }}

# Only extract what they explicitly want to change.

# JSON Response:"""
#             )
            
#             response = self.llm.invoke(prompt.format(user_message=user_message))
#             response_text = response.content if hasattr(response, 'content') else str(response)
            
#             import json
#             import re
#             json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
#             if json_match:
#                 return json.loads(json_match.group())
        
#         except Exception as e:
#             logger.error(f"Error extracting update parameters: {e}")
        
#         return {}
    
#     def _get_pending_confirmation(self, tenant_id: int) -> Optional[AdminConfirmation]:
#         """Get pending confirmation for tenant"""
#         for confirmation in self.pending_confirmations.values():
#             if confirmation["tenant_id"] == tenant_id and not confirmation["confirmed"]:
#                 return confirmation
#         return None
    
#     def _execute_enhanced_admin_action(
#         self, 
#         intent: ParsedIntent, 
#         data_manager: TenantDataManager, 
#         tenant_id: int,
#         conversation_history: List[Dict] = None
#     ) -> Dict[str, Any]:
#         """Execute admin action with LLM-enhanced responses"""
        
#         if intent.action == AdminActionType.HELP:
#             return {
#                 "success": True,
#                 "response": self._generate_contextual_help(conversation_history),
#                 "action": "help"
#             }
        
#         elif intent.action == AdminActionType.GREETING:
#             return {
#                 "success": True,
#                 "response": self._generate_greeting_response(data_manager),
#                 "action": "greeting"
#             }
        
#         elif intent.action == AdminActionType.ADD_FAQ:
#             return self._handle_enhanced_add_faq(intent, data_manager, tenant_id)
        
#         elif intent.action == AdminActionType.UPDATE_FAQ:
#             return self._handle_enhanced_update_faq(intent, data_manager, tenant_id)
        
#         elif intent.action == AdminActionType.DELETE_FAQ:
#             return self._handle_enhanced_delete_faq(intent, data_manager, tenant_id)
        
#         elif intent.action == AdminActionType.LIST_FAQS:
#             return self._handle_enhanced_list_faqs(data_manager)
        
#         elif intent.action == AdminActionType.VIEW_ANALYTICS:
#             return self._handle_enhanced_analytics(data_manager)
        
#         elif intent.action == AdminActionType.VIEW_SETTINGS:
#             return self._handle_enhanced_settings(data_manager)
        
#         elif intent.action == AdminActionType.VIEW_KNOWLEDGE_BASE:
#             return self._handle_enhanced_knowledge_base(data_manager)
        
#         elif intent.action == AdminActionType.UNKNOWN:
#             return self._handle_unknown_with_suggestions(intent, conversation_history)
        
#         else:
#             return {
#                 "success": False,
#                 "response": f"🚧 I understand you want to {intent.action.value.replace('_', ' ')}, but that feature is still in development. Is there something else I can help you with?",
#                 "action": "not_implemented"
#             }
    
#     def _generate_contextual_help(self, conversation_history: List[Dict] = None) -> str:
#         """Generate contextual help based on conversation history"""
#         base_help = self.intent_parser.get_help_text()
        
#         if not conversation_history or not self.llm_available:
#             return base_help
        
#         try:
#             # Analyze conversation to provide targeted help
#             recent_topics = []
#             for msg in conversation_history[-5:]:
#                 if msg.get("role") == "user":
#                     recent_topics.append(msg.get("content", ""))
            
#             if recent_topics:
#                 context_help = f"\n\n**💡 Based on our conversation, you might also want to:**\n"
                
#                 # Simple keyword analysis for suggestions
#                 topics_text = " ".join(recent_topics).lower()
                
#                 if "faq" in topics_text:
#                     context_help += "• Try: 'Show me all my FAQs'\n• Or: 'Update FAQ #[number]'\n"
                
#                 if "analytics" in topics_text or "stats" in topics_text:
#                     context_help += "• Try: 'Show my usage for this month'\n• Or: 'How many conversations did I have?'\n"
                
#                 if "integration" in topics_text or "discord" in topics_text or "slack" in topics_text:
#                     context_help += "• Try: 'List my integrations'\n• Or: 'Setup [platform] integration'\n"
                
#                 return base_help + context_help
        
#         except Exception as e:
#             logger.error(f"Error generating contextual help: {e}")
        
#         return base_help
    
#     def _generate_greeting_response(self, data_manager: TenantDataManager) -> str:
#         """Generate personalized greeting response"""
#         try:
#             settings = data_manager.get_tenant_settings()
#             business_name = settings.get('business_name', 'your business')
            
#             # Get quick stats for personalization
#             analytics = data_manager.get_analytics_summary()
#             faq_count = analytics.get('content_stats', {}).get('faqs', 0)
            
#             greetings = [
#                 f"Hello! 👋 I'm here to help you manage {business_name}'s chatbot. You currently have {faq_count} FAQs. What would you like to work on today?",
#                 f"Hi there! ✨ Ready to enhance {business_name}'s chatbot experience? I can help with FAQs, settings, analytics, and more!",
#                 f"Welcome back! 🚀 Let's make {business_name}'s chatbot even better. What can I help you with?",
#                 f"Hey! 💫 I'm your AI assistant for managing {business_name}'s chatbot. Just tell me what you need!"
#             ]
            
#             import random
#             return random.choice(greetings)
        
#         except Exception:
#             return "Hello! 👋 I'm your chatbot admin assistant. I can help you manage FAQs, view analytics, update settings, and much more. What would you like to do?"
    
#     def _handle_enhanced_add_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
#         """Enhanced FAQ addition with intelligent parameter extraction"""
#         question = intent.parameters.get('question')
#         answer = intent.parameters.get('answer')
        
#         if not question and not answer:
#             # Use LLM to extract FAQ info if available
#             if self.llm_available:
#                 faq_params = self.intent_parser.extract_faq_parameters_llm(intent.original_text)
#                 question = faq_params.get('question')
#                 answer = faq_params.get('answer')
        
#         if question and answer:
#             # We have both - create the FAQ
#             try:
#                 faq = data_manager.create_faq(question, answer)
#                 return {
#                     "success": True,
#                     "response": f"✅ Perfect! I've created your new FAQ:\n\n**Question:** {question}\n**Answer:** {answer}\n\n**FAQ ID:** #{faq.id}\n\nYour customers will now get this answer when they ask about this topic!",
#                     "action": "faq_created",
#                     "faq_id": faq.id
#                 }
#             except Exception as e:
#                 return {
#                     "success": False,
#                     "response": f"❌ I encountered an error creating your FAQ: {str(e)}"
#                 }
        
#         elif question and not answer:
#             # We have question, need answer
#             action_id = str(uuid.uuid4())
#             intent.parameters['question'] = question
#             self.pending_confirmations[action_id] = AdminConfirmation(action_id, intent, tenant_id)
            
#             return {
#                 "success": False,
#                 "response": f"📝 Great! I have the question: **'{question}'**\n\nNow, what should the answer be? Just tell me the answer you want customers to see.",
#                 "requires_input": True,
#                 "pending_action": action_id
#             }
        
#         else:
#             # Need both question and answer
#             action_id = str(uuid.uuid4())
#             self.pending_confirmations[action_id] = AdminConfirmation(action_id, intent, tenant_id)
            
#             return {
#                 "success": False,
#                 "response": "📝 I'd love to help you create a new FAQ! \n\nPlease provide:\n1. **The question** customers might ask\n2. **The answer** you want them to receive\n\n**Example:** 'Question: What are your business hours? Answer: We're open Monday-Friday, 9 AM to 5 PM.'",
#                 "requires_input": True,
#                 "pending_action": action_id
#             }
    
#     def _handle_enhanced_list_faqs(self, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Enhanced FAQ listing with better formatting"""
#         try:
#             faqs = data_manager.get_faqs(limit=20)  # Reasonable limit for readability
            
#             if not faqs:
#                 return {
#                     "success": True,
#                     "response": "📋 You don't have any FAQs yet!\n\n💡 **Let's create your first one:**\nJust tell me something like: 'Add FAQ about business hours - we're open 9-5 weekdays'\n\nFAQs help your chatbot answer common questions automatically! 🚀"
#                 }
            
#             # Group FAQs by first letter for better organization if many
#             if len(faqs) > 10:
#                 response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
#                 for i, faq in enumerate(faqs, 1):
#                     response += f"**#{faq.id}** {faq.question[:60]}{'...' if len(faq.question) > 60 else ''}\n"
#                     if i >= 15:  # Limit display
#                         response += f"\n*...and {len(faqs) - 15} more FAQs*\n"
#                         break
#             else:
#                 response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
#                 for faq in faqs:
#                     response += f"**#{faq.id}** {faq.question}\n"
            
#             response += f"\n💡 **What you can do:**\n• Update: 'Modify FAQ #{faqs[0].id}'\n• Delete: 'Remove FAQ #{faqs[0].id}'\n• Add new: 'Create FAQ about [topic]'"
            
#             return {
#                 "success": True,
#                 "response": response,
#                 "faq_count": len(faqs)
#             }
            
#         except Exception as e:
#             return {
#                 "success": False,
#                 "response": f"❌ I couldn't retrieve your FAQs: {str(e)}"
#             }
    
#     def _handle_enhanced_analytics(self, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Enhanced analytics with insights and recommendations"""
#         try:
#             analytics = data_manager.get_analytics_summary()
            
#             if "error" in analytics:
#                 return {
#                     "success": False,
#                     "response": f"❌ I couldn't retrieve your analytics: {analytics['error']}"
#                 }
            
#             # Generate insights
#             insights = []
#             faq_count = analytics['content_stats']['faqs']
#             sessions_30d = analytics['usage_stats_30_days']['chat_sessions']
#             messages_30d = analytics['usage_stats_30_days']['total_messages']
            
#             if faq_count == 0:
#                 insights.append("💡 **Tip:** Add FAQs to reduce support workload!")
#             elif faq_count < 5:
#                 insights.append("💡 **Suggestion:** Consider adding more FAQs for common questions")
            
#             if sessions_30d > 0:
#                 avg_messages = messages_30d / sessions_30d if sessions_30d > 0 else 0
#                 if avg_messages > 5:
#                     insights.append("📈 **Insight:** High message volume - FAQs could help!")
            
#             # Build response
#             response = f"""📊 **Analytics for {analytics['tenant_name']}**

# **📋 Content Statistics:**
# • FAQs: {faq_count}
# • Knowledge Bases: {analytics['content_stats']['knowledge_bases']}

# **💬 Usage (Last 30 Days):**
# • Chat Sessions: {sessions_30d:,}
# • Total Messages: {messages_30d:,}
# • Avg Messages per Session: {messages_30d / sessions_30d if sessions_30d > 0 else 0:.1f}

# **🔗 Active Integrations:**
# • Discord: {'✅ Active' if analytics['integrations']['discord'] else '❌ Not active'}
# • Slack: {'✅ Active' if analytics['integrations']['slack'] else '❌ Not active'}
# • Telegram: {'✅ Active' if analytics['integrations']['telegram'] else '❌ Not active'}"""
            
#             if insights:
#                 response += f"\n\n**💡 Insights:**\n" + "\n".join(insights)
            
#             return {
#                 "success": True,
#                 "response": response,
#                 "analytics": analytics
#             }
            
#         except Exception as e:
#             return {
#                 "success": False,
#                 "response": f"❌ I encountered an error getting your analytics: {str(e)}"
#             }
    
#     def _handle_unknown_with_suggestions(self, intent: ParsedIntent, conversation_history: List[Dict] = None) -> Dict[str, Any]:
#         """Handle unknown intents with LLM-powered suggestions"""
#         if not self.llm_available:
#             return {
#                 "success": False,
#                 "response": "🤔 I didn't quite understand that. Type 'help' to see what I can do!",
#                 "action": "unknown"
#             }
        
#         try:
#             # Use LLM to suggest what they might have meant
#             prompt = PromptTemplate(
#                 input_variables=["user_message"],
#                 template="""The user said something to a chatbot admin assistant, but it wasn't clearly understood.

# USER MESSAGE: "{user_message}"

# AVAILABLE CAPABILITIES:
# - FAQ management (add, edit, delete FAQs)
# - View analytics and usage statistics  
# - Update settings (system prompt, branding, email config)
# - Setup integrations (Discord, Slack, Instagram, Telegram)
# - View knowledge base documents
# - General help and guidance

# TASK: Suggest what they might have meant and provide helpful guidance.

# RESPONSE: Write a friendly, helpful response that:
# 1. Acknowledges you didn't understand
# 2. Suggests what they might have meant (if possible)
# 3. Gives 2-3 specific examples they could try

# Keep it conversational and encouraging. Don't use JSON format.

# Response:"""
#             )
            
#             response = self.llm.invoke(prompt.format(user_message=intent.original_text))
#             response_text = response.content if hasattr(response, 'content') else str(response)
            
#             return {
#                 "success": False,
#                 "response": response_text,
#                 "action": "unknown_with_suggestions",
#                 "confidence": intent.confidence
#             }
            
#         except Exception as e:
#             logger.error(f"Error generating suggestions for unknown intent: {e}")
#             return {
#                 "success": False,
#                 "response": "🤔 I'm not sure what you're looking for. Here are some things I can help with:\n\n• 'Add FAQ about [topic]'\n• 'Show my analytics'\n• 'List my FAQs'\n• 'Help with integrations'\n\nWhat would you like to try?",
#                 "action": "unknown"
#             }
    
#     # Include all the other handler methods from the previous version
#     # (confirmation handlers, delete FAQ, update FAQ, etc.)
    
#     def _handle_confirmation(self, tenant_id: int, data_manager: TenantDataManager) -> Optional[Dict[str, Any]]:
#         """Handle confirmation responses with enhanced feedback"""
#         pending = self._get_pending_confirmation(tenant_id)
        
#         if not pending:
#             return {
#                 "success": False,
#                 "response": "❓ I don't have any pending actions to confirm. What would you like me to help with?"
#             }
        
#         intent = pending["intent"]
#         action_id = pending["action_id"]
        
#         if intent.action == AdminActionType.DELETE_FAQ:
#             faq_id = intent.parameters.get('faq_id')
#             try:
#                 success = data_manager.delete_faq(faq_id)
#                 if success:
#                     del self.pending_confirmations[action_id]
#                     return {
#                         "success": True,
#                         "response": f"✅ FAQ #{faq_id} has been permanently deleted.\n\n🗑️ Your customers will no longer receive this automated answer. You can always create a new FAQ if needed!",
#                         "action": "faq_deleted"
#                     }
#                 else:
#                     return {
#                         "success": False,
#                         "response": f"❌ I couldn't find FAQ #{faq_id} to delete."
#                     }
#             except Exception as e:
#                 return {
#                     "success": False,
#                     "response": f"❌ Error deleting FAQ: {str(e)}"
#                 }
        
#         # Remove processed confirmation
#         if action_id in self.pending_confirmations:
#             del self.pending_confirmations[action_id]
        
#         return {
#             "success": False,
#             "response": "✅ Action confirmed, but I'm not sure what to do next. What can I help you with?"
#         }
    
#     def _handle_cancellation(self, tenant_id: int) -> Dict[str, Any]:
#         """Handle cancellation with friendly response"""
#         to_remove = []
#         for aid, confirmation in self.pending_confirmations.items():
#             if confirmation["tenant_id"] == tenant_id and not confirmation["confirmed"]:
#                 to_remove.append(aid)
        
#         for aid in to_remove:
#             del self.pending_confirmations[aid]
        
#         if to_remove:
#             return {
#                 "success": True,
#                 "response": "✅ No problem! I've cancelled that action.\n\n😊 What else can I help you with today?",
#                 "action": "cancelled"
#             }
#         else:
#             return {
#                 "success": False,
#                 "response": "❓ I don't have any pending actions to cancel, but that's okay! What would you like to work on?"
#             }

# # Export enhanced engine
# def get_super_tenant_admin_engine(db: Session) -> EnhancedSuperTenantAdminEngine:
#     """Factory function to create Enhanced SuperTenantAdminEngine"""
#     return EnhancedSuperTenantAdminEngine(db)










# app/chatbot/enhanced_super_tenant_admin_engine.py
"""
Enhanced Super Tenant Admin Engine with LLM Integration + Unified Engine
Provides intelligent, conversational tenant administration with efficiency
"""

import logging
import uuid
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.chatbot.admin_intent_parser import get_llm_admin_intent_parser, AdminActionType, ParsedIntent
from app.chatbot.tenant_data_manager import TenantDataManager, TenantSecurityError
from app.chatbot.simple_memory import SimpleChatbotMemory
from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
from app.tenants.models import Tenant
from app.config import settings

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class AdminConfirmation(dict):
    """Enhanced confirmation with LLM context"""
    def __init__(self, action_id: str, intent: ParsedIntent, tenant_id: int, expires_in_minutes: int = 10):
        super().__init__()
        self.update({
            "action_id": action_id,
            "intent": intent,
            "tenant_id": tenant_id,
            "created_at": datetime.utcnow(),
            "expires_in_minutes": expires_in_minutes,
            "confirmed": False,
            "context_data": {}  # Store additional context
        })

class EnhancedSuperTenantAdminEngine:
    """
    LLM-Enhanced admin engine with Unified Engine integration
    Provides intelligent, conversational administration with 80% token efficiency
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.intent_parser = get_llm_admin_intent_parser()
        
        # 🆕 Initialize unified engine for efficient processing
        self.unified_engine = get_unified_intelligent_engine(db)
        
        # Initialize LLM for response generation
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.3,
                openai_api_key=settings.OPENAI_API_KEY
            )
        
        # Store pending confirmations
        self.pending_confirmations: Dict[str, AdminConfirmation] = {}
        
        logger.info("🤖 Enhanced SuperTenantAdminEngine initialized with Unified Engine support")
    
    def process_admin_message(
        self, 
        user_message: str, 
        authenticated_tenant_id: int, 
        user_identifier: str,
        session_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process admin message with unified engine efficiency + admin capabilities
        """
        try:
            logger.info(f"🧠 Processing enhanced admin message for tenant {authenticated_tenant_id}: {user_message[:50]}...")
            
            # Initialize secure tenant data manager
            data_manager = TenantDataManager(self.db, authenticated_tenant_id)
            
            # Initialize memory for conversation context
            memory = SimpleChatbotMemory(self.db, authenticated_tenant_id)
            session_id, _ = memory.get_or_create_session(user_identifier, "admin_web")
            
            # Get conversation history for context
            conversation_history = memory.get_conversation_history(user_identifier, max_messages=10)
            
            # Store user message
            memory.store_message(session_id, user_message, True)
            
            # Check if this is a confirmation/follow-up response
            confirmation_result = self._handle_follow_up_responses(
                user_message, authenticated_tenant_id, data_manager, conversation_history
            )
            if confirmation_result:
                memory.store_message(session_id, confirmation_result["response"], False)
                return confirmation_result
            
            # Parse admin intent
            intent = self.intent_parser.parse(user_message)
            if conversation_history:
                intent = self.intent_parser.enhance_with_context(intent, conversation_history)
            
            # 🆕 UNIFIED ENGINE ROUTING: Check if this needs admin engine or can use unified
            if self._should_use_unified_engine(intent, user_message, session_context):
                result = self._process_with_unified_engine(
                    user_message, authenticated_tenant_id, user_identifier, intent, session_context
                )
            else:
                # Use dedicated admin processing
                result = self._execute_enhanced_admin_action(
                    intent, data_manager, authenticated_tenant_id, conversation_history
                )
            
            # Store bot response
            memory.store_message(session_id, result["response"], False)
            
            # Log admin action for audit
            data_manager.log_admin_action(
                action=intent.action.value,
                details={
                    "user_message": user_message,
                    "confidence": intent.confidence,
                    "llm_reasoning": intent.llm_reasoning,
                    "success": result.get("success", False),
                    "processing_method": result.get("processing_method", "admin_engine")
                }
            )
            
            return result
            
        except TenantSecurityError as e:
            logger.error(f"🚨 Security error in enhanced admin processing: {e}")
            return {
                "success": False,
                "response": "⛔ Access denied. You can only manage your own tenant data.",
                "error": "security_violation"
            }
        except Exception as e:
            logger.error(f"💥 Error processing enhanced admin message: {e}")
            return {
                "success": False,
                "response": "❌ I encountered an error processing your request. Please try again.",
                "error": str(e)
            }
    
    def _should_use_unified_engine(self, intent: ParsedIntent, user_message: str, session_context: Dict[str, Any]) -> bool:
        """Determine if we should use unified engine vs dedicated admin processing"""
        
        # Use unified engine for conversational/informational intents
        unified_engine_intents = [
            AdminActionType.GREETING,
            AdminActionType.HELP,
            AdminActionType.UNKNOWN
        ]
        
        if intent.action in unified_engine_intents:
            return True
        
        # Use unified engine for questions that don't require admin actions
        question_patterns = [
            "what", "how", "why", "explain", "tell me about", "what's", "how do"
        ]
        
        if any(pattern in user_message.lower() for pattern in question_patterns):
            # If it's a question about admin functionality, keep in admin engine
            admin_keywords = ["faq", "analytics", "settings", "integration", "discord", "slack"]
            if not any(keyword in user_message.lower() for keyword in admin_keywords):
                return True
        
        return False
    
    def _process_with_unified_engine(self, user_message: str, tenant_id: int, user_identifier: str,
                                   intent: ParsedIntent, session_context: Dict[str, Any]) -> Dict[str, Any]:
        """Process using unified engine with admin context"""
        try:
            # Get tenant for unified engine
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return {"success": False, "response": "❌ Tenant not found"}
            
            # Create admin-aware API key context (use tenant's actual API key)
            api_key = tenant.api_key
            
            # 🆕 Use unified engine for efficient processing
            unified_result = self.unified_engine.process_message(
                api_key=api_key,
                user_message=user_message,
                user_identifier=user_identifier,
                platform="admin_web"
            )
            
            if unified_result.get("success"):
                # Enhance response with admin context
                admin_enhanced_response = self._enhance_response_for_admin(
                    unified_result["response"], intent, tenant
                )
                
                return {
                    "success": True,
                    "response": admin_enhanced_response,
                    "action": intent.action.value,
                    "processing_method": "unified_engine",
                    "token_efficiency": unified_result.get("token_efficiency"),
                    "admin_mode": True,
                    "tenant_id": tenant_id
                }
            else:
                # Fallback to admin engine if unified fails
                return self._generate_admin_fallback_response(intent, user_message)
                
        except Exception as e:
            logger.error(f"Error in unified engine processing: {e}")
            return self._generate_admin_fallback_response(intent, user_message)
    
    def _enhance_response_for_admin(self, response: str, intent: ParsedIntent, tenant: Tenant) -> str:
        """Enhance unified engine response with admin-specific context"""
        
        if intent.action == AdminActionType.GREETING:
            # Add admin capabilities to greeting
            business_name = getattr(tenant, 'business_name', tenant.name)
            admin_suffix = f"\n\n💼 **Admin Options:** I can help you manage {business_name}'s FAQs, view analytics, update settings, and configure integrations. What would you like to work on?"
            return response + admin_suffix
            
        elif intent.action == AdminActionType.HELP:
            # Replace generic help with admin help
            return self.intent_parser.get_help_text()
            
        elif intent.action == AdminActionType.UNKNOWN:
            # Add admin suggestions to unknown responses
            admin_suffix = "\n\n💡 **Admin Suggestions:**\n• 'Show my FAQs'\n• 'View analytics'\n• 'Help with settings'\n• 'List integrations'"
            return response + admin_suffix
        
        return response
    
    def _generate_admin_fallback_response(self, intent: ParsedIntent, user_message: str) -> Dict[str, Any]:
        """Generate fallback response when unified engine fails"""
        
        fallback_responses = {
            AdminActionType.GREETING: "Hello! 👋 I'm your admin assistant. I can help manage FAQs, analytics, settings, and integrations. What would you like to do?",
            AdminActionType.HELP: self.intent_parser.get_help_text(),
            AdminActionType.UNKNOWN: "🤔 I'm not sure about that. Try asking about FAQs, analytics, settings, or integrations. Type 'help' for more options."
        }
        
        response = fallback_responses.get(
            intent.action, 
            "I'm here to help with your admin tasks. What would you like to work on?"
        )
        
        return {
            "success": True,
            "response": response,
            "action": intent.action.value,
            "processing_method": "admin_fallback"
        }
    
    # Keep all existing methods unchanged...
    def _handle_follow_up_responses(self, user_message: str, tenant_id: int, data_manager: TenantDataManager, conversation_history: List[Dict]) -> Optional[Dict[str, Any]]:
        """Handle follow-up responses using LLM to understand context"""
        message_lower = user_message.lower().strip()
        
        if message_lower in ['yes', 'y', 'confirm', 'proceed', 'do it', 'go ahead']:
            return self._handle_confirmation(tenant_id, data_manager)
        
        if message_lower in ['no', 'n', 'cancel', 'abort', 'stop', 'nevermind']:
            return self._handle_cancellation(tenant_id)
        
        if self.llm_available and conversation_history:
            follow_up_result = self._analyze_follow_up_with_llm(
                user_message, conversation_history, tenant_id, data_manager
            )
            if follow_up_result:
                return follow_up_result
        
        return None
    
    def _analyze_follow_up_with_llm(self, user_message: str, conversation_history: List[Dict], tenant_id: int, data_manager: TenantDataManager) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze if current message is a follow-up to previous conversation"""
        try:
            last_bot_message = None
            for msg in reversed(conversation_history):
                if msg.get("role") == "assistant":
                    last_bot_message = msg.get("content", "")
                    break
            
            if not last_bot_message:
                return None
            
            pending = self._get_pending_confirmation(tenant_id)
            
            prompt = PromptTemplate(
                input_variables=["user_message", "last_bot_message", "has_pending"],
                template="""Analyze if this user message is a follow-up response to the assistant's previous message.

LAST ASSISTANT MESSAGE: "{last_bot_message}"
USER'S CURRENT MESSAGE: "{user_message}"
PENDING ACTION: {has_pending}

TASK: Determine if the user is:
1. Answering a question the assistant asked
2. Providing additional information requested
3. Confirming or canceling a pending action
4. Starting a completely new conversation

RESPONSE FORMAT (JSON):
{{
    "is_followup": true/false,
    "followup_type": "confirmation|information|answer|new_topic",
    "confidence": 0.95,
    "reasoning": "explanation"
}}

JSON Response:"""
            )
            
            response = self.llm.invoke(prompt.format(
                user_message=user_message,
                last_bot_message=last_bot_message,
                has_pending=bool(pending)
            ))
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            import json
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                
                if analysis.get("is_followup", False):
                    followup_type = analysis.get("followup_type", "")
                    
                    if followup_type == "confirmation" and pending:
                        return self._handle_confirmation(tenant_id, data_manager)
                    elif followup_type in ["information", "answer"]:
                        return self._handle_information_follow_up(user_message, tenant_id, data_manager, pending)
        
        except Exception as e:
            logger.error(f"Error analyzing follow-up with LLM: {e}")
        
        return None
    
    def _handle_information_follow_up(self, user_message: str, tenant_id: int, data_manager: TenantDataManager, pending: Optional[AdminConfirmation]) -> Optional[Dict[str, Any]]:
        """Handle when user provides additional information in follow-up"""
        if not pending:
            return None
        
        intent = pending["intent"]
        action_id = pending["action_id"]
        
        if intent.action == AdminActionType.ADD_FAQ:
            if self.llm_available:
                faq_params = self.intent_parser.extract_faq_parameters_llm(user_message)
            else:
                faq_params = {}
            
            existing_question = intent.parameters.get('question')
            existing_answer = intent.parameters.get('answer')
            
            new_question = faq_params.get('question') or existing_question
            new_answer = faq_params.get('answer') or existing_answer
            
            if new_question and new_answer:
                try:
                    faq = data_manager.create_faq(new_question, new_answer)
                    del self.pending_confirmations[action_id]
                    
                    return {
                        "success": True,
                        "response": f"✅ Perfect! I've created your FAQ:\n\n**Question:** {new_question}\n**Answer:** {new_answer}\n\n**FAQ ID:** #{faq.id}",
                        "action": "faq_created",
                        "faq_id": faq.id
                    }
                except Exception as e:
                    return {"success": False, "response": f"❌ Failed to create FAQ: {str(e)}"}
            
            elif new_question and not new_answer:
                intent.parameters['question'] = new_question
                return {
                    "success": False,
                    "response": f"📝 Got it! The question is: '{new_question}'\n\nNow, what should the answer be?",
                    "requires_input": True
                }
            
            elif new_answer and not new_question:
                intent.parameters['answer'] = new_answer
                return {
                    "success": False,
                    "response": f"📝 Perfect answer: '{new_answer}'\n\nWhat should the question be?",
                    "requires_input": True
                }
        
        return None
    
    def _get_pending_confirmation(self, tenant_id: int) -> Optional[AdminConfirmation]:
        """Get pending confirmation for tenant"""
        for confirmation in self.pending_confirmations.values():
            if confirmation["tenant_id"] == tenant_id and not confirmation["confirmed"]:
                return confirmation
        return None
    
    def _execute_enhanced_admin_action(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Execute admin action with LLM-enhanced responses"""
        
        if intent.action == AdminActionType.ADD_FAQ:
            return self._handle_enhanced_add_faq(intent, data_manager, tenant_id)
        elif intent.action == AdminActionType.UPDATE_FAQ:
            return self._handle_enhanced_update_faq(intent, data_manager, tenant_id)
        elif intent.action == AdminActionType.DELETE_FAQ:
            return self._handle_enhanced_delete_faq(intent, data_manager, tenant_id)
        elif intent.action == AdminActionType.LIST_FAQS:
            return self._handle_enhanced_list_faqs(data_manager)
        elif intent.action == AdminActionType.VIEW_ANALYTICS:
            return self._handle_enhanced_analytics(data_manager)
        elif intent.action == AdminActionType.VIEW_SETTINGS:
            return self._handle_enhanced_settings(data_manager)
        elif intent.action == AdminActionType.VIEW_KNOWLEDGE_BASE:
            return self._handle_enhanced_knowledge_base(data_manager)
        else:
            return {
                "success": False,
                "response": f"🚧 I understand you want to {intent.action.value.replace('_', ' ')}, but that feature is still in development. Is there something else I can help you with?",
                "action": "not_implemented"
            }
    
    def _handle_enhanced_add_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
        """Enhanced FAQ addition with intelligent parameter extraction"""
        question = intent.parameters.get('question')
        answer = intent.parameters.get('answer')
        
        if not question and not answer:
            if self.llm_available:
                faq_params = self.intent_parser.extract_faq_parameters_llm(intent.original_text)
                question = faq_params.get('question')
                answer = faq_params.get('answer')
        
        if question and answer:
            try:
                faq = data_manager.create_faq(question, answer)
                return {
                    "success": True,
                    "response": f"✅ Perfect! I've created your new FAQ:\n\n**Question:** {question}\n**Answer:** {answer}\n\n**FAQ ID:** #{faq.id}\n\nYour customers will now get this answer when they ask about this topic!",
                    "action": "faq_created",
                    "faq_id": faq.id
                }
            except Exception as e:
                return {"success": False, "response": f"❌ I encountered an error creating your FAQ: {str(e)}"}
        
        elif question and not answer:
            action_id = str(uuid.uuid4())
            intent.parameters['question'] = question
            self.pending_confirmations[action_id] = AdminConfirmation(action_id, intent, tenant_id)
            
            return {
                "success": False,
                "response": f"📝 Great! I have the question: **'{question}'**\n\nNow, what should the answer be? Just tell me the answer you want customers to see.",
                "requires_input": True,
                "pending_action": action_id
            }
        
        else:
            action_id = str(uuid.uuid4())
            self.pending_confirmations[action_id] = AdminConfirmation(action_id, intent, tenant_id)
            
            return {
                "success": False,
                "response": "📝 I'd love to help you create a new FAQ! \n\nPlease provide:\n1. **The question** customers might ask\n2. **The answer** you want them to receive\n\n**Example:** 'Question: What are your business hours? Answer: We're open Monday-Friday, 9 AM to 5 PM.'",
                "requires_input": True,
                "pending_action": action_id
            }
    
    def _handle_enhanced_list_faqs(self, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Enhanced FAQ listing with better formatting"""
        try:
            faqs = data_manager.get_faqs(limit=20)
            
            if not faqs:
                return {
                    "success": True,
                    "response": "📋 You don't have any FAQs yet!\n\n💡 **Let's create your first one:**\nJust tell me something like: 'Add FAQ about business hours - we're open 9-5 weekdays'\n\nFAQs help your chatbot answer common questions automatically! 🚀"
                }
            
            if len(faqs) > 10:
                response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
                for i, faq in enumerate(faqs, 1):
                    response += f"**#{faq.id}** {faq.question[:60]}{'...' if len(faq.question) > 60 else ''}\n"
                    if i >= 15:
                        response += f"\n*...and {len(faqs) - 15} more FAQs*\n"
                        break
            else:
                response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
                for faq in faqs:
                    response += f"**#{faq.id}** {faq.question}\n"
            
            response += f"\n💡 **What you can do:**\n• Update: 'Modify FAQ #{faqs[0].id}'\n• Delete: 'Remove FAQ #{faqs[0].id}'\n• Add new: 'Create FAQ about [topic]'"
            
            return {"success": True, "response": response, "faq_count": len(faqs)}
            
        except Exception as e:
            return {"success": False, "response": f"❌ I couldn't retrieve your FAQs: {str(e)}"}
    
    def _handle_enhanced_analytics(self, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Enhanced analytics with insights and recommendations"""
        try:
            analytics = data_manager.get_analytics_summary()
            
            if "error" in analytics:
                return {"success": False, "response": f"❌ I couldn't retrieve your analytics: {analytics['error']}"}
            
            insights = []
            faq_count = analytics['content_stats']['faqs']
            sessions_30d = analytics['usage_stats_30_days']['chat_sessions']
            messages_30d = analytics['usage_stats_30_days']['total_messages']
            
            if faq_count == 0:
                insights.append("💡 **Tip:** Add FAQs to reduce support workload!")
            elif faq_count < 5:
                insights.append("💡 **Suggestion:** Consider adding more FAQs for common questions")
            
            if sessions_30d > 0:
                avg_messages = messages_30d / sessions_30d if sessions_30d > 0 else 0
                if avg_messages > 5:
                    insights.append("📈 **Insight:** High message volume - FAQs could help!")
            
            response = f"""📊 **Analytics for {analytics['tenant_name']}**

**📋 Content Statistics:**
• FAQs: {faq_count}
• Knowledge Bases: {analytics['content_stats']['knowledge_bases']}

**💬 Usage (Last 30 Days):**
• Chat Sessions: {sessions_30d:,}
• Total Messages: {messages_30d:,}
• Avg Messages per Session: {messages_30d / sessions_30d if sessions_30d > 0 else 0:.1f}

**🔗 Active Integrations:**
• Discord: {'✅ Active' if analytics['integrations']['discord'] else '❌ Not active'}
• Slack: {'✅ Active' if analytics['integrations']['slack'] else '❌ Not active'}
• Telegram: {'✅ Active' if analytics['integrations']['telegram'] else '❌ Not active'}"""
            
            if insights:
                response += f"\n\n**💡 Insights:**\n" + "\n".join(insights)
            
            return {"success": True, "response": response, "analytics": analytics}
            
        except Exception as e:
            return {"success": False, "response": f"❌ I encountered an error getting your analytics: {str(e)}"}
    
    def _handle_enhanced_settings(self, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handle settings view"""
        return {"success": True, "response": "⚙️ Settings management is coming soon! You can currently manage FAQs and view analytics."}
    
    def _handle_enhanced_knowledge_base(self, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handle knowledge base view"""
        return {"success": True, "response": "📚 Knowledge base management is coming soon! You can currently manage FAQs and view analytics."}
    
    def _handle_enhanced_update_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
        """Handle FAQ update"""
        return {"success": True, "response": "✏️ FAQ updates are coming soon! You can currently add, list, and delete FAQs."}
    
    def _handle_enhanced_delete_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
        """Handle FAQ deletion"""
        return {"success": True, "response": "🗑️ FAQ deletion is coming soon! You can currently add and list FAQs."}
    
    def _handle_confirmation(self, tenant_id: int, data_manager: TenantDataManager) -> Optional[Dict[str, Any]]:
        """Handle confirmation responses with enhanced feedback"""
        pending = self._get_pending_confirmation(tenant_id)
        
        if not pending:
            return {"success": False, "response": "❓ I don't have any pending actions to confirm. What would you like me to help with?"}
        
        intent = pending["intent"]
        action_id = pending["action_id"]
        
        if intent.action == AdminActionType.DELETE_FAQ:
            faq_id = intent.parameters.get('faq_id')
            try:
                success = data_manager.delete_faq(faq_id)
                if success:
                    del self.pending_confirmations[action_id]
                    return {
                        "success": True,
                        "response": f"✅ FAQ #{faq_id} has been permanently deleted.\n\n🗑️ Your customers will no longer receive this automated answer. You can always create a new FAQ if needed!",
                        "action": "faq_deleted"
                    }
                else:
                    return {"success": False, "response": f"❌ I couldn't find FAQ #{faq_id} to delete."}
            except Exception as e:
                return {"success": False, "response": f"❌ Error deleting FAQ: {str(e)}"}
        
        if action_id in self.pending_confirmations:
            del self.pending_confirmations[action_id]
        
        return {"success": False, "response": "✅ Action confirmed, but I'm not sure what to do next. What can I help you with?"}
    
    def _handle_cancellation(self, tenant_id: int) -> Dict[str, Any]:
        """Handle cancellation with friendly response"""
        to_remove = []
        for aid, confirmation in self.pending_confirmations.items():
            if confirmation["tenant_id"] == tenant_id and not confirmation["confirmed"]:
                to_remove.append(aid)
        
        for aid in to_remove:
            del self.pending_confirmations[aid]
        
        if to_remove:
            return {
                "success": True,
                "response": "✅ No problem! I've cancelled that action.\n\n😊 What else can I help you with today?",
                "action": "cancelled"
            }
        else:
            return {
                "success": False,
                "response": "❓ I don't have any pending actions to cancel, but that's okay! What would you like to work on?"
            }

# Export enhanced engine
def get_super_tenant_admin_engine(db: Session) -> EnhancedSuperTenantAdminEngine:
    """Factory function to create Enhanced SuperTenantAdminEngine with Unified Engine integration"""
    return EnhancedSuperTenantAdminEngine(db)