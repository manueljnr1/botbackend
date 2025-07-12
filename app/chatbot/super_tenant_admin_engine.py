


# # app/chatbot/enhanced_super_tenant_admin_engine.py
# """
# Enhanced Super Tenant Admin Engine with LLM Integration + Unified Engine
# Provides intelligent, conversational tenant administration with efficiency
# """

# import logging
# import uuid
# from typing import Dict, Any, Optional, Tuple, List
# from sqlalchemy.orm import Session
# from datetime import datetime

# from app.chatbot.admin_intent_parser import get_llm_admin_intent_parser, AdminActionType, ParsedIntent
# from app.chatbot.tenant_data_manager import TenantDataManager, TenantSecurityError
# from app.chatbot.simple_memory import SimpleChatbotMemory
# from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
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
#     LLM-Enhanced admin engine with Unified Engine integration
#     Provides intelligent, conversational administration with 80% token efficiency
#     """
    
#     def __init__(self, db: Session):
#         self.db = db
#         self.intent_parser = get_llm_admin_intent_parser()
        
#         # 🆕 Initialize unified engine for efficient processing
#         self.unified_engine = get_unified_intelligent_engine(db)
        
#         # Initialize LLM for response generation
#         self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
#         if self.llm_available:
#             self.llm = ChatOpenAI(
#                 model_name="gpt-3.5-turbo",
#                 temperature=0.3,
#                 openai_api_key=settings.OPENAI_API_KEY
#             )
        
#         # Store pending confirmations
#         self.pending_confirmations: Dict[str, AdminConfirmation] = {}
        
#         logger.info("🤖 Enhanced SuperTenantAdminEngine initialized with Unified Engine support")
    
#     def process_admin_message(
#         self, 
#         user_message: str, 
#         authenticated_tenant_id: int, 
#         user_identifier: str,
#         session_context: Dict[str, Any] = None
#     ) -> Dict[str, Any]:
#         """
#         Process admin message with unified engine efficiency + admin capabilities
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
            
#             # Parse admin intent
#             intent = self.intent_parser.parse(user_message)
#             if conversation_history:
#                 intent = self.intent_parser.enhance_with_context(intent, conversation_history)
            
#             # 🆕 UNIFIED ENGINE ROUTING: Check if this needs admin engine or can use unified
#             if self._should_use_unified_engine(intent, user_message, session_context):
#                 result = self._process_with_unified_engine(
#                     user_message, authenticated_tenant_id, user_identifier, intent, session_context
#                 )
#             else:
#                 # Use dedicated admin processing
#                 result = self._execute_enhanced_admin_action(
#                     intent, data_manager, authenticated_tenant_id, conversation_history
#                 )
            
#             # Store bot response
#             memory.store_message(session_id, result["response"], False)
            
#             # Log admin action for audit
#             data_manager.log_admin_action(
#                 action=intent.action.value,
#                 details={
#                     "user_message": user_message,
#                     "confidence": intent.confidence,
#                     "llm_reasoning": intent.llm_reasoning,
#                     "success": result.get("success", False),
#                     "processing_method": result.get("processing_method", "admin_engine")
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
    
#     def _should_use_unified_engine(self, intent: ParsedIntent, user_message: str, session_context: Dict[str, Any]) -> bool:
#         """Determine if we should use unified engine vs dedicated admin processing"""
        
#         # Use unified engine for conversational/informational intents
#         unified_engine_intents = [
#             AdminActionType.GREETING,
#             AdminActionType.HELP,
#             AdminActionType.UNKNOWN
#         ]
        
#         if intent.action in unified_engine_intents:
#             return True
        
#         # Use unified engine for questions that don't require admin actions
#         question_patterns = [
#             "what", "how", "why", "explain", "tell me about", "what's", "how do"
#         ]
        
#         if any(pattern in user_message.lower() for pattern in question_patterns):
#             # If it's a question about admin functionality, keep in admin engine
#             admin_keywords = ["faq", "analytics", "settings", "integration", "discord", "slack"]
#             if not any(keyword in user_message.lower() for keyword in admin_keywords):
#                 return True
        
