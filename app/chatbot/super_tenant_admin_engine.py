


# # app/chatbot/super_tenant_admin_engine.py
# """
# Refactored Super Tenant Admin Engine with Conversational State Management
# Provides an intelligent, stateful, and natural tenant administration experience.
# """

# import logging
# import uuid
# from typing import Dict, Any, Optional, List
# from sqlalchemy.orm import Session
# from datetime import datetime, timedelta

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

# # NEW: State management class to track conversation context
# class AdminConversationState:
#     """Tracks the state of an admin conversation for more natural multi-turn dialogue."""
#     def __init__(self, user_identifier: str, tenant_id: int):
#         self.user_identifier = user_identifier
#         self.tenant_id = tenant_id
#         self.current_intent: Optional[AdminActionType] = None
#         self.required_params: Dict[str, Any] = {}
#         self.pending_confirmation: bool = False
#         self.last_interaction = datetime.utcnow()
#         self.context_data: Dict[str, Any] = {} # Store things like a recently viewed FAQ ID
#         # --- ADDITION ---: Added this attribute to track the last action for suggestions
#         self.last_intent_for_suggestion: Optional[AdminActionType] = None


#     def is_expired(self, timeout_minutes: int = 10) -> bool:
#         """Check if the conversation state has timed out."""
#         return datetime.utcnow() > self.last_interaction + timedelta(minutes=timeout_minutes)

#     def update_state(self, intent: ParsedIntent, required_params: Dict[str, Any] = None):
#         """Update the state with a new intent and required parameters."""
#         self.current_intent = intent.action
#         self.required_params = required_params or {}
#         self.pending_confirmation = intent.requires_confirmation
#         self.last_interaction = datetime.utcnow()
#         # Also update the suggestion tracker
#         self.last_intent_for_suggestion = self.current_intent


#     def add_context(self, key: str, value: Any):
#         """Add data to the conversation context."""
#         self.context_data[key] = value

#     def clear(self):
#         """Reset the conversation state."""
#         self.current_intent = None
#         self.required_params = {}
#         self.pending_confirmation = False
#         self.context_data = {}
#         self.last_intent_for_suggestion = None


# class RefactoredSuperTenantAdminEngine:
#     """
#     A refactored admin engine that uses conversational state management for a more
#     natural and robust user experience.
#     """
#     def __init__(self, db: Session):
#         self.db = db
#         self.intent_parser = get_llm_admin_intent_parser()
#         self.active_conversations: Dict[str, AdminConversationState] = {}

#         self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
#         if self.llm_available:
#             self.llm = ChatOpenAI(
#                 model_name="gpt-3.5-turbo",
#                 temperature=0.4,
#                 openai_api_key=settings.OPENAI_API_KEY
#             )
#         logger.info("🤖 Refactored SuperTenantAdminEngine initialized.")

#     def _get_or_create_conversation_state(self, user_identifier: str, tenant_id: int) -> AdminConversationState:
#         """Gets or creates a state for the current conversation."""
#         state = self.active_conversations.get(user_identifier)
#         if not state or state.is_expired():
#             state = AdminConversationState(user_identifier, tenant_id)
#             self.active_conversations[user_identifier] = state
#         state.last_interaction = datetime.utcnow() # Keep state alive
#         return state

#     # --- FUNCTION REPLACED ---
#     def process_admin_message(
#         self,
#         user_message: str,
#         authenticated_tenant_id: int,
#         user_identifier: str,
#         session_context: Dict[str, Any] = None
#     ) -> Dict[str, Any]:
#         """
#         Main processing loop using LLM mediation instead of rigid intent parsing
#         """
#         try:
#             data_manager = TenantDataManager(self.db, authenticated_tenant_id)
#             memory = SimpleChatbotMemory(self.db, authenticated_tenant_id)
#             session_id, _ = memory.get_or_create_session(user_identifier, "admin_web")
#             conversation_history = memory.get_conversation_history(user_identifier, max_messages=10)

#             memory.store_message(session_id, user_message, True)

#             # Get the current state of the conversation
#             state = self._get_or_create_conversation_state(user_identifier, authenticated_tenant_id)
            
#             # Get tenant for mediation context
#             tenant = self.db.query(Tenant).filter(Tenant.id == authenticated_tenant_id).first()

#             # 🆕 NEW: Use LLM mediator instead of rigid intent parsing
#             result = self._admin_llm_mediator(
#                 user_message=user_message,
#                 state=state,
#                 tenant=tenant,
#                 conversation_history=conversation_history
#             )

#             # 🆕 NEW: Proactive suggestions after successful mediated actions
#             if result.get("success") and not state.pending_confirmation and not state.required_params:
#                 suggestion = self._get_proactive_suggestion(state, data_manager)
#                 if suggestion:
#                     result["response"] += f"\n\n{suggestion}"

#             memory.store_message(session_id, result["response"], False)
#             data_manager.log_admin_action(
#                 action=result.get("action", "mediated_action"),
#                 details={
#                     "user_message": user_message, 
#                     "success": result.get("success", False),
#                     "llm_mediated": result.get("llm_mediated", False),
#                     "mediation_confidence": result.get("mediation_confidence")
#                 }
#             )
#             return result

#         except TenantSecurityError as e:
#             logger.error(f"🚨 Security error in admin processing: {e}")
#             return {"success": False, "response": "⛔ Access denied. You can only manage your own tenant data."}
#         except Exception as e:
#             logger.error(f"💥 Error processing admin message: {e}", exc_info=True)
#             return {"success": False, "response": "❌ I encountered an error. Please try again."}
    


#     def _admin_llm_mediator(self, user_message: str, state: AdminConversationState, 
#                             tenant: Tenant, conversation_history: List[Dict] = None) -> Dict[str, Any]:
#         """
#         LLM mediator for admin requests - intelligently processes and routes admin tasks
#         Replaces rigid intent parsing with conversational understanding
#         """
        
#         if not self.llm_available:
#             return self._fallback_admin_routing(user_message, state)
        
#         try:
#             # Build rich context for admin mediation
#             admin_context = self._build_admin_mediation_context(state, tenant, conversation_history)
            
#             # Let LLM understand and route the admin request
#             mediation_result = self._mediate_admin_request(user_message, admin_context, state)
            
#             # Execute the mediated action - ADD DATA_MANAGER
#             from app.chatbot.tenant_data_manager import TenantDataManager
#             data_manager = TenantDataManager(self.db, tenant.id)
            
#             return self._execute_mediated_admin_action(mediation_result, state, data_manager)
            
#         except Exception as e:
#             logger.error(f"Admin LLM mediation failed: {e}")
#             return self._fallback_admin_routing(user_message, state)


