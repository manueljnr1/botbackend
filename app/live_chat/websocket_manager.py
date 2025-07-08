# app/live_chat/websocket_manager.py
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import uuid

from app.live_chat.models import (
    LiveChatConversation, LiveChatMessage, Agent, AgentSession,
    ConversationStatus, MessageType, SenderType
)
from app.live_chat.queue_service import LiveChatQueueService
from app.live_chat.email_transcript_service import EmailTranscriptService

logger = logging.getLogger(__name__)


class ConnectionType:
    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class WebSocketMessage:
    """Standard WebSocket message format"""
    
    def __init__(self, message_type: str, data: dict, conversation_id: str = None):
        self.type = message_type
        self.data = data
        self.conversation_id = conversation_id
        self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": self.data,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class Connection:
    """Represents a WebSocket connection"""
    
    def __init__(self, websocket: WebSocket, connection_id: str, 
                 connection_type: str, user_id: str, tenant_id: int):
        self.websocket = websocket
        self.connection_id = connection_id
        self.connection_type = connection_type
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.conversation_ids: Set[str] = set()
        self.is_active = True
    
    async def send_message(self, message: WebSocketMessage):
        """Send message to this connection"""
        try:
            # Check if connection is still active and WebSocket is open
            if self.is_active and self.websocket.client_state.name == "CONNECTED":
                await self.websocket.send_text(message.to_json())
                self.last_activity = datetime.utcnow()
            else:
                logger.warning(f"Attempted to send message to closed connection {self.connection_id}")
                self.is_active = False
        except Exception as e:
            logger.error(f"Error sending message to {self.connection_id}: {str(e)}")
            self.is_active = False

    async def send_json(self, data: dict):
        """Send JSON data directly"""
        try:
            # Check if connection is still active and WebSocket is open
            if self.is_active and self.websocket.client_state.name == "CONNECTED":
                await self.websocket.send_json(data)
                self.last_activity = datetime.utcnow()
            else:
                logger.warning(f"Attempted to send JSON to closed connection {self.connection_id}")
                self.is_active = False
        except Exception as e:
            logger.error(f"Error sending JSON to {self.connection_id}: {str(e)}")
            self.is_active = False


