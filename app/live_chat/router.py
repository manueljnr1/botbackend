# app/live_chat/router.py - FIXED API KEY AUTHENTICATION
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.live_chat.websocket_manager import websocket_manager, LiveChatMessageHandler
from app.live_chat.queue_service import LiveChatQueueService
from app.live_chat.agent_service import AgentSessionService
from app.live_chat.models import LiveChatConversation, Agent, ConversationStatus, LiveChatMessage, MessageType, SenderType
from app.tenants.router import get_tenant_from_api_key
from app.tenants.models import Tenant

# 🔥 PRICING INTEGRATION
from app.pricing.integration_helpers import (
    check_conversation_limit_dependency_with_super_tenant,
    track_conversation_started_with_super_tenant
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic Models
class StartChatRequest(BaseModel):
    customer_identifier: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    initial_message: Optional[str] = None
    handoff_context: Optional[Dict] = None
    chatbot_session_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    conversation_id: int
    queue_position: Optional[int] = None
    estimated_wait_time: Optional[int] = None
    websocket_url: str
    message: str

class QueueStatusResponse(BaseModel):
    tenant_id: int
    queue_length: int
    available_agents: int
    max_queue_size: int
    estimated_wait_time: int

class ConversationSummary(BaseModel):
    conversation_id: int
    customer_identifier: str
    customer_name: Optional[str]
    status: str
    assigned_agent_id: Optional[int]
    agent_name: Optional[str]
    created_at: str
    last_activity_at: str
    message_count: int
    wait_time_minutes: Optional[int]

class ConversationTransferRequest(BaseModel):
    to_agent_id: int
    reason: Optional[str] = "transfer"
    notes: Optional[str] = ""

class ConversationCloseRequest(BaseModel):
    reason: Optional[str] = "resolved"
    notes: Optional[str] = ""
    resolution_status: Optional[str] = "resolved"

class ManualAssignmentRequest(BaseModel):
    queue_id: int
    agent_id: int


# =============================================================================
# CUSTOMER ENDPOINTS
# =============================================================================

@router.post("/start-chat", response_model=ChatResponse)
async def start_live_chat(
    request: StartChatRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Start a new live chat conversation (customer-facing)"""
    try:
        # 🔒 PRICING CHECK - Check conversation limits
        tenant = get_tenant_from_api_key(api_key, db)
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Create new conversation
        conversation = LiveChatConversation(
            tenant_id=tenant.id,
            customer_identifier=request.customer_identifier,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            chatbot_session_id=request.chatbot_session_id,
            handoff_reason="manual" if not request.handoff_context else "triggered",
            handoff_context=json.dumps(request.handoff_context) if request.handoff_context else None,
            original_question=request.initial_message,
            status=ConversationStatus.QUEUED
        )
        
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        # Add to queue
        queue_service = LiveChatQueueService(db)
        queue_result = queue_service.add_to_queue(
            conversation_id=conversation.id,
            priority=1,  # Normal priority
            assignment_criteria={"source": "customer_request"}
        )
        
        # 📊 PRICING TRACK - Track conversation usage
        track_conversation_started_with_super_tenant(
            tenant_id=tenant.id,
            user_identifier=request.customer_identifier,
            platform="live_chat",
            db=db
        )
        
        # Generate WebSocket URL
        websocket_url = f"/live-chat/ws/customer/{conversation.id}?customer_id={request.customer_identifier}&tenant_id={tenant.id}"
        
        logger.info(f"Live chat started: conversation {conversation.id} for tenant {tenant.id}")
        
        return {
            "success": True,
            "conversation_id": conversation.id,
            "queue_position": queue_result.get("position"),
            "estimated_wait_time": queue_result.get("estimated_wait_time"),
            "websocket_url": websocket_url,
            "message": "Chat started! You are in the queue. An agent will join you shortly."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting live chat: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to start chat")


@router.websocket("/ws/customer/{conversation_id}")
async def customer_websocket_endpoint(
    websocket: WebSocket,
    conversation_id: int,
    customer_id: str = Query(...),
    tenant_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for customers"""
    connection_id = None
    try:
        # Verify conversation exists and belongs to tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == tenant_id,
            LiveChatConversation.customer_identifier == customer_id
        ).first()
        
        if not conversation:
            await websocket.close(code=4004, reason="Conversation not found")
            return
        
        # Connect customer
        connection_id = await websocket_manager.connect_customer(
            websocket=websocket,
            customer_id=customer_id,
            tenant_id=tenant_id,
            conversation_id=str(conversation_id)
        )
        
        # Initialize message handler
        message_handler = LiveChatMessageHandler(db, websocket_manager)
        
        # Listen for messages
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                await message_handler.handle_message(connection_id, message_data)
                
            except WebSocketDisconnect:
                logger.info(f"Customer disconnected: {customer_id}")
                break
            except json.JSONDecodeError:
                await message_handler._send_error(connection_id, "Invalid JSON format")
            except Exception as e:
                logger.error(f"Error in customer websocket: {str(e)}")
                await message_handler._send_error(connection_id, "Message processing failed")
                
    except Exception as e:
        logger.error(f"Error in customer websocket endpoint: {str(e)}")
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


# 🔧 FIXED: Added API key authentication
@router.get("/queue-status")
async def get_queue_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current queue status for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        queue_service = LiveChatQueueService(db)
        status = queue_service.get_queue_status(tenant.id)
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get queue status")


# =============================================================================
# AGENT ENDPOINTS (FIXED API KEY AUTHENTICATION)
# =============================================================================

@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    agent_id: int,
    session_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for agents"""
    connection_id = None
    try:
        # Verify agent and session
        agent = db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.status == "active",
            Agent.is_active == True
        ).first()
        
        if not agent:
            await websocket.close(code=4004, reason="Agent not found or inactive")
            return
        
        # Update agent session with WebSocket
        session_service = AgentSessionService(db)
        session_service.update_session_status(session_id, "active")
        
        # Connect agent
        connection_id = await websocket_manager.connect_agent(
            websocket=websocket,
            agent_id=agent_id,
            tenant_id=agent.tenant_id,
            session_id=session_id
        )
        
        # Initialize message handler
        message_handler = LiveChatMessageHandler(db, websocket_manager)
        
        # Send initial queue data
        queue_service = LiveChatQueueService(db)
        queue_status = queue_service.get_queue_status(agent.tenant_id)
        
        initial_data = {
            "type": "initial_data",
            "data": {
                "queue_status": queue_status,
                "agent_info": {
                    "agent_id": agent.id,
                    "display_name": agent.display_name,
                    "tenant_id": agent.tenant_id
                }
            }
        }
        await websocket.send_json(initial_data)
        
        # Listen for messages
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                await message_handler.handle_message(connection_id, message_data)
                
            except WebSocketDisconnect:
                logger.info(f"Agent disconnected: {agent_id}")
                break
            except json.JSONDecodeError:
                await message_handler._send_error(connection_id, "Invalid JSON format")
            except Exception as e:
                logger.error(f"Error in agent websocket: {str(e)}")
                await message_handler._send_error(connection_id, "Message processing failed")
                
    except Exception as e:
        logger.error(f"Error in agent websocket endpoint: {str(e)}")
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)
        
        # Update agent session
        try:
            session_service = AgentSessionService(db)
            session_service.update_session_status(session_id, "offline")
        except Exception as e:
            logger.error(f"Error updating agent session: {str(e)}")


# 🔧 FIXED: Added API key authentication
@router.post("/assign-conversation")
async def manually_assign_conversation(
    request: ManualAssignmentRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Manually assign a queued conversation to an agent"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify agent belongs to tenant
        agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == tenant.id,
            Agent.status == "active"
        ).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Assign conversation
        queue_service = LiveChatQueueService(db)
        success = queue_service.assign_conversation(request.queue_id, request.agent_id, "manual")
        
        if success:
            return {
                "success": True,
                "message": f"Conversation assigned to {agent.display_name}",
                "agent_id": request.agent_id,
                "agent_name": agent.display_name
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to assign conversation")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to assign conversation")


# 🔧 FIXED: Added API key authentication
@router.get("/conversations/active")
async def get_active_conversations(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get all active conversations for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        conversations = db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.status.in_([
                ConversationStatus.QUEUED,
                ConversationStatus.ASSIGNED,
                ConversationStatus.ACTIVE
            ])
        ).order_by(LiveChatConversation.created_at.desc()).all()
        
        conversation_list = []
        for conv in conversations:
            agent_name = None
            if conv.assigned_agent_id:
                agent = db.query(Agent).filter(Agent.id == conv.assigned_agent_id).first()
                agent_name = agent.display_name if agent else "Unknown Agent"
            
            wait_time = None
            if conv.queue_entry_time:
                if conv.assigned_at:
                    wait_time = int((conv.assigned_at - conv.queue_entry_time).total_seconds() / 60)
                else:
                    wait_time = int((datetime.utcnow() - conv.queue_entry_time).total_seconds() / 60)
            
            conversation_list.append({
                "conversation_id": conv.id,
                "customer_identifier": conv.customer_identifier,
                "customer_name": conv.customer_name,
                "customer_email": conv.customer_email,
                "status": conv.status,
                "assigned_agent_id": conv.assigned_agent_id,
                "agent_name": agent_name,
                "created_at": conv.created_at.isoformat(),
                "last_activity_at": conv.last_activity_at.isoformat(),
                "message_count": conv.message_count,
                "wait_time_minutes": wait_time,
                "queue_position": conv.queue_position
            })
        
        return {
            "success": True,
            "conversations": conversation_list,
            "total_count": len(conversation_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting active conversations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")


# 🔧 FIXED: Added API key authentication
@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get message history for a conversation"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify conversation belongs to tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get messages
        messages = db.query(LiveChatMessage).filter(
            LiveChatMessage.conversation_id == conversation_id
        ).order_by(LiveChatMessage.sent_at.desc()).limit(limit).all()
        
        message_list = []
        for msg in reversed(messages):  # Reverse to get chronological order
            message_list.append({
                "message_id": msg.id,
                "content": msg.content,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name,
                "sent_at": msg.sent_at.isoformat(),
                "message_type": msg.message_type,
                "is_internal": msg.is_internal,
                "attachment_url": msg.attachment_url,
                "attachment_name": msg.attachment_name
            })
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "messages": message_list,
            "total_count": len(message_list),
            "conversation_status": conversation.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get history")


# 🔧 FIXED: Added API key authentication
@router.post("/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: int,
    request: ConversationCloseRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Close a conversation"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify conversation belongs to tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Close conversation
        conversation.status = ConversationStatus.CLOSED
        conversation.closed_at = datetime.utcnow()
        conversation.closed_by = "admin"
        conversation.closure_reason = request.reason
        conversation.agent_notes = request.notes
        conversation.resolution_status = request.resolution_status
        
        # Calculate duration
        if conversation.assigned_at:
            duration = (datetime.utcnow() - conversation.assigned_at).total_seconds()
            conversation.conversation_duration_seconds = int(duration)
        
        # Update agent session if assigned
        if conversation.assigned_agent_id:
            from app.live_chat.models import AgentSession
            agent_session = db.query(AgentSession).filter(
                AgentSession.agent_id == conversation.assigned_agent_id,
                AgentSession.logout_at.is_(None)
            ).first()
            
            if agent_session:
                agent_session.active_conversations = max(0, agent_session.active_conversations - 1)
        
        db.commit()
        
        # Notify via WebSocket
        from app.live_chat.websocket_manager import WebSocketMessage
        close_notification = WebSocketMessage(
            message_type="conversation_closed",
            data={
                "conversation_id": conversation_id,
                "closed_by": "admin",
                "reason": conversation.closure_reason,
                "closed_at": conversation.closed_at.isoformat()
            },
            conversation_id=str(conversation_id)
        )
        
        await websocket_manager.send_to_conversation(str(conversation_id), close_notification)
        
        logger.info(f"Conversation {conversation_id} closed by admin")
        
        return {
            "success": True,
            "message": "Conversation closed successfully",
            "conversation_id": conversation_id,
            "closed_at": conversation.closed_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing conversation: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to close conversation")


# 🔧 FIXED: Added API key authentication
@router.post("/conversations/{conversation_id}/transfer")
async def transfer_conversation(
    conversation_id: int,
    request: ConversationTransferRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Transfer conversation to another agent"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify conversation and agents
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        to_agent = db.query(Agent).filter(
            Agent.id == request.to_agent_id,
            Agent.tenant_id == tenant.id,
            Agent.status == "active"
        ).first()
        
        if not to_agent:
            raise HTTPException(status_code=404, detail="Target agent not found")
        
        # Perform transfer
        queue_service = LiveChatQueueService(db)
        success = queue_service.transfer_conversation(
            conversation_id=conversation_id,
            from_agent_id=conversation.assigned_agent_id,
            to_agent_id=request.to_agent_id,
            reason=request.reason
        )
        
        if success:
            # Add transfer note as system message
            from_agent_name = "System"
            if conversation.assigned_agent_id:
                from_agent = db.query(Agent).filter(Agent.id == conversation.assigned_agent_id).first()
                from_agent_name = from_agent.display_name if from_agent else "Agent"
            
            transfer_message = LiveChatMessage(
                conversation_id=conversation_id,
                content=f"Conversation transferred from {from_agent_name} to {to_agent.display_name}. Reason: {request.reason}",
                message_type=MessageType.SYSTEM,
                sender_type=SenderType.SYSTEM,
                system_event_type="transfer",
                system_event_data=json.dumps({
                    "from_agent_id": conversation.assigned_agent_id,
                    "to_agent_id": request.to_agent_id,
                    "reason": request.reason,
                    "notes": request.notes
                })
            )
            
            db.add(transfer_message)
            db.commit()
            
            return {
                "success": True,
                "message": f"Conversation transferred to {to_agent.display_name}",
                "to_agent_id": request.to_agent_id,
                "to_agent_name": to_agent.display_name
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to transfer conversation")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transferring conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to transfer conversation")


# =============================================================================
# ANALYTICS & REPORTING ENDPOINTS (FIXED API KEY AUTHENTICATION)
# =============================================================================

# 🔧 FIXED: Added API key authentication
@router.get("/analytics/summary")
async def get_live_chat_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get live chat analytics summary"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Calculate date range
        from_date = datetime.utcnow() - timedelta(days=days)
        
        # Get conversation statistics
        total_conversations = db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date
        ).count()
        
        completed_conversations = db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date,
            LiveChatConversation.status == ConversationStatus.CLOSED
        ).count()
        
        abandoned_conversations = db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date,
            LiveChatConversation.status == ConversationStatus.ABANDONED
        ).count()
        
        # Calculate average metrics
        from sqlalchemy import func
        avg_wait_time = db.query(func.avg(LiveChatConversation.wait_time_seconds)).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date,
            LiveChatConversation.wait_time_seconds.isnot(None)
        ).scalar() or 0
        
        avg_duration = db.query(func.avg(LiveChatConversation.conversation_duration_seconds)).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date,
            LiveChatConversation.conversation_duration_seconds.isnot(None)
        ).scalar() or 0
        
        avg_satisfaction = db.query(func.avg(LiveChatConversation.customer_satisfaction)).filter(
            LiveChatConversation.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date,
            LiveChatConversation.customer_satisfaction.isnot(None)
        ).scalar() or 0
        
        # Agent performance
        agent_stats = db.query(
            Agent.id,
            Agent.display_name,
            func.count(LiveChatConversation.id).label('total_conversations'),
            func.avg(LiveChatConversation.customer_satisfaction).label('avg_satisfaction')
        ).join(LiveChatConversation, Agent.id == LiveChatConversation.assigned_agent_id).filter(
            Agent.tenant_id == tenant.id,
            LiveChatConversation.created_at >= from_date
        ).group_by(Agent.id, Agent.display_name).all()
        
        agent_performance = []
        for stat in agent_stats:
            agent_performance.append({
                "agent_id": stat.id,
                "agent_name": stat.display_name,
                "total_conversations": stat.total_conversations,
                "avg_satisfaction": round(stat.avg_satisfaction or 0, 2)
            })
        
        return {
            "success": True,
            "period_days": days,
            "summary": {
                "total_conversations": total_conversations,
                "completed_conversations": completed_conversations,
                "abandoned_conversations": abandoned_conversations,
                "completion_rate": round((completed_conversations / total_conversations * 100) if total_conversations > 0 else 0, 2),
                "abandonment_rate": round((abandoned_conversations / total_conversations * 100) if total_conversations > 0 else 0, 2),
                "avg_wait_time_minutes": round(avg_wait_time / 60, 2),
                "avg_conversation_duration_minutes": round(avg_duration / 60, 2),
                "avg_customer_satisfaction": round(avg_satisfaction, 2)
            },
            "agent_performance": agent_performance,
            "current_status": websocket_manager.get_connection_stats(tenant.id)
        }
        
    except Exception as e:
        logger.error(f"Error getting live chat analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")


# =============================================================================
# ADMIN & MANAGEMENT ENDPOINTS (FIXED API KEY AUTHENTICATION)
# =============================================================================

# 🔧 FIXED: Added API key authentication
@router.get("/status")
async def get_live_chat_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get overall live chat system status"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get current queue status
        queue_service = LiveChatQueueService(db)
        queue_status = queue_service.get_queue_status(tenant.id)
        
        # Get WebSocket connection stats
        connection_stats = websocket_manager.get_connection_stats(tenant.id)
        
        # Get active agents
        session_service = AgentSessionService(db)
        active_agents = session_service.get_active_agents(tenant.id)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "live_chat_enabled": True,  # TODO: Get from settings
            "queue_status": queue_status,
            "connection_stats": connection_stats,
            "active_agents": active_agents,
            "system_health": "healthy",  # TODO: Add actual health checks
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting live chat status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get status")


# 🔧 FIXED: Added API key authentication
@router.post("/cleanup")
async def cleanup_expired_sessions(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Clean up expired queue entries and inactive connections"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Cleanup queue
        queue_service = LiveChatQueueService(db)
        cleaned_queue = queue_service.cleanup_expired_queue_entries(tenant.id)
        
        # Cleanup WebSocket connections
        await websocket_manager.cleanup_inactive_connections()
        
        return {
            "success": True,
            "cleaned_queue_entries": cleaned_queue,
            "message": "Cleanup completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail="Cleanup failed")