#     def _mediate_admin_request(self, user_message: str, admin_context: str, 
#                             state: AdminConversationState) -> Dict[str, Any]:
#         """Core LLM mediation for admin requests"""
        
#         prompt = f"""You are an intelligent admin assistant mediator. Analyze this admin request and determine the best action.

#     ADMIN CONTEXT:
#     {admin_context}

#     USER REQUEST: "{user_message}"

#     AVAILABLE ADMIN ACTIONS:
#     - FAQ Management: add_faq, update_faq, delete_faq, list_faqs
#     - Analytics: view_analytics, conversation_stats, usage_reports
#     - Settings: update_prompt, update_branding, email_config
#     - Integrations: setup_discord, setup_slack, setup_telegram
#     - General: help, greeting, clarification_needed

#     CONVERSATION STATE:
#     - Current Intent: {state.current_intent.value if state.current_intent else 'None'}
#     - Pending Confirmation: {state.pending_confirmation}
#     - Required Params: {list(state.required_params.keys()) if state.required_params else 'None'}

#     MEDIATION TASK:
#     1. Understand what the user really wants to accomplish
#     2. Determine if this continues their current task or starts a new one
#     3. Identify what information is needed to complete the task
#     4. Choose the most appropriate action and response style

#     RESPONSE FORMAT (JSON):
#     {{
#         "admin_action": "specific_action_name",
#         "confidence": 0.95,
#         "requires_parameters": ["param1", "param2"],
#         "requires_confirmation": true/false,
#         "conversation_flow": "continuation|new_task|clarification|completion",
#         "response_style": "direct|guided|conversational|supportive",
#         "user_intent_summary": "clear description of what user wants",
#         "reasoning": "why this action and approach"
#     }}

#     Mediation Analysis:"""

#         try:
#             result = self.llm.invoke(prompt)
#             import json, re
#             json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
#             if json_match:
#                 mediation = json.loads(json_match.group())
#                 logger.info(f"🧠 Admin mediation: {mediation.get('admin_action')} - {mediation.get('reasoning', '')[:50]}...")
#                 return mediation
#         except Exception as e:
#             logger.error(f"Admin mediation parsing failed: {e}")
        
#         return {"admin_action": "help", "confidence": 0.3, "conversation_flow": "clarification"}

#     def _build_admin_mediation_context(self, state: AdminConversationState, tenant: Tenant, 
#                                     conversation_history: List[Dict] = None) -> str:
#         """Build rich context for admin mediation"""
        
#         context_parts = []
        
#         # Tenant context
#         context_parts.append(f"Business: {tenant.business_name or tenant.name}")
#         context_parts.append(f"Tenant ID: {tenant.id}")
        
#         # Current state context
#         if state.current_intent:
#             context_parts.append(f"Currently working on: {state.current_intent.value.replace('_', ' ')}")
        
#         if state.context_data:
#             context_parts.append(f"Context data: {state.context_data}")
        
#         # Conversation history context
#         if conversation_history:
#             recent_topics = self._extract_admin_topics(conversation_history)
#             if recent_topics:
#                 context_parts.append(f"Recent topics: {recent_topics}")
            
#             user_expertise = self._assess_user_expertise(conversation_history)
#             context_parts.append(f"User expertise level: {user_expertise}")
        
#         # System capabilities context
#         context_parts.append("Available: FAQ management, Analytics, Settings, Integrations")
        
#         return "\n".join(context_parts)

#     # def _execute_mediated_admin_action(self, mediation_result: Dict, state: AdminConversationState, 
#     #                               data_manager: TenantDataManager) -> Dict[str, Any]:
#     #     """Execute the action determined by LLM mediation"""
        
#     #     admin_action = mediation_result.get('admin_action', 'help')
#     #     response_style = mediation_result.get('response_style', 'conversational')
        
#     #     # Update state based on mediation
#     #     from app.chatbot.admin_intent_parser import AdminActionType
#     #     try:
#     #         action_type = AdminActionType(admin_action)
#     #         state.update_state(
#     #             type('MockIntent', (), {
#     #                 'action': action_type,
#     #                 'requires_confirmation': mediation_result.get('requires_confirmation', False),
#     #                 'parameters': {}
#     #             })(),
#     #             required_params={param: None for param in mediation_result.get('requires_parameters', [])}
#     #         )
#     #     except ValueError:
#     #         action_type = AdminActionType.HELP
        
#     #     # Generate contextual response
#     #     response = self._generate_mediated_response(mediation_result, state, tenant)
        
#     #     return {
#     #         "success": True,
#     #         "response": response,
#     #         "action": admin_action,
#     #         "mediation_confidence": mediation_result.get('confidence', 0.7),
#     #         "conversation_flow": mediation_result.get('conversation_flow'),
#     #         "llm_mediated": True
#     #     }

#     def _generate_mediated_response(self, mediation_result: Dict, state: AdminConversationState, 
#                                 tenant: Tenant) -> str:
#         """Generate natural response based on mediation results"""
        
#         if not self.llm_available:
#             return f"I'll help you with {mediation_result.get('admin_action', 'your request')}"
        
#         response_style = mediation_result.get('response_style', 'conversational')
#         user_intent = mediation_result.get('user_intent_summary', 'your admin task')
#         admin_action = mediation_result.get('admin_action', 'unknown')
        
#         prompt = f"""Generate a natural admin assistant response based on this mediation:

#         MEDIATION RESULTS:
#         - Action: {admin_action}
#         - User Intent: {user_intent}
#         - Response Style: {response_style}
#         - Conversation Flow: {mediation_result.get('conversation_flow')}

#         BUSINESS CONTEXT:
#         - Company: {tenant.business_name or tenant.name}
#         - Current State: {state.current_intent.value if state.current_intent else 'Starting new task'}

#         RESPONSE GUIDELINES:
#         - Be natural and conversational, not robotic
#         - Use the {response_style} style appropriately
#         - Be helpful and efficient

#         CRITICAL ACTION-SPECIFIC RULES:
#         - For "greeting" actions: Respond with a simple, natural greeting. Do NOT assume any business accomplishments or reference setup tasks.
#         - For "help" actions: Provide clear guidance on available options
#         - For executable commands: Acknowledge what you'll help them accomplish
#         - For questions: Provide direct, helpful information

#         EXAMPLES:
#         - greeting → "Hello! How can I help you manage your chatbot today?"
#         - help → "I can help you manage FAQs, view analytics, update settings, and more. What would you like to do?"
#         - add_faq → "I'll help you add a new FAQ. What question would you like to add?"
#         - NOT for greetings → "Great job on setting up..." or "Would you like to add more FAQs?"

#         Generate a helpful, natural admin response:"""
        
