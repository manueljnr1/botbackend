# app/live_chat/router.py - COMPLETE TIMEZONE AND DATETIME FIXES

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.sql import and_, desc
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi.security import HTTPBearer
from fastapi import Security


from app.database import get_db
from app.live_chat.websocket_manager import websocket_manager, LiveChatMessageHandler
from app.live_chat.queue_service import LiveChatQueueService
from app.live_chat.agent_dashboard_service import AgentDashboardService
from app.live_chat.agent_service import AgentSessionService
from app.live_chat.models import LiveChatConversation, Agent, ConversationStatus, LiveChatMessage, MessageType, SenderType, AgentStatus, ChatQueue, AgentSession
from app.tenants.router import get_tenant_from_api_key
from app.tenants.models import Tenant
from app.live_chat.customer_detection_service import CustomerDetectionService
from app.live_chat.auth_utils import get_tenant_context, get_agent_or_tenant_context
from app.live_chat.agent_dashboard_service import SharedDashboardService
from app.pricing.integration_helpers import check_conversation_limit_dependency_with_super_tenant, track_conversation_started_with_super_tenant
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.live_chat.models import AgentSession


bearer_scheme = HTTPBearer(auto_error=False)



logger = logging.getLogger(__name__)
router = APIRouter()

# 🔧 TIMEZONE UTILITY FUNCTIONS
def utc_now():
    """Get current UTC time with timezone info"""
    return datetime.now(timezone.utc)

def make_timezone_naive(dt):
    """Make a timezone-aware datetime naive (for database comparison)"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def make_timezone_aware(dt):
    """Make a naive datetime timezone-aware (UTC)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def safe_datetime_subtract(dt1, dt2):
    """Safely subtract two datetime objects, handling timezone issues"""
    try:
        # Make both naive for subtraction
        dt1_naive = make_timezone_naive(dt1) if dt1 else datetime.utcnow()
        dt2_naive = make_timezone_naive(dt2) if dt2 else datetime.utcnow()
        return dt1_naive - dt2_naive
    except Exception as e:
        logger.warning(f"Datetime subtraction error: {str(e)}")
        return timedelta(0)

# 🔧 OAuth2 scheme for Bearer token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="live-chat/auth/login", auto_error=False)