#         return False
    
#     def _process_with_unified_engine(self, user_message: str, tenant_id: int, user_identifier: str,
#                                    intent: ParsedIntent, session_context: Dict[str, Any]) -> Dict[str, Any]:
#         """Process using unified engine with admin context"""
#         try:
#             # Get tenant for unified engine
#             tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
#             if not tenant:
#                 return {"success": False, "response": "❌ Tenant not found"}
            
#             # Create admin-aware API key context (use tenant's actual API key)
#             api_key = tenant.api_key
            
#             # 🆕 Use unified engine for efficient processing
#             unified_result = self.unified_engine.process_message(
#                 api_key=api_key,
#                 user_message=user_message,
#                 user_identifier=user_identifier,
#                 platform="admin_web"
#             )
            
#             if unified_result.get("success"):
#                 # Enhance response with admin context
#                 admin_enhanced_response = self._enhance_response_for_admin(
#                     unified_result["response"], intent, tenant
#                 )
                
#                 return {
#                     "success": True,
#                     "response": admin_enhanced_response,
#                     "action": intent.action.value,
#                     "processing_method": "unified_engine",
#                     "token_efficiency": unified_result.get("token_efficiency"),
#                     "admin_mode": True,
#                     "tenant_id": tenant_id
#                 }
#             else:
#                 # Fallback to admin engine if unified fails
#                 return self._generate_admin_fallback_response(intent, user_message)
                
#         except Exception as e:
#             logger.error(f"Error in unified engine processing: {e}")
#             return self._generate_admin_fallback_response(intent, user_message)
    
#     def _enhance_response_for_admin(self, response: str, intent: ParsedIntent, tenant: Tenant) -> str:
#         """Enhance unified engine response with admin-specific context"""
        
#         if intent.action == AdminActionType.GREETING:
#             # Add admin capabilities to greeting
#             business_name = getattr(tenant, 'business_name', tenant.name)
#             admin_suffix = f"\n\n💼 **Admin Options:** I can help you manage {business_name}'s FAQs, view analytics, update settings, and configure integrations. What would you like to work on?"
#             return response + admin_suffix
            
#         elif intent.action == AdminActionType.HELP:
#             # Replace generic help with admin help
#             return self.intent_parser.get_help_text()
            
#         elif intent.action == AdminActionType.UNKNOWN:
#             # Add admin suggestions to unknown responses
#             admin_suffix = "\n\n💡 **Admin Suggestions:**\n• 'Show my FAQs'\n• 'View analytics'\n• 'Help with settings'\n• 'List integrations'"
#             return response + admin_suffix
        
#         return response
    
#     def _generate_admin_fallback_response(self, intent: ParsedIntent, user_message: str) -> Dict[str, Any]:
#         """Generate fallback response when unified engine fails"""
        
#         fallback_responses = {
#             AdminActionType.GREETING: "Hello! 👋 I'm your admin assistant. I can help manage FAQs, analytics, settings, and integrations. What would you like to do?",
#             AdminActionType.HELP: self.intent_parser.get_help_text(),
#             AdminActionType.UNKNOWN: "🤔 I'm not sure about that. Try asking about FAQs, analytics, settings, or integrations. Type 'help' for more options."
#         }
        
#         response = fallback_responses.get(
#             intent.action, 
#             "I'm here to help with your admin tasks. What would you like to work on?"
#         )
        
#         return {
#             "success": True,
#             "response": response,
#             "action": intent.action.value,
#             "processing_method": "admin_fallback"
#         }
    
#     # Keep all existing methods unchanged...
#     def _handle_follow_up_responses(self, user_message: str, tenant_id: int, data_manager: TenantDataManager, conversation_history: List[Dict]) -> Optional[Dict[str, Any]]:
#         """Handle follow-up responses using LLM to understand context"""
#         message_lower = user_message.lower().strip()
        
