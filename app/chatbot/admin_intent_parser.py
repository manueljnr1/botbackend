# app/chatbot/llm_admin_intent_parser.py
"""
LLM-Enhanced Admin Intent Parser
Uses OpenAI to understand natural language admin commands with high flexibility
"""

import re
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel
from app.config import settings

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class AdminActionType(Enum):
    # FAQ Management
    ADD_FAQ = "add_faq"
    UPDATE_FAQ = "update_faq"
    DELETE_FAQ = "delete_faq"
    LIST_FAQS = "list_faqs"
    SEARCH_FAQS = "search_faqs"
    
    # Settings Management
    UPDATE_PROMPT = "update_prompt"
    UPDATE_BRANDING = "update_branding"
    UPDATE_EMAIL_CONFIG = "update_email_config"
    UPDATE_BUSINESS_INFO = "update_business_info"
    
    # Analytics & Info
    VIEW_ANALYTICS = "view_analytics"
    VIEW_SETTINGS = "view_settings"
    VIEW_USAGE = "view_usage"
    
    # Integration Management
    SETUP_DISCORD = "setup_discord"
    SETUP_SLACK = "setup_slack"
    SETUP_INSTAGRAM = "setup_instagram"
    SETUP_TELEGRAM = "setup_telegram"
    LIST_INTEGRATIONS = "list_integrations"
    
    # Knowledge Base
    VIEW_KNOWLEDGE_BASE = "view_knowledge_base"
    UPLOAD_DOCUMENT = "upload_document"
    
    # API & Security
    RESET_API_KEY = "reset_api_key"
    VIEW_API_INFO = "view_api_info"
    
    # General
    HELP = "help"
    GREETING = "greeting"
    UNKNOWN = "unknown"

class ParsedIntent(BaseModel):
    action: AdminActionType
    confidence: float
    parameters: Dict[str, Any] = {}
    original_text: str
    requires_confirmation: bool = True
    security_risk: bool = False
    llm_reasoning: Optional[str] = None