# 🔧 UTILITY FUNCTION FOR JSON SERIALIZATION
def serialize_datetime_objects(obj):
    """Convert datetime objects to ISO format strings for JSON serialization"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetime_objects(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime_objects(item) for item in obj]
    else:
        return obj

# 🔧 AGENT AUTHENTICATION DEPENDENCY
def get_current_agent(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get current authenticated agent"""
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required"
        )
    
    try:
        from app.core.security import verify_token
        
        # Decode and verify JWT token
        payload = verify_token(token)
        agent_id = payload.get("sub")
        user_type = payload.get("type")
        
        if user_type != "agent":
            raise HTTPException(
                status_code=403,
                detail="Invalid user type - agent token required"
            )
        
        # Get agent from database
        agent = db.query(Agent).filter(
            Agent.id == int(agent_id),
            Agent.status == AgentStatus.ACTIVE,
            Agent.is_active == True
        ).first()
        
        if not agent:
            raise HTTPException(
                status_code=404,
                detail="Agent not found or inactive"
            )
        
        return agent
        
    except Exception as e:
        logger.error(f"Error verifying agent token: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )





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

class ManualAssignmentRequest(BaseModel):
    queue_id: int
    agent_id: int

class ConversationTransferRequest(BaseModel):
    to_agent_id: int
    reason: Optional[str] = "transfer"
    notes: Optional[str] = ""

class ConversationCloseRequest(BaseModel):
    reason: Optional[str] = "resolved"
    notes: Optional[str] = ""
    resolution_status: Optional[str] = "resolved"


class BulkAssignmentRequest(BaseModel):
    assignments: List[ManualAssignmentRequest]


class CustomerDetectionResponse(BaseModel):
    success: bool
    customer_profile: Dict[str, Any]
    current_session: Dict[str, Any]
    geolocation: Dict[str, Any]
    device_info: Dict[str, Any]
    visitor_history: Dict[str, Any]
    preferences: Dict[str, Any]
    routing_suggestions: Dict[str, Any]
    privacy_compliance: Dict[str, Any]





async def get_last_message_preview(conversation_id: int, db: Session) -> Dict[str, Any]:
    """Get preview of the last customer message in a conversation"""
    try:
        from app.live_chat.agent_dashboard_service import TextPreviewService
        
        # Get the last customer message
        last_customer_message = db.query(LiveChatMessage).filter(
            and_(
                LiveChatMessage.conversation_id == conversation_id,
                LiveChatMessage.sender_type == SenderType.CUSTOMER
            )
        ).order_by(LiveChatMessage.sent_at.desc()).first()
        
        # If no customer message found, check for original_question in conversation
        if not last_customer_message:
            conversation = db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if conversation and conversation.original_question:
                # Generate preview from original question
                preview_result = TextPreviewService.generate_message_preview(
                    text=conversation.original_question,
                    max_snippet_length=120
                )
                
                return {
                    "snippet": preview_result.snippet,
                    "has_messages": True,
                    "sent_at": conversation.created_at.isoformat() if conversation.created_at else None,
                    "source": "original_question"
                }
            else:
                # No messages at all
                return {
                    "snippet": "Customer is waiting to start conversation",
                    "has_messages": False,
                    "sent_at": None,
                    "source": "no_messages"
                }
        
        # Generate preview from last customer message
        preview_result = TextPreviewService.generate_message_preview(
            text=last_customer_message.content,
            max_snippet_length=120
        )
        
        # Safe datetime serialization
        try:
            sent_at = last_customer_message.sent_at.isoformat() if last_customer_message.sent_at else None
        except Exception as e:
            logger.warning(f"Message datetime serialization error: {str(e)}")
            sent_at = str(last_customer_message.sent_at) if last_customer_message.sent_at else None
        
        return {
            "snippet": preview_result.snippet,
            "has_messages": True,
            "sent_at": sent_at,
            "source": "last_message"
        }
        
    except Exception as e:
        logger.error(f"Error generating message preview for conversation {conversation_id}: {str(e)}")
        # Return fallback preview on error
        return {
            "snippet": "Unable to load message preview",
            "has_messages": False,
            "sent_at": None,
            "source": "error"
        }




# =============================================================================
# CUSTOMER ENDPOINTS (API KEY AUTHENTICATION)
# =============================================================================







@router.get("/agent/enhanced-dashboard")
async def get_enhanced_agent_dashboard(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get enhanced agent dashboard with customer intelligence"""
    try:
        dashboard_service = AgentDashboardService(db)
        
        # Get enhanced queue
        enhanced_queue = await dashboard_service.get_enhanced_queue_for_agent(current_agent)
        
        # Get agent's current workload
        from app.live_chat.models import AgentSession
        agent_session = db.query(AgentSession).filter(
            and_(
                AgentSession.agent_id == current_agent.id,
                AgentSession.logout_at.is_(None)
            )
        ).first()
        
        current_workload = {
            "active_conversations": agent_session.active_conversations if agent_session else 0,
            "max_capacity": agent_session.max_concurrent_chats if agent_session else 3,
            "is_accepting_chats": agent_session.is_accepting_chats if agent_session else True,
            "status": agent_session.status if agent_session else "offline"
        }
        
        # Get recent performance metrics
        recent_conversations = db.query(LiveChatConversation).filter(
            and_(
                LiveChatConversation.assigned_agent_id == current_agent.id,
                LiveChatConversation.created_at >= datetime.utcnow() - timedelta(days=7)
            )
        ).all()
        
        performance_metrics = {
            "conversations_this_week": len(recent_conversations),
            "average_satisfaction": sum([conv.customer_satisfaction for conv in recent_conversations 
                                       if conv.customer_satisfaction]) / len(recent_conversations) if recent_conversations else 0,
            "resolution_rate": sum([1 for conv in recent_conversations 
                                  if conv.resolution_status == "resolved"]) / len(recent_conversations) if recent_conversations else 0
        }
        
        return {
            "success": True,
            "agent_info": {
                "agent_id": current_agent.id,
                "display_name": current_agent.display_name,
                "tenant_id": current_agent.tenant_id
            },
            "current_workload": current_workload,
            "performance_metrics": performance_metrics,
            "enhanced_queue": enhanced_queue,
            "dashboard_timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting enhanced agent dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard data")
    








@router.post("/start-chat", response_model=ChatResponse)
async def start_live_chat(
    request: StartChatRequest,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Start a new live chat conversation - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        # 🔒 PRICING CHECK - Check conversation limits
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
        queue_result = await queue_service.add_to_queue_with_smart_routing(
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
        
        # ✅ CRITICAL FIX: Accept the WebSocket connection FIRST
        await websocket.accept()
        
        # Connect customer
        connection_id = await websocket_manager.connect_customer(
            websocket=websocket,
            customer_id=customer_id,
            tenant_id=tenant_id,
            conversation_id=str(conversation_id)
        )
        
        # Initialize message handler
        message_handler = LiveChatMessageHandler(db, websocket_manager)
        
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "data": {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "status": "connected",
                "message": "Connected to live chat"
            }
        })
        
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



@router.get("/queue-status")
async def get_queue_status(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get current queue status - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        service = SharedDashboardService(db, tenant.id)
        result = service.get_queue_status()
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get queue status")


# =============================================================================
# AGENT ENDPOINTS (BEARER TOKEN AUTHENTICATION)
# =============================================================================

@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    agent_id: int,
    session_id: str = Query(...),
    db: Session = Depends(get_db)
):
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
        
        # ✅ ADD THIS: Accept the WebSocket connection FIRST
        await websocket.accept()
        
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
        
        # Send initial queue data - FIXED: Serialize datetime objects
        queue_service = LiveChatQueueService(db)
        queue_status = queue_service.get_queue_status(agent.tenant_id)
        
        # 🔧 SERIALIZE DATETIME OBJECTS BEFORE SENDING
        serialized_queue_status = serialize_datetime_objects(queue_status)
        
        initial_data = {
            "type": "initial_data",
            "data": {
                "queue_status": serialized_queue_status,
                "agent_info": {
                    "agent_id": agent.id,
                    "display_name": agent.display_name,
                    "tenant_id": agent.tenant_id
                }
            }
        }
        
        # Send initial data
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


@router.post("/assign-conversation")
async def manually_assign_conversation(
    request: ManualAssignmentRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Agent manually assigns a queued conversation to another agent"""
    try:
        # Verify queue entry exists and belongs to same tenant
        queue_entry = db.query(ChatQueue).filter(
            ChatQueue.id == request.queue_id,
            ChatQueue.tenant_id == current_agent.tenant_id,
            ChatQueue.status == "waiting"
        ).first()
        
        if not queue_entry:
            raise HTTPException(status_code=404, detail="Queue entry not found or already processed")
        
        # Verify target agent exists and belongs to same tenant
        target_agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == current_agent.tenant_id,
            Agent.status == AgentStatus.ACTIVE,  # Use enum instead of string
            Agent.is_active == True
        ).first()
        
        if not target_agent:
            raise HTTPException(status_code=404, detail="Target agent not found or inactive")
        
        # Optional: Check if current agent has permission to assign
        # You could add a permission field to Agent model later
        # if not current_agent.can_assign_conversations:
        #     raise HTTPException(status_code=403, detail="Permission denied")
        
        # Assign conversation
        queue_service = LiveChatQueueService(db)
        success = queue_service.assign_conversation(
            request.queue_id, 
            request.agent_id, 
            f"manual_by_agent_{current_agent.id}"
        )
        
        if success:
            logger.info(f"Conversation {request.queue_id} assigned to agent {request.agent_id} by agent {current_agent.id}")
            return {
                "success": True,
                "message": f"Conversation assigned to {target_agent.display_name}",
                "agent_id": request.agent_id,
                "agent_name": target_agent.display_name,
                "queue_id": request.queue_id,
                "assigned_by": current_agent.display_name
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail="Assignment failed - queue entry may have been processed or agent unavailable"
            )
            
    except HTTPException:
        raise  # Let HTTPException pass through with original status code
    except Exception as e:
        logger.error(f"Error in agent assign conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to assign conversation")




@router.post("/admin/assign-conversation")
async def admin_assign_conversation(
    request: ManualAssignmentRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Admin/Tenant manually assigns a queued conversation to an agent"""
    try:
        # Get tenant from API key
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify queue entry exists and belongs to tenant
        queue_entry = db.query(ChatQueue).filter(
            ChatQueue.id == request.queue_id,
            ChatQueue.tenant_id == tenant.id,
            ChatQueue.status == "waiting"
        ).first()
        
        if not queue_entry:
            raise HTTPException(
                status_code=404, 
                detail="Queue entry not found, already processed, or doesn't belong to your tenant"
            )
        
        # Verify target agent exists, belongs to tenant, and is available
        target_agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == tenant.id,
            Agent.status == AgentStatus.ACTIVE,
            Agent.is_active == True
        ).first()
        
        if not target_agent:
            raise HTTPException(
                status_code=404, 
                detail="Target agent not found, inactive, or doesn't belong to your tenant"
            )
        
        # Optional: Check if agent is available (not at max capacity)
        agent_session = db.query(AgentSession).filter(
            AgentSession.agent_id == request.agent_id,
            AgentSession.logout_at.is_(None),
            AgentSession.is_accepting_chats == True
        ).first()
        
        if agent_session and agent_session.active_conversations >= agent_session.max_concurrent_chats:
            raise HTTPException(
                status_code=400,
                detail=f"Agent {target_agent.display_name} is at maximum capacity ({agent_session.max_concurrent_chats} conversations)"
            )
        
        # Get conversation details for logging
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == queue_entry.conversation_id
        ).first()
        
        # Assign conversation
        queue_service = LiveChatQueueService(db)
        success = queue_service.assign_conversation(
            request.queue_id, 
            request.agent_id, 
            "manual_admin"
        )
        
        if success:
            logger.info(f"Admin assigned conversation {queue_entry.conversation_id} (queue {request.queue_id}) to agent {request.agent_id}")
            
            return {
                "success": True,
                "message": f"Conversation assigned to {target_agent.display_name}",
                "conversation_id": queue_entry.conversation_id,
                "queue_id": request.queue_id,
                "agent_id": request.agent_id,
                "agent_name": target_agent.display_name,
                "customer_identifier": conversation.customer_identifier if conversation else None,
                "assigned_by": "admin",
                "assignment_method": "manual_admin"
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail="Assignment failed - queue entry may have been processed by another agent or system error occurred"
            )
            
    except HTTPException:
        raise  # Let HTTPException pass through with original status code
    except Exception as e:
        logger.error(f"Error in admin assign conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to assign conversation")



@router.get("/admin/assignable-agents")
async def get_assignable_agents(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get list of agents available for manual assignment - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            from app.tenants.router import get_tenant_from_api_key
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            # Extract the actual token string
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            from app.live_chat.models import AgentStatus
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        service = SharedDashboardService(db, tenant.id)
        result = service.get_assignable_agents()
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignable agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents")
    

@router.get("/conversations/active")
async def get_active_conversations(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get all active conversations for agent's tenant with last message previews"""
    try:
        # Import TextPreviewService for generating message previews
        from app.live_chat.agent_dashboard_service import TextPreviewService
        
        conversations = db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == current_agent.tenant_id,
            LiveChatConversation.status.in_([
                ConversationStatus.QUEUED,
                ConversationStatus.ASSIGNED,
                ConversationStatus.ACTIVE
            ])
        ).order_by(LiveChatConversation.created_at.desc()).all()
        
        conversation_list = []
        current_time = datetime.utcnow()  # Use naive datetime
        
        for conv in conversations:
            agent_name = None
            if conv.assigned_agent_id:
                agent = db.query(Agent).filter(Agent.id == conv.assigned_agent_id).first()
                agent_name = agent.display_name if agent else "Unknown Agent"
            
            # 🔧 FIXED: Safe datetime calculations
            wait_time = None
            if conv.queue_entry_time:
                if conv.assigned_at:
                    time_diff = safe_datetime_subtract(conv.assigned_at, conv.queue_entry_time)
                    wait_time = int(time_diff.total_seconds() / 60)
                else:
                    time_diff = safe_datetime_subtract(current_time, conv.queue_entry_time)
                    wait_time = int(time_diff.total_seconds() / 60)
            
            # 🔧 FIXED: Safe datetime serialization
            try:
                created_at = conv.created_at.isoformat() if conv.created_at else None
                last_activity_at = conv.last_activity_at.isoformat() if conv.last_activity_at else None
            except Exception as e:
                logger.warning(f"Datetime serialization error: {str(e)}")
                created_at = str(conv.created_at) if conv.created_at else None
                last_activity_at = str(conv.last_activity_at) if conv.last_activity_at else None
            
            # 🆕 NEW: Get last customer message and generate preview
            last_message_preview = await get_last_message_preview(conv.id, db)
            
            conversation_list.append({
                "conversation_id": conv.id,
                "customer_identifier": conv.customer_identifier,
                "customer_name": conv.customer_name,
                "customer_email": conv.customer_email,
                "status": conv.status,
                "assigned_agent_id": conv.assigned_agent_id,
                "agent_name": agent_name,
                "created_at": created_at,
                "last_activity_at": last_activity_at,
                "message_count": conv.message_count,
                "wait_time_minutes": wait_time,
                "queue_position": conv.queue_position,
                "last_message_preview": last_message_preview  # 🆕 NEW: Message preview
            })
        
        return {
            "success": True,
            "conversations": conversation_list,
            "total_count": len(conversation_list)
        }
        
    except Exception as e:
        logger.error(f"Error getting active conversations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")


@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(
    conversation_id: int,
    current_agent: Agent = Depends(get_current_agent),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get message history for a conversation"""
    try:
        # Verify conversation belongs to agent's tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get messages
        messages = db.query(LiveChatMessage).filter(
            LiveChatMessage.conversation_id == conversation_id
        ).order_by(LiveChatMessage.sent_at.desc()).limit(limit).all()
        
        message_list = []
        for msg in reversed(messages):  # Reverse to get chronological order
            # 🔧 FIXED: Safe datetime serialization
            try:
                sent_at = msg.sent_at.isoformat() if msg.sent_at else None
            except Exception as e:
                logger.warning(f"Message datetime serialization error: {str(e)}")
                sent_at = str(msg.sent_at) if msg.sent_at else None
            
            message_list.append({
                "message_id": msg.id,
                "content": msg.content,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name,
                "sent_at": sent_at,
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


@router.post("/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: int,
    request: ConversationCloseRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Close a conversation"""
    try:
        # Verify conversation belongs to agent's tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Close conversation
        current_time = datetime.utcnow()
        conversation.status = ConversationStatus.CLOSED
        conversation.closed_at = current_time
        conversation.closed_by = f"agent_{current_agent.id}"
        conversation.closure_reason = request.reason
        conversation.agent_notes = request.notes
        conversation.resolution_status = request.resolution_status
        
        # Calculate duration - FIXED: Safe datetime calculation
        if conversation.assigned_at:
            duration_delta = safe_datetime_subtract(current_time, conversation.assigned_at)
            conversation.conversation_duration_seconds = int(duration_delta.total_seconds())
        
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
                "closed_by": f"agent_{current_agent.id}",
                "reason": conversation.closure_reason,
                "closed_at": conversation.closed_at.isoformat()
            },
            conversation_id=str(conversation_id)
        )
        
        await websocket_manager.send_to_conversation(str(conversation_id), close_notification)
        
        logger.info(f"Conversation {conversation_id} closed by agent {current_agent.id}")
        
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


