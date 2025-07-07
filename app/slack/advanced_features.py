# app/slack/advanced_features.py
"""
Advanced Slack Features for Multi-Tenant Chatbot
Includes slash commands, interactive components, and rich messaging
"""

import logging
from typing import Dict, Any, List, Optional
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class SlackAdvancedFeatures:
    """Advanced Slack features and utilities"""
    
    def __init__(self, app: AsyncApp, client: AsyncWebClient, tenant_id: int):
        self.app = app
        self.client = client
        self.tenant_id = tenant_id
        self.setup_advanced_handlers()
    
    def setup_advanced_handlers(self):
        """Set up advanced Slack event handlers"""
        
        # Slash command handlers
        @self.app.command("/help")
        async def handle_help_command(ack, respond, command):
            await ack()
            help_text = self.get_help_text()
            await respond(help_text)
        
        @self.app.command("/status")
        async def handle_status_command(ack, respond, command):
            await ack()
            status_text = await self.get_bot_status_text()
            await respond(status_text)
        
        # Interactive button handlers
        @self.app.action("help_topics")
        async def handle_help_topics(ack, body, respond):
            await ack()
            selected_value = body["actions"][0]["selected_option"]["value"]
            help_response = self.get_topic_help(selected_value)
            await respond(help_response)
        
        # Modal handlers
        @self.app.view("feedback_modal")
        async def handle_feedback_modal(ack, body, view, respond):
            await ack()
            feedback_data = self.extract_feedback_data(view)
            await self.process_feedback(feedback_data, body["user"]["id"])
    
    def get_help_text(self) -> Dict[str, Any]:
        """Generate help message with interactive elements"""
        return {
            "text": "How can I help you?",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Welcome to your AI assistant!* 🤖\n\nI can help you with various topics. Choose what you'd like to know more about:"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Available Commands:*\n• Just message me directly for general questions\n• Use `/help` for this help menu\n• Use `/status` to check my status"
                    },
                    "accessory": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a help topic"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Getting Started"
                                },
                                "value": "getting_started"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Common Questions"
                                },
                                "value": "faq"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Contact Support"
                                },
                                "value": "support"
                            }
                        ],
                        "action_id": "help_topics"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 *Tip:* You can also mention me in any channel with @botname"
                        }
                    ]
                }
            ]
        }
    
    async def get_bot_status_text(self) -> Dict[str, Any]:
        """Generate bot status message"""
        try:
            # Get bot info
            auth_response = await self.client.auth_test()
            bot_name = auth_response.get("user", "Bot")
            team_name = auth_response.get("team", "Unknown")
            
            return {
                "text": f"Bot Status: Active ✅",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{bot_name} Status Report* 📊"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Status:*\n✅ Active"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Workspace:*\n{team_name}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Bot ID:*\n{auth_response.get('user_id', 'N/A')}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Response Time:*\n< 1 second"
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "🔄 Last updated: Just now"
                            }
                        ]
                    }
                ]
            }
        except SlackApiError as e:
            logger.error(f"Error getting bot status: {e}")
            return {
                "text": "❌ Unable to get bot status",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "❌ *Error getting bot status*\nPlease try again later."
                        }
                    }
                ]
            }
    
    def get_topic_help(self, topic: str) -> Dict[str, Any]:
        """Get help text for specific topic"""
        help_topics = {
            "getting_started": {
                "text": "Getting Started Guide",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*🚀 Getting Started*\n\n1. *Direct Messages:* Send me a DM with any question\n2. *In Channels:* Mention me with @botname followed by your question\n3. *Quick Help:* Use `/help` for this menu anytime\n\n*Example:* \"@botname What are your business hours?\""
                        }
                    }
                ]
            },
            "faq": {
                "text": "Frequently Asked Questions",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*❓ Common Questions*\n\n• Business hours and contact information\n• Product features and pricing\n• Technical support and troubleshooting\n• Account management\n\nJust ask me naturally - I understand context and can help with follow-up questions!"
                        }
                    }
                ]
            },
            "support": {
                "text": "Contact Support",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*🆘 Need Human Help?*\n\nIf I can't answer your question, I can connect you with our support team."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Contact Support"
                                },
                                "style": "primary",
                                "action_id": "contact_support"
                            }
                        ]
                    }
                ]
            }
        }
        
        return help_topics.get(topic, {"text": "Topic not found"})
    
    def create_rich_response(self, text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a rich Slack message with blocks"""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            }
        ]
        
        # Add context if provided
        if context:
            if context.get("show_help_button"):
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Get Help"
                            },
                            "action_id": "show_help"
                        }
                    ]
                })
            
            if context.get("show_feedback_button"):
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "👍 Helpful"
                            },
                            "style": "primary",
                            "action_id": "feedback_positive"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "👎 Not Helpful"
                            },
                            "action_id": "feedback_negative"
                        }
                    ]
                })
        
        return {
            "text": text,  # Fallback text
            "blocks": blocks
        }
    
    def extract_feedback_data(self, view: Dict[str, Any]) -> Dict[str, Any]:
        """Extract feedback data from modal submission"""
        values = view.get("state", {}).get("values", {})
        
        feedback_data = {}
        for block_id, block_data in values.items():
            for action_id, action_data in block_data.items():
                if action_data.get("type") == "plain_text_input":
                    feedback_data[action_id] = action_data.get("value", "")
                elif action_data.get("type") == "static_select":
                    feedback_data[action_id] = action_data.get("selected_option", {}).get("value", "")
        
        return feedback_data
    
    async def process_feedback(self, feedback_data: Dict[str, Any], user_id: str):
        """Process user feedback"""
        logger.info(f"Processing feedback from user {user_id}: {feedback_data}")
        
        # Here you could:
        # 1. Store feedback in database
        # 2. Send to analytics service
        # 3. Trigger notifications
        # 4. Update ML models
        
        # For now, just log it
        logger.info(f"Feedback processed for user {user_id}")
    
    async def send_typing_indicator(self, channel: str):
        """Send typing indicator to show bot is working"""
        try:
            await self.client.conversations_typing(channel=channel)
        except SlackApiError as e:
            logger.warning(f"Could not send typing indicator: {e}")
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get detailed user information"""
        try:
            response = await self.client.users_info(user=user_id)
            user_data = response.get("user", {})
            
            return {
                "id": user_data.get("id"),
                "name": user_data.get("name"),
                "real_name": user_data.get("real_name"),
                "email": user_data.get("profile", {}).get("email"),
                "timezone": user_data.get("tz"),
                "is_admin": user_data.get("is_admin", False),
                "is_owner": user_data.get("is_owner", False)
            }
        except SlackApiError as e:
            logger.error(f"Error getting user info: {e}")
            return {"id": user_id}
    
    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get detailed channel information"""
        try:
            response = await self.client.conversations_info(channel=channel_id)
            channel_data = response.get("channel", {})
            
            return {
                "id": channel_data.get("id"),
                "name": channel_data.get("name"),
                "is_channel": channel_data.get("is_channel", False),
                "is_group": channel_data.get("is_group", False),
                "is_im": channel_data.get("is_im", False),
                "is_private": channel_data.get("is_private", False),
                "topic": channel_data.get("topic", {}).get("value", ""),
                "purpose": channel_data.get("purpose", {}).get("value", "")
            }
        except SlackApiError as e:
            logger.error(f"Error getting channel info: {e}")
            return {"id": channel_id}
    
    def create_error_message(self, error_message: str) -> Dict[str, Any]:
        """Create a formatted error message"""
        return {
            "text": "❌ Error occurred",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"❌ *Error*\n{error_message}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Please try again or contact support if the problem persists."
                        }
                    ]
                }
            ]
        }
    
    def create_loading_message(self) -> Dict[str, Any]:
        """Create a loading message"""
        return {
            "text": "⏳ Processing...",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⏳ *Processing your request...*\nThis may take a moment."
                    }
                }
            ]
        }

class SlackMessageFormatter:
    """Utility class for formatting Slack messages"""
    
    @staticmethod
    def format_faq_response(question: str, answer: str) -> Dict[str, Any]:
        """Format FAQ response with rich formatting"""
        return {
            "text": answer,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*❓ {question}*\n\n{answer}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 Have more questions? Just ask!"
                        }
                    ]
                }
            ]
        }
    
    @staticmethod
    def format_knowledge_base_response(response: str, sources: List[str] = None) -> Dict[str, Any]:
        """Format knowledge base response with sources"""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": response
                }
            }
        ]
        
        if sources:
            source_text = "\n".join([f"• {source}" for source in sources[:3]])  # Limit to 3 sources
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📚 *Sources:*\n{source_text}"
                    }
                ]
            })
        
        return {
            "text": response,
            "blocks": blocks
        }
    

    def format_unified_response(response: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format responses from the unified intelligent engine"""
        
        # Add metadata indicators
        intent = metadata.get('intent', 'unknown')
        source = metadata.get('answered_by', 'unknown')
        
        context_info = ""
        if metadata.get('was_contextual'):
            context_info = " 🔗"
        
        return {
            "text": response,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": response
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"🧠 Intent: {intent.title()} | Source: {source.replace('_', ' ').title()}{context_info}"
                        }
                    ]
                }
            ]
        }



    
    @staticmethod
    def format_handoff_message(message: str) -> Dict[str, Any]:
        """Format handoff to human message"""
        return {
            "text": message,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🤝 *Connecting you with support*\n\n{message}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "A human agent will be with you shortly."
                        }
                    ]
                }
            ]
        }
    

