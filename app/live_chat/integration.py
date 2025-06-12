from app.live_chat.api import router as live_chat_router
from app.live_chat.router_service import LiveChatRouter
from app.live_chat.state_manager import state_manager

async def check_for_handoff(tenant_id: int, user_message: str, customer_id: str, 
                           bot_session_id: str, db: Session) -> dict:
    """
    Check if user message should trigger handoff to live chat
    Call this from your chatbot engine before processing the message
    """
    
    chat_router = LiveChatRouter(db, state_manager)
    
    # Check for handoff triggers
    is_handoff, reason = chat_router.check_handoff_triggers(user_message)
    
    if is_handoff:
        # Initiate handoff
        result = chat_router.initiate_handoff(
            tenant_id=tenant_id,
            customer_id=customer_id,
            bot_session_id=bot_session_id,
            handoff_reason=reason
        )
        
        return {
            "handoff_initiated": True,
            "session_id": result["session_id"],
            "message": result["message"],
            "queue_position": result.get("queue_position", 0)
        }
    
    return {"handoff_initiated": False}