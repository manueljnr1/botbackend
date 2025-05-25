# app/live_chat/router.py
from fastapi import APIRouter, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
import logging
import json
from datetime import datetime

from app.database import get_db
from app.live_chat.models import Agent, LiveChat, LiveChatMessage, AgentStatus, ChatStatus, MessageType
from app.live_chat.manager import LiveChatManager
from app.live_chat.websocket_manager import connection_manager, LiveChatWebSocketHandler
from app.tenants.router import get_tenant_from_api_key
from app.tenants.models import Tenant
from app.chatbot.engine import ChatbotEngine

logger = logging.getLogger(__name__)
router = APIRouter()

# ========================== PYDANTIC MODELS ==========================

class AgentCreate(BaseModel):
    name: str
    email: str
    department: Optional[str] = "general"
    skills: Optional[List[str]] = []
    max_concurrent_chats: int = 3

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    skills: Optional[List[str]] = None
    max_concurrent_chats: Optional[int] = None
    is_active: Optional[bool] = None

class AgentOut(BaseModel):
    id: int
    name: str
    email: str
    department: Optional[str]
    status: AgentStatus
    is_active: bool
    max_concurrent_chats: int
    current_chat_count: int
    total_chats_handled: int
    
    class Config:
        from_attributes = True

class LiveChatRequest(BaseModel):
    user_identifier: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    platform: str = "web"
    department: Optional[str] = "general"
    subject: Optional[str] = None
    chatbot_session_id: Optional[str] = None

class LiveChatOut(BaseModel):
    id: int
    session_id: str
    user_identifier: str
    user_name: Optional[str]
    status: ChatStatus
    agent_id: Optional[int]
    agent_name: Optional[str] = None
    platform: str
    subject: Optional[str]
    queue_position: Optional[int] = None
    estimated_wait_time: Optional[int] = None
    started_at: datetime
    
    class Config:
        from_attributes = True

class MessageSend(BaseModel):
    content: str
    message_type: MessageType = MessageType.TEXT
    is_internal: bool = False

class MessageOut(BaseModel):
    id: int
    content: str
    message_type: MessageType
    is_from_user: bool
    sender_name: Optional[str]
    is_internal: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class HandoffRequest(BaseModel):
    user_message: str
    user_identifier: str
    chatbot_session_id: Optional[str] = None
    platform: str = "web"
    user_name: Optional[str] = None
    user_email: Optional[str] = None

class AgentStatusUpdate(BaseModel):
    status: AgentStatus

class ChatEndRequest(BaseModel):
    satisfaction_rating: Optional[int] = None

# ========================== AGENT MANAGEMENT ==========================

