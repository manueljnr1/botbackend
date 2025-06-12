from fastapi import APIRouter, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import redis
import logging
import json
from datetime import datetime

from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.live_chat.router_service import LiveChatRouter
from app.live_chat.message_service import MessageService
from app.live_chat.agent_service import AgentService
from app.live_chat.state_manager import ChatStateManager
from app.live_chat.websocket_hub import websocket_hub

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis connection (configure in your settings)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
state_manager = ChatStateManager(redis_client)

# ===== PYDANTIC MODELS =====

class HandoffRequest(BaseModel):
    customer_id: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    message: str
    bot_session_id: Optional[str] = None
    platform: str = "web"
    department: str = "general"

class SendMessageRequest(BaseModel):
    session_id: str
    message: str
    from_agent: bool = False
    agent_id: Optional[int] = None

class AgentStatusRequest(BaseModel):
    agent_id: int
    status: str  # "online", "offline", "busy", "away"

# ===== HANDOFF ENDPOINTS =====

@router.post("/handoff")
async def initiate_handoff(
    request: HandoffRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Initiate handoff from bot to live chat"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat_router = LiveChatRouter(db, state_manager)
    
    # Check if message contains handoff trigger
    is_handoff, reason = chat_router.check_handoff_triggers(request.message)
    
    if is_handoff:
        # Initiate live chat
        result = chat_router.initiate_handoff(
            tenant_id=tenant.id,
            customer_id=request.customer_id,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            bot_session_id=request.bot_session_id,
            handoff_reason=reason,
            department=request.department,
            platform=request.platform
        )
        
        # Notify available agents via WebSocket
        await websocket_hub.notify_agents_new_conversation(tenant.id, {
            "session_id": result["session_id"],
            "customer_name": request.customer_name or "Anonymous",
            "department": request.department,
            "platform": request.platform,
            "handoff_reason": reason
        })
        
        return {
            "handoff_initiated": True,
            "session_id": result["session_id"],
            "status": result["status"],
            "queue_position": result.get("queue_position", 0),
            "estimated_wait_minutes": result.get("estimated_wait_minutes", 0),
            "message": result["message"]
        }
    else:
        # No handoff needed - let bot handle it
        return {
            "handoff_initiated": False,
            "message": "Continue with bot conversation"
        }

@router.get("/conversation/{session_id}/status")
async def get_conversation_status(
    session_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current status of a conversation"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat_router = LiveChatRouter(db, state_manager)
    status = chat_router._get_conversation_status(session_id)
    
    return status

# ===== MESSAGE ENDPOINTS =====

@router.post("/messages")
async def send_message(
    request: SendMessageRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Send a message in conversation"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    message_service = MessageService(db, state_manager)
    
    try:
        message_data = message_service.send_message(
            session_id=request.session_id,
            content=request.message,
            from_agent=request.from_agent,
            agent_id=request.agent_id
        )
        
        # Broadcast via WebSocket
        await websocket_hub.broadcast_to_conversation(request.session_id, {
            "type": "new_message",
            "data": message_data
        })
        
        return message_data
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/conversation/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = 50,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get messages for a conversation"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    message_service = MessageService(db, state_manager)
    messages = message_service.get_conversation_messages(session_id, limit)
    
    return {"messages": messages}

# ===== AGENT ENDPOINTS =====

@router.post("/agent/login")
async def agent_login(
    request: AgentStatusRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Agent login/come online"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent_service = AgentService(db, state_manager)
    success = agent_service.agent_login(request.agent_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Process queue for new assignments
    chat_router = LiveChatRouter(db, state_manager)
    chat_router.process_queue(tenant.id)
    
    return {"status": "online", "message": "Agent is now online"}

@router.post("/agent/logout")
async def agent_logout(
    request: AgentStatusRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Agent logout/go offline"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent_service = AgentService(db, state_manager)
    success = agent_service.agent_logout(request.agent_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {"status": "offline", "message": "Agent is now offline"}

@router.get("/agent/{agent_id}/dashboard")
async def get_agent_dashboard(
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get agent dashboard data"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent_service = AgentService(db, state_manager)
    dashboard_data = agent_service.get_agent_dashboard_data(agent_id)
    
    if "error" in dashboard_data:
        raise HTTPException(status_code=404, detail=dashboard_data["error"])
    
    return dashboard_data

@router.post("/agent/{agent_id}/take-conversation/{session_id}")
async def agent_take_conversation(
    agent_id: int,
    session_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Agent manually takes a conversation from queue"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Get conversation
    from app.live_chat.models import Conversation, ConversationStatus
    conversation = db.query(Conversation).filter(
        Conversation.session_id == session_id,
        Conversation.tenant_id == tenant.id,
        Conversation.status == ConversationStatus.QUEUED
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not available")
    
    # Check agent availability
    available_agents = state_manager.get_available_agents(tenant.id)
    agent_available = any(a["agent_id"] == agent_id for a in available_agents)
    
    if not agent_available:
        raise HTTPException(status_code=400, detail="Agent not available")
    
    # Assign conversation
    chat_router = LiveChatRouter(db, state_manager)
    conversation.agent_id = agent_id
    conversation.status = ConversationStatus.ACTIVE
    conversation.assigned_at = datetime.utcnow()
    
    # Calculate queue time
    queue_time = (datetime.utcnow() - conversation.created_at).total_seconds()
    conversation.queue_time_seconds = int(queue_time)
    
    db.commit()
    
    # Update Redis
    state_manager.update_conversation_state(session_id, {
        "status": "active",
        "agent_id": agent_id,
        "assigned_at": datetime.utcnow().isoformat()
    })
    
    state_manager.assign_conversation_to_agent(tenant.id, agent_id, session_id)
    state_manager.remove_from_queue(tenant.id, session_id)
    
    # Notify via WebSocket
    await websocket_hub.notify_conversation_assigned(session_id, agent_id)
    
    return {"message": "Conversation assigned successfully"}

# ===== STATS ENDPOINTS =====

@router.get("/stats/dashboard")
async def get_dashboard_stats(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get live chat dashboard statistics"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Get stats from Redis and DB
    queue_length = state_manager.get_queue_length(tenant.id)
    available_agents = len(state_manager.get_available_agents(tenant.id))
    
    # Active conversations from DB
    from app.live_chat.models import Conversation, ConversationStatus
    active_conversations = db.query(Conversation).filter(
        Conversation.tenant_id == tenant.id,
        Conversation.status == ConversationStatus.ACTIVE
    ).count()
    
    return {
        "queue_length": queue_length,
        "active_conversations": active_conversations,
        "available_agents": available_agents,
        "total_agents_online": len(state_manager.get_available_agents(tenant.id))
    }


@router.websocket("/ws/customer/{customer_id}")
async def websocket_customer_endpoint(
    websocket: WebSocket,
    customer_id: str,
    session_id: str = None
):
    """WebSocket endpoint for customers"""
    await websocket_hub.connect_customer(websocket, customer_id, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "send_message":
                # Handle customer message
                session_id = message_data.get("session_id")
                content = message_data.get("message")
                
                if session_id and content:
                    # Send via message service
                    message_service = MessageService(next(get_db()), state_manager)
                    try:
                        message_result = message_service.send_message(
                            session_id=session_id,
                            content=content,
                            from_agent=False,
                            sender_name="Customer"
                        )
                        
                        # Broadcast to conversation
                        await websocket_hub.broadcast_to_conversation(session_id, {
                            "type": "new_message",
                            "data": message_result
                        })
                        
                    except Exception as e:
                        logger.error(f"Error sending customer message: {e}")
            
            elif message_data.get("type") == "typing":
                # Handle typing indicator
                session_id = message_data.get("session_id")
                if session_id:
                    await websocket_hub.broadcast_to_conversation(session_id, {
                        "type": "typing_indicator",
                        "data": {
                            "is_typing": message_data.get("is_typing", False),
                            "from_agent": False
                        }
                    })
                    
    except Exception as e:
        logger.error(f"Customer WebSocket error: {e}")
    finally:
        websocket_hub.disconnect_customer(customer_id, session_id)

@router.websocket("/ws/agent/{agent_id}")
async def websocket_agent_endpoint(
    websocket: WebSocket,
    agent_id: int
):
    """WebSocket endpoint for agents"""
    await websocket_hub.connect_agent(websocket, agent_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "send_message":
                # Handle agent message
                session_id = message_data.get("session_id")
                content = message_data.get("message")
                
                if session_id and content:
                    # Send via message service
                    message_service = MessageService(next(get_db()), state_manager)
                    try:
                        message_result = message_service.send_message(
                            session_id=session_id,
                            content=content,
                            from_agent=True,
                            agent_id=agent_id,
                            sender_name="Agent"
                        )
                        
                        # Broadcast to conversation
                        await websocket_hub.broadcast_to_conversation(session_id, {
                            "type": "new_message",
                            "data": message_result
                        })
                        
                    except Exception as e:
                        logger.error(f"Error sending agent message: {e}")
            
            elif message_data.get("type") == "typing":
                # Handle typing indicator
                session_id = message_data.get("session_id")
                if session_id:
                    await websocket_hub.broadcast_to_conversation(session_id, {
                        "type": "typing_indicator",
                        "data": {
                            "is_typing": message_data.get("is_typing", False),
                            "from_agent": True,
                            "agent_id": agent_id
                        }
                    })
            
            elif message_data.get("type") == "take_conversation":
                # Handle agent taking conversation from queue
                session_id = message_data.get("session_id")
                if session_id:
                    try:
                        # Use the existing API endpoint logic
                        db = next(get_db())
                        from app.live_chat.models import Conversation, ConversationStatus
                        
                        conversation = db.query(Conversation).filter(
                            Conversation.session_id == session_id,
                            Conversation.status == ConversationStatus.QUEUED
                        ).first()
                        
                        if conversation:
                            # Assign conversation
                            conversation.agent_id = agent_id
                            conversation.status = ConversationStatus.ACTIVE
                            conversation.assigned_at = datetime.utcnow()
                            
                            # Calculate queue time
                            queue_time = (datetime.utcnow() - conversation.created_at).total_seconds()
                            conversation.queue_time_seconds = int(queue_time)
                            
                            db.commit()
                            
                            # Update Redis
                            state_manager.update_conversation_state(session_id, {
                                "status": "active",
                                "agent_id": agent_id,
                                "assigned_at": datetime.utcnow().isoformat()
                            })
                            
                            state_manager.assign_conversation_to_agent(conversation.tenant_id, agent_id, session_id)
                            state_manager.remove_from_queue(conversation.tenant_id, session_id)
                            
                            # Notify participants
                            await websocket_hub.notify_conversation_assigned(session_id, agent_id)
                            
                        db.close()
                        
                    except Exception as e:
                        logger.error(f"Error taking conversation: {e}")
                    
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
    finally:
        websocket_hub.disconnect_agent(agent_id)