@router.post("/conversations/{conversation_id}/transfer")
async def transfer_conversation(
    conversation_id: int,
    request: ConversationTransferRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Transfer conversation to another agent"""
    try:
        # Verify conversation and agents
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        to_agent = db.query(Agent).filter(
            Agent.id == request.to_agent_id,
            Agent.tenant_id == current_agent.tenant_id,
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
            transfer_message = LiveChatMessage(
                conversation_id=conversation_id,
                content=f"Conversation transferred from {current_agent.display_name} to {to_agent.display_name}. Reason: {request.reason}",
                message_type=MessageType.SYSTEM,
                sender_type=SenderType.SYSTEM,
                system_event_type="transfer",
                system_event_data=json.dumps({
                    "from_agent_id": current_agent.id,
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
# ADMIN ENDPOINTS (API KEY AUTHENTICATION)
# =============================================================================

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





@router.get("/status")
async def get_live_chat_status(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get overall live chat system status - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        service = SharedDashboardService(db, tenant.id)
        
        # Get queue status
        queue_status = service.get_queue_status()
        
        # Get WebSocket connection stats
        connection_stats = websocket_manager.get_connection_stats(tenant.id)
        
        # Get active agents
        session_service = AgentSessionService(db)
        active_agents = session_service.get_active_agents(tenant.id)
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "live_chat_enabled": True,
            "queue_status": queue_status,
            "connection_stats": connection_stats,
            "active_agents": active_agents,
            "system_health": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting live chat status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get status")



    

@router.get("/cleanup")
async def cleanup_expired_sessions(
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Clean up expired queue entries and inactive connections - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
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









# =============================================================================
# CUSTOMER DETECTION ENDPOINTS
# =============================================================================







@router.post("/detect-customer")
async def detect_customer_profile(
    request: Request,
    customer_identifier: Optional[str] = None,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Comprehensive customer detection and profiling - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        # Initialize customer detection service
        detection_service = CustomerDetectionService(db)
        
        # Perform comprehensive customer detection
        customer_data = await detection_service.detect_customer(
            request=request,
            tenant_id=tenant.id,
            customer_identifier=customer_identifier
        )
        
        # Log successful detection (privacy-conscious)
        logger.info(f"Customer detection completed for tenant {tenant.id}")
        
        return {
            "success": True,
            **customer_data,
            "detection_timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in customer detection: {str(e)}")
        raise HTTPException(status_code=500, detail="Customer detection failed")





@router.get("/customer-profile/{customer_identifier}")
async def get_customer_profile(
    customer_identifier: str,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get existing customer profile and history - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        # Get customer profile
        from app.live_chat.customer_detection_service import CustomerProfile
        customer_profile = db.query(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerProfile.customer_identifier == customer_identifier
            )
        ).first()
        
        if not customer_profile:
            raise HTTPException(status_code=404, detail="Customer profile not found")
        
        # Get recent conversations
        recent_conversations = db.query(LiveChatConversation).filter(
            and_(
                LiveChatConversation.tenant_id == tenant.id,
                LiveChatConversation.customer_identifier == customer_identifier
            )
        ).order_by(desc(LiveChatConversation.created_at)).limit(20).all()
        
        # Get customer devices
        from app.live_chat.customer_detection_service import CustomerDevice
        devices = db.query(CustomerDevice).filter(
            CustomerDevice.customer_profile_id == customer_profile.id
        ).all()
        
        # Get customer preferences
        from app.live_chat.customer_detection_service import CustomerPreferences
        preferences = db.query(CustomerPreferences).filter(
            CustomerPreferences.customer_profile_id == customer_profile.id
        ).first()
        
        # Format response
        profile_data = {
            "customer_profile": {
                "id": customer_profile.id,
                "identifier": customer_profile.customer_identifier,
                "first_seen": customer_profile.first_seen.isoformat() if customer_profile.first_seen else None,
                "last_seen": customer_profile.last_seen.isoformat() if customer_profile.last_seen else None,
                "total_conversations": customer_profile.total_conversations,
                "total_sessions": customer_profile.total_sessions,
                "customer_satisfaction_avg": customer_profile.customer_satisfaction_avg,
                "preferred_language": customer_profile.preferred_language,
                "time_zone": customer_profile.time_zone
            },
            "conversations": [
                {
                    "id": conv.id,
                    "created_at": conv.created_at.isoformat(),
                    "status": conv.status,
                    "resolution_status": conv.resolution_status,
                    "customer_satisfaction": conv.customer_satisfaction,
                    "agent_id": conv.assigned_agent_id,
                    "duration_minutes": conv.conversation_duration_seconds // 60 if conv.conversation_duration_seconds else None,
                    "message_count": conv.message_count
                } for conv in recent_conversations
            ],
            "devices": [
                {
                    "device_type": device.device_type,
                    "browser_name": device.browser_name,
                    "operating_system": device.operating_system,
                    "first_seen": device.first_seen.isoformat() if device.first_seen else None,
                    "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                    "total_sessions": device.total_sessions
                } for device in devices
            ],
            "preferences": {
                "preferred_language": preferences.preferred_language if preferences else "en",
                "communication_style": preferences.preferred_communication_style if preferences else None,
                "accessibility_required": preferences.requires_accessibility_features if preferences else False,
                "privacy_preferences": {
                    "data_retention": preferences.data_retention_preference if preferences else "standard",
                    "email_notifications": preferences.email_notifications if preferences else False,
                    "marketing_consent": customer_profile.marketing_consent
                }
            } if preferences else {}
        }
        
        return {
            "success": True,
            **profile_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customer profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get customer profile")
    









@router.post("/update-customer-preferences/{customer_identifier}")
async def update_customer_preferences(
    customer_identifier: str,
    preferences_data: Dict[str, Any],
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Update customer preferences and privacy settings - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        # Get or create customer profile
        from app.live_chat.customer_detection_service import CustomerProfile, CustomerPreferences
        customer_profile = db.query(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerProfile.customer_identifier == customer_identifier
            )
        ).first()
        
        if not customer_profile:
            # Create new customer profile
            customer_profile = CustomerProfile(
                tenant_id=tenant.id,
                customer_identifier=customer_identifier,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
            db.add(customer_profile)
            db.commit()
            db.refresh(customer_profile)
        
        # Get or create preferences
        preferences = db.query(CustomerPreferences).filter(
            CustomerPreferences.customer_profile_id == customer_profile.id
        ).first()
        
        if not preferences:
            preferences = CustomerPreferences(
                customer_profile_id=customer_profile.id
            )
            db.add(preferences)
        
        # Update preferences
        if "preferred_language" in preferences_data:
            preferences.preferred_language = preferences_data["preferred_language"]
            customer_profile.preferred_language = preferences_data["preferred_language"]
        
        if "communication_style" in preferences_data:
            preferences.preferred_communication_style = preferences_data["communication_style"]
        
        if "accessibility_features" in preferences_data:
            preferences.requires_accessibility_features = preferences_data["accessibility_features"]
        
        if "email_notifications" in preferences_data:
            preferences.email_notifications = preferences_data["email_notifications"]
        
        if "data_retention" in preferences_data:
            preferences.data_retention_preference = preferences_data["data_retention"]
        
        if "marketing_consent" in preferences_data:
            customer_profile.marketing_consent = preferences_data["marketing_consent"]
            customer_profile.last_consent_update = datetime.utcnow()
        
        if "data_collection_consent" in preferences_data:
            customer_profile.data_collection_consent = preferences_data["data_collection_consent"]
            customer_profile.last_consent_update = datetime.utcnow()
        
        preferences.updated_at = datetime.utcnow()
        customer_profile.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": "Customer preferences updated successfully",
            "customer_id": customer_profile.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating customer preferences: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update preferences")





@router.get("/agent-routing-suggestions/{customer_identifier}")
async def get_agent_routing_suggestions(
    customer_identifier: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get intelligent agent routing suggestions for a customer"""
    try:
        detection_service = CustomerDetectionService(db)
        
        # Get customer profile
        from app.live_chat.customer_detection_service import CustomerProfile
        customer_profile = db.query(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == current_agent.tenant_id,
                CustomerProfile.customer_identifier == customer_identifier
            )
        ).first()
        
        if not customer_profile:
            return {
                "success": True,
                "routing_suggestions": {
                    "recommended_agents": [],
                    "routing_criteria": ["New customer - no history available"],
                    "priority_score": 1.0,
                    "special_considerations": ["First-time visitor"]
                }
            }
        
        # Get recent conversation history for context
        recent_conversations = db.query(LiveChatConversation).filter(
            and_(
                LiveChatConversation.tenant_id == current_agent.tenant_id,
                LiveChatConversation.customer_identifier == customer_identifier
            )
        ).order_by(desc(LiveChatConversation.created_at)).limit(5).all()
        
        # Build visitor history context
        visitor_history = {
            "is_returning": True,
            "previous_conversations": [
                {
                    "agent_id": conv.assigned_agent_id,
                    "satisfaction": conv.customer_satisfaction,
                    "resolution_status": conv.resolution_status,
                    "created_at": conv.created_at
                } for conv in recent_conversations
            ]
        }
        
        # Generate routing suggestions
        routing_suggestions = await detection_service._get_routing_suggestions(
            tenant_id=current_agent.tenant_id,
            geolocation={"country": "Unknown"},  # Would be filled from recent session
            device_info={"device_type": "unknown"},
            visitor_history=visitor_history
        )
        
        # Get available agents with their current load
        available_agents = db.query(Agent).filter(
            and_(
                Agent.tenant_id == current_agent.tenant_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True
            )
        ).all()
        
        agent_recommendations = []
        for agent in available_agents:
            # Get current session
            session = db.query(AgentSession).filter(
                and_(
                    AgentSession.agent_id == agent.id,
                    AgentSession.logout_at.is_(None)
                )
            ).first()
            
            if session and session.active_conversations < session.max_concurrent_chats:
                # Check if this agent has history with customer
                agent_history_count = len([
                    conv for conv in recent_conversations 
                    if conv.assigned_agent_id == agent.id
                ])
                
                recommendation_reason = "Available agent"
                priority = 0.5
                
                if agent_history_count > 0:
                    avg_satisfaction = sum([
                        conv.customer_satisfaction or 0 
                        for conv in recent_conversations 
                        if conv.assigned_agent_id == agent.id and conv.customer_satisfaction
                    ]) / agent_history_count if agent_history_count > 0 else 0
                    
                    if avg_satisfaction > 4:
                        recommendation_reason = f"Previous successful interactions (avg rating: {avg_satisfaction:.1f})"
                        priority = 0.9
                    elif avg_satisfaction > 3:
                        recommendation_reason = f"Previous interactions (avg rating: {avg_satisfaction:.1f})"
                        priority = 0.7
                
                agent_recommendations.append({
                    "agent_id": agent.id,
                    "agent_name": agent.display_name,
                    "reason": recommendation_reason,
                    "priority": priority,
                    "current_load": session.active_conversations,
                    "max_capacity": session.max_concurrent_chats,
                    "previous_interactions": agent_history_count
                })
        
        # Sort by priority
        agent_recommendations.sort(key=lambda x: x["priority"], reverse=True)
        
        routing_suggestions["recommended_agents"] = agent_recommendations[:5]
        
        return {
            "success": True,
            "customer_identifier": customer_identifier,
            "routing_suggestions": routing_suggestions,
            "customer_context": {
                "is_returning": True,
                "total_conversations": customer_profile.total_conversations,
                "avg_satisfaction": customer_profile.customer_satisfaction_avg,
                "preferred_language": customer_profile.preferred_language
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting routing suggestions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get routing suggestions")








@router.get("/customer-analytics")
async def get_customer_analytics(
    days: int = Query(30, ge=1, le=365),
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get customer analytics and insights for the tenant - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        from_date = datetime.utcnow() - timedelta(days=days)
        
        # Get customer profiles stats
        from app.live_chat.customer_detection_service import CustomerProfile, CustomerSession
        
        total_customers = db.query(CustomerProfile).filter(
            CustomerProfile.tenant_id == tenant.id
        ).count()
        
        new_customers = db.query(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerProfile.first_seen >= from_date
            )
        ).count()
        
        returning_customers = db.query(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerProfile.total_conversations > 1
            )
        ).count()
        
        # Geographic distribution
        from sqlalchemy import func
        geographic_data = db.query(
            CustomerSession.country,
            func.count(CustomerSession.id).label('count')
        ).join(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerSession.started_at >= from_date,
                CustomerSession.country.isnot(None)
            )
        ).group_by(CustomerSession.country).order_by(desc('count')).limit(10).all()
        
        # Device type distribution
        device_data = db.query(
            CustomerSession.user_agent,
            func.count(CustomerSession.id).label('count')
        ).join(CustomerProfile).filter(
            and_(
                CustomerProfile.tenant_id == tenant.id,
                CustomerSession.started_at >= from_date
            )
        ).group_by(CustomerSession.user_agent).all()
        
        # Analyze device types
        device_counts = {"mobile": 0, "desktop": 0, "tablet": 0, "unknown": 0}
        for session_ua, count in device_data:
            if session_ua:
                try:
                    from user_agents import parse as parse_user_agent
                    parsed_ua = parse_user_agent(session_ua)
                    if parsed_ua.is_mobile:
                        device_counts["mobile"] += count
                    elif parsed_ua.is_tablet:
                        device_counts["tablet"] += count
                    elif parsed_ua.is_pc:
                        device_counts["desktop"] += count
                    else:
                        device_counts["unknown"] += count
                except:
                    device_counts["unknown"] += count
        
        # Customer satisfaction trends
        satisfaction_data = db.query(
            func.avg(LiveChatConversation.customer_satisfaction).label('avg_satisfaction'),
            func.count(LiveChatConversation.id).label('total_rated')
        ).filter(
            and_(
                LiveChatConversation.tenant_id == tenant.id,
                LiveChatConversation.created_at >= from_date,
                LiveChatConversation.customer_satisfaction.isnot(None)
            )
        ).first()
        
        return {
            "success": True,
            "period_days": days,
            "customer_metrics": {
                "total_customers": total_customers,
                "new_customers": new_customers,
                "returning_customers": returning_customers,
                "return_rate": round((returning_customers / total_customers * 100) if total_customers > 0 else 0, 2)
            },
            "geographic_distribution": [
                {"country": country, "count": count}
                for country, count in geographic_data
            ],
            "device_distribution": device_counts,
            "satisfaction_metrics": {
                "average_satisfaction": round(satisfaction_data.avg_satisfaction or 0, 2),
                "total_rated_conversations": satisfaction_data.total_rated or 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customer analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get customer analytics")

# =============================================================================
# ENHANCED START CHAT WITH AUTOMATIC DETECTION
# =============================================================================



@router.post("/start-chat-with-detection", response_model=ChatResponse)
async def start_live_chat_with_detection(
    request: StartChatRequest,
    http_request: Request,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Enhanced start chat endpoint with automatic customer detection - supports both API key and agent token"""
    try:
        # Try API key first
        if api_key:
            tenant = get_tenant_from_api_key(api_key, db)
        # Try bearer token
        elif token:
            actual_token = token.credentials if hasattr(token, 'credentials') else token
            
            from app.core.security import verify_token
            
            payload = verify_token(actual_token)
            agent_id = payload.get("sub")
            user_type = payload.get("type")
            
            if user_type == "agent":
                agent = db.query(Agent).filter(
                    Agent.id == int(agent_id),
                    Agent.status == AgentStatus.ACTIVE,
                    Agent.is_active == True
                ).first()
                
                if agent:
                    tenant = db.query(Tenant).filter(Tenant.id == agent.tenant_id).first()
                    if not tenant:
                        raise HTTPException(status_code=404, detail="Agent's tenant not found")
                else:
                    raise HTTPException(status_code=401, detail="Invalid agent token")
            else:
                raise HTTPException(status_code=401, detail="Invalid token type")
        else:
            raise HTTPException(status_code=401, detail="API key or agent authentication required")
        
        # 🔒 PRICING CHECK
        check_conversation_limit_dependency_with_super_tenant(tenant.id, db)
        
        # Initialize customer detection service
        detection_service = CustomerDetectionService(db)
        
        # Perform comprehensive customer detection
        customer_data = await detection_service.detect_customer(
            request=http_request,
            tenant_id=tenant.id,
            customer_identifier=request.customer_identifier
        )
        
        # Create conversation with enhanced customer data
        conversation = LiveChatConversation(
            tenant_id=tenant.id,
            customer_identifier=request.customer_identifier,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            chatbot_session_id=request.chatbot_session_id,
            handoff_reason="manual" if not request.handoff_context else "triggered",
            handoff_context=json.dumps(request.handoff_context) if request.handoff_context else None,
            original_question=request.initial_message,
            status=ConversationStatus.QUEUED,
            
            # Enhanced customer data from detection
            customer_ip=customer_data["geolocation"]["ip_address"],
            customer_user_agent=customer_data["device_info"]["user_agent"]
        )
        
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        # Add to queue with intelligent routing
        queue_service = LiveChatQueueService(db)
        
        # Determine priority based on customer data
        priority = 1  # Normal priority
        if customer_data["visitor_history"]["is_returning"]:
            if customer_data["visitor_history"].get("conversation_outcomes", {}).get("abandoned", 0) > 1:
                priority = 2  # Higher priority for customers with abandonment history
        
        queue_result = await queue_service.add_to_queue_with_smart_routing(
            conversation_id=conversation.id,
            priority=priority,
            assignment_criteria={
                "source": "customer_request_with_detection",
                "customer_type": "returning" if customer_data["visitor_history"]["is_returning"] else "new",
                "device_type": customer_data["device_info"]["device_type"],
                "geographic_region": customer_data["geolocation"].get("country", "unknown")
            }
        )
        
        # 📊 PRICING TRACK
        track_conversation_started_with_super_tenant(
            tenant_id=tenant.id,
            user_identifier=request.customer_identifier,
            platform="live_chat_enhanced",
            db=db
        )
        
        # Generate WebSocket URL
        websocket_url = f"/live-chat/ws/customer/{conversation.id}?customer_id={request.customer_identifier}&tenant_id={tenant.id}"
        
        # Enhanced response with customer insights
        response_message = "Chat started!"
        if customer_data["visitor_history"]["is_returning"]:
            response_message += " Welcome back! We have your previous conversation history."
        
        logger.info(f"Enhanced live chat started: conversation {conversation.id} for tenant {tenant.id}")
        
        return {
            "success": True,
            "conversation_id": conversation.id,
            "queue_position": queue_result.get("position"),
            "estimated_wait_time": queue_result.get("estimated_wait_time"),
            "websocket_url": websocket_url,
            "message": response_message,
            
            # Additional customer insights for the frontend
            "customer_insights": {
                "is_returning_visitor": customer_data["visitor_history"]["is_returning"],
                "device_type": customer_data["device_info"]["device_type"],
                "location": customer_data["geolocation"].get("city", "Unknown"),
                "preferred_language": customer_data["customer_profile"].get("preferred_language", "en"),
                "routing_priority": "high" if priority > 1 else "normal"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting enhanced live chat: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to start chat")



# Add this endpoint to your router.py file

@router.post("/conversations/{conversation_id}/accept")
async def accept_conversation(
    conversation_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Agent accepts a conversation from the queue"""
    try:
        # Get conversation
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check if conversation is available for acceptance
        if conversation.status not in [ConversationStatus.QUEUED]:
            raise HTTPException(
                status_code=400, 
                detail=f"Conversation cannot be accepted. Current status: {conversation.status}"
            )
        
        # Check if agent is available
        agent_session = db.query(AgentSession).filter(
            AgentSession.agent_id == current_agent.id,
            AgentSession.logout_at.is_(None)
        ).first()
        
        if not agent_session:
            raise HTTPException(status_code=400, detail="Agent session not found")
        
        if not agent_session.is_accepting_chats:
            raise HTTPException(status_code=400, detail="Agent is not accepting chats")
        
        if agent_session.active_conversations >= agent_session.max_concurrent_chats:
            raise HTTPException(
                status_code=400, 
                detail=f"Agent at maximum capacity ({agent_session.max_concurrent_chats} conversations)"
            )
        
        # Accept the conversation
        conversation.status = ConversationStatus.ASSIGNED
        conversation.assigned_agent_id = current_agent.id
        conversation.assigned_at = datetime.utcnow()
        conversation.assignment_method = "agent_self_accept"
        
        # Update agent session
        agent_session.active_conversations += 1
        
        # Remove from queue if exists
        queue_entry = db.query(ChatQueue).filter(
            ChatQueue.conversation_id == conversation_id,
            ChatQueue.status == "waiting"
        ).first()
        
        if queue_entry:
            queue_entry.status = "assigned"
            queue_entry.assigned_at = datetime.utcnow()
            queue_entry.assigned_agent_id = current_agent.id
        
        # Add assignment message
        assignment_message = LiveChatMessage(
            conversation_id=conversation_id,
            content=f"Agent {current_agent.display_name} has joined the conversation",
            message_type=MessageType.SYSTEM,
            sender_type=SenderType.SYSTEM,
            sender_name="System",
            system_event_type="agent_joined",
            system_event_data=json.dumps({
                "agent_id": current_agent.id,
                "agent_name": current_agent.display_name,
                "assignment_method": "self_accept"
            })
        )
        
        db.add(assignment_message)
        db.commit()
        
        # Notify via WebSocket
        from app.live_chat.websocket_manager import WebSocketMessage
        accept_notification = WebSocketMessage(
            message_type="conversation_accepted",
            data={
                "conversation_id": conversation_id,
                "agent_id": current_agent.id,
                "agent_name": current_agent.display_name,
                "accepted_at": conversation.assigned_at.isoformat()
            },
            conversation_id=str(conversation_id)
        )
        
        await websocket_manager.send_to_conversation(str(conversation_id), accept_notification)
        
        logger.info(f"Conversation {conversation_id} accepted by agent {current_agent.id}")
        
        return {
            "success": True,
            "message": "Conversation accepted successfully",
            "conversation_id": conversation_id,
            "agent_id": current_agent.id,
            "agent_name": current_agent.display_name,
            "accepted_at": conversation.assigned_at.isoformat(),
            "websocket_url": f"/live-chat/ws/agent/{current_agent.id}",
            "customer_info": {
                "customer_identifier": conversation.customer_identifier,
                "customer_name": conversation.customer_name,
                "customer_email": conversation.customer_email
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting conversation: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to accept conversation")