#         if message_lower in ['yes', 'y', 'confirm', 'proceed', 'do it', 'go ahead']:
#             return self._handle_confirmation(tenant_id, data_manager)
        
#         if message_lower in ['no', 'n', 'cancel', 'abort', 'stop', 'nevermind']:
#             return self._handle_cancellation(tenant_id)
        
#         if self.llm_available and conversation_history:
#             follow_up_result = self._analyze_follow_up_with_llm(
#                 user_message, conversation_history, tenant_id, data_manager
#             )
#             if follow_up_result:
#                 return follow_up_result
        
#         return None
    
#     def _analyze_follow_up_with_llm(self, user_message: str, conversation_history: List[Dict], tenant_id: int, data_manager: TenantDataManager) -> Optional[Dict[str, Any]]:
#         """Use LLM to analyze if current message is a follow-up to previous conversation"""
#         try:
#             last_bot_message = None
#             for msg in reversed(conversation_history):
#                 if msg.get("role") == "assistant":
#                     last_bot_message = msg.get("content", "")
#                     break
            
#             if not last_bot_message:
#                 return None
            
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
                    
#                     if followup_type == "confirmation" and pending:
#                         return self._handle_confirmation(tenant_id, data_manager)
#                     elif followup_type in ["information", "answer"]:
#                         return self._handle_information_follow_up(user_message, tenant_id, data_manager, pending)
        
#         except Exception as e:
#             logger.error(f"Error analyzing follow-up with LLM: {e}")
        
#         return None
    
#     def _handle_information_follow_up(self, user_message: str, tenant_id: int, data_manager: TenantDataManager, pending: Optional[AdminConfirmation]) -> Optional[Dict[str, Any]]:
#         """Handle when user provides additional information in follow-up"""
#         if not pending:
#             return None
        
#         intent = pending["intent"]
#         action_id = pending["action_id"]
        
#         if intent.action == AdminActionType.ADD_FAQ:
#             if self.llm_available:
#                 faq_params = self.intent_parser.extract_faq_parameters_llm(user_message)
#             else:
#                 faq_params = {}
            
#             existing_question = intent.parameters.get('question')
#             existing_answer = intent.parameters.get('answer')
            
#             new_question = faq_params.get('question') or existing_question
#             new_answer = faq_params.get('answer') or existing_answer
            
#             if new_question and new_answer:
#                 try:
#                     faq = data_manager.create_faq(new_question, new_answer)
#                     del self.pending_confirmations[action_id]
                    
#                     return {
#                         "success": True,
#                         "response": f"✅ Perfect! I've created your FAQ:\n\n**Question:** {new_question}\n**Answer:** {new_answer}\n\n**FAQ ID:** #{faq.id}",
#                         "action": "faq_created",
#                         "faq_id": faq.id
#                     }
#                 except Exception as e:
#                     return {"success": False, "response": f"❌ Failed to create FAQ: {str(e)}"}
            
#             elif new_question and not new_answer:
#                 intent.parameters['question'] = new_question
#                 return {
#                     "success": False,
#                     "response": f"📝 Got it! The question is: '{new_question}'\n\nNow, what should the answer be?",
#                     "requires_input": True
#                 }
            
#             elif new_answer and not new_question:
#                 intent.parameters['answer'] = new_answer
#                 return {
#                     "success": False,
#                     "response": f"📝 Perfect answer: '{new_answer}'\n\nWhat should the question be?",
#                     "requires_input": True
#                 }
        
#         return None
    
#     def _get_pending_confirmation(self, tenant_id: int) -> Optional[AdminConfirmation]:
#         """Get pending confirmation for tenant"""
#         for confirmation in self.pending_confirmations.values():
#             if confirmation["tenant_id"] == tenant_id and not confirmation["confirmed"]:
#                 return confirmation
#         return None
    
