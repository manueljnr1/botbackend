# app/live_chat/manager.py
import uuid
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from app.live_chat.models import (
    Agent, LiveChat, LiveChatMessage, AgentSession, ChatQueue,
    AgentStatus, ChatStatus, MessageType
)
from app.chatbot.models import ChatSession, ChatMessage
from app.tenants.models import Tenant

logger = logging.getLogger(__name__)

class LiveChatManager:
    """Manages live chat operations, agent assignment, and queue management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========================== HANDOFF DETECTION ==========================
    
    def detect_handoff_request(self, message: str) -> Tuple[bool, str, str]:
        """
        Detect if user is requesting to talk to a human agent
        Returns: (is_handoff_request, reason, department_hint)
        """
        message_lower = message.lower()
        
        # Direct handoff keywords
        handoff_patterns = [
            "talk to human", "speak to agent", "customer service", "live chat",
            "human support", "real person", "customer representative", 
            "talk to someone", "speak to someone", "human agent",
            "live support", "customer care", "help desk", "support team"
        ]
        
        # Frustration indicators
        frustration_patterns = [
            "not helpful", "doesn't understand", "not working", "frustrated",
            "useless", "terrible", "worst", "horrible", "stupid bot",
            "doesn't work", "can't help", "waste of time"
        ]
        
        # Department hints
        department_hints = {
            "sales": ["buy", "purchase", "price", "cost", "demo", "trial", "sales"],
            "technical": ["bug", "error", "broken", "technical", "code", "api", "integration"],
            "billing": ["bill", "payment", "invoice", "refund", "subscription", "charge"],
            "general": ["complaint", "feedback", "suggestion", "general"]
        }
        
        # Check for direct handoff requests
        for pattern in handoff_patterns:
            if pattern in message_lower:
                reason = f"User requested: {pattern}"
                department = self._determine_department(message_lower, department_hints)
                return True, reason, department
        
        # Check for frustration patterns
        for pattern in frustration_patterns:
            if pattern in message_lower:
                reason = f"User expressed frustration: {pattern}"
                department = self._determine_department(message_lower, department_hints)
                return True, reason, department
        
        # Check for complex queries that might need human help
        complex_indicators = [
            "complex", "complicated", "detailed", "specific situation",
            "special case", "exception", "urgent", "important"
        ]
        
        for indicator in complex_indicators:
            if indicator in message_lower:
                reason = f"Complex query detected: {indicator}"
                department = self._determine_department(message_lower, department_hints)
                return True, reason, department
        
        return False, "", ""
    
    def _determine_department(self, message: str, department_hints: Dict) -> str:
        """Determine which department the user likely needs"""
        for dept, keywords in department_hints.items():
            if any(keyword in message for keyword in keywords):
                return dept
        return "general"
    
    # ========================== CHAT INITIATION ==========================
    
    def initiate_live_chat(self, tenant_id: int, user_identifier: str, 
                          chatbot_session_id: str = None, handoff_reason: str = None,
                          platform: str = "web", user_name: str = None,
                          user_email: str = None, department: str = None) -> LiveChat:
        """
        Initiate a new live chat session
        """
        # Check if user already has an active live chat
        existing_chat = self.db.query(LiveChat).filter(
            and_(
                LiveChat.tenant_id == tenant_id,
                LiveChat.user_identifier == user_identifier,
                LiveChat.status.in_([ChatStatus.WAITING, ChatStatus.ACTIVE])
            )
        ).first()
        
        if existing_chat:
            logger.info(f"User {user_identifier} already has active chat: {existing_chat.session_id}")
            return existing_chat
        
        # Get bot context if available
        bot_context = None
        if chatbot_session_id:
            bot_context = self._get_bot_context(chatbot_session_id)
        
        # Create new live chat session
        session_id = f"live_{str(uuid.uuid4())[:8]}"
        
        live_chat = LiveChat(
            session_id=session_id,
            tenant_id=tenant_id,
            user_identifier=user_identifier,
            user_name=user_name,
            user_email=user_email,
            platform=platform,
            chatbot_session_id=chatbot_session_id,
            handoff_reason=handoff_reason,
            bot_context=json.dumps(bot_context) if bot_context else None,
            department=department or "general",
            status=ChatStatus.WAITING
        )
        
        self.db.add(live_chat)
        self.db.commit()
        self.db.refresh(live_chat)
        
        # Add to queue
        self._add_to_queue(live_chat)
        
        # Send system message
        self._send_system_message(
            live_chat.id,
            "You've been connected to our live chat system. An agent will be with you shortly."
        )
        
        logger.info(f"Created live chat session: {session_id} for user: {user_identifier}")
        return live_chat
    
    def _get_bot_context(self, chatbot_session_id: str) -> Optional[Dict]:
        """Get context from bot conversation for agent reference"""
        try:
            session = self.db.query(ChatSession).filter(
                ChatSession.session_id == chatbot_session_id
            ).first()
            
            if not session:
                return None
            
            # Get recent messages
            messages = self.db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).order_by(desc(ChatMessage.created_at)).limit(10).all()
            
            context = {
                "recent_messages": [
                    {
                        "content": msg.content,
                        "is_from_user": msg.is_from_user,
                        "timestamp": msg.created_at.isoformat()
                    }
                    for msg in reversed(messages)
                ],
                "session_language": session.language_code,
                "platform": session.platform
            }
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting bot context: {e}")
            return None
    
    # ========================== QUEUE MANAGEMENT ==========================
    
    def _add_to_queue(self, live_chat: LiveChat):
        """Add chat to the queue for agent assignment"""
        # Get current queue position
        current_position = self.db.query(ChatQueue).filter(
            ChatQueue.tenant_id == live_chat.tenant_id
        ).count() + 1
        
        # Estimate wait time based on queue length and average resolution time
        estimated_wait = self._calculate_estimated_wait_time(live_chat.tenant_id, current_position)
        
        queue_entry = ChatQueue(
            tenant_id=live_chat.tenant_id,
            chat_id=live_chat.id,
            position=current_position,
            estimated_wait_time=estimated_wait,
            department=live_chat.department,
            priority=live_chat.priority
        )
        
        self.db.add(queue_entry)
        self.db.commit()
        
        logger.info(f"Added chat {live_chat.session_id} to queue at position {current_position}")
        
        # Try immediate assignment
        self._try_assign_agent(live_chat)
    
    def _calculate_estimated_wait_time(self, tenant_id: int, position: int) -> int:
        """Calculate estimated wait time in minutes"""
        # Get average resolution time for recent chats
        recent_chats = self.db.query(LiveChat).filter(
            and_(
                LiveChat.tenant_id == tenant_id,
                LiveChat.resolution_time.isnot(None),
                LiveChat.created_at > datetime.utcnow() - timedelta(days=7)
            )
        ).limit(50).all()
        
        if not recent_chats:
            avg_resolution = 15  # Default 15 minutes
        else:
            avg_resolution = sum(chat.resolution_time for chat in recent_chats) / len(recent_chats) / 60
        
        # Get number of available agents
        available_agents = self._get_available_agents(tenant_id)
        agent_count = len(available_agents) or 1
        
        # Calculate wait time
        estimated_minutes = int((position * avg_resolution) / agent_count)
        return max(1, estimated_minutes)  # Minimum 1 minute
    
    # ========================== AGENT ASSIGNMENT ==========================
    
    def _try_assign_agent(self, live_chat: LiveChat):
        """Try to assign an available agent to the chat"""
        available_agents = self._get_available_agents(live_chat.tenant_id, live_chat.department)
        
        if not available_agents:
            logger.info(f"No available agents for chat {live_chat.session_id}")
            return False
        
        # Use round-robin or skill-based assignment
        best_agent = self._select_best_agent(available_agents, live_chat)
        
        if best_agent:
            self._assign_agent_to_chat(live_chat, best_agent)
            return True
        
        return False
    
    def _get_available_agents(self, tenant_id: int, department: str = None) -> List[Agent]:
        """Get list of available agents for assignment"""
        query = self.db.query(Agent).filter(
            and_(
                Agent.tenant_id == tenant_id,
                Agent.is_active == True,
                Agent.status.in_([AgentStatus.ONLINE, AgentStatus.AWAY]),
                Agent.current_chat_count < Agent.max_concurrent_chats
            )
        )
        
        if department and department != "general":
            query = query.filter(Agent.department == department)
        
        return query.all()
    
    def _select_best_agent(self, agents: List[Agent], live_chat: LiveChat) -> Optional[Agent]:
        """Select the best agent for the chat based on various criteria"""
        if not agents:
            return None
        
        # Priority 1: Agent with least current chats
        agents_by_load = sorted(agents, key=lambda a: a.current_chat_count)
        
        # Priority 2: Agent with matching department
        dept_agents = [a for a in agents_by_load if a.department == live_chat.department]
        if dept_agents:
            return dept_agents[0]
        
        # Priority 3: Any available agent
        return agents_by_load[0]
    
    def _assign_agent_to_chat(self, live_chat: LiveChat, agent: Agent):
        """Assign an agent to a chat"""
        # Update chat
        live_chat.agent_id = agent.id
        live_chat.assigned_at = datetime.utcnow()
        live_chat.status = ChatStatus.ACTIVE
        
        # Update agent
        agent.current_chat_count += 1
        agent.total_chats_handled += 1
        
        # Remove from queue
        queue_entry = self.db.query(ChatQueue).filter(
            ChatQueue.chat_id == live_chat.id
        ).first()
        if queue_entry:
            live_chat.queue_time = int((datetime.utcnow() - queue_entry.queued_at).total_seconds())
            self.db.delete(queue_entry)
        
        self.db.commit()
        
        # Send system messages
        self._send_system_message(
            live_chat.id,
            f"Agent {agent.name} has joined the chat. How can I help you today?"
        )
        
        logger.info(f"Assigned agent {agent.name} to chat {live_chat.session_id}")
    
    # ========================== MESSAGE HANDLING ==========================
    
    def send_message(self, chat_id: int, content: str, is_from_user: bool = True,
                    agent_id: int = None, message_type: MessageType = MessageType.TEXT,
                    file_url: str = None, is_internal: bool = False) -> LiveChatMessage:
        """Send a message in a live chat"""
        chat = self.db.query(LiveChat).filter(LiveChat.id == chat_id).first()
        if not chat:
            raise ValueError(f"Chat {chat_id} not found")
        
        message = LiveChatMessage(
            chat_id=chat_id,
            content=content,
            message_type=message_type,
            file_url=file_url,
            is_from_user=is_from_user,
            agent_id=agent_id,
            is_internal=is_internal,
            sender_name=chat.agent.name if agent_id and chat.agent else chat.user_name
        )
        
        self.db.add(message)
        
        # Update first response time if this is agent's first message
        if not is_from_user and agent_id and not chat.first_response_time:
            chat.first_response_time = int((datetime.utcnow() - chat.assigned_at).total_seconds())
        
        self.db.commit()
        self.db.refresh(message)
        
        logger.info(f"Message sent in chat {chat.session_id} by {'user' if is_from_user else 'agent'}")
        return message
    
    def _send_system_message(self, chat_id: int, content: str):
        """Send a system message (not from user or agent)"""
        message = LiveChatMessage(
            chat_id=chat_id,
            content=content,
            message_type=MessageType.SYSTEM,
            is_from_user=False,
            sender_name="System"
        )
        
        self.db.add(message)
        self.db.commit()
    
    # ========================== CHAT OPERATIONS ==========================
    
    def end_chat(self, chat_id: int, agent_id: int = None, 
                satisfaction_rating: int = None) -> bool:
        """End a live chat session"""
        chat = self.db.query(LiveChat).filter(LiveChat.id == chat_id).first()
        if not chat:
            return False
        
        # Update chat status
        chat.status = ChatStatus.RESOLVED
        chat.ended_at = datetime.utcnow()
        chat.customer_satisfaction = satisfaction_rating
        
        if chat.started_at:
            chat.resolution_time = int((chat.ended_at - chat.started_at).total_seconds())
        
        # Update agent availability
        if chat.agent:
            chat.agent.current_chat_count = max(0, chat.agent.current_chat_count - 1)
        
        # Remove from queue if still there
        queue_entry = self.db.query(ChatQueue).filter(ChatQueue.chat_id == chat.id).first()
        if queue_entry:
            self.db.delete(queue_entry)
        
        self.db.commit()
        
        logger.info(f"Ended chat {chat.session_id}")
        return True
    
    def transfer_chat(self, chat_id: int, target_agent_id: int, 
                     transfer_reason: str = None) -> bool:
        """Transfer chat to another agent"""
        chat = self.db.query(LiveChat).filter(LiveChat.id == chat_id).first()
        if not chat:
            return False
        
        target_agent = self.db.query(Agent).filter(Agent.id == target_agent_id).first()
        if not target_agent or target_agent.current_chat_count >= target_agent.max_concurrent_chats:
            return False
        
        # Update current agent
        if chat.agent:
            chat.agent.current_chat_count -= 1
        
        # Update new agent
        chat.agent_id = target_agent_id
        target_agent.current_chat_count += 1
        
        # Send system message
        self._send_system_message(
            chat.id,
            f"Chat has been transferred to {target_agent.name}. {transfer_reason or ''}"
        )
        
        self.db.commit()
        
        logger.info(f"Transferred chat {chat.session_id} to agent {target_agent.name}")
        return True
    
    # ========================== AGENT MANAGEMENT ==========================
    
    def update_agent_status(self, agent_id: int, status: AgentStatus):
        """Update agent status"""
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if agent:
            agent.status = status
            agent.last_seen = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Updated agent {agent.name} status to {status}")
    
    def get_agent_workload(self, agent_id: int) -> Dict:
        """Get current workload for an agent"""
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return {}
        
        active_chats = self.db.query(LiveChat).filter(
            and_(
                LiveChat.agent_id == agent_id,
                LiveChat.status == ChatStatus.ACTIVE
            )
        ).all()
        
        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "status": agent.status,
            "current_chats": len(active_chats),
            "max_chats": agent.max_concurrent_chats,
            "availability": agent.max_concurrent_chats - len(active_chats),
            "active_chat_sessions": [chat.session_id for chat in active_chats]
        }
    
    # ========================== QUEUE OPERATIONS ==========================
    
    def get_queue_status(self, tenant_id: int) -> Dict:
        """Get current queue status for a tenant"""
        queue_entries = self.db.query(ChatQueue).filter(
            ChatQueue.tenant_id == tenant_id
        ).order_by(ChatQueue.position).all()
        
        available_agents = self._get_available_agents(tenant_id)
        
        return {
            "tenant_id": tenant_id,
            "queue_length": len(queue_entries),
            "available_agents": len(available_agents),
            "estimated_wait_time": queue_entries[0].estimated_wait_time if queue_entries else 0,
            "queue_entries": [
                {
                    "chat_id": entry.chat_id,
                    "position": entry.position,
                    "wait_time": entry.estimated_wait_time,
                    "department": entry.department
                }
                for entry in queue_entries
            ]
        }