#         try:
#             result = self.llm.invoke(prompt)
#             return result.content.strip()
#         except Exception as e:
#             logger.error(f"Mediated response generation failed: {e}")
#             return f"I understand you want to {user_intent}. Let me help you with that."



#     def _extract_admin_topics(self, conversation_history: List[Dict]) -> str:
#         """Extract admin-related topics from conversation"""
        
#         admin_keywords = []
#         for msg in conversation_history[-5:]:  # Last 5 messages
#             content = msg.get('content', '').lower()
#             if 'faq' in content: admin_keywords.append('FAQ')
#             if 'analytic' in content: admin_keywords.append('Analytics')
#             if 'setting' in content: admin_keywords.append('Settings')
#             if any(word in content for word in ['discord', 'slack', 'telegram']): 
#                 admin_keywords.append('Integrations')
        
#         return ', '.join(set(admin_keywords)) if admin_keywords else 'General admin'

#     def _assess_user_expertise(self, conversation_history: List[Dict]) -> str:
#         """Assess user's admin expertise level from conversation"""
        
#         user_messages = [msg.get('content', '') for msg in conversation_history if msg.get('role') == 'user']
        
#         # Simple heuristics
#         if len(user_messages) > 10:
#             return 'experienced'
#         elif any(word in ' '.join(user_messages).lower() for word in ['help', 'how', 'what', 'guide']):
#             return 'beginner'
#         else:
#             return 'intermediate'

#     def _fallback_admin_routing(self, user_message: str, state: AdminConversationState) -> Dict[str, Any]:
#         """Fallback routing when LLM mediation fails"""
        
#         message_lower = user_message.lower()
        
#         if 'faq' in message_lower:
#             action = 'list_faqs'
#         elif any(word in message_lower for word in ['analytic', 'stat', 'usage']):
#             action = 'view_analytics'
#         elif any(word in message_lower for word in ['help', 'what', 'how']):
#             action = 'help'
#         else:
#             action = 'greeting'
        
#         return {
#             "success": True,
#             "response": f"I'll help you with {action.replace('_', ' ')}",
#             "action": action,
#             "fallback_routing": True
#         }





#     def _execute_action(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Executes the action defined in the current state or asks for more info."""
#         # Check if all required parameters are present
#         missing_params = [p for p in state.required_params if p not in state.context_data and p not in state.required_params]

#         if missing_params:
#             # We need more information from the user
#             return self._ask_for_missing_info(state, missing_params)

#         if state.pending_confirmation:
#             # We need confirmation from the user
#             return self._ask_for_confirmation(state)

#         # All parameters and confirmations are present, execute the action
#         action_method = getattr(self, f"_action_{state.current_intent.value}", self._action_unknown)
#         result = action_method(state, data_manager)

#         # Clear state after successful execution
#         if result.get("success"):
#             state.clear()

#         return result

#     def _execute_mediated_admin_action(self, mediation_result: Dict, state: AdminConversationState, 
#                                   data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Execute action based on LLM mediation results"""
        
#         admin_action = mediation_result.get('admin_action', 'help')
#         response_style = mediation_result.get('response_style', 'conversational')
#         conversation_flow = mediation_result.get('conversation_flow', 'new_task')
        
#         # Map mediated action to existing action methods
#         action_mapping = {
#             'add_faq': self._action_add_faq,
#             'update_faq': self._action_update_faq,
#             'delete_faq': self._action_delete_faq,
#             'list_faqs': self._action_list_faqs,
#             'view_analytics': self._action_view_analytics,
#             'view_settings': self._action_view_settings,
#             'help': self._action_help,
#             'greeting': self._action_greeting,
#             'setup_discord': self._action_setup_integration,
#             'setup_slack': self._action_setup_integration,
#             'setup_telegram': self._action_setup_integration
#         }
        
#         # Get the appropriate action method
#         action_method = action_mapping.get(admin_action, self._action_unknown)
        
#         # Update state with mediation results
#         if conversation_flow == 'continuation':
#             # Don't clear existing state, we're continuing
#             pass
#         elif conversation_flow == 'new_task':
#             # Set up new task state
#             from app.chatbot.admin_intent_parser import AdminActionType
#             try:
#                 action_type = AdminActionType(admin_action)
#                 state.current_intent = action_type
#                 state.required_params = {param: None for param in mediation_result.get('requires_parameters', [])}
#                 state.pending_confirmation = mediation_result.get('requires_confirmation', False)
#             except ValueError:
#                 state.current_intent = AdminActionType.HELP
        
#         # Store mediation context in state for enhanced responses
#         state.add_context('mediation_style', response_style)
#         state.add_context('mediation_confidence', mediation_result.get('confidence', 0.7))
#         state.add_context('user_intent_summary', mediation_result.get('user_intent_summary', ''))
        
#         # Execute the action with enhanced context
#         try:
#             result = action_method(state, data_manager)
            
#             # Enhance response based on mediation style
#             if result.get("success") and response_style != 'direct':
#                 enhanced_response = self._enhance_response_with_mediation_style(
#                     result["response"], response_style, mediation_result
#                 )
#                 result["response"] = enhanced_response
            
#             # Add mediation metadata
#             result.update({
#                 "mediation_confidence": mediation_result.get('confidence', 0.7),
#                 "conversation_flow": conversation_flow,
#                 "response_style": response_style,
#                 "llm_mediated": True
#             })
            
#             # Clear state after successful execution (unless it's a continuation)
#             if result.get("success") and conversation_flow != 'continuation':
#                 state.clear()
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Error executing mediated action {admin_action}: {e}")
#             return {
#                 "success": False,
#                 "response": f"I encountered an error while trying to {admin_action.replace('_', ' ')}. Please try again.",
#                 "error": str(e)
#             }

#     def _enhance_response_with_mediation_style(self, response: str, style: str, 
#                                             mediation_result: Dict) -> str:
#         """Enhance response based on mediation style preferences"""
        
#         if not self.llm_available or style == 'direct':
#             return response
        
#         try:
#             user_intent = mediation_result.get('user_intent_summary', 'admin task')
            
#             enhancement_prompt = f"""Enhance this admin response to match the requested style:

#     ORIGINAL RESPONSE: {response}

#     ENHANCEMENT STYLE: {style}
#     USER INTENT: {user_intent}

#     Style Guidelines:
#     - guided: Provide step-by-step guidance and next steps
#     - conversational: Be more natural and engaging
#     - supportive: Show understanding and encouragement
#     - direct: Keep it concise (no changes needed)

#     Enhance the response to match the {style} style while keeping all the original information:"""
            
#             result = self.llm.invoke(enhancement_prompt)
#             enhanced = result.content.strip()
            
