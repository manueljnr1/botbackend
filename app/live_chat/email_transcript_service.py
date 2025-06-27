# app/live_chat/email_transcript_service.py

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import json

from app.live_chat.models import (
    LiveChatConversation, LiveChatMessage, Agent, SenderType, MessageType
)
from app.email.resend_service import email_service

logger = logging.getLogger(__name__)

class EmailTranscriptService:
    """Service for sending conversation transcripts via email"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def send_conversation_transcript(
        self, 
        conversation_id: int, 
        agent_id: int, 
        recipient_email: str,
        subject: Optional[str] = None,
        include_agent_notes: bool = True,
        include_system_messages: bool = False
    ) -> Dict[str, Any]:
        """Send complete conversation transcript via email"""
        try:
            # Get conversation details
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                return {"success": False, "error": "Conversation not found"}
            
            # Get agent details
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}
            
            # Verify agent has access to this conversation
            if conversation.tenant_id != agent.tenant_id:
                return {"success": False, "error": "Access denied"}
            
            # Get messages
            messages = await self._get_formatted_messages(
                conversation_id, 
                include_system_messages
            )
            
            # Generate transcript
            transcript_data = await self._generate_transcript_data(
                conversation, 
                messages, 
                agent, 
                include_agent_notes
            )
            
            # Generate email content
            html_content = await self._generate_html_transcript(transcript_data)
            plain_content = await self._generate_plain_transcript(transcript_data)
            
            # Prepare email subject
            if not subject:
                subject = f"Chat Transcript - Conversation #{conversation_id}"
                if conversation.customer_name:
                    subject += f" with {conversation.customer_name}"
            
            # Send email
            email_result = await email_service.send_conversation_transcript(
                to_email=recipient_email,
                subject=subject,
                html_content=html_content,
                plain_content=plain_content,
                conversation_id=conversation_id,
                agent_name=agent.display_name
            )
            
            if email_result["success"]:
                await self._log_transcript_send(
                    conversation_id, 
                    agent_id, 
                    recipient_email, 
                    email_result.get("email_id")
                )
                
                logger.info(f"Transcript sent for conversation {conversation_id} to {recipient_email}")
                
                return {
                    "success": True,
                    "message": f"Transcript sent successfully to {recipient_email}",
                    "email_id": email_result.get("email_id"),
                    "conversation_id": conversation_id,
                    "message_count": len(messages),
                    "sent_at": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to send email: {email_result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error sending conversation transcript: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def send_selected_messages(
        self,
        conversation_id: int,
        agent_id: int,
        message_ids: List[int],
        recipient_email: str,
        subject: Optional[str] = None,
        additional_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send selected messages from a conversation"""
        try:
            # Get conversation and agent
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            
            if not conversation or not agent:
                return {"success": False, "error": "Conversation or agent not found"}
            
            # Verify access
            if conversation.tenant_id != agent.tenant_id:
                return {"success": False, "error": "Access denied"}
            
            # Get selected messages
            messages = self.db.query(LiveChatMessage).filter(
                and_(
                    LiveChatMessage.conversation_id == conversation_id,
                    LiveChatMessage.id.in_(message_ids)
                )
            ).order_by(LiveChatMessage.sent_at.asc()).all()
            
            if not messages:
                return {"success": False, "error": "No messages found with provided IDs"}
            
            # Format messages
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "id": msg.id,
                    "content": msg.content,
                    "sender_type": msg.sender_type,
                    "sender_name": msg.sender_name or ("Agent" if msg.sender_type == SenderType.AGENT else "Customer"),
                    "sent_at": msg.sent_at,
                    "message_type": msg.message_type,
                    "is_internal": msg.is_internal
                })
            
            # Generate transcript data
            transcript_data = {
                "conversation": {
                    "id": conversation.id,
                    "customer_name": conversation.customer_name or "Customer",
                    "customer_email": conversation.customer_email,
                    "created_at": conversation.created_at,
                    "status": conversation.status
                },
                "messages": formatted_messages,
                "agent": {
                    "name": agent.display_name,
                    "email": agent.email
                },
                "metadata": {
                    "total_messages": len(formatted_messages),
                    "selection_type": "selected_messages",
                    "generated_at": datetime.utcnow(),
                    "additional_notes": additional_notes
                }
            }
            
            # Generate email content
            html_content = await self._generate_html_transcript(transcript_data)
            plain_content = await self._generate_plain_transcript(transcript_data)
            
            # Prepare subject
            if not subject:
                subject = f"Selected Messages - Conversation #{conversation_id}"
                if conversation.customer_name:
                    subject += f" with {conversation.customer_name}"
            
            # Send email
            email_result = await email_service.send_conversation_transcript(
                to_email=recipient_email,
                subject=subject,
                html_content=html_content,
                plain_content=plain_content,
                conversation_id=conversation_id,
                agent_name=agent.display_name
            )
            
            if email_result["success"]:
                await self._log_transcript_send(
                    conversation_id, 
                    agent_id, 
                    recipient_email, 
                    email_result.get("email_id"),
                    selection_type="selected_messages",
                    message_count=len(messages)
                )
                
                return {
                    "success": True,
                    "message": f"Selected messages sent to {recipient_email}",
                    "email_id": email_result.get("email_id"),
                    "message_count": len(messages)
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to send email: {email_result.get('error')}"
                }
                
        except Exception as e:
            logger.error(f"Error sending selected messages: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _get_formatted_messages(
        self, 
        conversation_id: int, 
        include_system_messages: bool = False
    ) -> List[Dict]:
        """Get and format conversation messages"""
        query = self.db.query(LiveChatMessage).filter(
            LiveChatMessage.conversation_id == conversation_id
        )
        
        if not include_system_messages:
            query = query.filter(LiveChatMessage.sender_type != SenderType.SYSTEM)
        
        messages = query.order_by(LiveChatMessage.sent_at.asc()).all()
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "id": msg.id,
                "content": msg.content,
                "sender_type": msg.sender_type,
                "sender_name": msg.sender_name or ("Agent" if msg.sender_type == SenderType.AGENT else "Customer"),
                "sent_at": msg.sent_at,
                "message_type": msg.message_type,
                "is_internal": msg.is_internal,
                "attachment_url": msg.attachment_url,
                "attachment_name": msg.attachment_name
            })
        
        return formatted_messages
    
    async def _generate_transcript_data(
        self, 
        conversation: LiveChatConversation, 
        messages: List[Dict], 
        agent: Agent,
        include_agent_notes: bool = True
    ) -> Dict:
        """Generate comprehensive transcript data"""
        transcript_data = {
            "conversation": {
                "id": conversation.id,
                "customer_name": conversation.customer_name or "Customer",
                "customer_email": conversation.customer_email,
                "created_at": conversation.created_at,
                "closed_at": conversation.closed_at,
                "status": conversation.status,
                "customer_satisfaction": conversation.customer_satisfaction,
                "duration_minutes": (
                    conversation.conversation_duration_seconds // 60 
                    if conversation.conversation_duration_seconds else None
                ),
                "message_count": conversation.message_count
            },
            "messages": messages,
            "agent": {
                "name": agent.display_name,
                "email": agent.email
            },
            "metadata": {
                "total_messages": len(messages),
                "generated_at": datetime.utcnow(),
                "generated_by": agent.display_name,
                "include_agent_notes": include_agent_notes
            }
        }
        
        # Add agent notes if requested
        if include_agent_notes and conversation.agent_notes:
            transcript_data["agent_notes"] = conversation.agent_notes
        
        return transcript_data
    
    async def _generate_html_transcript(self, transcript_data: Dict) -> str:
        """Generate HTML email content for transcript"""
        conversation = transcript_data["conversation"]
        messages = transcript_data["messages"]
        agent = transcript_data["agent"]
        metadata = transcript_data["metadata"]
        
        # Format dates
        created_at_str = conversation["created_at"].strftime("%B %d, %Y at %I:%M %p UTC")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Chat Transcript</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .header {{ background: #6d28d9; color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .info-section {{ padding: 25px; border-bottom: 1px solid #e5e7eb; }}
                .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }}
                .info-item {{ }}
                .info-label {{ font-weight: 600; color: #374151; margin-bottom: 4px; }}
                .info-value {{ color: #6b7280; }}
                .messages-section {{ padding: 25px; }}
                .message {{ margin-bottom: 20px; padding: 15px; border-radius: 8px; border-left: 4px solid; }}
                .message.customer {{ background: #f3f4f6; border-left-color: #3b82f6; }}
                .message.agent {{ background: #ecfdf5; border-left-color: #10b981; }}
                .message-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
                .sender {{ font-weight: 600; }}
                .timestamp {{ color: #6b7280; font-size: 14px; }}
                .message-content {{ line-height: 1.5; }}
                .footer {{ padding: 20px; text-align: center; color: #6b7280; font-size: 14px; background: #f9fafb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💬 Chat Transcript</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Conversation #{conversation["id"]}</p>
                </div>
                
                <div class="info-section">
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">Customer</div>
                            <div class="info-value">{conversation["customer_name"]}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Started</div>
                            <div class="info-value">{created_at_str}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">Status</div>
                            <div class="info-value">{conversation["status"].title()}</div>
                        </div>
                    </div>
                </div>
                
                <div class="messages-section">
                    <h3 style="margin-top: 0; color: #374151;">Messages</h3>
        """
        
        # Add messages
        for message in messages:
            sender_class = message["sender_type"].lower()
            timestamp = message["sent_at"].strftime("%I:%M %p")
            
            html_content += f"""
                    <div class="message {sender_class}">
                        <div class="message-header">
                            <span class="sender">{message["sender_name"]}</span>
                            <span class="timestamp">{timestamp}</span>
                        </div>
                        <div class="message-content">{message["content"]}</div>
                    </div>
            """
        
        html_content += f"""
                </div>
                
                <div class="footer">
                    <p>Generated by {agent["name"]} on {metadata["generated_at"].strftime("%B %d, %Y at %I:%M %p UTC")}</p>
                    <p>Total Messages: {metadata["total_messages"]}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    async def _generate_plain_transcript(self, transcript_data: Dict) -> str:
        """Generate plain text version of transcript"""
        conversation = transcript_data["conversation"]
        messages = transcript_data["messages"]
        agent = transcript_data["agent"]
        metadata = transcript_data["metadata"]
        
        # Header
        plain_content = f"""
CHAT TRANSCRIPT - Conversation #{conversation["id"]}
{'=' * 50}

Customer: {conversation["customer_name"]}
Started: {conversation["created_at"].strftime("%B %d, %Y at %I:%M %p UTC")}
Status: {conversation["status"].title()}
Total Messages: {metadata["total_messages"]}

{'=' * 50}
MESSAGES
{'=' * 50}

"""
        
        # Messages
        for message in messages:
            timestamp = message["sent_at"].strftime("%Y-%m-%d %I:%M %p")
            plain_content += f"[{timestamp}] {message['sender_name']}: {message['content']}\n\n"
        
        # Footer
        plain_content += f"\n{'=' * 50}\nGenerated by {agent['name']} on {metadata['generated_at'].strftime('%B %d, %Y at %I:%M %p UTC')}\n"
        
        return plain_content
    
    async def _log_transcript_send(
        self, 
        conversation_id: int, 
        agent_id: int, 
        recipient_email: str, 
        email_id: Optional[str] = None,
        selection_type: str = "full_transcript",
        message_count: Optional[int] = None
    ):
        """Log transcript send for audit purposes"""
        try:
            log_data = {
                "conversation_id": conversation_id,
                "agent_id": agent_id,
                "recipient_email": recipient_email,
                "email_id": email_id,
                "selection_type": selection_type,
                "message_count": message_count,
                "sent_at": datetime.utcnow()
            }
            
            logger.info(f"Transcript sent: {json.dumps(log_data)}")
            
        except Exception as e:
            logger.error(f"Error logging transcript send: {str(e)}")