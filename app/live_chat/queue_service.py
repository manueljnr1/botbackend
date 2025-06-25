# app/live_chat/queue_service.py - COMPLETE TIMEZONE FIX
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Dict, Optional
import json

from app.live_chat.models import (
    LiveChatConversation, ChatQueue, Agent, AgentSession, 
    ConversationStatus, AgentStatus, LiveChatSettings
)
from app.live_chat.agent_service import AgentSessionService

logger = logging.getLogger(__name__)


def utc_now():
    """Get current UTC time - ALWAYS NAIVE for database consistency"""
    return datetime.utcnow()

def ensure_naive_datetime(dt):
    """Ensure datetime is naive (no timezone) for database operations"""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        # Convert timezone-aware to naive UTC
        if dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=None)
    return dt

def safe_datetime_subtract(dt1, dt2):
    """Safely subtract two datetimes, ensuring both are naive"""
    if dt1 is None or dt2 is None:
        return timedelta(0)
    
    dt1_naive = ensure_naive_datetime(dt1)
    dt2_naive = ensure_naive_datetime(dt2)
    
    try:
        return dt1_naive - dt2_naive
    except Exception as e:
        logger.warning(f"Datetime subtraction error: {e}, using default timedelta")
        return timedelta(0)


class QueueAssignmentStrategy:
    """Different strategies for assigning conversations to agents"""
    
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    SKILLS_BASED = "skills_based"
    SPECIFIC_AGENT = "specific_agent"
    RANDOM = "random"


