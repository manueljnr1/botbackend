from typing import Dict, List
from sqlalchemy.orm import Session
from app.live_chat.models import Agent, LiveChat, ChatStatus, AgentStatus

class LiveChatFrontendHelpers:
    """Helper functions for frontend integration"""
    
    @staticmethod
    def get_tenant_live_chat_config(tenant_id: int, db: Session) -> Dict:
        """Get live chat configuration for frontend"""
        
        # Count available agents
        available_agents = db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_active == True,
            Agent.status.in_([AgentStatus.ONLINE, AgentStatus.AWAY])
        ).count()
        
        # Count current queue
        queue_length = db.query(LiveChat).filter(
            LiveChat.tenant_id == tenant_id,
            LiveChat.status == ChatStatus.WAITING
        ).count()
        
        # Get departments
        departments = db.query(Agent.department).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_active == True
        ).distinct().all()
        
        department_list = [dept[0] for dept in departments if dept[0]]
        
        return {
            "enabled": available_agents > 0,
            "available_agents": available_agents,
            "queue_length": queue_length,
            "departments": department_list,
            "estimated_wait_time": max(1, queue_length * 3) if queue_length > 0 else 0  # Simple estimate
        }
    
    @staticmethod
    def format_chat_for_frontend(chat: LiveChat, include_agent_info: bool = True) -> Dict:
        """Format chat object for frontend consumption"""
        
        result = {
            "session_id": chat.session_id,
            "user_identifier": chat.user_identifier,
            "user_name": chat.user_name,
            "status": chat.status.value,
            "platform": chat.platform,
            "subject": chat.subject,
            "department": chat.department,
            "started_at": chat.started_at.isoformat() if chat.started_at else None,
            "ended_at": chat.ended_at.isoformat() if chat.ended_at else None,
            "queue_time": chat.queue_time,
            "resolution_time": chat.resolution_time,
            "customer_satisfaction": chat.customer_satisfaction
        }
        
        if include_agent_info and chat.agent:
            result["agent"] = {
                "id": chat.agent.id,
                "name": chat.agent.name,
                "department": chat.agent.department,
                "avatar_url": chat.agent.avatar_url
            }
        
        return result
    
    @staticmethod
    def get_handoff_triggers() -> List[str]:
        """Get list of phrases that trigger handoff to live chat"""
        return [
            "talk to human",
            "speak to agent", 
            "customer service",
            "live chat",
            "human support",
            "real person",
            "customer representative",
            "talk to someone",
            "speak to someone",
            "human agent",
            "live support",
            "customer care",
            "help desk",
            "support team",
            "not helpful",
            "doesn't understand",
            "frustrated",
            "can't help"
        ]