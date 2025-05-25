import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
from app.database import get_db
from app.live_chat.models import LiveChat, ChatStatus, Agent, AgentStatus
from app.live_chat.manager import LiveChatManager
# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def cleanup_abandoned_chats():
    """Clean up chats that have been abandoned"""
    db = next(get_db())
    
    try:
        # Find chats waiting for more than 30 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        
        abandoned_chats = db.query(LiveChat).filter(
            LiveChat.status == ChatStatus.WAITING,
            LiveChat.started_at < cutoff_time
        ).all()
        
        chat_manager = LiveChatManager(db)
        
        for chat in abandoned_chats:
            chat.status = ChatStatus.ABANDONED
            
            # Remove from queue
            from app.live_chat.models import ChatQueue
            queue_entry = db.query(ChatQueue).filter(ChatQueue.chat_id == chat.id).first()
            if queue_entry:
                db.delete(queue_entry)
        
        db.commit()
        
        if abandoned_chats:
            logger.info(f"Marked {len(abandoned_chats)} chats as abandoned")
            
    except Exception as e:
        logger.error(f"Error in cleanup_abandoned_chats: {e}")
        db.rollback()
    finally:
        db.close()

async def update_agent_status():
    """Update agent status based on activity"""
    db = next(get_db())
    
    try:
        # Mark agents as away if no activity for 10 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        
        inactive_agents = db.query(Agent).filter(
            Agent.status == AgentStatus.ONLINE,
            Agent.last_seen < cutoff_time
        ).all()
        
        for agent in inactive_agents:
            agent.status = AgentStatus.AWAY
        
        db.commit()
        
        if inactive_agents:
            logger.info(f"Marked {len(inactive_agents)} agents as away due to inactivity")
            
    except Exception as e:
        logger.error(f"Error in update_agent_status: {e}")
        db.rollback()
    finally:
        db.close()