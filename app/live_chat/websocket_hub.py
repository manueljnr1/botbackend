import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class WebSocketHub:
    """Centralized WebSocket management for live chat"""
    
    def __init__(self):
        # Store connections: {session_id: {role: websocket}}
        self.conversation_connections: Dict[str, Dict[str, WebSocket]] = {}
        
        # Agent connections: {agent_id: websocket}
        self.agent_connections: Dict[int, WebSocket] = {}
        
        # Customer connections: {customer_id: websocket}
        self.customer_connections: Dict[str, WebSocket] = {}
    
    async def connect_customer(self, websocket: WebSocket, customer_id: str, session_id: str = None):
        """Connect a customer"""
        await websocket.accept()
        
        self.customer_connections[customer_id] = websocket
        
        if session_id:
            if session_id not in self.conversation_connections:
                self.conversation_connections[session_id] = {}
            self.conversation_connections[session_id]["customer"] = websocket
        
        logger.info(f"Customer {customer_id} connected")
    
    async def connect_agent(self, websocket: WebSocket, agent_id: int):
        """Connect an agent"""
        await websocket.accept()
        
        self.agent_connections[agent_id] = websocket
        logger.info(f"Agent {agent_id} connected")
    
    def disconnect_customer(self, customer_id: str, session_id: str = None):
        """Disconnect a customer"""
        if customer_id in self.customer_connections:
            del self.customer_connections[customer_id]
        
        if session_id and session_id in self.conversation_connections:
            if "customer" in self.conversation_connections[session_id]:
                del self.conversation_connections[session_id]["customer"]
            
            # Clean up empty conversation
            if not self.conversation_connections[session_id]:
                del self.conversation_connections[session_id]
        
        logger.info(f"Customer {customer_id} disconnected")
    
    def disconnect_agent(self, agent_id: int):
        """Disconnect an agent"""
        if agent_id in self.agent_connections:
            del self.agent_connections[agent_id]
        
        # Remove from all conversations
        for session_id, connections in self.conversation_connections.items():
            if "agent" in connections and hasattr(connections["agent"], "agent_id"):
                if connections["agent"].agent_id == agent_id:
                    del connections["agent"]
        
        logger.info(f"Agent {agent_id} disconnected")
    
    def add_agent_to_conversation(self, session_id: str, agent_id: int):
        """Add agent to a conversation"""
        if session_id not in self.conversation_connections:
            self.conversation_connections[session_id] = {}
        
        if agent_id in self.agent_connections:
            agent_ws = self.agent_connections[agent_id]
            agent_ws.agent_id = agent_id  # Store agent_id on websocket
            self.conversation_connections[session_id]["agent"] = agent_ws
    
    async def send_to_websocket(self, websocket: WebSocket, message: dict):
        """Send message to specific websocket"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")
    
    async def broadcast_to_conversation(self, session_id: str, message: dict):
        """Broadcast message to all participants in a conversation"""
        if session_id not in self.conversation_connections:
            return
        
        tasks = []
        for role, websocket in self.conversation_connections[session_id].items():
            tasks.append(self.send_to_websocket(websocket, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def notify_agents_new_conversation(self, tenant_id: int, conversation_data: dict):
        """Notify all online agents about new conversation"""
        message = {
            "type": "new_conversation_available",
            "data": conversation_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all connected agents (you might want to filter by tenant)
        tasks = []
        for agent_id, websocket in self.agent_connections.items():
            tasks.append(self.send_to_websocket(websocket, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def notify_conversation_assigned(self, session_id: str, agent_id: int):
        """Notify participants that conversation has been assigned"""
        # Add agent to conversation
        self.add_agent_to_conversation(session_id, agent_id)
        
        # Notify customer
        message = {
            "type": "agent_assigned",
            "data": {
                "session_id": session_id,
                "agent_id": agent_id,
                "message": "An agent has joined the conversation"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_conversation(session_id, message)

# Global WebSocket hub
websocket_hub = WebSocketHub()

