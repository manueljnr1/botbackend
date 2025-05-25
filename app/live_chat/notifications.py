import asyncio
import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from app.live_chat.models import Agent, AgentStatus
from app.live_chat.websocket_manager import connection_manager

logger = logging.getLogger(__name__)

class LiveChatNotificationService:
    """Service for sending notifications to agents about new chats"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def notify_available_agents(self, tenant_id: int, chat_data: Dict):
        """Notify all available agents about a new chat"""
        
        # Get available agents
        available_agents = self.db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_active == True,
            Agent.status.in_([AgentStatus.ONLINE, AgentStatus.AWAY]),
            Agent.current_chat_count < Agent.max_concurrent_chats
        ).all()
        
        if not available_agents:
            logger.warning(f"No available agents for tenant {tenant_id}")
            return
        
        # Send WebSocket notifications
        await connection_manager.notify_new_chat(tenant_id, chat_data)
        
        # Here you could also add:
        # - Email notifications
        # - SMS notifications  
        # - Push notifications
        # - Slack/Teams notifications
        
        logger.info(f"Notified {len(available_agents)} agents about new chat")
    
    async def send_agent_email_notification(self, agent: Agent, chat_data: Dict):
        """Send email notification to agent (implement based on your email service)"""
        # Example implementation:
        # from app.utils.email_service import email_service
        # 
        # email_service.send_email(
        #     to_email=agent.email,
        #     subject="New Customer Chat Available",
        #     html_content=f"""
        #     <h3>New Chat Request</h3>
        #     <p>A customer is waiting for assistance:</p>
        #     <ul>
        #         <li>User: {chat_data.get('user_name', 'Anonymous')}</li>
        #         <li>Platform: {chat_data.get('platform', 'Web')}</li>
        #         <li>Department: {chat_data.get('department', 'General')}</li>
        #     </ul>
        #     <p><a href="https://yourdomain.com/agent-dashboard">Login to Agent Dashboard</a></p>
        #     """
        # )
        pass
    
    async def notify_chat_timeout(self, chat_session_id: str, wait_time_minutes: int):
        """Notify when a chat has been waiting too long"""
        await connection_manager.broadcast_to_agents(
            tenant_id=1,  # You'd get this from the chat
            message={
                "type": "chat_timeout_warning",
                "chat_session_id": chat_session_id,
                "wait_time_minutes": wait_time_minutes,
                "priority": "high"
            }
        )