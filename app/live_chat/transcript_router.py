# app/live_chat/transcript_router.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Security
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from datetime import datetime


from fastapi.security import HTTPBearer
from typing import Optional



from app.database import get_db
from app.live_chat.auth_router import get_current_agent
from app.live_chat.email_transcript_service import EmailTranscriptService
from app.live_chat.models import Agent, LiveChatConversation
from app.tenants.models import Tenant
from app.tenants.router import get_tenant_from_api_key

bearer_scheme = HTTPBearer(auto_error=False)



logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic Models
class SendTranscriptRequest(BaseModel):
    conversation_id: int
    recipient_email: EmailStr
    subject: Optional[str] = None
    include_agent_notes: bool = True
    include_system_messages: bool = False
    cc_emails: Optional[List[EmailStr]] = None
    bcc_emails: Optional[List[EmailStr]] = None

class SendSelectedMessagesRequest(BaseModel):
    conversation_id: int
    message_ids: List[int]
    recipient_email: EmailStr
    subject: Optional[str] = None
    additional_notes: Optional[str] = None
    cc_emails: Optional[List[EmailStr]] = None

class TranscriptResponse(BaseModel):
    success: bool
    message: str
    email_id: Optional[str] = None
    conversation_id: int
    message_count: Optional[int] = None
    sent_at: str

class MessageSelectionRequest(BaseModel):
    conversation_id: int
    sender_type: Optional[str] = None  # "customer", "agent", "system"
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_attachments: bool = True

# =============================================================================
# AGENT ENDPOINTS (Bearer Token Authentication)
# =============================================================================

