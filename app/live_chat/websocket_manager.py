# app/live_chat/websocket_manager.py
import json
import asyncio
import logging
from typing import Dict, List, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections for live chat"""
    
    def __init__(self):
        # Store active connections: {tenant_id: {connection_type: {connection_id: websocket}}}
        self.active_connections: Dict[int, Dict[str, Dict[str, WebSocket]]] = {}
        
        # Map chat sessions to connections
        self.chat_connections: Dict[str, Dict[str, WebSocket]] = {}  # {session_id: {user/agent: websocket}}
        
        # Agent connections: {agent_id: websocket}
        self.agent_connections: Dict[int, WebSocket] = {}
        
        # User connections: {user_identifier: websocket}
        self.user_connections: Dict[str, WebSocket] = {}
    
    async def connect_user(self, websocket: WebSocket, tenant_id: int, 
                          user_identifier: str, chat_session_id: str = None):
        """Connect a user to the live chat system"""
        await websocket.accept()
        
        # Initialize tenant connections if not exists
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = {"users": {}, "agents": {}}
        
        # Store user connection
        self.active_connections[tenant_id]["users"][user_identifier] = websocket
        self.user_connections[user_identifier] = websocket
        
        # If chat session provided, map it
        if chat_session_id:
            if chat_session_id not in self.chat_connections:
                self.chat_connections[chat_session_id] = {}
            self.chat_connections[chat_session_id]["user"] = websocket
        
        logger.info(f"User {user_identifier} connected to tenant {tenant_id}")
        
        # Send connection confirmation
        await self.send_personal_message({
            "type": "connection_established",
            "user_identifier": user_identifier,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
    
    async def connect_agent(self, websocket: WebSocket, tenant_id: int, 
                           agent_id: int, agent_name: str):
        """Connect an agent to the live chat system"""
        await websocket.accept()
        
        # Initialize tenant connections if not exists
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = {"users": {}, "agents": {}}
        
        # Store agent connection
        self.active_connections[tenant_id]["agents"][agent_id] = websocket
        self.agent_connections[agent_id] = websocket
        
        logger.info(f"Agent {agent_name} (ID: {agent_id}) connected to tenant {tenant_id}")
        
        # Send connection confirmation
        await self.send_personal_message({
            "type": "agent_connected",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        
        # Notify other agents that this agent is online
        await self.broadcast_to_agents(tenant_id, {
            "type": "agent_status_update",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "status": "online",
            "timestamp": datetime.utcnow().isoformat()
        }, exclude_agent=agent_id)
    
    def disconnect_user(self, tenant_id: int, user_identifier: str, chat_session_id: str = None):
        """Disconnect a user"""
        # Remove from tenant connections
        if tenant_id in self.active_connections and user_identifier in self.active_connections[tenant_id]["users"]:
            del self.active_connections[tenant_id]["users"][user_identifier]
        
        # Remove from user connections
        if user_identifier in self.user_connections:
            del self.user_connections[user_identifier]
        
        # Remove from chat connections
        if chat_session_id and chat_session_id in self.chat_connections:
            if "user" in self.chat_connections[chat_session_id]:
                del self.chat_connections[chat_session_id]["user"]
            
            # Clean up empty chat session
            if not self.chat_connections[chat_session_id]:
                del self.chat_connections[chat_session_id]
        
        logger.info(f"User {user_identifier} disconnected from tenant {tenant_id}")
    
    def disconnect_agent(self, tenant_id: int, agent_id: int):
        """Disconnect an agent"""
        # Remove from tenant connections
        if tenant_id in self.active_connections and agent_id in self.active_connections[tenant_id]["agents"]:
            del self.active_connections[tenant_id]["agents"][agent_id]
        
        # Remove from agent connections
        if agent_id in self.agent_connections:
            del self.agent_connections[agent_id]
        
        logger.info(f"Agent {agent_id} disconnected from tenant {tenant_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to a specific websocket connection"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def send_message_to_user(self, user_identifier: str, message: dict):
        """Send message to a specific user"""
        if user_identifier in self.user_connections:
            await self.send_personal_message(message, self.user_connections[user_identifier])
    
    async def send_message_to_agent(self, agent_id: int, message: dict):
        """Send message to a specific agent"""
        if agent_id in self.agent_connections:
            await self.send_personal_message(message, self.agent_connections[agent_id])
    
    async def broadcast_to_chat(self, chat_session_id: str, message: dict, exclude_sender: str = None):
        """Broadcast message to all participants in a chat"""
        if chat_session_id not in self.chat_connections:
            return
        
        tasks = []
        for participant_type, websocket in self.chat_connections[chat_session_id].items():
            if exclude_sender and participant_type == exclude_sender:
                continue
            tasks.append(self.send_personal_message(message, websocket))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_to_agents(self, tenant_id: int, message: dict, exclude_agent: int = None):
        """Broadcast message to all agents of a tenant"""
        if tenant_id not in self.active_connections:
            return
        
        tasks = []
        for agent_id, websocket in self.active_connections[tenant_id]["agents"].items():
            if exclude_agent and agent_id == exclude_agent:
                continue
            tasks.append(self.send_personal_message(message, websocket))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def notify_new_chat(self, tenant_id: int, chat_data: dict):
        """Notify all available agents about a new chat in queue"""
        await self.broadcast_to_agents(tenant_id, {
            "type": "new_chat_in_queue",
            "chat": chat_data,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def notify_chat_assigned(self, chat_session_id: str, agent_id: int, agent_name: str):
        """Notify user that an agent has been assigned"""
        if chat_session_id in self.chat_connections and "user" in self.chat_connections[chat_session_id]:
            await self.send_personal_message({
                "type": "agent_assigned",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "chat_session_id": chat_session_id,
                "timestamp": datetime.utcnow().isoformat()
            }, self.chat_connections[chat_session_id]["user"])
    
    async def notify_agent_chat_assigned(self, agent_id: int, chat_data: dict):
        """Notify agent that they've been assigned to a chat"""
        await self.send_message_to_agent(agent_id, {
            "type": "chat_assigned",
            "chat": chat_data,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def add_agent_to_chat(self, chat_session_id: str, agent_id: int):
        """Add agent websocket to chat session"""
        if chat_session_id not in self.chat_connections:
            self.chat_connections[chat_session_id] = {}
        
        if agent_id in self.agent_connections:
            self.chat_connections[chat_session_id]["agent"] = self.agent_connections[agent_id]
    
    def get_active_connections_count(self, tenant_id: int) -> dict:
        """Get count of active connections for a tenant"""
        if tenant_id not in self.active_connections:
            return {"users": 0, "agents": 0}
        
        return {
            "users": len(self.active_connections[tenant_id]["users"]),
            "agents": len(self.active_connections[tenant_id]["agents"])
        }

# Global connection manager instance
connection_manager = ConnectionManager()

class LiveChatWebSocketHandler:
    """Handle WebSocket events for live chat"""
    
    def __init__(self, db_session, live_chat_manager):
        self.db = db_session
        self.chat_manager = live_chat_manager
    
    async def handle_user_message(self, websocket: WebSocket, data: dict):
        """Handle incoming message from user"""
        try:
            chat_session_id = data.get("chat_session_id")
            message_content = data.get("message", "")
            user_identifier = data.get("user_identifier")
            
            if not all([chat_session_id, message_content, user_identifier]):
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "Missing required fields"
                }, websocket)
                return
            
            # Get chat from database
            from app.live_chat.models import LiveChat
            chat = self.db.query(LiveChat).filter(
                LiveChat.session_id == chat_session_id
            ).first()
            
            if not chat:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "Chat session not found"
                }, websocket)
                return
            
            # Save message to database
            message = self.chat_manager.send_message(
                chat_id=chat.id,
                content=message_content,
                is_from_user=True
            )
            
            # Broadcast to chat participants
            await connection_manager.broadcast_to_chat(chat_session_id, {
                "type": "new_message",
                "message": {
                    "id": message.id,
                    "content": message.content,
                    "is_from_user": True,
                    "sender_name": chat.user_name or "User",
                    "timestamp": message.created_at.isoformat()
                },
                "chat_session_id": chat_session_id
            })
            
        except Exception as e:
            logger.error(f"Error handling user message: {e}")
            await connection_manager.send_personal_message({
                "type": "error",
                "message": "Failed to send message"
            }, websocket)
    
    async def handle_agent_message(self, websocket: WebSocket, data: dict):
        """Handle incoming message from agent"""
        try:
            chat_session_id = data.get("chat_session_id")
            message_content = data.get("message", "")
            agent_id = data.get("agent_id")
            is_internal = data.get("is_internal", False)
            
            if not all([chat_session_id, message_content, agent_id]):
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "Missing required fields"
                }, websocket)
                return
            
            # Get chat from database
            from app.live_chat.models import LiveChat
            chat = self.db.query(LiveChat).filter(
                LiveChat.session_id == chat_session_id
            ).first()
            
            if not chat or chat.agent_id != agent_id:
                await connection_manager.send_personal_message({
                    "type": "error",
                    "message": "Chat not found or agent not assigned"
                }, websocket)
                return
            
            # Save message to database
            message = self.chat_manager.send_message(
                chat_id=chat.id,
                content=message_content,
                is_from_user=False,
                agent_id=agent_id,
                is_internal=is_internal
            )
            
            # Broadcast to appropriate participants
            message_data = {
                "type": "new_message",
                "message": {
                    "id": message.id,
                    "content": message.content,
                    "is_from_user": False,
                    "sender_name": chat.agent.name,
                    "timestamp": message.created_at.isoformat(),
                    "is_internal": is_internal
                },
                "chat_session_id": chat_session_id
            }
            
            if is_internal:
                # Only send to other agents
                await connection_manager.broadcast_to_agents(chat.tenant_id, message_data)
            else:
                # Send to all chat participants
                await connection_manager.broadcast_to_chat(chat_session_id, message_data)
            
        except Exception as e:
            logger.error(f"Error handling agent message: {e}")
            await connection_manager.send_personal_message({
                "type": "error",
                "message": "Failed to send message"
            }, websocket)
    
    async def handle_typing_indicator(self, websocket: WebSocket, data: dict):
        """Handle typing indicators"""
        try:
            chat_session_id = data.get("chat_session_id")
            is_typing = data.get("is_typing", False)
            sender_type = data.get("sender_type")  # "user" or "agent"
            
            if not chat_session_id:
                return
            
            # Broadcast typing indicator to other participants
            await connection_manager.broadcast_to_chat(chat_session_id, {
                "type": "typing_indicator",
                "is_typing": is_typing,
                "sender_type": sender_type,
                "chat_session_id": chat_session_id,
                "timestamp": datetime.utcnow().isoformat()
            }, exclude_sender=sender_type)
            
        except Exception as e:
            logger.error(f"Error handling typing indicator: {e}")
    
    async def handle_agent_status_update(self, websocket: WebSocket, data: dict):
        """Handle agent status updates"""
        try:
            agent_id = data.get("agent_id")
            status = data.get("status")
            
            if not all([agent_id, status]):
                return
            
            # Update agent status in database
            from app.live_chat.models import AgentStatus
            self.chat_manager.update_agent_status(agent_id, AgentStatus(status))
            
            # Get agent's tenant to broadcast to other agents
            from app.live_chat.models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                await connection_manager.broadcast_to_agents(agent.tenant_id, {
                    "type": "agent_status_update",
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "status": status,
                    "timestamp": datetime.utcnow().isoformat()
                }, exclude_agent=agent_id)
            
        except Exception as e:
            logger.error(f"Error handling agent status update: {e}")
    
    async def handle_chat_assignment_request(self, websocket: WebSocket, data: dict):
        """Handle agent requesting to take a chat from queue"""
        try:
            agent_id = data.get("agent_id")
            chat_session_id = data.get("chat_session_id")
            
            if not all([agent_id, chat_session_id]):
                return
            
            # Get chat from database
            from app.live_chat.models import LiveChat, ChatStatus
            chat = self.db.query(LiveChat).filter(
                LiveChat.session_id == chat_session_id,
                LiveChat.status == ChatStatus.WAITING
            ).first()
            
            if not chat:
                await connection_manager.send_personal_message({
                    "type": "assignment_failed",
                    "message": "Chat no longer available"
                }, websocket)
                return
            
            # Try to assign agent
            from app.live_chat.models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            
            if not agent or agent.current_chat_count >= agent.max_concurrent_chats:
                await connection_manager.send_personal_message({
                    "type": "assignment_failed",
                    "message": "Agent not available"
                }, websocket)
                return
            
            # Assign agent to chat
            self.chat_manager._assign_agent_to_chat(chat, agent)
            
            # Add agent to chat websocket
            connection_manager.add_agent_to_chat(chat_session_id, agent_id)
            
            # Notify agent of successful assignment
            await connection_manager.notify_agent_chat_assigned(agent_id, {
                "session_id": chat.session_id,
                "user_identifier": chat.user_identifier,
                "user_name": chat.user_name,
                "platform": chat.platform,
                "subject": chat.subject,
                "handoff_reason": chat.handoff_reason
            })
            
            # Notify user that agent has joined
            await connection_manager.notify_chat_assigned(
                chat_session_id, agent_id, agent.name
            )
            
        except Exception as e:
            logger.error(f"Error handling chat assignment request: {e}")
            await connection_manager.send_personal_message({
                "type": "assignment_failed",
                "message": "Failed to assign chat"
            }, websocket)