#     def _execute_enhanced_admin_action(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int, conversation_history: List[Dict] = None) -> Dict[str, Any]:
#         """Execute admin action with LLM-enhanced responses"""
        
#         if intent.action == AdminActionType.ADD_FAQ:
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
#         else:
#             return {
#                 "success": False,
#                 "response": f"🚧 I understand you want to {intent.action.value.replace('_', ' ')}, but that feature is still in development. Is there something else I can help you with?",
#                 "action": "not_implemented"
#             }
    
#     def _handle_enhanced_add_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
#         """Enhanced FAQ addition with intelligent parameter extraction"""
#         question = intent.parameters.get('question')
#         answer = intent.parameters.get('answer')
        
#         if not question and not answer:
#             if self.llm_available:
#                 faq_params = self.intent_parser.extract_faq_parameters_llm(intent.original_text)
#                 question = faq_params.get('question')
#                 answer = faq_params.get('answer')
        
#         if question and answer:
#             try:
#                 faq = data_manager.create_faq(question, answer)
#                 return {
#                     "success": True,
#                     "response": f"✅ Perfect! I've created your new FAQ:\n\n**Question:** {question}\n**Answer:** {answer}\n\n**FAQ ID:** #{faq.id}\n\nYour customers will now get this answer when they ask about this topic!",
#                     "action": "faq_created",
#                     "faq_id": faq.id
#                 }
#             except Exception as e:
#                 return {"success": False, "response": f"❌ I encountered an error creating your FAQ: {str(e)}"}
        
#         elif question and not answer:
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
#             faqs = data_manager.get_faqs(limit=20)
            
#             if not faqs:
#                 return {
#                     "success": True,
#                     "response": "📋 You don't have any FAQs yet!\n\n💡 **Let's create your first one:**\nJust tell me something like: 'Add FAQ about business hours - we're open 9-5 weekdays'\n\nFAQs help your chatbot answer common questions automatically! 🚀"
#                 }
            
#             if len(faqs) > 10:
#                 response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
#                 for i, faq in enumerate(faqs, 1):
#                     response += f"**#{faq.id}** {faq.question[:60]}{'...' if len(faq.question) > 60 else ''}\n"
#                     if i >= 15:
#                         response += f"\n*...and {len(faqs) - 15} more FAQs*\n"
#                         break
#             else:
#                 response = f"📋 **Your FAQs ({len(faqs)} total):**\n\n"
#                 for faq in faqs:
#                     response += f"**#{faq.id}** {faq.question}\n"
            
#             response += f"\n💡 **What you can do:**\n• Update: 'Modify FAQ #{faqs[0].id}'\n• Delete: 'Remove FAQ #{faqs[0].id}'\n• Add new: 'Create FAQ about [topic]'"
            
#             return {"success": True, "response": response, "faq_count": len(faqs)}
            
#         except Exception as e:
#             return {"success": False, "response": f"❌ I couldn't retrieve your FAQs: {str(e)}"}
    
#     def _handle_enhanced_analytics(self, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Enhanced analytics with insights and recommendations"""
#         try:
#             analytics = data_manager.get_analytics_summary()
            
#             if "error" in analytics:
#                 return {"success": False, "response": f"❌ I couldn't retrieve your analytics: {analytics['error']}"}
            
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
            
#             return {"success": True, "response": response, "analytics": analytics}
            
#         except Exception as e:
#             return {"success": False, "response": f"❌ I encountered an error getting your analytics: {str(e)}"}
    
#     def _handle_enhanced_settings(self, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handle settings view"""
#         return {"success": True, "response": "⚙️ Settings management is coming soon! You can currently manage FAQs and view analytics."}
    
#     def _handle_enhanced_knowledge_base(self, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handle knowledge base view"""
#         return {"success": True, "response": "📚 Knowledge base management is coming soon! You can currently manage FAQs and view analytics."}
    
#     def _handle_enhanced_update_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
#         """Handle FAQ update"""
#         return {"success": True, "response": "✏️ FAQ updates are coming soon! You can currently add, list, and delete FAQs."}
    