@router.post("/send-transcript", response_model=TranscriptResponse)
async def send_conversation_transcript(
    request: SendTranscriptRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Send complete conversation transcript via email"""
    try:
        # Verify conversation belongs to agent's tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == request.conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found or access denied"
            )
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Send transcript
        result = await transcript_service.send_conversation_transcript(
            conversation_id=request.conversation_id,
            agent_id=current_agent.id,
            recipient_email=request.recipient_email,
            subject=request.subject,
            include_agent_notes=request.include_agent_notes,
            include_system_messages=request.include_system_messages
        )
        
        if result["success"]:
            logger.info(
                f"Transcript sent by agent {current_agent.id} for conversation {request.conversation_id} "
                f"to {request.recipient_email}"
            )
            
            return TranscriptResponse(
                success=True,
                message=result["message"],
                email_id=result.get("email_id"),
                conversation_id=request.conversation_id,
                message_count=result.get("message_count"),
                sent_at=result["sent_at"]
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending transcript: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send transcript")


@router.post("/send-selected-messages", response_model=TranscriptResponse)
async def send_selected_messages(
    request: SendSelectedMessagesRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Send selected messages from conversation via email"""
    try:
        # Verify conversation belongs to agent's tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == request.conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found or access denied"
            )
        
        if not request.message_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one message ID is required"
            )
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Send selected messages
        result = await transcript_service.send_selected_messages(
            conversation_id=request.conversation_id,
            agent_id=current_agent.id,
            message_ids=request.message_ids,
            recipient_email=request.recipient_email,
            subject=request.subject,
            additional_notes=request.additional_notes
        )
        
        if result["success"]:
            logger.info(
                f"Selected messages sent by agent {current_agent.id} for conversation {request.conversation_id} "
                f"to {request.recipient_email} (messages: {len(request.message_ids)})"
            )
            
            return TranscriptResponse(
                success=True,
                message=result["message"],
                email_id=result.get("email_id"),
                conversation_id=request.conversation_id,
                message_count=result.get("message_count"),
                sent_at=datetime.utcnow().isoformat()
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending selected messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send selected messages")


@router.get("/conversation/{conversation_id}/messages")
async def get_conversation_messages_for_selection(
    conversation_id: int,
    current_agent: Agent = Depends(get_current_agent),
    sender_type: Optional[str] = Query(None, description="Filter by sender type: customer, agent, system"),
    include_system: bool = Query(False, description="Include system messages"),
    limit: int = Query(100, ge=1, le=500, description="Number of messages to return"),
    db: Session = Depends(get_db)
):
    """Get conversation messages with metadata for selection"""
    try:
        # Verify conversation access
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found or access denied"
            )
        
        # Build query
        from app.live_chat.models import LiveChatMessage, SenderType
        from sqlalchemy import and_
        
        query = db.query(LiveChatMessage).filter(
            LiveChatMessage.conversation_id == conversation_id
        )
        
        # Apply filters
        if sender_type:
            query = query.filter(LiveChatMessage.sender_type == sender_type)
        
        if not include_system:
            query = query.filter(LiveChatMessage.sender_type != SenderType.SYSTEM)
        
        # Get messages
        messages = query.order_by(
            LiveChatMessage.sent_at.asc()
        ).limit(limit).all()
        
        # Format messages for selection interface
        message_list = []
        for msg in messages:
            message_data = {
                "message_id": msg.id,
                "content": msg.content,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name or ("Agent" if msg.sender_type == SenderType.AGENT else "Customer"),
                "sent_at": msg.sent_at.isoformat(),
                "message_type": msg.message_type,
                "is_internal": msg.is_internal,
                "has_attachment": bool(msg.attachment_url),
                "attachment_name": msg.attachment_name,
                "character_count": len(msg.content) if msg.content else 0
            }
            message_list.append(message_data)
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "messages": message_list,
            "total_count": len(message_list),
            "conversation_info": {
                "customer_name": conversation.customer_name,
                "customer_email": conversation.customer_email,
                "status": conversation.status,
                "created_at": conversation.created_at.isoformat(),
                "total_messages": conversation.message_count
            },
            "filters_applied": {
                "sender_type": sender_type,
                "include_system": include_system,
                "limit": limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get messages")


@router.get("/conversation/{conversation_id}/transcript-preview")
async def get_transcript_preview(
    conversation_id: int,
    current_agent: Agent = Depends(get_current_agent),
    include_agent_notes: bool = Query(True),
    include_system_messages: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get a preview of what the transcript will look like"""
    try:
        # Verify conversation access
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found or access denied"
            )
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Get formatted messages
        messages = await transcript_service._get_formatted_messages(
            conversation_id, 
            include_system_messages
        )
        
        # Generate transcript data
        transcript_data = await transcript_service._generate_transcript_data(
            conversation, 
            messages, 
            current_agent, 
            include_agent_notes
        )
        
        # Return preview data
        return {
            "success": True,
            "conversation_id": conversation_id,
            "preview": {
                "conversation_info": transcript_data["conversation"],
                "message_count": len(messages),
                "estimated_length": sum(len(msg["content"]) for msg in messages if msg["content"]),
                "participants": list(set(msg["sender_name"] for msg in messages if msg["sender_name"])),
                "date_range": {
                    "start": messages[0]["sent_at"].isoformat() if messages else None,
                    "end": messages[-1]["sent_at"].isoformat() if messages else None
                },
                "includes_attachments": any(msg.get("attachment_url") for msg in messages),
                "includes_agent_notes": include_agent_notes and bool(conversation.agent_notes),
                "includes_system_messages": include_system_messages
            },
            "sample_messages": messages[:3] if messages else []  # First 3 messages as sample
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript preview: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get preview")


@router.get("/conversation/{conversation_id}/transcript-history")
async def get_transcript_history(
    conversation_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get history of transcript sends for this conversation"""
    try:
        # Verify conversation access
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == current_agent.tenant_id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found or access denied"
            )
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Get transcript history
        history = await transcript_service.get_transcript_history(
            conversation_id, 
            current_agent.id
        )
        
        return history
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get history")


# =============================================================================
# ADMIN ENDPOINTS (API Key Authentication)
# =============================================================================

# @router.post("/admin/send-transcript")
# async def admin_send_transcript(
#     request: SendTranscriptRequest,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Admin endpoint to send conversation transcript"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         # Verify conversation belongs to tenant
#         conversation = db.query(LiveChatConversation).filter(
#             LiveChatConversation.id == request.conversation_id,
#             LiveChatConversation.tenant_id == tenant.id
#         ).first()
        
#         if not conversation:
#             raise HTTPException(
#                 status_code=404, 
#                 detail="Conversation not found"
#             )
        
#         # Get a representative agent (could be the assigned agent or any active agent)
#         agent = None
#         if conversation.assigned_agent_id:
#             agent = db.query(Agent).filter(Agent.id == conversation.assigned_agent_id).first()
        
#         if not agent:
#             # Get any active agent from this tenant
#             agent = db.query(Agent).filter(
#                 Agent.tenant_id == tenant.id,
#                 Agent.is_active == True
#             ).first()
        
#         if not agent:
#             raise HTTPException(
#                 status_code=404,
#                 detail="No agents found for this tenant"
#             )
        
#         # Initialize transcript service
#         transcript_service = EmailTranscriptService(db)
        
#         # Send transcript
#         result = await transcript_service.send_conversation_transcript(
#             conversation_id=request.conversation_id,
#             agent_id=agent.id,
#             recipient_email=request.recipient_email,
#             subject=request.subject,
#             include_agent_notes=request.include_agent_notes,
#             include_system_messages=request.include_system_messages
#         )
        
#         if result["success"]:
#             return {
#                 "success": True,
#                 "message": result["message"],
#                 "email_id": result.get("email_id"),
#                 "conversation_id": request.conversation_id,
#                 "sent_by": "admin"
#             }
#         else:
#             raise HTTPException(
#                 status_code=500,
#                 detail=result["error"]
#             )
            
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in admin send transcript: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to send transcript")



@router.post("/admin/send-transcript")
async def admin_send_transcript(
    request: SendTranscriptRequest,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Admin endpoint to send conversation transcript - supports both API key and agent token"""
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
        
        # Verify conversation belongs to tenant
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == request.conversation_id,
            LiveChatConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=404, 
                detail="Conversation not found"
            )
        
        # Get a representative agent (could be the assigned agent or any active agent)
        agent_for_transcript = None
        if conversation.assigned_agent_id:
            agent_for_transcript = db.query(Agent).filter(Agent.id == conversation.assigned_agent_id).first()
        
        if not agent_for_transcript:
            # Get any active agent from this tenant
            agent_for_transcript = db.query(Agent).filter(
                Agent.tenant_id == tenant.id,
                Agent.is_active == True
            ).first()
        
        if not agent_for_transcript:
            raise HTTPException(
                status_code=404,
                detail="No agents found for this tenant"
            )
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Send transcript
        result = await transcript_service.send_conversation_transcript(
            conversation_id=request.conversation_id,
            agent_id=agent_for_transcript.id,
            recipient_email=request.recipient_email,
            subject=request.subject,
            include_agent_notes=request.include_agent_notes,
            include_system_messages=request.include_system_messages
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "email_id": result.get("email_id"),
                "conversation_id": request.conversation_id,
                "sent_by": "admin"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin send transcript: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send transcript")




# @router.get("/admin/conversation/{conversation_id}/transcript-options")
# async def admin_get_transcript_options(
#     conversation_id: int,
#     api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db)
# ):
#     """Get transcript options and metadata for admin"""
#     try:
#         tenant = get_tenant_from_api_key(api_key, db)
        
#         # Verify conversation
#         conversation = db.query(LiveChatConversation).filter(
#             LiveChatConversation.id == conversation_id,
#             LiveChatConversation.tenant_id == tenant.id
#         ).first()
        
#         if not conversation:
#             raise HTTPException(status_code=404, detail="Conversation not found")
        
#         # Get message statistics
#         from app.live_chat.models import LiveChatMessage, SenderType
#         from sqlalchemy import func
        
#         message_stats = db.query(
#             LiveChatMessage.sender_type,
#             func.count(LiveChatMessage.id).label('count')
#         ).filter(
#             LiveChatMessage.conversation_id == conversation_id
#         ).group_by(LiveChatMessage.sender_type).all()
        
#         stats_dict = {stat.sender_type: stat.count for stat in message_stats}
        
#         # Get available options
#         return {
#             "success": True,
#             "conversation_id": conversation_id,
#             "conversation_info": {
#                 "customer_name": conversation.customer_name,
#                 "customer_email": conversation.customer_email,
#                 "status": conversation.status,
#                 "created_at": conversation.created_at.isoformat(),
#                 "closed_at": conversation.closed_at.isoformat() if conversation.closed_at else None,
#                 "assigned_agent_id": conversation.assigned_agent_id,
#                 "has_agent_notes": bool(conversation.agent_notes),
#                 "has_internal_notes": bool(conversation.internal_notes)
#             },
#             "message_statistics": {
#                 "total_messages": sum(stats_dict.values()),
#                 "customer_messages": stats_dict.get(SenderType.CUSTOMER, 0),
#                 "agent_messages": stats_dict.get(SenderType.AGENT, 0),
#                 "system_messages": stats_dict.get(SenderType.SYSTEM, 0)
#             },
#             "transcript_options": {
#                 "can_include_agent_notes": bool(conversation.agent_notes),
#                 "can_include_internal_notes": bool(conversation.internal_notes),
#                 "can_filter_by_sender": True,
#                 "can_select_date_range": True,
#                 "available_formats": ["html", "plain_text"]
#             },
#             "suggested_recipients": [
#                 conversation.customer_email
#             ] if conversation.customer_email else []
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting transcript options: {str(e)}")
#         raise HTTPException(status_code=500, detail="Failed to get options")





@router.get("/admin/conversation/{conversation_id}/transcript-options")
async def admin_get_transcript_options(
    conversation_id: int,
    api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Security(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get transcript options and metadata for admin - supports both API key and agent token"""
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
        
        # Verify conversation
        conversation = db.query(LiveChatConversation).filter(
            LiveChatConversation.id == conversation_id,
            LiveChatConversation.tenant_id == tenant.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get message statistics
        from app.live_chat.models import LiveChatMessage, SenderType
        from sqlalchemy import func
        
        message_stats = db.query(
            LiveChatMessage.sender_type,
            func.count(LiveChatMessage.id).label('count')
        ).filter(
            LiveChatMessage.conversation_id == conversation_id
        ).group_by(LiveChatMessage.sender_type).all()
        
        stats_dict = {stat.sender_type: stat.count for stat in message_stats}
        
        # Get available options
        return {
            "success": True,
            "conversation_id": conversation_id,
            "conversation_info": {
                "customer_name": conversation.customer_name,
                "customer_email": conversation.customer_email,
                "status": conversation.status,
                "created_at": conversation.created_at.isoformat(),
                "closed_at": conversation.closed_at.isoformat() if conversation.closed_at else None,
                "assigned_agent_id": conversation.assigned_agent_id,
                "has_agent_notes": bool(conversation.agent_notes),
                "has_internal_notes": bool(conversation.internal_notes)
            },
            "message_statistics": {
                "total_messages": sum(stats_dict.values()),
                "customer_messages": stats_dict.get(SenderType.CUSTOMER, 0),
                "agent_messages": stats_dict.get(SenderType.AGENT, 0),
                "system_messages": stats_dict.get(SenderType.SYSTEM, 0)
            },
            "transcript_options": {
                "can_include_agent_notes": bool(conversation.agent_notes),
                "can_include_internal_notes": bool(conversation.internal_notes),
                "can_filter_by_sender": True,
                "can_select_date_range": True,
                "available_formats": ["html", "plain_text"]
            },
            "suggested_recipients": [
                conversation.customer_email
            ] if conversation.customer_email else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript options: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get options")


# =============================================================================
# WEBSOCKET MESSAGE HANDLERS FOR TRANSCRIPT FEATURES
# =============================================================================

# Add these message types to your existing websocket_manager.py WebSocket message handler

async def handle_transcript_request(self, connection_id: str, data: dict):
    """Handle transcript request via WebSocket"""
    try:
        request_type = data.get("request_type")  # "full_transcript" or "selected_messages"
        conversation_id = data.get("conversation_id")
        recipient_email = data.get("recipient_email")
        
        if not all([request_type, conversation_id, recipient_email]):
            await self._send_error(connection_id, "Missing required fields")
            return
        
        connection = self.websocket_manager.connections.get(connection_id)
        if not connection or connection.connection_type != "agent":
            await self._send_error(connection_id, "Invalid agent connection")
            return
        
        agent_id = int(connection.user_id)
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(self.db)
        
        if request_type == "full_transcript":
            # Send full transcript
            result = await transcript_service.send_conversation_transcript(
                conversation_id=conversation_id,
                agent_id=agent_id,
                recipient_email=recipient_email,
                subject=data.get("subject"),
                include_agent_notes=data.get("include_agent_notes", True),
                include_system_messages=data.get("include_system_messages", False)
            )
        
        elif request_type == "selected_messages":
            # Send selected messages
            message_ids = data.get("message_ids", [])
            if not message_ids:
                await self._send_error(connection_id, "No messages selected")
                return
            
            result = await transcript_service.send_selected_messages(
                conversation_id=conversation_id,
                agent_id=agent_id,
                message_ids=message_ids,
                recipient_email=recipient_email,
                subject=data.get("subject"),
                additional_notes=data.get("additional_notes")
            )
        
        else:
            await self._send_error(connection_id, "Invalid request type")
            return
        
        # Send response back to agent
        response_data = {
            "request_type": request_type,
            "success": result["success"],
            "conversation_id": conversation_id,
            "recipient_email": recipient_email
        }
        
        if result["success"]:
            response_data.update({
                "message": result["message"],
                "email_id": result.get("email_id"),
                "message_count": result.get("message_count")
            })
        else:
            response_data["error"] = result["error"]
        
        from app.live_chat.websocket_manager import WebSocketMessage
        response_msg = WebSocketMessage(
            message_type="transcript_response",
            data=response_data,
            conversation_id=str(conversation_id)
        )
        
        await connection.send_message(response_msg)
        
        logger.info(f"Transcript {request_type} processed for agent {agent_id}")
        
    except Exception as e:
        logger.error(f"Error handling transcript request: {str(e)}")
        await self._send_error(connection_id, "Failed to process transcript request")


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/email-templates/preview")
async def preview_email_template(
    template_type: str = Query(..., description="Template type: transcript or selected_messages"),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Preview email template for transcript"""
    try:
        if template_type not in ["transcript", "selected_messages"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid template type. Use 'transcript' or 'selected_messages'"
            )
        
        # Create sample data for preview
        sample_conversation = {
            "id": 12345,
            "customer_name": "John Doe",
            "customer_email": "john.doe@example.com",
            "created_at": datetime.utcnow(),
            "closed_at": datetime.utcnow(),
            "status": "closed",
            "duration_minutes": 15,
            "customer_satisfaction": 5
        }
        
        sample_messages = [
            {
                "id": 1,
                "content": "Hello, I need help with my account",
                "sender_type": "customer",
                "sender_name": "John Doe",
                "sent_at": datetime.utcnow(),
                "message_type": "text",
                "is_internal": False
            },
            {
                "id": 2,
                "content": "Hi John! I'd be happy to help you with your account. What specific issue are you experiencing?",
                "sender_type": "agent",
                "sender_name": current_agent.display_name,
                "sent_at": datetime.utcnow(),
                "message_type": "text",
                "is_internal": False
            },
            {
                "id": 3,
                "content": "I can't log into my account. It says my password is incorrect.",
                "sender_type": "customer",
                "sender_name": "John Doe",
                "sent_at": datetime.utcnow(),
                "message_type": "text",
                "is_internal": False
            }
        ]
        
        sample_transcript_data = {
            "conversation": sample_conversation,
            "messages": sample_messages,
            "agent": {
                "name": current_agent.display_name,
                "email": current_agent.email
            },
            "metadata": {
                "total_messages": len(sample_messages),
                "generated_at": datetime.utcnow(),
                "generated_by": current_agent.display_name
            }
        }
        
        # Initialize transcript service
        transcript_service = EmailTranscriptService(db)
        
        # Generate preview
        html_content = await transcript_service._generate_html_transcript(sample_transcript_data)
        plain_content = await transcript_service._generate_plain_transcript(sample_transcript_data)
        
        return {
            "success": True,
            "template_type": template_type,
            "preview": {
                "html_content": html_content,
                "plain_content": plain_content,
                "sample_data": sample_transcript_data
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating template preview: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate preview")


@router.get("/health")
async def transcript_service_health():
    """Health check for transcript service"""
    try:
        from app.email.resend_service import email_service
        
        # Test email service
        email_health = await email_service.test_email_connection()
        
        return {
            "success": True,
            "service": "transcript_service",
            "email_service": {
                "enabled": email_service.enabled,
                "status": "healthy" if email_health["success"] else "unhealthy",
                "provider": "Resend"
            },
            "features": {
                "full_transcript": True,
                "selected_messages": True,
                "html_email": True,
                "plain_text_email": True,
                "attachments_support": True
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in transcript service health check: {str(e)}")
        return {
            "success": False,
            "service": "transcript_service",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }