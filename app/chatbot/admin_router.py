# app/chatbot/enhanced_admin_router.py
"""
Enhanced Admin Router with LLM-powered natural language understanding
Replaces the basic admin router with intelligent conversation capabilities
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.chatbot.super_tenant_admin_engine import get_super_tenant_admin_engine
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()

class EnhancedAdminChatRequest(BaseModel):
    message: str
    user_identifier: str
    session_context: Optional[Dict[str, Any]] = None
    conversation_mode: bool = True  # Enable conversational features

class EnhancedAdminChatResponse(BaseModel):
    success: bool
    response: str
    action: Optional[str] = None
    requires_confirmation: bool = False
    requires_input: bool = False
    pending_action: Optional[str] = None
    tenant_id: int
    session_id: Optional[str] = None
    error: Optional[str] = None
    confidence: Optional[float] = None
    llm_reasoning: Optional[str] = None
    conversation_enhanced: bool = True

@router.post("/enhanced-admin-chat", response_model=EnhancedAdminChatResponse)
async def enhanced_admin_chat(
    request: EnhancedAdminChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Enhanced admin chat with LLM-powered natural language understanding
    Supports flexible, conversational tenant management
    """
    try:
        logger.info(f"🧠 Enhanced admin chat request: {request.message[:50]}...")
        
        # 🔒 CRITICAL: Validate API key and get authenticated tenant
        tenant = get_tenant_from_api_key(api_key, db)
        logger.info(f"🔒 Authenticated tenant: {tenant.name} (ID: {tenant.id})")
        
        # 🔒 SECURITY CHECK: Verify tenant is active
        if not tenant.is_active:
            logger.warning(f"🚨 Inactive tenant attempted admin access: {tenant.id}")
            raise HTTPException(status_code=403, detail="Tenant account is inactive")
        
        # Initialize enhanced admin engine with LLM capabilities
        admin_engine = get_super_tenant_admin_engine(db)
        
        # 🔒 CRITICAL: Pass authenticated tenant ID to ensure security boundary
        result = admin_engine.process_admin_message(
            user_message=request.message,
            authenticated_tenant_id=tenant.id,  # 🔒 Security boundary
            user_identifier=request.user_identifier,
            session_context=request.session_context
        )
        
        logger.info(f"✅ Enhanced admin action processed for tenant {tenant.id}: {result.get('success')}")
        
        return EnhancedAdminChatResponse(
            success=result.get("success", False),
            response=result.get("response", ""),
            action=result.get("action"),
            requires_confirmation=result.get("requires_confirmation", False),
            requires_input=result.get("requires_input", False),
            pending_action=result.get("pending_action"),
            tenant_id=tenant.id,
            session_id=result.get("session_id"),
            error=result.get("error"),
            confidence=result.get("confidence"),
            llm_reasoning=result.get("llm_reasoning"),
            conversation_enhanced=True
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (like invalid API key)
        raise
    except Exception as e:
        logger.error(f"💥 Error in enhanced admin chat: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="An internal error occurred processing your admin request"
        )

@router.get("/admin-capabilities-enhanced")
async def get_enhanced_admin_capabilities(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get enhanced admin capabilities with LLM features
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "business_name": tenant.business_name,
            "enhanced_features": {
                "natural_language_processing": True,
                "conversation_memory": True,
                "intelligent_suggestions": True,
                "context_awareness": True,
                "flexible_commands": True
            },
            "admin_capabilities": {
                "faq_management": True,
                "settings_update": True,
                "analytics_view": True,
                "branding_update": True,
                "integration_setup": True,
                "knowledge_base_view": True
            },
            "conversation_examples": [
                {
                    "natural": "I want to add a FAQ about our return policy",
                    "ai_response": "I'll help you create that FAQ! What should customers know about your return policy?"
                },
                {
                    "natural": "How many people used my chatbot last month?",
                    "ai_response": "Let me get your analytics... You had 234 chat sessions with 1,456 total messages last month!"
                },
                {
                    "natural": "Remove the FAQ about shipping",
                    "ai_response": "I found FAQ #5 about shipping. Are you sure you want to delete it?"
                },
                {
                    "natural": "What integrations do I have?",
                    "ai_response": "You have Discord ✅ and Slack ✅ active. Telegram is not set up yet."
                }
            ],
            "intelligence_features": [
                "Understands natural language - no rigid commands needed",
                "Remembers conversation context across messages",
                "Provides intelligent suggestions based on your usage",
                "Handles follow-up questions seamlessly",
                "Offers contextual help and recommendations",
                "Learns from your communication style"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting enhanced admin capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get admin capabilities")

@router.post("/admin-natural-command")
async def process_natural_admin_command(
    command: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Process a single natural language admin command
    Simplified endpoint for direct command execution
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Generate a simple user identifier for this request
        import uuid
        user_identifier = f"direct_command_{str(uuid.uuid4())[:8]}"
        
        # Process command
        admin_engine = get_enhanced_super_tenant_admin_engine(db)
        result = admin_engine.process_admin_message(
            user_message=command,
            authenticated_tenant_id=tenant.id,
            user_identifier=user_identifier,
            session_context={"direct_command": True}
        )
        
        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "action_taken": result.get("action"),
            "requires_follow_up": result.get("requires_input", False) or result.get("requires_confirmation", False),
            "tenant_id": tenant.id,
            "command_understood": result.get("confidence", 0) > 0.5
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing natural command: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process command")

class ConversationTestRequest(BaseModel):
    messages: List[Dict[str, str]]  # [{"role": "user", "content": "message"}]

@router.post("/test-conversation")
async def test_admin_conversation(
    request: ConversationTestRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Test a full conversation flow for development/debugging
    Processes multiple messages in sequence
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        admin_engine = get_enhanced_super_tenant_admin_engine(db)
        user_identifier = f"test_conversation_{tenant.id}"
        
        conversation_results = []
        
        for i, message in enumerate(request.messages):
            if message.get("role") == "user":
                result = admin_engine.process_admin_message(
                    user_message=message["content"],
                    authenticated_tenant_id=tenant.id,
                    user_identifier=user_identifier,
                    session_context={"test_mode": True, "message_index": i}
                )
                
                conversation_results.append({
                    "message_index": i,
                    "user_input": message["content"],
                    "ai_response": result.get("response", ""),
                    "success": result.get("success", False),
                    "action": result.get("action"),
                    "confidence": result.get("confidence"),
                    "requires_follow_up": result.get("requires_input", False)
                })
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "conversation_results": conversation_results,
            "total_messages": len(conversation_results),
            "test_completed": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to test conversation")

@router.get("/admin-conversation-examples")
async def get_conversation_examples(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get example conversations showing the AI's capabilities
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        examples = [
            {
                "title": "Adding a FAQ naturally",
                "conversation": [
                    {"role": "user", "content": "I need to add information about our refund policy"},
                    {"role": "assistant", "content": "I'll help you create a FAQ about your refund policy! What should customers know about getting refunds?"},
                    {"role": "user", "content": "We offer full refunds within 30 days of purchase"},
                    {"role": "assistant", "content": "Perfect! I've created your FAQ:\n\n**Question:** What is your refund policy?\n**Answer:** We offer full refunds within 30 days of purchase\n\n**FAQ ID:** #24"}
                ]
            },
            {
                "title": "Casual analytics request",
                "conversation": [
                    {"role": "user", "content": "How's my bot doing this month?"},
                    {"role": "assistant", "content": "📊 **Analytics for YourBusiness**\n\n**Usage (Last 30 Days):**\n• Chat Sessions: 456\n• Total Messages: 1,234\n• Avg Messages per Session: 2.7\n\n**💡 Insight:** Your chatbot is performing well! Consider adding more FAQs to handle the high message volume."}
                ]
            },
            {
                "title": "Managing FAQs conversationally",
                "conversation": [
                    {"role": "user", "content": "Can you show me my FAQs?"},
                    {"role": "assistant", "content": "📋 **Your FAQs (8 total):**\n\n**#1** What are your business hours?\n**#2** How do I track my order?\n**#3** What's your return policy?\n\n💡 **What you can do:**\n• Update: 'Modify FAQ #1'\n• Delete: 'Remove FAQ #2'\n• Add new: 'Create FAQ about shipping'"},
                    {"role": "user", "content": "Delete the second one"},
                    {"role": "assistant", "content": "⚠️ **Are you sure you want to delete FAQ #2?**\n\n**Question:** How do I track my order?\n**Answer:** You can track your order using the link in your email\n\nType 'yes' to confirm or 'no' to cancel."},
                    {"role": "user", "content": "yes"},
                    {"role": "assistant", "content": "✅ FAQ #2 has been permanently deleted.\n\n🗑️ Your customers will no longer receive this automated answer. You can always create a new FAQ if needed!"}
                ]
            },
            {
                "title": "Flexible command understanding",
                "conversation": [
                    {"role": "user", "content": "I want to change my chatbot's personality to be more friendly"},
                    {"role": "assistant", "content": "🔧 **System Prompt Update**\n\nI can help you make your chatbot more friendly! Please provide your new system prompt that controls how your chatbot behaves.\n\n**Example:** 'You are a super friendly customer service agent for XYZ Company. Use emojis, be enthusiastic, and make customers feel welcome!'"},
                    {"role": "user", "content": "Make it sound like a helpful friend who loves helping customers"},
                    {"role": "assistant", "content": "✅ I've updated your chatbot's personality! Your bot will now:\n• Act like a helpful friend\n• Show enthusiasm for helping customers\n• Use a warm, approachable tone\n\nYour customers will notice the friendlier personality in their next conversation! 😊"}
                ]
            }
        ]
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "examples": examples,
            "key_features": [
                "🧠 **Natural Language**: No rigid commands - just talk naturally",
                "💭 **Context Memory**: Remembers what you discussed earlier",
                "🔄 **Follow-up Questions**: Handles back-and-forth conversations",
                "💡 **Smart Suggestions**: Offers relevant next steps",
                "⚡ **Instant Understanding**: Quickly grasps what you want to do"
            ],
            "tips": [
                "Be specific about what you want to change",
                "You can refer to FAQs by number or description",
                "Ask for help anytime - I understand casual questions",
                "Use follow-up messages to refine your requests",
                "I'll always confirm before making destructive changes"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation examples: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get examples")

@router.get("/admin-intelligence-status")
async def get_admin_intelligence_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get the status of LLM and intelligence features
    """
    try:
        # 🔒 Validate authentication
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Check LLM availability
        from app.chatbot.admin_intent_parser import LLM_AVAILABLE
        from app.config import settings
        
        llm_status = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "intelligence_status": {
                "llm_available": llm_status,
                "natural_language_processing": llm_status,
                "conversation_memory": True,  # Always available
                "context_awareness": llm_status,
                "intelligent_suggestions": llm_status
            },
            "features": {
                "enabled": [
                    "Basic command parsing",
                    "Conversation memory",
                    "Security validation",
                    "Audit logging"
                ],
                "enhanced_with_llm": [
                    "Natural language understanding",
                    "Context-aware responses", 
                    "Intelligent suggestions",
                    "Flexible parameter extraction",
                    "Conversational follow-ups"
                ] if llm_status else [],
                "fallback_mode": not llm_status
            },
            "performance": {
                "response_time": "Fast" if llm_status else "Very Fast",
                "accuracy": "High" if llm_status else "Good",
                "flexibility": "Maximum" if llm_status else "Standard"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting intelligence status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get status")
                