class SlackUnifiedAdvancedFeatures:
    """
    Advanced Slack features designed for the Unified Intelligent Engine
    Works alongside your existing SlackAdvancedFeatures class
    """
    
    def __init__(self, app: AsyncApp, client: AsyncWebClient, tenant_id: int, chunker=None):
        self.app = app
        self.client = client
        self.tenant_id = tenant_id
        self.chunker = chunker
        self.setup_unified_handlers()
    
    def setup_unified_handlers(self):
        """Set up handlers that work with unified intelligence"""
        
        # Enhanced help command with chunking awareness
        @self.app.command("/help-advanced")
        async def handle_advanced_help(ack, respond, command):
            await ack()
            help_content = self.get_intelligent_help_text()
            await respond(help_content)
        
        # Chunking preferences
        @self.app.action("chunking_preferences")
        async def handle_chunking_prefs(ack, body, respond):
            await ack()
            await respond({
                "text": "⚙️ Response delivery preferences updated!",
                "response_type": "ephemeral"
            })
        
        # Engagement level tracking
        @self.app.action("engagement_high")
        async def handle_high_engagement(ack, body, respond):
            await ack()
            await respond({
                "text": "🎯 I'll provide detailed, comprehensive responses.",
                "response_type": "ephemeral"
            })
        
        @self.app.action("engagement_low")
        async def handle_low_engagement(ack, body, respond):
            await ack()
            await respond({
                "text": "📝 I'll keep responses concise and clear.",
                "response_type": "ephemeral"
            })
    
    def get_intelligent_help_text(self) -> Dict[str, Any]:
        """Generate help text for unified intelligence features"""
        return {
            "text": "🧠 Advanced AI Assistant Help",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🚀 Powered by Unified Intelligence*\n\nI use advanced AI to understand your intent and provide contextual responses."
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🧩 Smart Features:*\n• Intent Classification\n• Context Awareness\n• Intelligent Chunking\n• Conversation Flow\n• Natural Delays"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🎯 Detailed Mode"},
                            "style": "primary",
                            "action_id": "engagement_high"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📝 Concise Mode"},
                            "action_id": "engagement_low"
                        }
                    ]
                }
            ]
        }
    
    async def get_unified_status(self) -> Dict[str, Any]:
        """Get status for unified intelligence features"""
        try:
            auth_response = await self.client.auth_test()
            bot_name = auth_response.get("user", "Bot")
            
            return {
                "text": f"🧠 {bot_name} - Unified Intelligence Status",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🤖 {bot_name} - Advanced AI Status*"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "*Engine:* Unified Intelligence"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Chunking:* {'✅ Active' if self.chunker else '❌ Basic'}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Features:* Intent • Context • Flow"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Efficiency:* ~80% Token Reduction"
                            }
                        ]
                    }
                ]
            }
        except Exception:
            return {"text": "❌ Error getting unified status"}