class LiveChatWebSocketManager:
    """Manages all WebSocket connections for live chat"""
    
    def __init__(self):
        # Store connections by connection_id
        self.connections: Dict[str, Connection] = {}
        
        # Index connections by different criteria for fast lookup
        self.connections_by_tenant: Dict[int, Set[str]] = {}
        self.connections_by_user: Dict[str, Set[str]] = {}
        self.connections_by_conversation: Dict[str, Set[str]] = {}
        self.agent_connections: Dict[int, str] = {}  # agent_id -> connection_id
        
        self._lock = asyncio.Lock()
        
    
    async def connect_customer(self, websocket: WebSocket, customer_id: str, 
                            tenant_id: int, conversation_id: str = None) -> str:
       """Connect a customer to live chat"""
       connection_id = f"customer_{customer_id}_{uuid.uuid4().hex[:8]}"
       
       try:
           connection = Connection(
               websocket=websocket,
               connection_id=connection_id,
               connection_type=ConnectionType.CUSTOMER,
               user_id=customer_id,
               tenant_id=tenant_id
           )
           
           if conversation_id:
               connection.conversation_ids.add(conversation_id)
           
           await self._add_connection(connection)
           
           logger.info(f"Customer connected: {customer_id} ({connection_id})")
           return connection_id
           
       except Exception as e:
           logger.error(f"Error connecting customer: {str(e)}")
           raise
    
    async def connect_agent(self, websocket: WebSocket, agent_id: int, 
                          tenant_id: int, session_id: str) -> str:
        """Connect an agent to live chat"""
        connection_id = f"agent_{agent_id}_{uuid.uuid4().hex[:8]}"
        
        try:
            await websocket.accept()
            
            connection = Connection(
                websocket=websocket,
                connection_id=connection_id,
                connection_type=ConnectionType.AGENT,
                user_id=str(agent_id),
                tenant_id=tenant_id
            )
            
            await self._add_connection(connection)
            
            # Store agent connection for quick lookup
            async with self._lock:
                self.agent_connections[agent_id] = connection_id
            
            # Send welcome message with agent dashboard data
            welcome_msg = WebSocketMessage(
                message_type="agent_connected",
                data={
                    "connection_id": connection_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            await connection.send_message(welcome_msg)
            
            logger.info(f"Agent connected: {agent_id} ({connection_id})")
            return connection_id
            
        except Exception as e:
            logger.error(f"Error connecting agent: {str(e)}")
            raise
    
    async def _add_connection(self, connection: Connection):
        """Add connection to all indexes"""
        async with self._lock:
            # Main connection store
            self.connections[connection.connection_id] = connection
            
            # Index by tenant
            if connection.tenant_id not in self.connections_by_tenant:
                self.connections_by_tenant[connection.tenant_id] = set()
            self.connections_by_tenant[connection.tenant_id].add(connection.connection_id)
            
            # Index by user
            user_key = f"{connection.connection_type}_{connection.user_id}"
            if user_key not in self.connections_by_user:
                self.connections_by_user[user_key] = set()
            self.connections_by_user[user_key].add(connection.connection_id)
            
            # Index by conversation
            for conv_id in connection.conversation_ids:
                if conv_id not in self.connections_by_conversation:
                    self.connections_by_conversation[conv_id] = set()
                self.connections_by_conversation[conv_id].add(connection.connection_id)
    
    async def disconnect(self, connection_id: str):
        """Disconnect and clean up a connection"""
        async with self._lock:
            connection = self.connections.get(connection_id)
            if not connection:
                return
            
            # Remove from main store
            del self.connections[connection_id]
            
            # Remove from tenant index
            if connection.tenant_id in self.connections_by_tenant:
                self.connections_by_tenant[connection.tenant_id].discard(connection_id)
                if not self.connections_by_tenant[connection.tenant_id]:
                    del self.connections_by_tenant[connection.tenant_id]
            
            # Remove from user index
            user_key = f"{connection.connection_type}_{connection.user_id}"
            if user_key in self.connections_by_user:
                self.connections_by_user[user_key].discard(connection_id)
                if not self.connections_by_user[user_key]:
                    del self.connections_by_user[user_key]
            
            # Remove from conversation indexes
            for conv_id in connection.conversation_ids:
                if conv_id in self.connections_by_conversation:
                    self.connections_by_conversation[conv_id].discard(connection_id)
                    if not self.connections_by_conversation[conv_id]:
                        del self.connections_by_conversation[conv_id]
            
            # Remove from agent connections if applicable
            if connection.connection_type == ConnectionType.AGENT:
                agent_id = int(connection.user_id)
                self.agent_connections.pop(agent_id, None)
            
            connection.is_active = False
            
            logger.info(f"Connection disconnected: {connection_id}")
    
    async def send_to_conversation(self, conversation_id: str, message: WebSocketMessage, 
                                 exclude_connection: str = None):
        """Send message to all connections in a conversation"""
        async with self._lock:
            connection_ids = self.connections_by_conversation.get(conversation_id, set()).copy()
        
        if exclude_connection:
            connection_ids.discard(exclude_connection)
        
        # Send to all connections
        for conn_id in connection_ids:
            connection = self.connections.get(conn_id)
            if connection and connection.is_active:
                try:
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"Error sending to conversation {conversation_id}: {str(e)}")
                    await self.disconnect(conn_id)
    
    async def send_to_agent(self, agent_id: int, message: WebSocketMessage):
        """Send message directly to an agent"""
        connection_id = self.agent_connections.get(agent_id)
        if connection_id:
            connection = self.connections.get(connection_id)
            if connection and connection.is_active:
                try:
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"Error sending to agent {agent_id}: {str(e)}")
                    await self.disconnect(connection_id)
    
    async def send_to_customer(self, customer_id: str, tenant_id: int, message: WebSocketMessage):
        """Send message to a specific customer"""
        user_key = f"{ConnectionType.CUSTOMER}_{customer_id}"
        connection_ids = self.connections_by_user.get(user_key, set()).copy()
        
        for conn_id in connection_ids:
            connection = self.connections.get(conn_id)
            if connection and connection.is_active and connection.tenant_id == tenant_id:
                try:
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"Error sending to customer {customer_id}: {str(e)}")
                    await self.disconnect(conn_id)
    
    async def broadcast_to_tenant_agents(self, tenant_id: int, message: WebSocketMessage, 
                                       exclude_agent: int = None):
        """Broadcast message to all agents of a tenant"""
        async with self._lock:
            connection_ids = self.connections_by_tenant.get(tenant_id, set()).copy()
        
        for conn_id in connection_ids:
            connection = self.connections.get(conn_id)
            if (connection and connection.is_active and 
                connection.connection_type == ConnectionType.AGENT and
                (exclude_agent is None or int(connection.user_id) != exclude_agent)):
                try:
                    await connection.send_message(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to tenant {tenant_id}: {str(e)}")
                    await self.disconnect(conn_id)
    
    async def add_connection_to_conversation(self, connection_id: str, conversation_id: str):
        """Add a connection to a conversation"""
        async with self._lock:
            connection = self.connections.get(connection_id)
            if connection:
                connection.conversation_ids.add(conversation_id)
                
                # Update conversation index
                if conversation_id not in self.connections_by_conversation:
                    self.connections_by_conversation[conversation_id] = set()
                self.connections_by_conversation[conversation_id].add(connection_id)
    
    async def remove_connection_from_conversation(self, connection_id: str, conversation_id: str):
        """Remove a connection from a conversation"""
        async with self._lock:
            connection = self.connections.get(connection_id)
            if connection:
                connection.conversation_ids.discard(conversation_id)
                
                # Update conversation index
                if conversation_id in self.connections_by_conversation:
                    self.connections_by_conversation[conversation_id].discard(connection_id)
                    if not self.connections_by_conversation[conversation_id]:
                        del self.connections_by_conversation[conversation_id]
    
    def get_connection_stats(self, tenant_id: int = None) -> Dict:
        """Get connection statistics"""
        stats = {
            "total_connections": len(self.connections),
            "active_connections": sum(1 for conn in self.connections.values() if conn.is_active),
            "customer_connections": 0,
            "agent_connections": 0,
            "conversations_with_connections": len(self.connections_by_conversation)
        }
        
        # Count by type
        for connection in self.connections.values():
            if not connection.is_active:
                continue
                
            if tenant_id and connection.tenant_id != tenant_id:
                continue
                
            if connection.connection_type == ConnectionType.CUSTOMER:
                stats["customer_connections"] += 1
            elif connection.connection_type == ConnectionType.AGENT:
                stats["agent_connections"] += 1
        
        if tenant_id:
            stats["tenant_id"] = tenant_id
            stats["tenant_connections"] = len(self.connections_by_tenant.get(tenant_id, set()))
        
        return stats
    
    async def cleanup_inactive_connections(self):
        """Clean up inactive connections"""
        inactive_connections = []
        
        async with self._lock:
            for conn_id, connection in self.connections.items():
                if not connection.is_active:
                    inactive_connections.append(conn_id)
        
        for conn_id in inactive_connections:
            await self.disconnect(conn_id)
        
        logger.info(f"Cleaned up {len(inactive_connections)} inactive connections")


class LiveChatMessageHandler:
    """Handles incoming WebSocket messages for live chat"""
    
    def __init__(self, db: Session, websocket_manager: LiveChatWebSocketManager):
        self.db = db
        self.websocket_manager = websocket_manager
        self.queue_service = LiveChatQueueService(db)
    
    async def handle_message(self, connection_id: str, message_data: dict):
        """Handle incoming WebSocket message - UPDATED VERSION"""
        try:
            message_type = message_data.get("type")
            data = message_data.get("data", {})
            
            # Route message based on type
            if message_type == "chat_message":
                await self._handle_chat_message(connection_id, data)
            elif message_type == "typing_start":
                await self._handle_typing_indicator(connection_id, data, True)
            elif message_type == "typing_stop":
                await self._handle_typing_indicator(connection_id, data, False)
            elif message_type == "agent_join_conversation":
                await self._handle_agent_join(connection_id, data)
            elif message_type == "agent_leave_conversation":
                await self._handle_agent_leave(connection_id, data)
            elif message_type == "close_conversation":
                await self._handle_close_conversation(connection_id, data)
            elif message_type == "transfer_conversation":
                await self._handle_transfer_conversation(connection_id, data)
            elif message_type == "get_conversation_history":
                await self._handle_get_history(connection_id, data)
            elif message_type == "ping":
                await self._handle_ping(connection_id)
            
            # ✨ ADD THESE NEW TRANSCRIPT MESSAGE TYPES:
            elif message_type == "send_full_transcript":
                await self._handle_send_full_transcript(connection_id, data)
            elif message_type == "send_selected_messages":
                await self._handle_send_selected_messages(connection_id, data)
            elif message_type == "get_transcript_preview":
                await self._handle_get_transcript_preview(connection_id, data)
            elif message_type == "get_message_selection":
                await self._handle_get_message_selection(connection_id, data)
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                await self._send_error(connection_id, f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling message from {connection_id}: {str(e)}")
            await self._send_error(connection_id, str(e))
    
    async def _handle_chat_message(self, connection_id: str, data: dict):
        """Handle a chat message from customer or agent"""
        try:
            conversation_id = data.get("conversation_id")
            content = data.get("content", "").strip()
            
            if not conversation_id or not content:
                await self._send_error(connection_id, "Missing conversation_id or content")
                return
            
            # Get connection details
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection:
                await self._send_error(connection_id, "Connection not found")
                return
            
            # Get conversation
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                await self._send_error(connection_id, "Conversation not found")
                return
            
            # Determine sender details
            if connection.connection_type == ConnectionType.CUSTOMER:
                sender_type = SenderType.CUSTOMER
                sender_id = connection.user_id
                sender_name = data.get("sender_name", "Customer")
                agent_id = None
            else:  # Agent
                sender_type = SenderType.AGENT
                agent_id = int(connection.user_id)
                sender_id = str(agent_id)
                
                # Get agent details
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                sender_name = agent.display_name if agent else "Agent"
            
            # Create message record
            message = LiveChatMessage(
                conversation_id=conversation_id,
                content=content,
                message_type=MessageType.TEXT,
                sender_type=sender_type,
                sender_id=sender_id,
                agent_id=agent_id,
                sender_name=sender_name
            )
            
            self.db.add(message)
            
            # Update conversation
            conversation.last_activity_at = datetime.utcnow()
            conversation.message_count += 1
            
            if sender_type == SenderType.AGENT:
                conversation.agent_message_count += 1
                # Mark as active if agent's first message
                if conversation.status == ConversationStatus.ASSIGNED:
                    conversation.status = ConversationStatus.ACTIVE
                    conversation.first_response_at = datetime.utcnow()
                    
                    # Calculate response time
                    if conversation.queue_entry_time:
                        response_seconds = (datetime.utcnow() - conversation.queue_entry_time).total_seconds()
                        conversation.response_time_seconds = int(response_seconds)
            else:
                conversation.customer_message_count += 1
            
            self.db.commit()
            self.db.refresh(message)
            
            # Broadcast message to conversation participants
            message_data = {
                "message_id": message.id,
                "conversation_id": conversation_id,
                "content": content,
                "sender_type": sender_type,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "sent_at": message.sent_at.isoformat(),
                "message_type": MessageType.TEXT
            }
            
            broadcast_msg = WebSocketMessage(
                message_type="new_message",
                data=message_data,
                conversation_id=conversation_id
            )
            
            await self.websocket_manager.send_to_conversation(
                conversation_id, broadcast_msg, exclude_connection=connection_id
            )
            
            # Send confirmation to sender
            confirmation = WebSocketMessage(
                message_type="message_sent",
                data={
                    "message_id": message.id,
                    "conversation_id": conversation_id,
                    "status": "delivered"
                }
            )
            
            await connection.send_message(confirmation)
            
            logger.info(f"Message sent in conversation {conversation_id} by {sender_type}")
            
        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}")
            self.db.rollback()
            await self._send_error(connection_id, "Failed to send message")
    
    async def _handle_typing_indicator(self, connection_id: str, data: dict, is_typing: bool):
        """Handle typing indicator"""
        try:
            conversation_id = data.get("conversation_id")
            if not conversation_id:
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection:
                return
            
            # Broadcast typing indicator to other participants
            typing_data = {
                "conversation_id": conversation_id,
                "user_id": connection.user_id,
                "user_type": connection.connection_type,
                "is_typing": is_typing
            }
            
            typing_msg = WebSocketMessage(
                message_type="typing_indicator",
                data=typing_data,
                conversation_id=conversation_id
            )
            
            await self.websocket_manager.send_to_conversation(
                conversation_id, typing_msg, exclude_connection=connection_id
            )
            
        except Exception as e:
            logger.error(f"Error handling typing indicator: {str(e)}")
    
    async def _handle_agent_join(self, connection_id: str, data: dict):
        """Handle agent joining a conversation"""
        try:
            conversation_id = data.get("conversation_id")
            if not conversation_id:
                await self._send_error(connection_id, "Missing conversation_id")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection or connection.connection_type != ConnectionType.AGENT:
                await self._send_error(connection_id, "Invalid agent connection")
                return
            
            agent_id = int(connection.user_id)
            
            # Get agent and conversation
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not agent or not conversation:
                await self._send_error(connection_id, "Agent or conversation not found")
                return
            
            # Add connection to conversation
            await self.websocket_manager.add_connection_to_conversation(connection_id, conversation_id)
            
            # Send system message about agent joining
            join_message = LiveChatMessage(
                conversation_id=conversation_id,
                content=f"{agent.display_name} has joined the chat",
                message_type=MessageType.SYSTEM,
                sender_type=SenderType.SYSTEM,
                system_event_type="agent_join",
                system_event_data=json.dumps({
                    "agent_id": agent_id,
                    "agent_name": agent.display_name
                })
            )
            
            self.db.add(join_message)
            self.db.commit()
            
            # Broadcast join notification
            join_data = {
                "conversation_id": conversation_id,
                "agent_id": agent_id,
                "agent_name": agent.display_name,
                "message": f"{agent.display_name} has joined the chat"
            }
            
            join_notification = WebSocketMessage(
                message_type="agent_joined",
                data=join_data,
                conversation_id=conversation_id
            )
            
            await self.websocket_manager.send_to_conversation(conversation_id, join_notification)
            
            logger.info(f"Agent {agent_id} joined conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error handling agent join: {str(e)}")
            await self._send_error(connection_id, "Failed to join conversation")
    
    async def _handle_close_conversation(self, connection_id: str, data: dict):
        """Handle closing a conversation"""
        try:
            conversation_id = data.get("conversation_id")
            closure_reason = data.get("reason", "completed")
            agent_notes = data.get("notes", "")
            
            if not conversation_id:
                await self._send_error(connection_id, "Missing conversation_id")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection:
                return
            
            # Get conversation
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                await self._send_error(connection_id, "Conversation not found")
                return
            
            # Close conversation
            conversation.status = ConversationStatus.CLOSED
            conversation.closed_at = datetime.utcnow()
            conversation.closed_by = connection.connection_type
            conversation.closure_reason = closure_reason
            
            if agent_notes:
                conversation.agent_notes = agent_notes
            
            # Calculate duration
            if conversation.assigned_at:
                duration = (datetime.utcnow() - conversation.assigned_at).total_seconds()
                conversation.conversation_duration_seconds = int(duration)
            
            # Update agent session
            if conversation.assigned_agent_id:
                from app.live_chat.models import AgentSession
                agent_session = self.db.query(AgentSession).filter(
                    AgentSession.agent_id == conversation.assigned_agent_id,
                    AgentSession.logout_at.is_(None)
                ).first()
                
                if agent_session:
                    agent_session.active_conversations = max(0, agent_session.active_conversations - 1)
            
            self.db.commit()
            
            # Notify all participants
            close_data = {
                "conversation_id": conversation_id,
                "closed_by": connection.connection_type,
                "reason": closure_reason,
                "closed_at": conversation.closed_at.isoformat()
            }
            
            close_notification = WebSocketMessage(
                message_type="conversation_closed",
                data=close_data,
                conversation_id=conversation_id
            )
            
            await self.websocket_manager.send_to_conversation(conversation_id, close_notification)
            
            logger.info(f"Conversation {conversation_id} closed by {connection.connection_type}")
            
        except Exception as e:
            logger.error(f"Error closing conversation: {str(e)}")
            self.db.rollback()
            await self._send_error(connection_id, "Failed to close conversation")
    
    async def _handle_get_history(self, connection_id: str, data: dict):
        """Handle request for conversation history"""
        try:
            conversation_id = data.get("conversation_id")
            limit = data.get("limit", 50)
            
            if not conversation_id:
                await self._send_error(connection_id, "Missing conversation_id")
                return
            
            # Get messages
            messages = self.db.query(LiveChatMessage).filter(
                LiveChatMessage.conversation_id == conversation_id
            ).order_by(LiveChatMessage.sent_at.desc()).limit(limit).all()
            
            # Format messages
            message_list = []
            for msg in reversed(messages):  # Reverse to get chronological order
                message_list.append({
                    "message_id": msg.id,
                    "content": msg.content,
                    "sender_type": msg.sender_type,
                    "sender_name": msg.sender_name,
                    "sent_at": msg.sent_at.isoformat(),
                    "message_type": msg.message_type,
                    "is_internal": msg.is_internal
                })
            
            # Send history
            connection = self.websocket_manager.connections.get(connection_id)
            if connection:
                history_msg = WebSocketMessage(
                    message_type="conversation_history",
                    data={
                        "conversation_id": conversation_id,
                        "messages": message_list,
                        "total_count": len(message_list)
                    }
                )
                await connection.send_message(history_msg)
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {str(e)}")
            await self._send_error(connection_id, "Failed to get history")
    
    async def _handle_ping(self, connection_id: str):
        """Handle ping message"""
        connection = self.websocket_manager.connections.get(connection_id)
        if connection:
            pong_msg = WebSocketMessage(
                message_type="pong",
                data={"timestamp": datetime.utcnow().isoformat()}
            )
            await connection.send_message(pong_msg)
    
    async def _send_error(self, connection_id: str, error_message: str):
        """Send error message to connection"""
        connection = self.websocket_manager.connections.get(connection_id)
        if connection:
            error_msg = WebSocketMessage(
                message_type="error",
                data={"message": error_message}
            )
            await connection.send_message(error_msg)




    async def _handle_send_full_transcript(self, connection_id: str, data: dict):
        """Handle request to send full conversation transcript"""
        try:
            conversation_id = data.get("conversation_id")
            recipient_email = data.get("recipient_email")
            
            if not conversation_id or not recipient_email:
                await self._send_error(connection_id, "Missing conversation_id or recipient_email")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection or connection.connection_type != ConnectionType.AGENT:
                await self._send_error(connection_id, "Invalid agent connection")
                return
            
            agent_id = int(connection.user_id)
            
            # Verify agent has access to conversation
            from app.live_chat.models import LiveChatConversation, Agent
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id,
                LiveChatConversation.tenant_id == connection.tenant_id
            ).first()
            
            if not conversation:
                await self._send_error(connection_id, "Conversation not found or access denied")
                return
            
            # Send status update
            await self._send_transcript_status(connection_id, "processing", "Generating transcript...")
            
            # Initialize transcript service
            transcript_service = EmailTranscriptService(self.db)
            
            # Send transcript
            result = await transcript_service.send_conversation_transcript(
                conversation_id=conversation_id,
                agent_id=agent_id,
                recipient_email=recipient_email,
                subject=data.get("subject"),
                include_agent_notes=data.get("include_agent_notes", True),
                include_system_messages=data.get("include_system_messages", False)
            )
            
            # Send result back to agent
            response_data = {
                "conversation_id": conversation_id,
                "recipient_email": recipient_email,
                "transcript_type": "full"
            }
            
            if result["success"]:
                response_data.update({
                    "success": True,
                    "message": result["message"],
                    "email_id": result.get("email_id"),
                    "message_count": result.get("message_count"),
                    "sent_at": result.get("sent_at")
                })
            else:
                response_data.update({
                    "success": False,
                    "error": result["error"]
                })
            
            response_msg = WebSocketMessage(
                message_type="transcript_sent",
                data=response_data,
                conversation_id=str(conversation_id)
            )
            
            await connection.send_message(response_msg)
            
            logger.info(f"Full transcript processed for agent {agent_id}")
            
        except Exception as e:
            logger.error(f"Error sending full transcript: {str(e)}")
            await self._send_error(connection_id, "Failed to send transcript")

    async def _handle_send_selected_messages(self, connection_id: str, data: dict):
        """Handle request to send selected messages"""
        try:
            conversation_id = data.get("conversation_id")
            message_ids = data.get("message_ids", [])
            recipient_email = data.get("recipient_email")
            
            if not conversation_id or not message_ids or not recipient_email:
                await self._send_error(connection_id, "Missing required fields")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection or connection.connection_type != ConnectionType.AGENT:
                await self._send_error(connection_id, "Invalid agent connection")
                return
            
            agent_id = int(connection.user_id)
            
            # Send status update
            await self._send_transcript_status(connection_id, "processing", f"Sending {len(message_ids)} selected messages...")
            
            # Initialize transcript service
            transcript_service = EmailTranscriptService(self.db)
            
            # Send selected messages
            result = await transcript_service.send_selected_messages(
                conversation_id=conversation_id,
                agent_id=agent_id,
                message_ids=message_ids,
                recipient_email=recipient_email,
                subject=data.get("subject"),
                additional_notes=data.get("additional_notes")
            )
            
            # Send result back to agent
            response_data = {
                "conversation_id": conversation_id,
                "recipient_email": recipient_email,
                "transcript_type": "selected_messages",
                "selected_count": len(message_ids)
            }
            
            if result["success"]:
                response_data.update({
                    "success": True,
                    "message": result["message"],
                    "email_id": result.get("email_id"),
                    "message_count": result.get("message_count")
                })
            else:
                response_data.update({
                    "success": False,
                    "error": result["error"]
                })
            
            response_msg = WebSocketMessage(
                message_type="transcript_sent",
                data=response_data,
                conversation_id=str(conversation_id)
            )
            
            await connection.send_message(response_msg)
            
            logger.info(f"Selected messages processed for agent {agent_id}")
            
        except Exception as e:
            logger.error(f"Error sending selected messages: {str(e)}")
            await self._send_error(connection_id, "Failed to send selected messages")

    async def _handle_get_transcript_preview(self, connection_id: str, data: dict):
        """Handle request for transcript preview"""
        try:
            conversation_id = data.get("conversation_id")
            include_agent_notes = data.get("include_agent_notes", True)
            include_system_messages = data.get("include_system_messages", False)
            
            if not conversation_id:
                await self._send_error(connection_id, "Missing conversation_id")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection or connection.connection_type != ConnectionType.AGENT:
                await self._send_error(connection_id, "Invalid agent connection")
                return
            
            agent_id = int(connection.user_id)
            
            # Get conversation and verify access
            from app.live_chat.models import LiveChatConversation
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id,
                LiveChatConversation.tenant_id == connection.tenant_id
            ).first()
            
            if not conversation:
                await self._send_error(connection_id, "Access denied or conversation not found")
                return
            
            # Initialize transcript service
            transcript_service = EmailTranscriptService(self.db)
            
            # Get formatted messages
            messages = await transcript_service._get_formatted_messages(
                conversation_id, 
                include_system_messages
            )
            
            # Generate preview data
            preview_data = {
                "conversation_id": conversation_id,
                "message_count": len(messages),
                "participants": list(set(msg["sender_name"] for msg in messages if msg["sender_name"])),
                "date_range": {
                    "start": messages[0]["sent_at"].isoformat() if messages else None,
                    "end": messages[-1]["sent_at"].isoformat() if messages else None
                },
                "estimated_size": sum(len(msg["content"]) for msg in messages if msg["content"]),
                "includes_attachments": any(msg.get("attachment_url") for msg in messages),
                "includes_agent_notes": include_agent_notes and bool(conversation.agent_notes),
                "includes_system_messages": include_system_messages,
                "sample_messages": messages[:3] if messages else []
            }
            
            response_msg = WebSocketMessage(
                message_type="transcript_preview",
                data={
                    "success": True,
                    "preview": preview_data
                },
                conversation_id=str(conversation_id)
            )
            
            await connection.send_message(response_msg)
            
        except Exception as e:
            logger.error(f"Error getting transcript preview: {str(e)}")
            await self._send_error(connection_id, "Failed to get transcript preview")

    async def _handle_get_message_selection(self, connection_id: str, data: dict):
        """Handle request for message selection interface data"""
        try:
            conversation_id = data.get("conversation_id")
            filters = data.get("filters", {})
            
            if not conversation_id:
                await self._send_error(connection_id, "Missing conversation_id")
                return
            
            connection = self.websocket_manager.connections.get(connection_id)
            if not connection or connection.connection_type != ConnectionType.AGENT:
                await self._send_error(connection_id, "Invalid agent connection")
                return
            
            # Get messages with filters
            from app.live_chat.models import LiveChatMessage, SenderType, LiveChatConversation
            from sqlalchemy import and_
            
            # Verify access
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id,
                LiveChatConversation.tenant_id == connection.tenant_id
            ).first()
            
            if not conversation:
                await self._send_error(connection_id, "Access denied")
                return
            
            # Build query
            query = self.db.query(LiveChatMessage).filter(
                LiveChatMessage.conversation_id == conversation_id
            )
            
            # Apply filters
            sender_type = filters.get("sender_type")
            if sender_type:
                query = query.filter(LiveChatMessage.sender_type == sender_type)
            
            include_system = filters.get("include_system", False)
            if not include_system:
                query = query.filter(LiveChatMessage.sender_type != SenderType.SYSTEM)
            
            # Get messages
            messages = query.order_by(LiveChatMessage.sent_at.asc()).limit(200).all()
            
            # Format for selection interface
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "message_id": msg.id,
                    "content": msg.content,
                    "sender_type": msg.sender_type,
                    "sender_name": msg.sender_name or ("Agent" if msg.sender_type == SenderType.AGENT else "Customer"),
                    "sent_at": msg.sent_at.isoformat(),
                    "message_type": msg.message_type,
                    "is_internal": msg.is_internal,
                    "has_attachment": bool(msg.attachment_url),
                    "attachment_name": msg.attachment_name,
                    "character_count": len(msg.content) if msg.content else 0,
                    "preview": msg.content[:100] + "..." if msg.content and len(msg.content) > 100 else msg.content
                })
            
            response_msg = WebSocketMessage(
                message_type="message_selection_data",
                data={
                    "success": True,
                    "conversation_id": conversation_id,
                    "messages": formatted_messages,
                    "total_count": len(formatted_messages),
                    "filters_applied": filters
                },
                conversation_id=str(conversation_id)
            )
            
            await connection.send_message(response_msg)
            
        except Exception as e:
            logger.error(f"Error getting message selection data: {str(e)}")
            await self._send_error(connection_id, "Failed to get message selection data")

    async def _send_transcript_status(self, connection_id: str, status: str, message: str):
        """Send transcript status update to connection"""
        connection = self.websocket_manager.connections.get(connection_id)
        if connection:
            status_msg = WebSocketMessage(
                message_type="transcript_status",
                data={
                    "status": status,
                    "message": message
                }
            )
            await connection.send_message(status_msg)




# Global WebSocket manager instance
websocket_manager = LiveChatWebSocketManager()