#     def _handle_enhanced_delete_faq(self, intent: ParsedIntent, data_manager: TenantDataManager, tenant_id: int) -> Dict[str, Any]:
#         """Handle FAQ deletion"""
#         return {"success": True, "response": "🗑️ FAQ deletion is coming soon! You can currently add and list FAQs."}
    
#     def _handle_confirmation(self, tenant_id: int, data_manager: TenantDataManager) -> Optional[Dict[str, Any]]:
#         """Handle confirmation responses with enhanced feedback"""
#         pending = self._get_pending_confirmation(tenant_id)
        
#         if not pending:
#             return {"success": False, "response": "❓ I don't have any pending actions to confirm. What would you like me to help with?"}
        
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
#                     return {"success": False, "response": f"❌ I couldn't find FAQ #{faq_id} to delete."}
#             except Exception as e:
#                 return {"success": False, "response": f"❌ Error deleting FAQ: {str(e)}"}
        
#         if action_id in self.pending_confirmations:
#             del self.pending_confirmations[action_id]
        
#         return {"success": False, "response": "✅ Action confirmed, but I'm not sure what to do next. What can I help you with?"}
    
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
#     """Factory function to create Enhanced SuperTenantAdminEngine with Unified Engine integration"""
#     return EnhancedSuperTenantAdminEngine(db)