#             # Validation - enhanced response should be reasonable length
#             if 0.8 <= len(enhanced) / len(response) <= 1.5:
#                 return enhanced
            
#         except Exception as e:
#             logger.error(f"Response enhancement failed: {e}")
        
#         return response

#     def _action_setup_integration(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handle integration setup actions"""
#         integration_type = state.current_intent.value.replace('setup_', '') if state.current_intent else 'unknown'
        
#         return {
#             "success": True,
#             "response": f"🔗 Setting up {integration_type.title()} integration is coming soon! I'll help you configure it when it's available.",
#             "action": f"setup_{integration_type}"
#         }



#     # --- FUNCTION ADDED ---
#     def _message_completes_action(self, intent: ParsedIntent, state: AdminConversationState) -> bool:
#         """
#         Determines if the new message provides the necessary info or confirmation to complete the pending action.
#         This is a key decision point in the conversational flow.
#         """
#         if not state.current_intent:
#             return False

#         # Scenario 1: User explicitly confirms a pending action (e.g., says "yes" to a deletion).
#         if state.pending_confirmation and intent.action == AdminActionType.CONFIRM:
#             # We were waiting for a 'yes', and we got it. The action is complete.
#             state.pending_confirmation = False # No longer needs confirmation
#             logger.info(f"✅ Confirmation received for action: {state.current_intent.value}")
#             return True

#         # Scenario 2: User provides the last piece of missing information.
#         if state.required_params:
#             # Check if any of the keys in the newly parsed parameters match what we need.
#             provided_params = [p for p in state.required_params if p in intent.parameters]
#             if provided_params:
#                 # User has provided some of the data we were waiting for.
#                 # We can now consider this part of the action "complete".
#                 # The main loop will update the state with this new info.
#                 logger.info(f"✅ User provided missing parameters: {provided_params}")
#                 # This logic is handled in the main loop, so we return true to proceed with execution.
#                 return True

#         return False

#     # --- FUNCTION ADDED ---
#     def _get_proactive_suggestion(self, state: AdminConversationState, data_manager: TenantDataManager) -> Optional[str]:
#         """
#         After a successful action, use the LLM to suggest a logical next step to the user,
#         making the chatbot feel more like a helpful assistant.
#         """
#         if not self.llm_available or not state.last_intent_for_suggestion:
#             return None

#         try:
#             template = """A user, a business owner named {tenant_name}, just successfully completed an admin action for their chatbot. Based on their last action, suggest a relevant and helpful next step. Keep the suggestion brief and conversational.

#             Last Action Completed: "{last_action}"

#             Contextual Information:
#             - If they listed FAQs, you could suggest they update or delete one.
#             - If they added an FAQ, you could ask if they want to add another or view the list.
#             - If they viewed analytics showing high traffic, you could suggest adding more FAQs.
#             - If they updated a setting, you could ask them to view all settings to confirm.

#             Your helpful, one-sentence suggestion:"""

#             context = {
#                 "last_action": state.last_intent_for_suggestion.value,
#                 "tenant_name": data_manager.tenant.business_name
#             }

#             prompt = PromptTemplate.from_template(template)
#             response = self.llm.invoke(prompt.format(**context))
#             suggestion = response.content.strip()

#             logger.info(f"💡 Proactive suggestion generated for action '{context['last_action']}': {suggestion}")
#             return suggestion

#         except Exception as e:
#             logger.error(f"Failed to generate proactive suggestion: {e}")
#             return None


#     # --- Dynamic Response and Suggestion Methods ---

#     def _generate_dynamic_response(self, prompt_template: str, context: Dict[str, Any]) -> str:
#         """Generates a natural, non-templated response using the LLM."""
#         if not self.llm_available:
#             return "Got it. What's next?" # Simple fallback

#         try:
#             prompt = PromptTemplate.from_template(prompt_template)
#             response = self.llm.invoke(prompt.format(**context))
#             return response.content.strip()
#         except Exception as e:
#             logger.error(f"Dynamic response generation failed: {e}")
#             return "I'm having a little trouble formulating a response. Could you try again?"


#     # --- Methods for asking for more info/confirmation ---

#     def _ask_for_missing_info(self, state: AdminConversationState, missing_params: List[str]) -> Dict[str, Any]:
#         """Asks the user for the information needed to complete an action."""
#         param_list = " and ".join(missing_params)
#         template = "To do that, I just need the following information: {params}. What should it be?"
#         response = self._generate_dynamic_response(template, {"params": param_list})
#         return {"success": False, "response": response, "requires_input": True}

#     def _ask_for_confirmation(self, state: AdminConversationState) -> Dict[str, Any]:
#         """Asks the user to confirm a destructive action."""
#         template = "Are you sure you want to {action_description}? This action cannot be undone."
#         # The description would be dynamically generated based on the intent
#         action_description = f"delete the FAQ #{state.context_data.get('faq_id')}"
#         response = self._generate_dynamic_response(template, {"action_description": action_description})
#         return {"success": False, "response": response, "requires_confirmation": True}

#     # --- Specific Action Implementation Methods ---
#     # These methods are called by _execute_action.

#     def _action_greeting(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handles a greeting from the admin user."""
#         state.last_intent_for_suggestion = AdminActionType.GREETING
#         tenant_name = data_manager.tenant.business_name
#         response = self._generate_dynamic_response(
#             "Hello! I'm ready to help you manage the chatbot for {tenant_name}. What can I assist you with today? You can ask me to add an FAQ, view analytics, and more.",
#             {"tenant_name": tenant_name}
#         )
#         return {"success": True, "response": response}



#     def _action_add_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         params = state.required_params
#         faq = data_manager.create_faq(question=params['question'], answer=params['answer'])
#         state.add_context("last_faq_id", faq.id)
#         state.last_intent_for_suggestion = AdminActionType.ADD_FAQ
#         response = self._generate_dynamic_response(
#             "I've successfully added that new FAQ for you (ID #{faq_id}). Your chatbot is now smarter!"
#             # {"faq_id": faq.id}
#         )
#         return {"success": True, "response": response}

#     def _action_list_faqs(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         faqs = data_manager.get_faqs(limit=20)
#         if not faqs:
#             return {"success": True, "response": "You don't have any FAQs yet. Let's create one! Just tell me what question to add."}

#         faq_list = "\n".join([f"• **#{faq.id}**: {faq.question}" for faq in faqs])
#         state.last_intent_for_suggestion = AdminActionType.LIST_FAQS
#         response = self._generate_dynamic_response(
#             "Here are your current FAQs:\n{faq_list}",
#             {"faq_list": faq_list}
#         )
#         return {"success": True, "response": response}