@router.post("/agents", response_model=AgentOut)
async def create_agent(
    agent_data: AgentCreate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create a new customer support agent"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Check if email already exists for this tenant
    existing_agent = db.query(Agent).filter(
        Agent.tenant_id == tenant.id,
        Agent.email == agent_data.email
    ).first()
    
    if existing_agent:
        raise HTTPException(status_code=400, detail="Agent with this email already exists")
    
    agent = Agent(
        tenant_id=tenant.id,
        name=agent_data.name,
        email=agent_data.email,
        department=agent_data.department,
        skills=json.dumps(agent_data.skills) if agent_data.skills else None,
        max_concurrent_chats=agent_data.max_concurrent_chats
    )
    
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    logger.info(f"Created agent {agent.name} for tenant {tenant.name}")
    return agent

@router.get("/agents", response_model=List[AgentOut])
async def list_agents(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """List all agents for the tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agents = db.query(Agent).filter(Agent.tenant_id == tenant.id).all()
    
    # Add agent_name to response
    for agent in agents:
        agent.agent_name = agent.name
    
    return agents

@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get specific agent details"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant.id
    ).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.agent_name = agent.name
    return agent

@router.put("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: int,
    agent_update: AgentUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update agent details"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant.id
    ).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    update_data = agent_update.model_dump(exclude_unset=True)
    
    # Handle skills separately
    if "skills" in update_data:
        update_data["skills"] = json.dumps(update_data["skills"])
    
    for key, value in update_data.items():
        setattr(agent, key, value)
    
    db.commit()
    db.refresh(agent)
    
    agent.agent_name = agent.name
    return agent

@router.put("/agents/{agent_id}/status")
async def update_agent_status(
    agent_id: int,
    status_update: AgentStatusUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update agent status (online, busy, away, offline)"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant.id
    ).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Update status using the manager
    chat_manager = LiveChatManager(db)
    chat_manager.update_agent_status(agent_id, status_update.status)
    
    return {"message": f"Agent status updated to {status_update.status}"}

# ========================== CHAT MANAGEMENT ==========================

@router.post("/chats", response_model=LiveChatOut)
async def initiate_live_chat(
    chat_request: LiveChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Initiate a new live chat session"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat_manager = LiveChatManager(db)
    
    # Check if this should be a handoff from bot
    handoff_reason = None
    if chat_request.chatbot_session_id:
        # This is likely a handoff from chatbot
        handoff_reason = "User requested human assistance"
    
    live_chat = chat_manager.initiate_live_chat(
        tenant_id=tenant.id,
        user_identifier=chat_request.user_identifier,
        chatbot_session_id=chat_request.chatbot_session_id,
        handoff_reason=handoff_reason,
        platform=chat_request.platform,
        user_name=chat_request.user_name,
        user_email=chat_request.user_email,
        department=chat_request.department
    )
    
    # Get queue position
    from app.live_chat.models import ChatQueue
    queue_entry = db.query(ChatQueue).filter(ChatQueue.chat_id == live_chat.id).first()
    
    response_data = {
        **live_chat.__dict__,
        "agent_name": live_chat.agent.name if live_chat.agent else None,
        "queue_position": queue_entry.position if queue_entry else None,
        "estimated_wait_time": queue_entry.estimated_wait_time if queue_entry else None
    }
    
    # Notify available agents about new chat
    await connection_manager.notify_new_chat(tenant.id, {
        "session_id": live_chat.session_id,
        "user_identifier": live_chat.user_identifier,
        "user_name": live_chat.user_name,
        "department": live_chat.department,
        "platform": live_chat.platform,
        "subject": live_chat.subject,
        "queue_position": queue_entry.position if queue_entry else None
    })
    
    logger.info(f"Initiated live chat {live_chat.session_id} for user {chat_request.user_identifier}")
    return response_data

@router.post("/handoff")
async def handle_bot_handoff(
    handoff_request: HandoffRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Handle handoff from chatbot to live chat"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # First, process the message with the chatbot to detect handoff intent
    chatbot_engine = ChatbotEngine(db)
    chat_manager = LiveChatManager(db)
    
    # Detect if this is a handoff request
    is_handoff, reason, department = chat_manager.detect_handoff_request(handoff_request.user_message)
    
    if is_handoff:
        # Initiate live chat
        live_chat = chat_manager.initiate_live_chat(
            tenant_id=tenant.id,
            user_identifier=handoff_request.user_identifier,
            chatbot_session_id=handoff_request.chatbot_session_id,
            handoff_reason=reason,
            platform=handoff_request.platform,
            user_name=handoff_request.user_name,
            user_email=handoff_request.user_email,
            department=department
        )
        
        # Get queue info
        from app.live_chat.models import ChatQueue
        queue_entry = db.query(ChatQueue).filter(ChatQueue.chat_id == live_chat.id).first()
        
        # Notify agents
        await connection_manager.notify_new_chat(tenant.id, {
            "session_id": live_chat.session_id,
            "user_identifier": live_chat.user_identifier,
            "user_name": live_chat.user_name,
            "department": live_chat.department,
            "handoff_reason": reason
        })
        
        return {
            "handoff_detected": True,
            "live_chat_session_id": live_chat.session_id,
            "queue_position": queue_entry.position if queue_entry else None,
            "estimated_wait_time": queue_entry.estimated_wait_time if queue_entry else None,
            "message": "You've been connected to our live support. An agent will be with you shortly."
        }
    else:
        # Process normally with chatbot
        result = chatbot_engine.process_message(
            api_key, handoff_request.user_message, handoff_request.user_identifier
        )
        
        return {
            "handoff_detected": False,
            "bot_response": result.get("response", ""),
            "session_id": result.get("session_id")
        }

@router.get("/chats", response_model=List[LiveChatOut])
async def list_live_chats(
    status: Optional[ChatStatus] = None,
    agent_id: Optional[int] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """List live chats for the tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    query = db.query(LiveChat).filter(LiveChat.tenant_id == tenant.id)
    
    if status:
        query = query.filter(LiveChat.status == status)
    
    if agent_id:
        query = query.filter(LiveChat.agent_id == agent_id)
    
    chats = query.order_by(LiveChat.created_at.desc()).all()
    
    # Add agent names and queue info
    for chat in chats:
        chat.agent_name = chat.agent.name if chat.agent else None
        
        # Get queue position if waiting
        if chat.status == ChatStatus.WAITING:
            from app.live_chat.models import ChatQueue
            queue_entry = db.query(ChatQueue).filter(ChatQueue.chat_id == chat.id).first()
            if queue_entry:
                chat.queue_position = queue_entry.position
                chat.estimated_wait_time = queue_entry.estimated_wait_time
    
    return chats

@router.get("/chats/{chat_session_id}", response_model=LiveChatOut)
async def get_live_chat(
    chat_session_id: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get specific live chat details"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.agent_name = chat.agent.name if chat.agent else None
    
    # Get queue info if waiting
    if chat.status == ChatStatus.WAITING:
        from app.live_chat.models import ChatQueue
        queue_entry = db.query(ChatQueue).filter(ChatQueue.chat_id == chat.id).first()
        if queue_entry:
            chat.queue_position = queue_entry.position
            chat.estimated_wait_time = queue_entry.estimated_wait_time
    
    return chat

@router.get("/chats/{chat_session_id}/messages", response_model=List[MessageOut])
async def get_chat_messages(
    chat_session_id: str,
    include_internal: bool = False,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get messages for a live chat"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    query = db.query(LiveChatMessage).filter(LiveChatMessage.chat_id == chat.id)
    
    if not include_internal:
        query = query.filter(LiveChatMessage.is_internal == False)
    
    messages = query.order_by(LiveChatMessage.created_at).all()
    return messages

@router.post("/chats/{chat_session_id}/messages", response_model=MessageOut)
async def send_chat_message(
    chat_session_id: str,
    message_data: MessageSend,
    agent_id: Optional[int] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Send a message in a live chat (for API clients)"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Determine if message is from agent or user
    is_from_user = agent_id is None
    
    chat_manager = LiveChatManager(db)
    message = chat_manager.send_message(
        chat_id=chat.id,
        content=message_data.content,
        is_from_user=is_from_user,
        agent_id=agent_id,
        message_type=message_data.message_type,
        is_internal=message_data.is_internal
    )
    
    # Broadcast via WebSocket
    await connection_manager.broadcast_to_chat(chat_session_id, {
        "type": "new_message",
        "message": {
            "id": message.id,
            "content": message.content,
            "is_from_user": is_from_user,
            "sender_name": message.sender_name,
            "timestamp": message.created_at.isoformat(),
            "is_internal": message.is_internal
        },
        "chat_session_id": chat_session_id
    })
    
    return message

@router.post("/chats/{chat_session_id}/assign/{agent_id}")
async def assign_agent_to_chat(
    chat_session_id: str,
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Manually assign an agent to a chat"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id,
        LiveChat.status == ChatStatus.WAITING
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or not waiting")
    
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant.id,
        Agent.is_active == True
    ).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.current_chat_count >= agent.max_concurrent_chats:
        raise HTTPException(status_code=400, detail="Agent at maximum capacity")
    
    # Assign agent
    chat_manager = LiveChatManager(db)
    chat_manager._assign_agent_to_chat(chat, agent)
    
    # WebSocket notifications
    connection_manager.add_agent_to_chat(chat_session_id, agent_id)
    
    await connection_manager.notify_agent_chat_assigned(agent_id, {
        "session_id": chat.session_id,
        "user_identifier": chat.user_identifier,
        "user_name": chat.user_name,
        "platform": chat.platform,
        "subject": chat.subject
    })
    
    await connection_manager.notify_chat_assigned(chat_session_id, agent_id, agent.name)
    
    return {"message": f"Agent {agent.name} assigned to chat"}

@router.post("/chats/{chat_session_id}/transfer/{target_agent_id}")
async def transfer_chat(
    chat_session_id: str,
    target_agent_id: int,
    transfer_reason: Optional[str] = None,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Transfer chat to another agent"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id,
        LiveChat.status == ChatStatus.ACTIVE
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Active chat not found")
    
    target_agent = db.query(Agent).filter(
        Agent.id == target_agent_id,
        Agent.tenant_id == tenant.id,
        Agent.is_active == True
    ).first()
    
    if not target_agent:
        raise HTTPException(status_code=404, detail="Target agent not found")
    
    if target_agent.current_chat_count >= target_agent.max_concurrent_chats:
        raise HTTPException(status_code=400, detail="Target agent at maximum capacity")
    
    # Transfer chat
    chat_manager = LiveChatManager(db)
    success = chat_manager.transfer_chat(chat.id, target_agent_id, transfer_reason)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to transfer chat")
    
    # Update WebSocket connections
    connection_manager.add_agent_to_chat(chat_session_id, target_agent_id)
    
    # Notify participants
    await connection_manager.broadcast_to_chat(chat_session_id, {
        "type": "chat_transferred",
        "new_agent_id": target_agent_id,
        "new_agent_name": target_agent.name,
        "reason": transfer_reason,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {"message": f"Chat transferred to {target_agent.name}"}

@router.post("/chats/{chat_session_id}/end")
async def end_chat(
    chat_session_id: str,
    end_request: ChatEndRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """End a live chat session"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat = db.query(LiveChat).filter(
        LiveChat.session_id == chat_session_id,
        LiveChat.tenant_id == tenant.id
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_manager = LiveChatManager(db)
    success = chat_manager.end_chat(
        chat.id,
        satisfaction_rating=end_request.satisfaction_rating
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to end chat")
    
    # Notify participants
    await connection_manager.broadcast_to_chat(chat_session_id, {
        "type": "chat_ended",
        "chat_session_id": chat_session_id,
        "satisfaction_rating": end_request.satisfaction_rating,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {"message": "Chat ended successfully"}

# ========================== QUEUE AND STATS ==========================

@router.get("/queue")
async def get_queue_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current queue status"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    chat_manager = LiveChatManager(db)
    queue_status = chat_manager.get_queue_status(tenant.id)
    
    return queue_status

@router.get("/agents/{agent_id}/workload")
async def get_agent_workload(
    agent_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get agent's current workload"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant.id
    ).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    chat_manager = LiveChatManager(db)
    workload = chat_manager.get_agent_workload(agent_id)
    
    return workload

@router.get("/stats/dashboard")
async def get_dashboard_stats(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics for live chat"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Active chats
    active_chats = db.query(LiveChat).filter(
        LiveChat.tenant_id == tenant.id,
        LiveChat.status == ChatStatus.ACTIVE
    ).count()
    
    # Waiting chats
    waiting_chats = db.query(LiveChat).filter(
        LiveChat.tenant_id == tenant.id,
        LiveChat.status == ChatStatus.WAITING
    ).count()
    
    # Online agents
    online_agents = db.query(Agent).filter(
        Agent.tenant_id == tenant.id,
        Agent.status.in_([AgentStatus.ONLINE, AgentStatus.AWAY]),
        Agent.is_active == True
    ).count()
    
    # Total agents
    total_agents = db.query(Agent).filter(
        Agent.tenant_id == tenant.id,
        Agent.is_active == True
    ).count()
    
    # Average response time (from recent chats)
    from sqlalchemy import func
    avg_response_time = db.query(func.avg(LiveChat.first_response_time)).filter(
        LiveChat.tenant_id == tenant.id,
        LiveChat.first_response_time.isnot(None)
    ).scalar() or 0
    
    # WebSocket connection counts
    connection_counts = connection_manager.get_active_connections_count(tenant.id)
    
    return {
        "active_chats": active_chats,
        "waiting_chats": waiting_chats,
        "online_agents": online_agents,
        "total_agents": total_agents,
        "average_response_time_seconds": int(avg_response_time or 0),
        "active_connections": connection_counts,
        "queue_status": LiveChatManager(db).get_queue_status(tenant.id)
    }

# ========================== WEBSOCKET ENDPOINTS ==========================

@router.websocket("/ws/user/{user_identifier}")
async def websocket_user_endpoint(
    websocket: WebSocket,
    user_identifier: str,
    tenant_id: int = Query(...),
    chat_session_id: Optional[str] = Query(None)
):
    """WebSocket endpoint for users"""
    db = next(get_db())
    chat_manager = LiveChatManager(db)
    handler = LiveChatWebSocketHandler(db, chat_manager)
    
    await connection_manager.connect_user(websocket, tenant_id, user_identifier, chat_session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            message_type = message_data.get("type")
            
            if message_type == "send_message":
                await handler.handle_user_message(websocket, message_data)
            elif message_type == "typing":
                await handler.handle_typing_indicator(websocket, message_data)
            else:
                logger.warning(f"Unknown message type from user: {message_type}")
                
    except WebSocketDisconnect:
        connection_manager.disconnect_user(tenant_id, user_identifier, chat_session_id)
        logger.info(f"User {user_identifier} disconnected")
    except Exception as e:
        logger.error(f"Error in user websocket: {e}")
        connection_manager.disconnect_user(tenant_id, user_identifier, chat_session_id)
    finally:
        db.close()

@router.websocket("/ws/agent/{agent_id}")
async def websocket_agent_endpoint(
    websocket: WebSocket,
    agent_id: int,
    tenant_id: int = Query(...)
):
    """WebSocket endpoint for agents"""
    db = next(get_db())
    chat_manager = LiveChatManager(db)
    handler = LiveChatWebSocketHandler(db, chat_manager)
    
    # Get agent details
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        await websocket.close(code=4404, reason="Agent not found")
        return
    
    await connection_manager.connect_agent(websocket, tenant_id, agent_id, agent.name)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            message_type = message_data.get("type")
            
            if message_type == "send_message":
                await handler.handle_agent_message(websocket, message_data)
            elif message_type == "typing":
                await handler.handle_typing_indicator(websocket, message_data)
            elif message_type == "status_update":
                await handler.handle_agent_status_update(websocket, message_data)
            elif message_type == "take_chat":
                await handler.handle_chat_assignment_request(websocket, message_data)
            else:
                logger.warning(f"Unknown message type from agent: {message_type}")
                
    except WebSocketDisconnect:
        connection_manager.disconnect_agent(tenant_id, agent_id)
        logger.info(f"Agent {agent_id} disconnected")
    except Exception as e:
        logger.error(f"Error in agent websocket: {e}")
        connection_manager.disconnect_agent(tenant_id, agent_id)
    finally:
        # Update agent status to offline
        chat_manager.update_agent_status(agent_id, AgentStatus.OFFLINE)
        db.close()