class LiveChatQueueService:
    def __init__(self, db: Session):
        self.db = db
        self.session_service = AgentSessionService(db)
    
    def add_to_queue(self, conversation_id: int, priority: int = 1, 
                    preferred_agent_id: int = None, assignment_criteria: Dict = None) -> Dict:
        """Add a conversation to the chat queue"""
        try:
            # Get conversation details
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
            
            # Check if already in queue
            existing_queue = self.db.query(ChatQueue).filter(
                ChatQueue.conversation_id == conversation_id
            ).first()
            
            if existing_queue:
                logger.warning(f"Conversation {conversation_id} already in queue")
                return self._get_queue_status(existing_queue)
            
            # Get next position in queue
            next_position = self._get_next_queue_position(conversation.tenant_id, priority)
            
            # Create queue entry - FIXED: Always use naive datetime
            queue_entry = ChatQueue(
                tenant_id=conversation.tenant_id,
                conversation_id=conversation_id,
                position=next_position,
                priority=priority,
                preferred_agent_id=preferred_agent_id,
                assignment_criteria=json.dumps(assignment_criteria) if assignment_criteria else None,
                customer_message_preview=self._get_customer_preview(conversation_id),
                queued_at=utc_now()  # Always naive
            )
            
            self.db.add(queue_entry)
            
            # Update conversation status - FIXED: Always use naive datetime
            conversation.status = ConversationStatus.QUEUED
            conversation.queue_position = next_position
            conversation.queue_entry_time = utc_now()  # Always naive
            
            self.db.commit()
            self.db.refresh(queue_entry)
            
            # Try immediate assignment if agents available
            assigned = self._try_immediate_assignment(queue_entry)
            
            logger.info(f"Conversation {conversation_id} added to queue at position {next_position}")
            
            return {
                "success": True,
                "queue_id": queue_entry.id,
                "position": next_position,
                "estimated_wait_time": self._calculate_wait_time(conversation.tenant_id, next_position),
                "immediately_assigned": assigned
            }
            
        except Exception as e:
            logger.error(f"Error adding to queue: {str(e)}")
            self.db.rollback()
            raise
    
    def assign_conversation(self, queue_id: int, agent_id: int, assignment_method: str = "auto") -> bool:
        """Assign a queued conversation to an agent - COMPLETE TIMEZONE FIX"""
        try:
            # Get queue entry
            queue_entry = self.db.query(ChatQueue).filter(
                ChatQueue.id == queue_id,
                ChatQueue.status == "waiting"
            ).first()
            
            if not queue_entry:
                logger.error(f"Queue entry {queue_id} not found or not waiting")
                return False
            
            # Get conversation
            conversation = queue_entry.conversation
            if not conversation:
                logger.error(f"Conversation not found for queue {queue_id}")
                return False
            
            # Verify agent availability
            agent_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == agent_id,
                AgentSession.logout_at.is_(None),
                AgentSession.active_conversations < AgentSession.max_concurrent_chats
            ).first()
            
            if not agent_session:
                logger.error(f"Agent {agent_id} not available for assignment")
                return False
            
            # FIXED: All datetime operations use naive datetimes
            now = utc_now()  # Always naive
            
            # Update conversation
            conversation.status = ConversationStatus.ASSIGNED
            conversation.assigned_agent_id = agent_id
            conversation.assigned_at = now
            conversation.assignment_method = assignment_method
            
            # FIXED: Calculate wait time safely
            if conversation.queue_entry_time:
                wait_delta = safe_datetime_subtract(now, conversation.queue_entry_time)
                conversation.wait_time_seconds = int(wait_delta.total_seconds())
            
            # Update queue entry
            queue_entry.status = "assigned"
            queue_entry.assigned_at = now
            
            # Update agent session
            agent_session.active_conversations += 1
            
            # Remove from queue position (update other positions)
            self._remove_from_queue_positions(queue_entry)
            
            self.db.commit()
            
            logger.info(f"Conversation {conversation.id} assigned to agent {agent_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error assigning conversation: {str(e)}")
            self.db.rollback()
            return False
    
    def get_queue_status(self, tenant_id: int) -> Dict:
        """Get current queue status for tenant - COMPLETE TIMEZONE FIX"""
        try:
            # Get waiting queue
            waiting_queue = self.db.query(ChatQueue).join(LiveChatConversation).filter(
                ChatQueue.tenant_id == tenant_id,
                ChatQueue.status == "waiting"
            ).order_by(ChatQueue.position.asc()).all()
            
            # Get available agents
            available_agents = self._get_available_agents(tenant_id)
            
            # Get settings
            settings = self.db.query(LiveChatSettings).filter(
                LiveChatSettings.tenant_id == tenant_id
            ).first()
            
            queue_data = []
            current_time = utc_now()  # Always naive
            
            for entry in waiting_queue:
                # FIXED: Safe datetime calculation
                try:
                    if entry.queued_at:
                        wait_delta = safe_datetime_subtract(current_time, entry.queued_at)
                        wait_minutes = int(wait_delta.total_seconds() / 60)
                    else:
                        wait_minutes = 0
                except Exception as e:
                    logger.warning(f"Wait time calculation error for queue entry {entry.id}: {str(e)}")
                    wait_minutes = 0
                
                queue_data.append({
                    "queue_id": entry.id,
                    "conversation_id": entry.conversation_id,
                    "position": entry.position,
                    "priority": entry.priority,
                    "customer_preview": entry.customer_message_preview,
                    "wait_time_minutes": wait_minutes,
                    "estimated_wait_time": self._calculate_wait_time(tenant_id, entry.position),
                    "queued_at": entry.queued_at.isoformat() if entry.queued_at else None
                })
            
            return {
                "tenant_id": tenant_id,
                "queue_length": len(waiting_queue),
                "available_agents": len(available_agents),
                "max_queue_size": settings.max_queue_size if settings else 50,
                "max_wait_time": settings.max_wait_time_minutes if settings else 30,
                "queue": queue_data,
                "agents": available_agents
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return {"error": str(e)}
    
    def _get_next_queue_position(self, tenant_id: int, priority: int) -> int:
        """Get the next available position in queue based on priority"""
        # Get current queue for tenant
        queue = self.db.query(ChatQueue).filter(
            ChatQueue.tenant_id == tenant_id,
            ChatQueue.status == "waiting"
        ).order_by(ChatQueue.priority.desc(), ChatQueue.position.asc()).all()
        
        if not queue:
            return 1
        
        # Find insertion position based on priority
        position = 1
        for entry in queue:
            if priority > entry.priority:
                # Higher priority, insert before this entry
                break
            position += 1
        
        # Update positions of entries that come after
        self.db.query(ChatQueue).filter(
            ChatQueue.tenant_id == tenant_id,
            ChatQueue.position >= position,
            ChatQueue.status == "waiting"
        ).update({ChatQueue.position: ChatQueue.position + 1})
        
        return position
    
    def _get_customer_preview(self, conversation_id: int) -> str:
        """Get a preview of the customer's first message"""
        from app.live_chat.models import LiveChatMessage
        
        first_message = self.db.query(LiveChatMessage).filter(
            LiveChatMessage.conversation_id == conversation_id,
            LiveChatMessage.sender_type == "customer"
        ).order_by(LiveChatMessage.sent_at.asc()).first()
        
        if first_message:
            content = first_message.content
            return content[:100] + "..." if len(content) > 100 else content
        
        return "Customer is waiting to chat"
    
    def _try_immediate_assignment(self, queue_entry: ChatQueue) -> bool:
        """Try to immediately assign conversation if agents available"""
        try:
            # Get available agents
            available_agents = self._get_available_agents(queue_entry.tenant_id)
            
            if not available_agents:
                return False
            
            # Select best agent based on assignment strategy
            selected_agent = self._select_agent(queue_entry, available_agents)
            
            if selected_agent:
                return self.assign_conversation(queue_entry.id, selected_agent["agent_id"])
            
            return False
            
        except Exception as e:
            logger.error(f"Error in immediate assignment: {str(e)}")
            return False
    
    def _get_available_agents(self, tenant_id: int) -> List[Dict]:
        """Get list of available agents for assignment"""
        try:
            # Query active agent sessions
            active_sessions = self.db.query(AgentSession).join(Agent).filter(
                Agent.tenant_id == tenant_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_online == True,
                AgentSession.logout_at.is_(None),
                AgentSession.status.in_([AgentStatus.ACTIVE, AgentStatus.BUSY]),
                AgentSession.is_accepting_chats == True,
                AgentSession.active_conversations < AgentSession.max_concurrent_chats
            ).all()
            
            available_agents = []
            for session in active_sessions:
                agent = session.agent
                available_agents.append({
                    "agent_id": agent.id,
                    "session_id": session.session_id,
                    "display_name": agent.display_name,
                    "active_conversations": session.active_conversations,
                    "max_concurrent_chats": session.max_concurrent_chats,
                    "average_response_time": agent.average_response_time or 0,
                    "total_conversations": agent.total_conversations,
                    "last_activity": session.last_activity
                })
            
            return available_agents
            
        except Exception as e:
            logger.error(f"Error getting available agents: {str(e)}")
            return []
    
    def _select_agent(self, queue_entry: ChatQueue, available_agents: List[Dict]) -> Optional[Dict]:
        """Select the best agent based on assignment strategy"""
        if not available_agents:
            return None
        
        # Get tenant settings for assignment method
        settings = self.db.query(LiveChatSettings).filter(
            LiveChatSettings.tenant_id == queue_entry.tenant_id
        ).first()
        
        assignment_method = settings.assignment_method if settings else QueueAssignmentStrategy.ROUND_ROBIN
        
        # Preferred agent check first
        if queue_entry.preferred_agent_id:
            preferred_agent = next(
                (agent for agent in available_agents if agent["agent_id"] == queue_entry.preferred_agent_id),
                None
            )
            if preferred_agent:
                return preferred_agent
        
        # Apply assignment strategy
        if assignment_method == QueueAssignmentStrategy.LEAST_BUSY:
            return min(available_agents, key=lambda x: x["active_conversations"])
        
        elif assignment_method == QueueAssignmentStrategy.ROUND_ROBIN:
            # Simple round-robin based on last assignment
            return self._round_robin_selection(queue_entry.tenant_id, available_agents)
        
        else:
            # Default to least busy
            return min(available_agents, key=lambda x: x["active_conversations"])
    
    def _round_robin_selection(self, tenant_id: int, available_agents: List[Dict]) -> Dict:
        """Round-robin agent selection"""
        # Get the last assigned agent
        last_assignment = self.db.query(LiveChatConversation).filter(
            LiveChatConversation.tenant_id == tenant_id,
            LiveChatConversation.assigned_agent_id.isnot(None)
        ).order_by(LiveChatConversation.assigned_at.desc()).first()
        
        if not last_assignment:
            return available_agents[0]
        
        # Find next agent in rotation
        agent_ids = [agent["agent_id"] for agent in available_agents]
        
        try:
            last_index = agent_ids.index(last_assignment.assigned_agent_id)
            next_index = (last_index + 1) % len(available_agents)
            return available_agents[next_index]
        except ValueError:
            # Last assigned agent not in available list
            return available_agents[0]
    
    def _remove_from_queue_positions(self, queue_entry: ChatQueue):
        """Remove from queue and update positions of remaining entries"""
        # Update positions of entries that come after
        self.db.query(ChatQueue).filter(
            ChatQueue.tenant_id == queue_entry.tenant_id,
            ChatQueue.position > queue_entry.position,
            ChatQueue.status == "waiting"
        ).update({ChatQueue.position: ChatQueue.position - 1})
    
    def _calculate_wait_time(self, tenant_id: int, position: int) -> int:
        """Calculate estimated wait time in minutes"""
        try:
            # Get available agents
            available_agents = len(self._get_available_agents(tenant_id))
            
            if available_agents == 0:
                return 30  # Default when no agents available
            
            # Simple calculation: assume 5 minutes per conversation ahead
            conversations_ahead = max(0, position - available_agents)
            estimated_minutes = conversations_ahead * 5
            
            return max(1, estimated_minutes)
            
        except Exception:
            return 15  # Default fallback
    
    def _get_queue_status(self, queue_entry: ChatQueue) -> Dict:
        """Get status for a specific queue entry"""
        return {
            "success": True,
            "queue_id": queue_entry.id,
            "position": queue_entry.position,
            "status": queue_entry.status,
            "estimated_wait_time": self._calculate_wait_time(queue_entry.tenant_id, queue_entry.position)
        }
    
    def abandon_conversation(self, conversation_id: int, reason: str = "customer_left") -> bool:
        """Remove conversation from queue (customer abandoned)"""
        try:
            # Find queue entry
            queue_entry = self.db.query(ChatQueue).filter(
                ChatQueue.conversation_id == conversation_id,
                ChatQueue.status == "waiting"
            ).first()
            
            if not queue_entry:
                return False
            
            # FIXED: Use naive datetime
            now = utc_now()
            
            # Update queue entry
            queue_entry.status = "abandoned"
            queue_entry.abandon_reason = reason
            queue_entry.removed_at = now
            
            # Update conversation
            conversation = queue_entry.conversation
            conversation.status = ConversationStatus.ABANDONED
            conversation.closed_at = now
            conversation.closed_by = "customer"
            conversation.closure_reason = reason
            
            # Remove from queue positions
            self._remove_from_queue_positions(queue_entry)
            
            self.db.commit()
            
            logger.info(f"Conversation {conversation_id} abandoned: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error abandoning conversation: {str(e)}")
            self.db.rollback()
            return False
    
    def transfer_conversation(self, conversation_id: int, from_agent_id: int, 
                            to_agent_id: int, reason: str = "transfer") -> bool:
        """Transfer conversation from one agent to another"""
        try:
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id,
                LiveChatConversation.assigned_agent_id == from_agent_id
            ).first()
            
            if not conversation:
                return False
            
            # Check if target agent is available
            target_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == to_agent_id,
                AgentSession.logout_at.is_(None),
                AgentSession.active_conversations < AgentSession.max_concurrent_chats
            ).first()
            
            if not target_session:
                # Put back in queue if target not available
                return self._requeue_conversation(conversation_id, reason="transfer_unavailable")
            
            # FIXED: Use naive datetime
            now = utc_now()
            
            # Update conversation
            conversation.previous_agent_id = from_agent_id
            conversation.assigned_agent_id = to_agent_id
            conversation.assigned_at = now
            conversation.assignment_method = "transfer"
            
            # Update agent sessions
            from_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == from_agent_id,
                AgentSession.logout_at.is_(None)
            ).first()
            
            if from_session:
                from_session.active_conversations = max(0, from_session.active_conversations - 1)
            
            target_session.active_conversations += 1
            
            self.db.commit()
            
            logger.info(f"Conversation {conversation_id} transferred from {from_agent_id} to {to_agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error transferring conversation: {str(e)}")
            self.db.rollback()
            return False
    
    def _requeue_conversation(self, conversation_id: int, reason: str = "requeue") -> bool:
        """Put a conversation back in the queue"""
        try:
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                return False
            
            # Remove current assignment
            if conversation.assigned_agent_id:
                agent_session = self.db.query(AgentSession).filter(
                    AgentSession.agent_id == conversation.assigned_agent_id,
                    AgentSession.logout_at.is_(None)
                ).first()
                
                if agent_session:
                    agent_session.active_conversations = max(0, agent_session.active_conversations - 1)
            
            conversation.assigned_agent_id = None
            conversation.assigned_at = None
            
            # Add back to queue
            result = self.add_to_queue(conversation_id, priority=2)  # Higher priority for requeue
            
            logger.info(f"Conversation {conversation_id} requeued: {reason}")
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"Error requeuing conversation: {str(e)}")
            return False
    
    def cleanup_expired_queue_entries(self, tenant_id: int = None) -> int:
        """Clean up expired queue entries - COMPLETE TIMEZONE FIX"""
        try:
            # Get settings for timeout
            if tenant_id:
                settings = self.db.query(LiveChatSettings).filter(
                    LiveChatSettings.tenant_id == tenant_id
                ).first()
                timeout_minutes = settings.max_wait_time_minutes if settings else 30
                tenants_filter = [tenant_id]
            else:
                timeout_minutes = 30
                tenants_filter = None
            
            # FIXED: Use naive datetime for comparison
            cutoff_time = utc_now() - timedelta(minutes=timeout_minutes)
            
            query = self.db.query(ChatQueue).filter(
                ChatQueue.status == "waiting",
                ChatQueue.queued_at < cutoff_time
            )
            
            if tenants_filter:
                query = query.filter(ChatQueue.tenant_id.in_(tenants_filter))
            
            expired_entries = query.all()
            
            # Process each expired entry
            cleaned_count = 0
            for entry in expired_entries:
                if self.abandon_conversation(entry.conversation_id, "timeout"):
                    cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} expired queue entries")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up queue: {str(e)}")
            return 0