class LLMAdminIntentParser:
    """
    Enhanced intent parser using LLM for flexible natural language understanding
    Falls back to pattern matching if LLM is unavailable
    """
    
    def __init__(self):
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.1,  # Low temperature for consistent parsing
                openai_api_key=settings.OPENAI_API_KEY
            )
            logger.info("✅ LLM-enhanced admin intent parser initialized")
        else:
            logger.warning("⚠️ LLM not available, using pattern-based fallback")
        
        # Fallback patterns for when LLM is unavailable
        self._init_fallback_patterns()
    
    def _init_fallback_patterns(self):
        """Initialize regex patterns as fallback"""
        self.fallback_patterns = {
            AdminActionType.ADD_FAQ: [
                r'(?:add|create|new)\s+(?:a\s+)?(?:new\s+)?faq',
                r'(?:add|create)\s+(?:a\s+)?(?:new\s+)?question',
                r'i\s+(?:want|need)\s+to\s+(?:add|create)\s+(?:a\s+)?faq'
            ],
            AdminActionType.LIST_FAQS: [
                r'(?:show|list|display)\s+(?:all\s+)?(?:my\s+)?faqs?',
                r'what\s+faqs?\s+do\s+i\s+have',
                r'(?:view|see)\s+(?:my\s+)?faqs?'
            ],
            AdminActionType.VIEW_ANALYTICS: [
                r'(?:show|display|view)\s+(?:my\s+)?(?:analytics|stats|statistics)',
                r'how\s+(?:is\s+)?(?:my\s+)?chatbot\s+(?:performing|doing)',
                r'(?:performance|usage)\s+(?:stats|data)'
            ],
            AdminActionType.HELP: [
                r'help',
                r'what\s+can\s+(?:you|i)\s+do',
                r'(?:show|list)\s+(?:commands|options)'
            ],
            AdminActionType.GREETING: [
                r'(?:hi|hello|hey)\s*$',
                r'good\s+(?:morning|afternoon|evening)',
                r'what\'?s\s+up'
            ]
        }
    
    def parse(self, user_message: str) -> ParsedIntent:
        """
        Parse user message using LLM first, fallback to patterns
        """
        logger.info(f"🔍 Parsing admin command with LLM: {user_message[:50]}...")
        
        if self.llm_available:
            try:
                return self._parse_with_llm(user_message)
            except Exception as e:
                logger.error(f"❌ LLM parsing failed: {e}, falling back to patterns")
                return self._parse_with_patterns(user_message)
        else:
            return self._parse_with_patterns(user_message)
    
    def _parse_with_llm(self, user_message: str) -> ParsedIntent:
        """Parse using LLM for maximum flexibility"""
        
        # Create comprehensive prompt for intent classification
        prompt = PromptTemplate(
            input_variables=["user_message", "available_actions"],
            template="""You are an expert intent classifier for a tenant admin assistant. A authenticated business owner is asking to manage their chatbot configuration.

IMPORTANT CONTEXT: This is a LOGGED-IN business owner managing their own chatbot. They have full rights to modify their own FAQ, settings, branding, etc.

USER MESSAGE: "{user_message}"

AVAILABLE ACTIONS:
{available_actions}

TASK: Classify the user's intent and extract parameters.

RESPONSE FORMAT (JSON only):
{{
    "action": "action_name",
    "confidence": 0.95,
    "parameters": {{}},
    "reasoning": "why you chose this action",
    "requires_confirmation": true/false
}}

CLASSIFICATION RULES:
1. FAQ Management: Adding, editing, deleting, or viewing FAQs
2. Settings: Changing system prompt, branding, email settings
3. Analytics: Viewing performance, usage statistics
4. Integrations: Setting up Discord, Slack, Instagram, Telegram
5. Help: General assistance or listing capabilities
6. Greeting: Simple greetings or casual conversation starters
7. If unsure, use "unknown" but provide reasoning

EXAMPLES:
- "Add a FAQ about our pricing" → add_faq
- "What's my chatbot usage this month?" → view_analytics  
- "Change my primary color to blue" → update_branding
- "How do I set up Discord?" → setup_discord
- "Remove question number 5" → delete_faq
- "Show me my current settings" → view_settings
- "Hello there!" → greeting

PARAMETER EXTRACTION:
- For FAQ operations: extract question, answer, faq_id if mentioned
- For updates: extract specific fields to change
- For integrations: extract platform name
- For deletions: always require confirmation

JSON Response:"""
        )
        
        # Build available actions list
        available_actions = []
        for action in AdminActionType:
            if action != AdminActionType.UNKNOWN:
                available_actions.append(f"- {action.value}: {self._get_action_description(action)}")
        
        actions_text = "\n".join(available_actions)
        
        # Generate response
        response = self.llm.invoke(prompt.format(
            user_message=user_message,
            available_actions=actions_text
        ))
        
        # Parse LLM response
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group())
            else:
                parsed_data = json.loads(response_text)
            
            # Validate and create ParsedIntent
            action_str = parsed_data.get("action", "unknown")
            try:
                action = AdminActionType(action_str)
            except ValueError:
                action = AdminActionType.UNKNOWN
            
            confidence = float(parsed_data.get("confidence", 0.5))
            parameters = parsed_data.get("parameters", {})
            reasoning = parsed_data.get("reasoning", "")
            requires_confirmation = parsed_data.get("requires_confirmation", True)
            
            # Override confirmation for safe actions
            if action in [AdminActionType.LIST_FAQS, AdminActionType.VIEW_ANALYTICS, 
                         AdminActionType.VIEW_SETTINGS, AdminActionType.HELP, 
                         AdminActionType.GREETING, AdminActionType.VIEW_KNOWLEDGE_BASE]:
                requires_confirmation = False
            
            logger.info(f"✅ LLM parsed: {action.value} (confidence: {confidence:.2f})")
            
            return ParsedIntent(
                action=action,
                confidence=confidence,
                parameters=parameters,
                original_text=user_message,
                requires_confirmation=requires_confirmation,
                security_risk=False,
                llm_reasoning=reasoning
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"❌ Failed to parse LLM response: {e}")
            logger.error(f"Raw LLM response: {response_text}")
            # Fall back to pattern matching
            return self._parse_with_patterns(user_message)
    
    def _parse_with_patterns(self, user_message: str) -> ParsedIntent:
        """Fallback pattern-based parsing"""
        logger.info("🔄 Using pattern-based fallback parsing")
        
        message_lower = user_message.lower().strip()
        
        # Check each pattern category
        for action_type, patterns in self.fallback_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    confidence = 0.7  # Lower confidence for pattern matching
                    
                    # Extract basic parameters for FAQ operations
                    parameters = {}
                    if action_type == AdminActionType.ADD_FAQ:
                        # Try to extract question and answer
                        qa_pattern = r'(?:question|faq)[:\s]+(.+?)(?:\s+answer[:\s]+(.+))?$'
                        qa_match = re.search(qa_pattern, user_message, re.IGNORECASE)
                        if qa_match:
                            parameters['question'] = qa_match.group(1).strip()
                            if qa_match.group(2):
                                parameters['answer'] = qa_match.group(2).strip()
                    
                    requires_confirmation = action_type not in [
                        AdminActionType.LIST_FAQS, AdminActionType.VIEW_ANALYTICS,
                        AdminActionType.VIEW_SETTINGS, AdminActionType.HELP,
                        AdminActionType.GREETING
                    ]
                    
                    return ParsedIntent(
                        action=action_type,
                        confidence=confidence,
                        parameters=parameters,
                        original_text=user_message,
                        requires_confirmation=requires_confirmation,
                        security_risk=False,
                        llm_reasoning="Pattern-based matching"
                    )
        
        # No patterns matched - unknown intent
        return ParsedIntent(
            action=AdminActionType.UNKNOWN,
            confidence=0.0,
            parameters={},
            original_text=user_message,
            requires_confirmation=False,
            llm_reasoning="No patterns matched"
        )
    
    def _get_action_description(self, action: AdminActionType) -> str:
        """Get human-readable description of action"""
        descriptions = {
            AdminActionType.ADD_FAQ: "Add new FAQ question and answer",
            AdminActionType.UPDATE_FAQ: "Modify existing FAQ",
            AdminActionType.DELETE_FAQ: "Remove FAQ permanently", 
            AdminActionType.LIST_FAQS: "Show all current FAQs",
            AdminActionType.SEARCH_FAQS: "Find specific FAQs",
            AdminActionType.UPDATE_PROMPT: "Change chatbot system prompt/personality",
            AdminActionType.UPDATE_BRANDING: "Modify colors, logo, appearance",
            AdminActionType.UPDATE_EMAIL_CONFIG: "Update email settings",
            AdminActionType.VIEW_ANALYTICS: "Show usage statistics and performance",
            AdminActionType.VIEW_SETTINGS: "Display current configuration",
            AdminActionType.SETUP_DISCORD: "Configure Discord integration",
            AdminActionType.SETUP_SLACK: "Configure Slack integration", 
            AdminActionType.SETUP_INSTAGRAM: "Configure Instagram integration",
            AdminActionType.SETUP_TELEGRAM: "Configure Telegram integration",
            AdminActionType.VIEW_KNOWLEDGE_BASE: "Show uploaded documents",
            AdminActionType.HELP: "Show available commands and assistance",
            AdminActionType.GREETING: "Friendly greeting or conversation starter"
        }
        return descriptions.get(action, "Unknown action")
    
    def enhance_with_context(self, intent: ParsedIntent, state, conversation_history: List[Dict] = None) -> ParsedIntent:
        """
        Enhances a parsed intent using the full conversational state.
        This is the core of contextual understanding for the admin engine.
        """
        if not self.llm_available or not state.current_intent:
            return intent

        # If the user just says "yes" or "confirm", and we are pending confirmation,
        # we can infer the intent is to confirm the action.
        confirmation_words = ['yes', 'y', 'confirm', 'proceed', 'do it', 'go ahead']
        if state.pending_confirmation and intent.original_text.lower().strip() in confirmation_words:
            intent.action = AdminActionType.CONFIRM
            intent.confidence = 0.99
            intent.llm_reasoning = "User provided a confirmation word while in a pending confirmation state."
            return intent

        try:
            # Build a rich context string for the LLM
            context_text = f"The user and bot were discussing how to '{state.current_intent.value}'. "
            if state.required_params:
                context_text += f"The bot is waiting for the user to provide: {', '.join(state.required_params.keys())}. "
            if state.pending_confirmation:
                context_text += "The bot is waiting for the user to confirm the action. "

            history_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in conversation_history[-4:]])


            enhance_prompt = PromptTemplate(
                input_variables=["current_message", "previous_context", "history"],
                template="""You are an expert intent refiner. A user is in the middle of an admin task. Your job is to interpret their latest message based on the conversational context.

Conversation Context: {previous_context}

Recent Chat History:
{history}

User's Latest Message: "{current_message}"

TASK: Analyze the user's latest message.
1.  Does it provide the missing information the bot was waiting for?
2.  Is it a confirmation ('yes') or cancellation ('no')?
3.  Is it a completely new request, meaning the user is abandoning the current task?

Based on your analysis, provide a refined action and extract any relevant parameters (like a question or answer for an FAQ).

RESPONSE FORMAT (JSON only):
{{
    "action": "action_name",
    "parameters": {{ "param_name": "value" }},
    "reasoning": "A brief explanation of your decision."
}}
"""
            )

            response = self.llm.invoke(enhance_prompt.format(
                current_message=intent.original_text,
                previous_context=context_text,
                history=history_text
            ))

            response_text = response.content if hasattr(response, 'content') else str(response)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                enhancement_data = json.loads(json_match.group())
                
                # Update the original intent with the new, context-aware information
                try:
                    intent.action = AdminActionType(enhancement_data.get("action", intent.action.value))
                except ValueError:
                    # Keep original action if LLM hallucinates an invalid one
                    pass 
                intent.parameters.update(enhancement_data.get("parameters", {}))
                intent.llm_reasoning = enhancement_data.get("reasoning", "")
                intent.confidence = 0.95 # High confidence as it's context-aware

                logger.info(f"🔄 Enhanced intent with context. New action: {intent.action.value}")
                return intent

        except Exception as e:
            logger.error(f"Error enhancing intent with context: {e}")
        
        # Fallback to the original intent if enhancement fails
        return intent
    
    
    
    def extract_faq_parameters_llm(self, user_message: str) -> Dict[str, Any]:
        """
        Use LLM to extract FAQ question and answer from flexible user input
        """
        if not self.llm_available:
            return {}
        
        try:
            extract_prompt = PromptTemplate(
                input_variables=["user_message"],
                template="""Extract FAQ question and answer from this user message.

USER MESSAGE: "{user_message}"

The user wants to add an FAQ but may have provided it in various formats:
- "Add FAQ: What are your hours? Answer: 9-5 weekdays"
- "Create a question about pricing - we charge $10/month"
- "Add this FAQ: How do I cancel? Users can cancel anytime in settings"
- "New FAQ about shipping: We ship worldwide in 3-5 days"

RESPONSE FORMAT (JSON):
{{
    "question": "extracted question or null",
    "answer": "extracted answer or null", 
    "partial": true/false,
    "confidence": 0.95
}}

If only partial information is provided, set partial=true.
If you can't extract clear question/answer, set both to null.

JSON Response:"""
            )
            
            response = self.llm.invoke(extract_prompt.format(user_message=user_message))
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                extraction_data = json.loads(json_match.group())
                logger.info(f"✅ Extracted FAQ parameters: {extraction_data}")
                return extraction_data
        
        except Exception as e:
            logger.error(f"Error extracting FAQ parameters: {e}")
        
        return {}
    
    def get_help_text(self) -> str:
        """Generate help text for available commands"""
        return """
🤖 **Super Tenant Admin Assistant - I understand natural language!**

**💬 Just tell me what you want to do:**

**📋 FAQ Management:**
• "Add FAQ about our business hours"
• "Create a question about pricing with answer $10/month"
• "Update FAQ number 5"
• "Delete the shipping FAQ"
• "Show me all my FAQs"

**⚙️ Settings:**
• "Change my chatbot's personality"
• "Update my branding colors"
• "Modify my email settings"
• "Show my current settings"

**📊 Analytics:**
• "How is my chatbot performing?"
• "Show usage statistics"
• "What's my monthly activity?"

**🔗 Integrations:**
• "Set up Discord for my chatbot"
• "How do I connect Slack?"
• "Configure Instagram messaging"

**📚 Knowledge Base:**
• "Show my uploaded documents"
• "What files do I have?"

**🆘 Examples:**
• "I need to add a FAQ about our return policy - customers can return items within 30 days"
• "Can you show me how many conversations I had this month?"
• "Remove question #3 from my FAQ list"
• "What integrations do I have set up?"

**I understand natural conversation - just ask me what you need!** 🚀
"""

# Export enhanced parser
def get_llm_admin_intent_parser() -> LLMAdminIntentParser:
    """Factory function to create LLM-enhanced intent parser"""
    return LLMAdminIntentParser()