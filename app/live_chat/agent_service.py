from datetime import datetime
from sqlalchemy.orm import Session
from app.live_chat.models import Agent, AgentStatus
from app.live_chat.state_manager import ChatStateManager
import logging
import json
from typing import Dict, List


logger = logging.getLogger(__name__)

class AgentService:
    """Manage agent operations"""
    
    def __init__(self, db: Session, state_manager: ChatStateManager):
        self.db = db
        self.state = state_manager
    
    def agent_login(self, agent_id: int) -> bool:
        """Agent comes online"""
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        
        # Update database
        agent.status = AgentStatus.ONLINE
        agent.last_seen = datetime.utcnow()
        self.db.commit()
        
        # Update Redis
        self.state.set_agent_online(agent.tenant_id, agent_id, {
            "name": agent.name,
            "email": agent.email,
            "department": agent.department,
            "max_concurrent_chats": agent.max_concurrent_chats
        })
        
        logger.info(f"Agent {agent.name} ({agent_id}) came online")
        return True
    
    def agent_logout(self, agent_id: int) -> bool:
        """Agent goes offline"""
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        
        # Update database
        agent.status = AgentStatus.OFFLINE
        agent.last_seen = datetime.utcnow()
        self.db.commit()
        
        # Update Redis
        self.state.set_agent_offline(agent.tenant_id, agent_id)
        
        logger.info(f"Agent {agent.name} ({agent_id}) went offline")
        return True
    
    def get_agent_dashboard_data(self, agent_id: int) -> Dict:
        """Get data for agent dashboard"""
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return {"error": "Agent not found"}
        
        # Get active conversations from Redis
        state_key = f"agents:online:{agent.tenant_id}"
        agent_data = self.state.redis.hget(state_key, agent_id)
        
        active_conversations = []
        if agent_data:
            agent_info = json.loads(agent_data)
            conversation_ids = agent_info.get("active_conversations", [])
            
            for session_id in conversation_ids:
                conv_state = self.state.get_conversation_state(session_id)
                if conv_state:
                    active_conversations.append({
                        "session_id": session_id,
                        "customer_name": conv_state.get("customer_name", "Anonymous"),
                        "customer_id": conv_state.get("customer_id"),
                        "platform": conv_state.get("platform", "web"),
                        "started_at": conv_state.get("assigned_at"),
                        "last_activity": conv_state.get("last_activity")
                    })
        
        # Get queue for this agent's department
        available_in_queue = []
        queue_key = f"queue:{agent.tenant_id}"
        queued_sessions = self.state.redis.zrange(queue_key, 0, -1)
        
        for session_id in queued_sessions:
            session_id = session_id.decode()
            conv_state = self.state.get_conversation_state(session_id)
            if conv_state and conv_state.get("department") == agent.department:
                available_in_queue.append({
                    "session_id": session_id,
                    "customer_name": conv_state.get("customer_name", "Anonymous"),
                    "waiting_since": conv_state.get("created_at"),
                    "platform": conv_state.get("platform", "web")
                })
        
        return {
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "department": agent.department,
                "status": agent.status,
                "max_concurrent_chats": agent.max_concurrent_chats
            },
            "active_conversations": active_conversations,
            "available_in_queue": available_in_queue,
            "current_load": len(active_conversations),
            "can_take_more": len(active_conversations) < agent.max_concurrent_chats
        }