# app/chatbot/super_tenant_admin_engine.py
"""
Refactored Super Tenant Admin Engine with Conversational State Management
Provides an intelligent, stateful, and natural tenant administration experience.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.chatbot.admin_intent_parser import get_llm_admin_intent_parser, AdminActionType, ParsedIntent
from app.chatbot.tenant_data_manager import TenantDataManager, TenantSecurityError
from app.chatbot.simple_memory import SimpleChatbotMemory
from app.tenants.models import Tenant
from app.config import settings

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

# NEW: State management class to track conversation context
class AdminConversationState:
    """Tracks the state of an admin conversation for more natural multi-turn dialogue."""
    def __init__(self, user_identifier: str, tenant_id: int):
        self.user_identifier = user_identifier
        self.tenant_id = tenant_id
        self.current_intent: Optional[AdminActionType] = None
        self.required_params: Dict[str, Any] = {}
        self.pending_confirmation: bool = False
        self.last_interaction = datetime.utcnow()
        self.context_data: Dict[str, Any] = {} # Store things like a recently viewed FAQ ID
        # --- ADDITION ---: Added this attribute to track the last action for suggestions
        self.last_intent_for_suggestion: Optional[AdminActionType] = None


    def is_expired(self, timeout_minutes: int = 10) -> bool:
        """Check if the conversation state has timed out."""
        return datetime.utcnow() > self.last_interaction + timedelta(minutes=timeout_minutes)

    def update_state(self, intent: ParsedIntent, required_params: Dict[str, Any] = None):
        """Update the state with a new intent and required parameters."""
        self.current_intent = intent.action
        self.required_params = required_params or {}
        self.pending_confirmation = intent.requires_confirmation
        self.last_interaction = datetime.utcnow()
        # Also update the suggestion tracker
        self.last_intent_for_suggestion = self.current_intent


    def add_context(self, key: str, value: Any):
        """Add data to the conversation context."""
        self.context_data[key] = value

    def clear(self):
        """Reset the conversation state."""
        self.current_intent = None
        self.required_params = {}
        self.pending_confirmation = False
        self.context_data = {}
        self.last_intent_for_suggestion = None


class RefactoredSuperTenantAdminEngine:
    """
    A refactored admin engine that uses conversational state management for a more
    natural and robust user experience.
    """
    def __init__(self, db: Session):
        self.db = db
        self.intent_parser = get_llm_admin_intent_parser()
        self.active_conversations: Dict[str, AdminConversationState] = {}

        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-4o", # Using a more advanced model for better reasoning
                temperature=0.4,
                openai_api_key=settings.OPENAI_API_KEY
            )
        logger.info("🤖 Refactored SuperTenantAdminEngine initialized.")

    def _get_or_create_conversation_state(self, user_identifier: str, tenant_id: int) -> AdminConversationState:
        """Gets or creates a state for the current conversation."""
        state = self.active_conversations.get(user_identifier)
        if not state or state.is_expired():
            state = AdminConversationState(user_identifier, tenant_id)
            self.active_conversations[user_identifier] = state
        state.last_interaction = datetime.utcnow() # Keep state alive
        return state

    # --- FUNCTION REPLACED ---
    def process_admin_message(
        self,
        user_message: str,
        authenticated_tenant_id: int,
        user_identifier: str,
        session_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Main processing loop using the new stateful conversational approach.
        """
        try:
            data_manager = TenantDataManager(self.db, authenticated_tenant_id)
            memory = SimpleChatbotMemory(self.db, authenticated_tenant_id)
            session_id, _ = memory.get_or_create_session(user_identifier, "admin_web")
            conversation_history = memory.get_conversation_history(user_identifier, max_messages=10)

            memory.store_message(session_id, user_message, True)

            # Get the current state of the conversation
            state = self._get_or_create_conversation_state(user_identifier, authenticated_tenant_id)

            # Correct two-step process: First parse the intent, then enhance it with context.
            # 1. Get the basic intent from the user's current message.
            initial_intent = self.intent_parser.parse(user_message)
            # 2. Enhance the initial intent using the conversation state and history.
            intent = self.intent_parser.enhance_with_context(initial_intent, state, conversation_history)


            # If the LLM determines this message completes a pending action, execute it
            if state.current_intent and self._message_completes_action(intent, state):
                # Populate the final required parameters from the new message
                state.required_params.update(intent.parameters)
                result = self._execute_action(state, data_manager)
            # If it's a new intent, handle it
            else:
                state.update_state(intent) # Update state with the new intent
                result = self._execute_action(state, data_manager)

            # NEW: Proactive suggestions after a successful action
            if result.get("success") and not state.pending_confirmation and not state.required_params:
                suggestion = self._get_proactive_suggestion(state, data_manager)
                if suggestion:
                    result["response"] += f"\n\n{suggestion}"

            memory.store_message(session_id, result["response"], False)
            data_manager.log_admin_action(
                action=intent.action.value,
                details={"user_message": user_message, "success": result.get("success", False)}
            )
            return result

        except TenantSecurityError as e:
            logger.error(f"🚨 Security error in admin processing: {e}")
            return {"success": False, "response": "⛔ Access denied. You can only manage your own tenant data."}
        except Exception as e:
            logger.error(f"💥 Error processing admin message: {e}", exc_info=True)
            return {"success": False, "response": "❌ I encountered an error. Please try again."}

    def _execute_action(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Executes the action defined in the current state or asks for more info."""
        # Check if all required parameters are present
        missing_params = [p for p in state.required_params if p not in state.context_data and p not in state.required_params]

        if missing_params:
            # We need more information from the user
            return self._ask_for_missing_info(state, missing_params)

        if state.pending_confirmation:
            # We need confirmation from the user
            return self._ask_for_confirmation(state)

        # All parameters and confirmations are present, execute the action
        action_method = getattr(self, f"_action_{state.current_intent.value}", self._action_unknown)
        result = action_method(state, data_manager)

        # Clear state after successful execution
        if result.get("success"):
            state.clear()

        return result

    # --- FUNCTION ADDED ---
    def _message_completes_action(self, intent: ParsedIntent, state: AdminConversationState) -> bool:
        """
        Determines if the new message provides the necessary info or confirmation to complete the pending action.
        This is a key decision point in the conversational flow.
        """
        if not state.current_intent:
            return False

        # Scenario 1: User explicitly confirms a pending action (e.g., says "yes" to a deletion).
        if state.pending_confirmation and intent.action == AdminActionType.CONFIRM:
            # We were waiting for a 'yes', and we got it. The action is complete.
            state.pending_confirmation = False # No longer needs confirmation
            logger.info(f"✅ Confirmation received for action: {state.current_intent.value}")
            return True

        # Scenario 2: User provides the last piece of missing information.
        if state.required_params:
            # Check if any of the keys in the newly parsed parameters match what we need.
            provided_params = [p for p in state.required_params if p in intent.parameters]
            if provided_params:
                # User has provided some of the data we were waiting for.
                # We can now consider this part of the action "complete".
                # The main loop will update the state with this new info.
                logger.info(f"✅ User provided missing parameters: {provided_params}")
                # This logic is handled in the main loop, so we return true to proceed with execution.
                return True

        return False

    # --- FUNCTION ADDED ---
    def _get_proactive_suggestion(self, state: AdminConversationState, data_manager: TenantDataManager) -> Optional[str]:
        """
        After a successful action, use the LLM to suggest a logical next step to the user,
        making the chatbot feel more like a helpful assistant.
        """
        if not self.llm_available or not state.last_intent_for_suggestion:
            return None

        try:
            template = """A user, a business owner named {tenant_name}, just successfully completed an admin action for their chatbot. Based on their last action, suggest a relevant and helpful next step. Keep the suggestion brief and conversational.

            Last Action Completed: "{last_action}"

            Contextual Information:
            - If they listed FAQs, you could suggest they update or delete one.
            - If they added an FAQ, you could ask if they want to add another or view the list.
            - If they viewed analytics showing high traffic, you could suggest adding more FAQs.
            - If they updated a setting, you could ask them to view all settings to confirm.

            Your helpful, one-sentence suggestion:"""

            context = {
                "last_action": state.last_intent_for_suggestion.value,
                "tenant_name": data_manager.tenant.business_name
            }

            prompt = PromptTemplate.from_template(template)
            response = self.llm.invoke(prompt.format(**context))
            suggestion = response.content.strip()

            logger.info(f"💡 Proactive suggestion generated for action '{context['last_action']}': {suggestion}")
            return suggestion

        except Exception as e:
            logger.error(f"Failed to generate proactive suggestion: {e}")
            return None


    # --- Dynamic Response and Suggestion Methods ---

    def _generate_dynamic_response(self, prompt_template: str, context: Dict[str, Any]) -> str:
        """Generates a natural, non-templated response using the LLM."""
        if not self.llm_available:
            return "Got it. What's next?" # Simple fallback

        try:
            prompt = PromptTemplate.from_template(prompt_template)
            response = self.llm.invoke(prompt.format(**context))
            return response.content.strip()
        except Exception as e:
            logger.error(f"Dynamic response generation failed: {e}")
            return "I'm having a little trouble formulating a response. Could you try again?"


    # --- Methods for asking for more info/confirmation ---

    def _ask_for_missing_info(self, state: AdminConversationState, missing_params: List[str]) -> Dict[str, Any]:
        """Asks the user for the information needed to complete an action."""
        param_list = " and ".join(missing_params)
        template = "To do that, I just need the following information: {params}. What should it be?"
        response = self._generate_dynamic_response(template, {"params": param_list})
        return {"success": False, "response": response, "requires_input": True}

    def _ask_for_confirmation(self, state: AdminConversationState) -> Dict[str, Any]:
        """Asks the user to confirm a destructive action."""
        template = "Are you sure you want to {action_description}? This action cannot be undone."
        # The description would be dynamically generated based on the intent
        action_description = f"delete the FAQ #{state.context_data.get('faq_id')}"
        response = self._generate_dynamic_response(template, {"action_description": action_description})
        return {"success": False, "response": response, "requires_confirmation": True}

    # --- Specific Action Implementation Methods ---
    # These methods are called by _execute_action.

    def _action_greeting(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handles a greeting from the admin user."""
        state.last_intent_for_suggestion = AdminActionType.GREETING
        tenant_name = data_manager.tenant.business_name
        response = self._generate_dynamic_response(
            "Hello! I'm ready to help you manage the chatbot for {tenant_name}. What can I assist you with today? You can ask me to add an FAQ, view analytics, and more.",
            {"tenant_name": tenant_name}
        )
        return {"success": True, "response": response}



    def _action_add_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        params = state.required_params
        faq = data_manager.create_faq(question=params['question'], answer=params['answer'])
        state.add_context("last_faq_id", faq.id)
        state.last_intent_for_suggestion = AdminActionType.ADD_FAQ
        response = self._generate_dynamic_response(
            "I've successfully added that new FAQ for you (ID #{faq_id}). Your chatbot is now smarter!"
            # {"faq_id": faq.id}
        )
        return {"success": True, "response": response}

    def _action_list_faqs(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        faqs = data_manager.get_faqs(limit=20)
        if not faqs:
            return {"success": True, "response": "You don't have any FAQs yet. Let's create one! Just tell me what question to add."}

        faq_list = "\n".join([f"• **#{faq.id}**: {faq.question}" for faq in faqs])
        state.last_intent_for_suggestion = AdminActionType.LIST_FAQS
        response = self._generate_dynamic_response(
            "Here are your current FAQs:\n{faq_list}",
            {"faq_list": faq_list}
        )
        return {"success": True, "response": response}

    def _action_view_analytics(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        analytics = data_manager.get_analytics_summary()
        # A real implementation would format this nicely.
        response = self._generate_dynamic_response(
            "Here are your analytics for the last 30 days:\n- Sessions: {sessions}\n- Messages: {messages}",
            {
                "sessions": analytics['usage_stats_30_days']['chat_sessions'],
                "messages": analytics['usage_stats_30_days']['total_messages']
            }
        )
        state.last_intent_for_suggestion = AdminActionType.VIEW_ANALYTICS
        return {"success": True, "response": response}

    def _action_unknown(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        response = self._generate_dynamic_response(
            "I'm not quite sure how to help with that. Could you try rephrasing? You can also ask for 'help' to see what I can do.",
            {}
        )
        return {"success": False, "response": response}

    def _action_confirm(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        # This action is handled by the main loop, but we need a placeholder
        return {"success": True, "response": "Confirmed."}



    def _action_help(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Provides a helpful message listing the bot's capabilities."""
        state.last_intent_for_suggestion = AdminActionType.HELP
        # The get_help_text() method is already available in the intent parser
        help_text = self.intent_parser.get_help_text()
        return {"success": True, "response": help_text}

    def _action_delete_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handles deleting an FAQ."""
        # This is a placeholder for the full implementation
        state.last_intent_for_suggestion = AdminActionType.DELETE_FAQ
        faq_id = state.required_params.get('faq_id', 'unknown')
        # A real implementation would confirm the deletion
        response = f"This is where the logic to delete FAQ #{faq_id} would go. This feature is coming soon!"
        return {"success": True, "response": response}

    def _action_update_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handles updating an FAQ."""
        # This is a placeholder for the full implementation
        state.last_intent_for_suggestion = AdminActionType.UPDATE_FAQ
        faq_id = state.required_params.get('faq_id', 'unknown')
        response = f"This is where the logic to update FAQ #{faq_id} would go. This feature is coming soon!"
        return {"success": True, "response": response}

    def _action_view_settings(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """Handles viewing tenant settings."""
        state.last_intent_for_suggestion = AdminActionType.VIEW_SETTINGS
        settings = data_manager.get_tenant_settings()
        # A real implementation would format this nicely
        response = f"Your current business name is {settings.get('business_name')}. The full settings view is coming soon!"
        return {"success": True, "response": response}


# Factory function remains the same
def get_super_tenant_admin_engine(db: Session) -> "RefactoredSuperTenantAdminEngine":
    """Factory function to create the Refactored SuperTenantAdminEngine."""
    return RefactoredSuperTenantAdminEngine(db)