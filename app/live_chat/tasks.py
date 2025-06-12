import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

# Import dependencies
from app.database import get_db
from app.live_chat.models import Conversation, ConversationStatus
from app.live_chat.router_service import LiveChatRouter
from app.live_chat.state_manager import ChatStateManager
from app.live_chat.config import get_redis_client

logger = logging.getLogger(__name__)

async def cleanup_abandoned_conversations():
    """Clean up conversations that have been abandoned"""
    db = next(get_db())
    
    try:
        # Create state manager instance
        try:
            redis_client = get_redis_client()
            state_manager = ChatStateManager(redis_client)
        except Exception as e:
            logger.warning(f"Redis not available for cleanup task: {e}")
            # Skip cleanup if Redis is not available
            return
        
        # Find conversations in queue for more than 30 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        
        abandoned = db.query(Conversation).filter(
            Conversation.status == ConversationStatus.QUEUED,
            Conversation.created_at < cutoff_time
        ).all()
        
        for conv in abandoned:
            conv.status = ConversationStatus.ABANDONED
            conv.resolved_at = datetime.utcnow()
            
            # Remove from Redis (if available)
            try:
                state_manager.remove_from_queue(conv.tenant_id, conv.session_id)
                state_manager.end_conversation_state(conv.session_id)
            except Exception as e:
                logger.warning(f"Could not update Redis state for abandoned conversation: {e}")
        
        if abandoned:
            db.commit()
            logger.info(f"Cleaned up {len(abandoned)} abandoned conversations")
            
    except Exception as e:
        logger.error(f"Error in cleanup task: {e}")
        db.rollback()
    finally:
        db.close()

async def process_queues():
    """Periodically process queues for agent assignment"""
    db = next(get_db())
    
    try:
        # Create state manager instance
        try:
            redis_client = get_redis_client()
            state_manager = ChatStateManager(redis_client)
        except Exception as e:
            logger.warning(f"Redis not available for queue processing: {e}")
            # Skip queue processing if Redis is not available
            return
        
        # Get all tenants with queued conversations
        tenants_with_queue = db.query(Conversation.tenant_id).filter(
            Conversation.status == ConversationStatus.QUEUED
        ).distinct().all()
        
        if tenants_with_queue:
            chat_router = LiveChatRouter(db, state_manager)
            
            for (tenant_id,) in tenants_with_queue:
                try:
                    chat_router.process_queue(tenant_id)
                except Exception as e:
                    logger.error(f"Error processing queue for tenant {tenant_id}: {e}")
            
    except Exception as e:
        logger.error(f"Error in queue processing: {e}")
    finally:
        db.close()