#     def _action_view_analytics(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         analytics = data_manager.get_analytics_summary()
#         # A real implementation would format this nicely.
#         response = self._generate_dynamic_response(
#             "Here are your analytics for the last 30 days:\n- Sessions: {sessions}\n- Messages: {messages}",
#             {
#                 "sessions": analytics['usage_stats_30_days']['chat_sessions'],
#                 "messages": analytics['usage_stats_30_days']['total_messages']
#             }
#         )
#         state.last_intent_for_suggestion = AdminActionType.VIEW_ANALYTICS
#         return {"success": True, "response": response}

#     def _action_unknown(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         response = self._generate_dynamic_response(
#             "I'm not quite sure how to help with that. Could you try rephrasing? You can also ask for 'help' to see what I can do.",
#             {}
#         )
#         return {"success": False, "response": response}

#     def _action_confirm(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         # This action is handled by the main loop, but we need a placeholder
#         return {"success": True, "response": "Confirmed."}



#     def _action_help(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Provides a helpful message listing the bot's capabilities."""
#         state.last_intent_for_suggestion = AdminActionType.HELP
#         # The get_help_text() method is already available in the intent parser
#         help_text = self.intent_parser.get_help_text()
#         return {"success": True, "response": help_text}

#     def _action_delete_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handles deleting an FAQ."""
#         # This is a placeholder for the full implementation
#         state.last_intent_for_suggestion = AdminActionType.DELETE_FAQ
#         faq_id = state.required_params.get('faq_id', 'unknown')
#         # A real implementation would confirm the deletion
#         response = f"This is where the logic to delete FAQ #{faq_id} would go. This feature is coming soon!"
#         return {"success": True, "response": response}

#     def _action_update_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handles updating an FAQ."""
#         # This is a placeholder for the full implementation
#         state.last_intent_for_suggestion = AdminActionType.UPDATE_FAQ
#         faq_id = state.required_params.get('faq_id', 'unknown')
#         response = f"This is where the logic to update FAQ #{faq_id} would go. This feature is coming soon!"
#         return {"success": True, "response": response}

#     def _action_view_settings(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
#         """Handles viewing tenant settings."""
#         state.last_intent_for_suggestion = AdminActionType.VIEW_SETTINGS
#         settings = data_manager.get_tenant_settings()
#         # A real implementation would format this nicely
#         response = f"Your current business name is {settings.get('business_name')}. The full settings view is coming soon!"
#         return {"success": True, "response": response}


# # Factory function remains the same
# def get_super_tenant_admin_engine(db: Session) -> "RefactoredSuperTenantAdminEngine":
#     """Factory function to create the Refactored SuperTenantAdminEngine."""
#     return RefactoredSuperTenantAdminEngine(db)









