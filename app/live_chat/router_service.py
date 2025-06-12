import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple
from sqlalchemy.orm import Session
from app.live_chat.models import Conversation, Agent, ConversationStatus, AgentStatus
from app.live_chat.state_manager import ChatStateManager
import logging

logger = logging.getLogger(__name__)

class LiveChatRouter:
    """Main orchestrator for live chat routing and management"""
    
    def __init__(self, db: Session, state_manager: ChatStateManager):
        self.db = db
        self.state = state_manager
    
    def check_handoff_triggers(self, message: str) -> Tuple[bool, str]:
        """Check if message contains handoff triggers"""
        triggers = [
            "speak to human", "talk to agent", "customer service", "live chat",
            "human support", "real person", "not helpful", "doesn't understand",
            "frustrated", "can't help", "talk to someone"
        ]
        
        message_lower = message.lower()
        for trigger in triggers:
            if trigger in message_lower:
                return True, f"Customer requested: {trigger}"
        
        return False, ""
    
    def initiate_handoff(self, tenant_id: int, customer_id: str, 
                        customer_name: str = None, customer_email: str = None,
                        bot_session_id: str = None, handoff_reason: str = None,
                        department: str = "general", platform: str = "web") -> Dict:
        """Initiate handoff from bot to live chat"""
        
        # Check if customer already has active conversation
        existing = self.db.query(Conversation).filter(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_id == customer_id,
            Conversation.status.in_([ConversationStatus.QUEUED, ConversationStatus.ACTIVE])
        ).first()
        
        if existing:
            logger.info(f"Customer {customer_id} already has active conversation: {existing.session_id}")
            return self._get_conversation_status(existing.session_id)
        
        # Create new conversation
        session_id = f"chat_{uuid.uuid4().hex[:8]}"
        
        conversation = Conversation(
            session_id=session_id,
            tenant_id=tenant_id,
            customer_id=customer_id,
            customer_name=customer_name,
            customer_email=customer_email,
            platform=platform,
            department=department,
            bot_session_id=bot_session_id,
            handoff_reason=handoff_reason,
            status=ConversationStatus.QUEUED
        )
        
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        
        # Create state in Redis
        self.state.create_conversation_state(session_id, {
            "conversation_id": conversation.id,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "status": "queued",
            "department": department,
            "platform": platform
        })
        
        # Try to assign agent immediately
        assigned = self._try_assign_agent(conversation)
        
        if not assigned:
            # Add to queue
            self.state.add_to_queue(tenant_id, session_id)
            queue_position = self.state.get_queue_position(tenant_id, session_id)
            estimated_wait = self._calculate_wait_time(tenant_id, queue_position)
        else:
            queue_position = 0
            estimated_wait = 0
        
        result = {
            "session_id": session_id,
            "status": "assigned" if assigned else "queued",
            "queue_position": queue_position,
            "estimated_wait_minutes": estimated_wait,
            "message": "Connected to agent" if assigned else "You're in queue. An agent will be with you shortly."
        }
        
        logger.info(f"Handoff initiated for {customer_id}: {session_id}")
        return result
    
    def _try_assign_agent(self, conversation: Conversation) -> bool:
        """Try to assign an available agent"""
        available_agents = self.state.get_available_agents(
            conversation.tenant_id, 
            conversation.department
        )
        
        if not available_agents:
            return False
        
        # Get best agent (least busy)
        best_agent = available_agents[0]
        agent_id = best_agent["agent_id"]
        
        # Assign in database
        conversation.agent_id = agent_id
        conversation.status = ConversationStatus.ACTIVE
        conversation.assigned_at = datetime.utcnow()
        self.db.commit()
        
        # Update Redis state
        self.state.update_conversation_state(conversation.session_id, {
            "status": "active",
            "agent_id": agent_id,
            "agent_name": best_agent["name"],
            "assigned_at": datetime.utcnow().isoformat()
        })
        
        # Assign to agent
        self.state.assign_conversation_to_agent(
            conversation.tenant_id, 
            agent_id, 
            conversation.session_id
        )
        
        # Remove from queue if it was there
        self.state.remove_from_queue(conversation.tenant_id, conversation.session_id)
        
        logger.info(f"Assigned conversation {conversation.session_id} to agent {agent_id}")
        return True
    
    def _calculate_wait_time(self, tenant_id: int, queue_position: int) -> int:
        """Calculate estimated wait time in minutes"""
        # Simple calculation: position * average_resolution_time / available_agents
        available_agents = len(self.state.get_available_agents(tenant_id))
        if available_agents == 0:
            return max(queue_position * 5, 1)  # 5 min per position if no agents
        
        # Assume average 10 minutes per conversation
        return max(int((queue_position * 10) / available_agents), 1)
    
    def _get_conversation_status(self, session_id: str) -> Dict:
        """Get current status of conversation"""
        state = self.state.get_conversation_state(session_id)
        if not state:
            return {"error": "Conversation not found"}
        
        if state["status"] == "queued":
            queue_position = self.state.get_queue_position(state["tenant_id"], session_id)
            estimated_wait = self._calculate_wait_time(state["tenant_id"], queue_position)
            
            return {
                "session_id": session_id,
                "status": "queued",
                "queue_position": queue_position,
                "estimated_wait_minutes": estimated_wait,
                "message": f"You're #{queue_position} in queue"
            }
        elif state["status"] == "active":
            return {
                "session_id": session_id,
                "status": "active",
                "agent_name": state.get("agent_name"),
                "message": "Connected to agent"
            }
        else:
            return {
                "session_id": session_id,
                "status": state["status"],
                "message": "Conversation ended"
            }
    
    def process_queue(self, tenant_id: int):
        """Process queue and assign available agents"""
        available_agents = self.state.get_available_agents(tenant_id)
        
        for agent in available_agents:
            # Check if agent can take more conversations
            current_load = agent["current_load"]
            max_chats = agent["max_concurrent_chats"]
            
            if current_load < max_chats:
                # Get next conversation from queue
                next_session_id = self.state.get_next_in_queue(tenant_id)
                
                if next_session_id:
                    # Get conversation from DB
                    conversation = self.db.query(Conversation).filter(
                        Conversation.session_id == next_session_id,
                        Conversation.status == ConversationStatus.QUEUED
                    ).first()
                    
                    if conversation:
                        # Assign agent
                        conversation.agent_id = agent["agent_id"]
                        conversation.status = ConversationStatus.ACTIVE
                        conversation.assigned_at = datetime.utcnow()
                        
                        # Calculate queue time
                        queue_time = (datetime.utcnow() - conversation.created_at).total_seconds()
                        conversation.queue_time_seconds = int(queue_time)
                        
                        self.db.commit()
                        
                        # Update Redis state
                        self.state.update_conversation_state(next_session_id, {
                            "status": "active",
                            "agent_id": agent["agent_id"],
                            "agent_name": agent["name"],
                            "assigned_at": datetime.utcnow().isoformat()
                        })
                        
                        # Assign to agent
                        self.state.assign_conversation_to_agent(
                            tenant_id, 
                            agent["agent_id"], 
                            next_session_id
                        )
                        
                        logger.info(f"Assigned queued conversation {next_session_id} to agent {agent['agent_id']}")