# app/chatbot/super_tenant_admin_engine.py
"""
Refactored Super Tenant Admin Engine with LLM Mediator Layer
Foundation: Working admin logic with natural conversation
Layer: Admin LLM Mediator + Unified Engine delegation for platform docs
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

class AdminConversationState:
    """Tracks the state of an admin conversation for more natural multi-turn dialogue."""
    def __init__(self, user_identifier: str, tenant_id: int):
        self.user_identifier = user_identifier
        self.tenant_id = tenant_id
        self.current_intent: Optional[AdminActionType] = None
        self.required_params: Dict[str, Any] = {}
        self.pending_confirmation: bool = False
        self.last_interaction = datetime.utcnow()
        self.context_data: Dict[str, Any] = {}
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
    Foundation: Working admin logic with natural conversation
    Layer: LLM Mediator + Unified Engine delegation
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.intent_parser = get_llm_admin_intent_parser()
        self.active_conversations: Dict[str, AdminConversationState] = {}

        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.4,
                openai_api_key=settings.OPENAI_API_KEY
            )
        logger.info("🤖 SuperTenantAdminEngine initialized with Foundation + Mediator Layer.")

    def _get_or_create_conversation_state(self, user_identifier: str, tenant_id: int) -> AdminConversationState:
        """Gets or creates a state for the current conversation."""
        state = self.active_conversations.get(user_identifier)
        if not state or state.is_expired():
            state = AdminConversationState(user_identifier, tenant_id)
            self.active_conversations[user_identifier] = state
        state.last_interaction = datetime.utcnow()
        return state

    async def process_admin_message(
        self,
        user_message: str,
        authenticated_tenant_id: int,
        user_identifier: str,
        session_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Main processing: Foundation logic + Mediator layer
        """
        try:
            data_manager = TenantDataManager(self.db, authenticated_tenant_id)
            memory = SimpleChatbotMemory(self.db, authenticated_tenant_id)
            session_id, _ = memory.get_or_create_session(user_identifier, "admin_web")
            conversation_history = memory.get_conversation_history(user_identifier, max_messages=10)

            memory.store_message(session_id, user_message, True)

            # Get conversation state
            state = self._get_or_create_conversation_state(user_identifier, authenticated_tenant_id)
            
            # Get tenant
            tenant = self.db.query(Tenant).filter(Tenant.id == authenticated_tenant_id).first()

            # NEW LAYER: Admin LLM Mediator - decides routing
            mediation_result = self._admin_llm_mediator(
                user_message=user_message,
                state=state,
                tenant=tenant,
                conversation_history=conversation_history
            )

            # Route based on mediation decision
            if mediation_result["delegate_to_unified"]:
                # NEW: Platform documentation questions
                result = await self._delegate_to_unified_mediator(
                    user_message=user_message,
                    tenant=tenant,
                    user_identifier=user_identifier,
                    mediation_context=mediation_result
                )
            else:
                # FOUNDATION: Working admin logic
                result = self._execute_foundation_admin_logic(
                    user_message=user_message,
                    state=state,
                    data_manager=data_manager,
                    tenant=tenant
                )

            # Foundation: Proactive suggestions
            if result.get("success") and not state.pending_confirmation and not state.required_params:
                suggestion = self._get_proactive_suggestion(state, data_manager)
                if suggestion:
                    result["response"] += f"\n\n{suggestion}"

            memory.store_message(session_id, result["response"], False)
            data_manager.log_admin_action(
                action=result.get("action", "processed_action"),
                details={
                    "user_message": user_message, 
                    "success": result.get("success", False),
                    "processing_method": result.get("processing_method", "foundation"),
                    "mediation_decision": mediation_result.get("reasoning", "")
                }
            )
            return result

        except TenantSecurityError as e:
            logger.error(f"🚨 Security error in admin processing: {e}")
            return {"success": False, "response": "⛔ Access denied. You can only manage your own tenant data."}
        except Exception as e:
            logger.error(f"💥 Error processing admin message: {e}", exc_info=True)
            return {"success": False, "response": "❌ I encountered an error. Please try again."}

    def _admin_llm_mediator(self, user_message: str, state: AdminConversationState, 
                           tenant: Tenant, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        NEW LAYER: Admin LLM Mediator - decides between tenant data vs platform docs
        """
        
        if not self.llm_available:
            return self._fallback_admin_mediation(user_message)
        
        try:
            prompt = PromptTemplate(
                input_variables=["user_message", "tenant_name"],
                template="""You are an admin mediator. Decide if this is about TENANT DATA or PLATFORM DOCUMENTATION.

USER MESSAGE: "{user_message}"
TENANT: {tenant_name}

INSTRUCTIONS (STRICT)
- If someone write a world or statement you do not understand, subtly ask for clarity instead of makig blind decisions

TENANT DATA MANAGEMENT (Admin Engine):
- Managing THEIR OWN FAQs: "show my FAQs", "add FAQ", "delete FAQ #5"
- THEIR analytics: "show my stats", "my chatbot performance"  
- THEIR settings: "update my branding", "change my prompt"

PLATFORM DOCUMENTATION (Unified Engine):
- How platform works: "how does knowledge base work?", "what features do you have?"
- Platform capabilities: "what integrations are available?", "how to use this platform?"
- General platform info: "what is this software?", "how do I get started?"
- Simple greetings: "hello", "hi", "hey", "good morning" (unless combined with admin commands)

CRITICAL RULE: Simple greetings like "hello" should ALWAYS go to unified engine (delegate_to_unified: true).

RESPONSE FORMAT (JSON):
{{
    "delegate_to_unified": true/false,
    "confidence": 0.95,
    "reasoning": "explanation"
}}

Analysis:"""
            )
            
            result = self.llm.invoke(prompt.format(
                user_message=user_message,
                tenant_name=tenant.business_name or tenant.name
            ))
            
            import json, re
            json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
            if json_match:
                mediation = json.loads(json_match.group())
                logger.info(f"🧠 Mediation: {'UNIFIED' if mediation.get('delegate_to_unified') else 'FOUNDATION'} - {mediation.get('reasoning', '')[:100]}...")
                return mediation
                
        except Exception as e:
            logger.error(f"Admin mediation failed: {e}")
        
        return self._fallback_admin_mediation(user_message)

    def _fallback_admin_mediation(self, user_message: str) -> Dict[str, Any]:
        """Fallback when LLM mediation fails"""
        message_lower = user_message.lower()
        
        # Platform keywords
        platform_keywords = ['how does', 'what is', 'explain', 'how to use', 'what features', 'platform', 'software']
        
        # Tenant keywords  
        tenant_keywords = ['my faq', 'my analytics', 'my settings', 'my chatbot', 'add faq', 'delete faq', 'show my']
        
        if any(keyword in message_lower for keyword in platform_keywords):
            return {"delegate_to_unified": True, "reasoning": "Fallback: Platform keywords detected"}
        else:
            return {"delegate_to_unified": False, "reasoning": "Fallback: Tenant data assumed"}

    async def _delegate_to_unified_mediator(self, user_message: str, tenant: Tenant, 
                                    user_identifier: str, mediation_context: Dict) -> Dict[str, Any]:
        """
        NEW LAYER: Delegate to Unified Engine for platform documentation
        """
        try:
            from app.chatbot.unified_intelligent_engine import get_unified_intelligent_engine
            
            # Get super tenant for platform docs
            SUPER_TENANT_IDS = [324112833]
            super_tenant = self.db.query(Tenant).filter(Tenant.id.in_(SUPER_TENANT_IDS)).first()
            
            if not super_tenant or not super_tenant.api_key:
                return {
                    "success": False,
                    "response": "❌ Platform documentation is temporarily unavailable.",
                    "processing_method": "unified_delegation_error"
                }
            
            # Initialize unified engine
            unified_engine = get_unified_intelligent_engine(self.db, super_tenant.id)
            
            # Enhance message for platform context
            enhanced_message = f"[ADMIN PLATFORM QUERY] {tenant.business_name or tenant.name} admin asking: {user_message}"
            
            logger.info(f"🔀 Delegating to Unified Mediator: {enhanced_message[:100]}...")
            
            # Process with unified mediator
            result =  await unified_engine.process_message(
                api_key=super_tenant.api_key,
                user_message=enhanced_message,
                user_identifier=f"admin_{user_identifier}",
                platform="admin_platform_docs"
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "response": self._add_admin_context_to_platform_response(result["response"], tenant),
                    "action": "platform_documentation",
                    "processing_method": "unified_mediator_delegation",
                    "answered_by": f"Platform Docs via {result.get('answered_by', 'Unified')}"
                }
            else:
                return {
                    "success": False,
                    "response": "❌ I couldn't find information about that platform feature.",
                    "processing_method": "unified_delegation_failed"
                }
                
        except Exception as e:
            logger.error(f"❌ Error in unified delegation: {e}")
            return {
                "success": False,
                "response": "❌ Platform documentation is temporarily unavailable.",
                "processing_method": "unified_delegation_error"
            }

    def _add_admin_context_to_platform_response(self, unified_response: str, tenant: Tenant) -> str:
        """Add light admin context to platform responses"""
        if "feature" in unified_response.lower():
            footer = f"\n\nAs a {tenant.business_name or tenant.name} admin, you can access these features through your dashboard."
            return unified_response + footer
        return unified_response

    def _execute_foundation_admin_logic(self, user_message: str, state: AdminConversationState,
                                      data_manager: TenantDataManager, tenant: Tenant) -> Dict[str, Any]:
        """
        FOUNDATION: Execute working admin logic with LLM mediation
        """
        try:
            # Use LLM mediator for admin requests
            result = self._admin_foundation_mediator(
                user_message=user_message,
                state=state,
                tenant=tenant,
                data_manager=data_manager
            )

            return result
            
        except Exception as e:
            logger.error(f"Foundation admin logic failed: {e}")
            return self._fallback_admin_routing(user_message, state)

    def _admin_foundation_mediator(self, user_message: str, state: AdminConversationState, 
                                 tenant: Tenant, data_manager: TenantDataManager) -> Dict[str, Any]:
        """
        FOUNDATION: LLM mediator for admin requests (working logic)
        """
        if not self.llm_available:
            return self._fallback_admin_routing(user_message, state)
        
        try:
            # Build context for admin mediation
            admin_context = self._build_admin_mediation_context(state, tenant)
            
            # Let LLM understand and route the admin request
            mediation_result = self._mediate_admin_request(user_message, admin_context, state)
            
            # Execute the mediated action
            return self._execute_mediated_admin_action(mediation_result, state, data_manager)
            
        except Exception as e:
            logger.error(f"Foundation admin mediation failed: {e}")
            return self._fallback_admin_routing(user_message, state)

    def _mediate_admin_request(self, user_message: str, admin_context: str, 
                             state: AdminConversationState) -> Dict[str, Any]:
        """FOUNDATION: Core LLM mediation for admin requests"""
        
        prompt = f"""You are an intelligent admin assistant mediator. Analyze this admin request and determine the best action.

ADMIN CONTEXT:
{admin_context}

USER REQUEST: "{user_message}"

AVAILABLE ADMIN ACTIONS:
- FAQ Management: add_faq, update_faq, delete_faq, list_faqs
- Analytics: view_analytics, conversation_stats, usage_reports
- Settings: update_prompt, update_branding, email_config, view_setting
- Integrations: setup_discord, setup_slack, setup_telegram
- General: help, greeting, clarification_needed

CONVERSATION STATE:
- Current Intent: {state.current_intent.value if state.current_intent else 'None'}
- Pending Confirmation: {state.pending_confirmation}
- Required Params: {list(state.required_params.keys()) if state.required_params else 'None'}

RESPONSE FORMAT (JSON):
{{
    "admin_action": "specific_action_name",
    "confidence": 0.95,
    "requires_parameters": ["param1", "param2"],
    "requires_confirmation": true/false,
    "conversation_flow": "continuation|new_task|clarification|completion",
    "response_style": "direct|guided|conversational|supportive",
    "user_intent_summary": "clear description of what user wants",
    "reasoning": "why this action and approach"
}}

Analysis:"""

        try:
            result = self.llm.invoke(prompt)
            import json, re
            json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
            if json_match:
                mediation = json.loads(json_match.group())
                logger.info(f"🧠 Foundation mediation: {mediation.get('admin_action')} - {mediation.get('reasoning', '')[:50]}...")
                return mediation
        except Exception as e:
            logger.error(f"Foundation mediation parsing failed: {e}")
        
        return {"admin_action": "help", "confidence": 0.3, "conversation_flow": "clarification"}

    def _build_admin_mediation_context(self, state: AdminConversationState, tenant: Tenant) -> str:
        """FOUNDATION: Build context for admin mediation"""
        context_parts = []
        
        # Tenant context
        context_parts.append(f"Business: {tenant.business_name or tenant.name}")
        context_parts.append(f"Tenant ID: {tenant.id}")
        
        # Current state context
        if state.current_intent:
            context_parts.append(f"Currently working on: {state.current_intent.value.replace('_', ' ')}")
        
        if state.context_data:
            context_parts.append(f"Context data: {state.context_data}")
        
        return "\n".join(context_parts)

    def _execute_mediated_admin_action(self, mediation_result: Dict, state: AdminConversationState, 
                                     data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Execute action based on LLM mediation results"""
        
        admin_action = mediation_result.get('admin_action', 'help')
        conversation_flow = mediation_result.get('conversation_flow', 'new_task')
        
        # Map mediated action to existing action methods (FOUNDATION)
        action_mapping = {
            'add_faq': self._action_add_faq,
            'update_faq': self._action_update_faq,
            'delete_faq': self._action_delete_faq,
            'list_faqs': self._action_list_faqs,
            'show_faqs': self._action_list_faqs,
            'view_analytics': self._action_view_analytics,
            'view_settings': self._action_view_settings,
            'show_settings': self._action_view_settings,
            'help': self._action_help,
            'greeting': self._action_greeting,
            'setup_discord': self._action_setup_integration,
            'setup_slack': self._action_setup_integration,
            'setup_telegram': self._action_setup_integration,
            'show_settings': self._action_view_settings,
            'display_settings': self._action_view_settings,
            'show_faqs': self._action_list_faqs,
            'display_faqs': self._action_list_faqs,
            'show_analytics': self._action_view_analytics,
            'display_analytics': self._action_view_analytics
        }
        
        # Get the appropriate action method
        action_method = action_mapping.get(admin_action, self._action_unknown)
        
        # Update state with mediation results
        if conversation_flow == 'new_task':
            from app.chatbot.admin_intent_parser import AdminActionType
            try:
                action_type = AdminActionType(admin_action)
                state.current_intent = action_type
                state.required_params = {param: None for param in mediation_result.get('requires_parameters', [])}
                state.pending_confirmation = mediation_result.get('requires_confirmation', False)
            except ValueError:
                state.current_intent = AdminActionType.HELP
        
        # Execute the action (FOUNDATION)
        try:
            result = action_method(state, data_manager)
            
            # Add mediation metadata
            result.update({
                "mediation_confidence": mediation_result.get('confidence', 0.7),
                "conversation_flow": conversation_flow,
                "llm_mediated": True,
                "processing_method": "foundation_with_mediation"
            })
            
            # Clear state after successful execution
            if result.get("success") and conversation_flow != 'continuation':
                state.clear()
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing mediated action {admin_action}: {e}")
            return {
                "success": False,
                "response": f"I encountered an error while trying to {admin_action.replace('_', ' ')}. Please try again.",
                "error": str(e)
            }

    def _fallback_admin_routing(self, user_message: str, state: AdminConversationState) -> Dict[str, Any]:
        """FOUNDATION: Fallback routing when LLM mediation fails"""
        message_lower = user_message.lower()
        
        if 'faq' in message_lower:
            action = 'list_faqs'
        elif any(word in message_lower for word in ['analytic', 'stat', 'usage']):
            action = 'view_analytics'
        elif any(word in message_lower for word in ['help', 'what', 'how']):
            action = 'help'
        else:
            action = 'greeting'
        
        return {
            "success": True,
            "response": f"I'll help you with {action.replace('_', ' ')}",
            "action": action,
            "processing_method": "fallback_routing"
        }

    def _action_greeting(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Greeting action"""
        state.last_intent_for_suggestion = AdminActionType.GREETING
        tenant_name = data_manager.tenant.business_name or data_manager.tenant.name
        response = self._generate_dynamic_response(
            "Hello! I'm ready to help you manage the chatbot for {tenant_name}. What can I assist you with today?",
            {"tenant_name": tenant_name}
        )
        return {"success": True, "response": response, "action": "greeting"}

    def _action_add_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Add FAQ action"""
        params = state.required_params
        if not params.get('question') or not params.get('answer'):
            return {
                "success": True,  # ✅ Changed to True
                "response": "I'd be happy to help you add an FAQ! What question would you like to add?",
                "requires_input": True,
                "action": "add_faq"  # ✅ Added action
            }
        
        try:
            faq = data_manager.create_faq(question=params['question'], answer=params['answer'])
            state.add_context("last_faq_id", faq.id)
            state.last_intent_for_suggestion = AdminActionType.ADD_FAQ
            response = f"✅ Successfully added FAQ #{faq.id}: '{params['question']}'"
            return {"success": True, "response": response, "action": "add_faq"}
        except Exception as e:
            logger.error(f"Error adding FAQ: {e}")
            return {"success": False, "response": "❌ Failed to add FAQ. Please try again.", "action": "add_faq"}

    def _action_list_faqs(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: List FAQs action"""
        try:
            faqs = data_manager.get_faqs(limit=20)
            if not faqs:
                return {"success": True, "response": "You don't have any FAQs yet. Let's create one! Just tell me what question to add."}

            faq_list = "\n".join([f"• **#{faq.id}**: {faq.question}" for faq in faqs])
            state.last_intent_for_suggestion = AdminActionType.LIST_FAQS
            response = f"Here are your current FAQs:\n\n{faq_list}"
            return {"success": True, "response": response, "action": "list_faqs"}
        except Exception as e:
            logger.error(f"Error listing FAQs: {e}")
            return {"success": False, "response": "❌ Could not retrieve FAQs.", "action": "list_faqs"}

    def _action_view_analytics(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: View analytics action - CLEAN DATA ONLY"""
        try:
            analytics = data_manager.get_analytics_summary()
            
            # FOUNDATION: Clean analytics formatting (no hallucination)
            response = f"""📊 **Your Chatbot Performance**

**Content:**
• {analytics['content_stats']['faqs']} FAQs
• {analytics['content_stats']['knowledge_bases']} knowledge bases

**Activity (Last 30 Days):**
• {analytics['usage_stats_30_days']['chat_sessions']} chat sessions
• {analytics['usage_stats_30_days']['total_messages']} total messages

**Integrations:**
• Discord: {'✅ Active' if analytics['integrations']['discord'] else '❌ Not set up'}
• Slack: {'✅ Active' if analytics['integrations']['slack'] else '❌ Not set up'}
• Telegram: {'✅ Active' if analytics['integrations']['telegram'] else '❌ Not set up'}"""

            state.last_intent_for_suggestion = AdminActionType.VIEW_ANALYTICS
            return {"success": True, "response": response, "action": "view_analytics"}
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {"success": False, "response": "❌ Could not retrieve analytics.", "action": "view_analytics"}

    def _action_delete_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Delete FAQ action"""
        faq_id = state.required_params.get('faq_id')
        if not faq_id:
            return {
                "success": False,
                "response": "Which FAQ would you like to delete? Please provide the FAQ ID.",
                "requires_input": True
            }
        
        try:
            success = data_manager.delete_faq(faq_id)
            if success:
                state.last_intent_for_suggestion = AdminActionType.DELETE_FAQ
                return {"success": True, "response": f"✅ Successfully deleted FAQ #{faq_id}", "action": "delete_faq"}
            else:
                return {"success": False, "response": f"❌ FAQ #{faq_id} not found.", "action": "delete_faq"}
        except Exception as e:
            logger.error(f"Error deleting FAQ: {e}")
            return {"success": False, "response": "❌ Failed to delete FAQ.", "action": "delete_faq"}

    def _action_view_settings(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: View settings action"""
        try:
            settings = data_manager.get_tenant_settings()
            response = f"""⚙️ **Current Settings**

**Business Info:**
• Name: {settings['business_name']}
• Email: {settings['email']}

**Chatbot:**
• Custom prompt: {'✅ Set' if settings['system_prompt'] else '❌ Default'}
• Branding: {'✅ Custom' if settings['branding']['logo_image_url'] else '❌ Default'}"""

            state.last_intent_for_suggestion = AdminActionType.VIEW_SETTINGS
            return {"success": True, "response": response, "action": "view_settings"}
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {"success": False, "response": "❌ Could not retrieve settings.", "action": "view_settings"}

    def _action_help(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Help action"""
        state.last_intent_for_suggestion = AdminActionType.HELP
        help_text = self.intent_parser.get_help_text()
        return {"success": True, "response": help_text, "action": "help"}

    def _action_setup_integration(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Setup integration action"""
        integration_type = state.current_intent.value.replace('setup_', '') if state.current_intent else 'unknown'
        return {
            "success": True,
            "response": f"🔗 {integration_type.title()} integration setup is coming soon!",
            "action": f"setup_{integration_type}"
        }

    def _action_unknown(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Unknown action"""
        response = self._generate_dynamic_response(
            "I'm not quite sure how to help with that. You can ask me to manage FAQs, view analytics, and more.",
            {}
        )
        return {"success": False, "response": response, "action": "unknown"}

    def _generate_dynamic_response(self, prompt_template: str, context: Dict[str, Any]) -> str:
        """FOUNDATION: Natural response generation"""
        if not self.llm_available:
            return prompt_template.format(**context) if context else prompt_template

        try:
            prompt = PromptTemplate.from_template(prompt_template)
            response = self.llm.invoke(prompt.format(**context))
            return response.content.strip()
        except Exception as e:
            logger.error(f"Dynamic response generation failed: {e}")
            return prompt_template.format(**context) if context else "I'm here to help!"

    def _get_proactive_suggestion(self, state: AdminConversationState, data_manager: TenantDataManager) -> Optional[str]:
        """FOUNDATION: Proactive suggestions"""
        if not self.llm_available or not state.last_intent_for_suggestion:
            return None

        try:
            template = """A business admin just completed an action. Suggest a brief, relevant next step.

Last Action: "{last_action}"
Business: {tenant_name}

Generate ONE brief suggestion:"""

            context = {
                "last_action": state.last_intent_for_suggestion.value,
                "tenant_name": data_manager.tenant.business_name or data_manager.tenant.name
            }

            prompt = PromptTemplate.from_template(template)
            response = self.llm.invoke(prompt.format(**context))
            suggestion = response.content.strip()

            logger.info(f"💡 Generated suggestion: {suggestion}")
            return suggestion

        except Exception as e:
            logger.error(f"Failed to generate suggestion: {e}")
            return None

    def _action_update_faq(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Update FAQ action (placeholder)"""
        state.last_intent_for_suggestion = AdminActionType.UPDATE_FAQ
        faq_id = state.required_params.get('faq_id', 'unknown')
        return {
            "success": True, 
            "response": f"FAQ update for #{faq_id} is coming soon!",
            "action": "update_faq"
        }

    def _action_confirm(self, state: AdminConversationState, data_manager: TenantDataManager) -> Dict[str, Any]:
        """FOUNDATION: Confirmation action"""
        return {"success": True, "response": "Confirmed.", "action": "confirm"}


def get_super_tenant_admin_engine(db: Session) -> RefactoredSuperTenantAdminEngine:
    """Factory function to create the admin engine with Foundation + Mediator Layer."""
    return RefactoredSuperTenantAdminEngine(db)