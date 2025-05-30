# app/slack/thread_memory.py
"""
Thread-Aware Memory System for Slack Integration
Handles separate conversation contexts for each thread while maintaining channel awareness
"""

import logging
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from app.database import Base
from app.chatbot.models import ChatSession

logger = logging.getLogger(__name__)

# Database Models for Thread Memory
class SlackThreadMemory(Base):
    """Store thread-specific conversation memory"""
    __tablename__ = "slack_thread_memory"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    channel_id = Column(String(50), nullable=False, index=True)
    thread_ts = Column(String(50), nullable=True, index=True)  # None for main channel
    user_id = Column(String(50), nullable=False, index=True)
    
    # Memory data
    conversation_context = Column(Text)  # JSON string of conversation history
    user_preferences = Column(Text)  # JSON string of user preferences
    topic_summary = Column(Text)  # AI-generated summary of conversation topic
    
    # Metadata
    message_count = Column(Integer, default=0)
    last_activity = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_slack_thread_tenant_channel', 'tenant_id', 'channel_id'),
        Index('idx_slack_thread_user_activity', 'user_id', 'last_activity'),
        Index('idx_slack_thread_ts', 'thread_ts'),
    )

class SlackChannelContext(Base):
    """Store channel-level context and settings"""
    __tablename__ = "slack_channel_context"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    channel_id = Column(String(50), nullable=False, index=True)
    channel_name = Column(String(100))
    
    # Channel settings
    channel_type = Column(String(20))  # public, private, dm, group
    bot_enabled = Column(Boolean, default=True)
    thread_mode = Column(String(20), default="auto")  # auto, always, never
    
    # Context data
    channel_topic = Column(Text)
    common_questions = Column(Text)  # JSON array of frequently asked questions
    channel_personality = Column(Text)  # Custom personality for this channel
    
    # Statistics
    total_messages = Column(Integer, default=0)
    active_threads = Column(Integer, default=0)
    last_activity = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_slack_channel_tenant', 'tenant_id', 'channel_id'),
    )

@dataclass
class ThreadContext:
    """Data class for thread conversation context"""
    thread_id: str
    channel_id: str
    user_id: str
    messages: List[Dict[str, Any]]
    topic_summary: Optional[str] = None
    user_preferences: Optional[Dict[str, Any]] = None
    last_activity: Optional[datetime] = None

@dataclass 
class ChannelContext:
    """Data class for channel-level context"""
    channel_id: str
    channel_name: str
    channel_type: str
    topic: Optional[str] = None
    personality: Optional[str] = None
    common_questions: Optional[List[str]] = None

class SlackThreadMemoryManager:
    """Manages thread-aware conversations and channel context"""
    
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.memory_cache: Dict[str, ThreadContext] = {}
        self.channel_cache: Dict[str, ChannelContext] = {}
        
    def get_thread_identifier(self, channel_id: str, thread_ts: Optional[str] = None) -> str:
        """Generate unique thread identifier"""
        if thread_ts:
            return f"{channel_id}:{thread_ts}"
        return f"{channel_id}:main"
    
    def get_or_create_thread_context(self, channel_id: str, user_id: str, 
                                   thread_ts: Optional[str] = None) -> ThreadContext:
        """Get or create thread context for conversation"""
        thread_id = self.get_thread_identifier(channel_id, thread_ts)
        
        # Check cache first
        if thread_id in self.memory_cache:
            context = self.memory_cache[thread_id]
            # Update activity timestamp
            context.last_activity = datetime.utcnow()
            return context
        
        # Get from database
        thread_memory = self.db.query(SlackThreadMemory).filter(
            SlackThreadMemory.tenant_id == self.tenant_id,
            SlackThreadMemory.channel_id == channel_id,
            SlackThreadMemory.thread_ts == thread_ts,
            SlackThreadMemory.user_id == user_id,
            SlackThreadMemory.is_active == True
        ).first()
        
        if thread_memory:
            # Load existing context
            messages = json.loads(thread_memory.conversation_context or "[]")
            preferences = json.loads(thread_memory.user_preferences or "{}")
            
            context = ThreadContext(
                thread_id=thread_id,
                channel_id=channel_id,
                user_id=user_id,
                messages=messages,
                topic_summary=thread_memory.topic_summary,
                user_preferences=preferences,
                last_activity=thread_memory.last_activity
            )
        else:
            # Create new context
            context = ThreadContext(
                thread_id=thread_id,
                channel_id=channel_id,
                user_id=user_id,
                messages=[],
                last_activity=datetime.utcnow()
            )
            
            # Create database record
            thread_memory = SlackThreadMemory(
                tenant_id=self.tenant_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                conversation_context="[]",
                user_preferences="{}",
                message_count=0
            )
            self.db.add(thread_memory)
            self.db.commit()
            
            logger.info(f"Created new thread context: {thread_id}")
        
        # Cache the context
        self.memory_cache[thread_id] = context
        return context
    
    def add_message_to_thread(self, channel_id: str, user_id: str, message: str, 
                            is_from_user: bool, thread_ts: Optional[str] = None,
                            message_ts: Optional[str] = None) -> bool:
        """Add message to thread context"""
        try:
            context = self.get_or_create_thread_context(channel_id, user_id, thread_ts)
            
            # Create message entry
            message_entry = {
                "content": message,
                "is_from_user": is_from_user,
                "timestamp": message_ts or datetime.utcnow().isoformat(),
                "user_id": user_id if is_from_user else "bot"
            }
            
            # Add to context
            context.messages.append(message_entry)
            context.last_activity = datetime.utcnow()
            
            # Limit message history (keep last 50 messages per thread)
            if len(context.messages) > 50:
                context.messages = context.messages[-50:]
            
            # Update database
            self._save_thread_context(context)
            
            logger.info(f"Added message to thread {context.thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding message to thread: {e}")
            return False
    
    def get_thread_conversation_history(self, channel_id: str, user_id: str, 
                                      thread_ts: Optional[str] = None, 
                                      max_messages: int = 20) -> List[Dict[str, Any]]:
        """Get conversation history for a specific thread"""
        context = self.get_or_create_thread_context(channel_id, user_id, thread_ts)
        
        # Return most recent messages
        messages = context.messages[-max_messages:] if context.messages else []
        
        logger.info(f"Retrieved {len(messages)} messages for thread {context.thread_id}")
        return messages
    
    def get_channel_context(self, channel_id: str) -> Optional[ChannelContext]:
        """Get channel-level context and settings"""
        if channel_id in self.channel_cache:
            return self.channel_cache[channel_id]
        
        channel_data = self.db.query(SlackChannelContext).filter(
            SlackChannelContext.tenant_id == self.tenant_id,
            SlackChannelContext.channel_id == channel_id
        ).first()
        
        if channel_data:
            common_questions = json.loads(channel_data.common_questions or "[]")
            
            context = ChannelContext(
                channel_id=channel_id,
                channel_name=channel_data.channel_name or "",
                channel_type=channel_data.channel_type or "public",
                topic=channel_data.channel_topic,
                personality=channel_data.channel_personality,
                common_questions=common_questions
            )
            
            self.channel_cache[channel_id] = context
            return context
        
        return None
    
    def update_channel_context(self, channel_id: str, channel_name: str = None,
                             channel_type: str = None, topic: str = None) -> bool:
        """Update channel context information"""
        try:
            channel_data = self.db.query(SlackChannelContext).filter(
                SlackChannelContext.tenant_id == self.tenant_id,
                SlackChannelContext.channel_id == channel_id
            ).first()
            
            if not channel_data:
                channel_data = SlackChannelContext(
                    tenant_id=self.tenant_id,
                    channel_id=channel_id,
                    channel_name=channel_name or "",
                    channel_type=channel_type or "public",
                    channel_topic=topic
                )
                self.db.add(channel_data)
            else:
                if channel_name:
                    channel_data.channel_name = channel_name
                if channel_type:
                    channel_data.channel_type = channel_type
                if topic:
                    channel_data.channel_topic = topic
                
                channel_data.last_activity = datetime.utcnow()
            
            self.db.commit()
            
            # Clear cache to force reload
            if channel_id in self.channel_cache:
                del self.channel_cache[channel_id]
            
            logger.info(f"Updated channel context for {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating channel context: {e}")
            return False
    
    def generate_context_prompt(self, user_message: str, channel_id: str, user_id: str,
                               thread_ts: Optional[str] = None, system_prompt: str = None) -> str:
        """Generate enhanced prompt with thread and channel context"""
        
        # Get thread conversation history
        thread_history = self.get_thread_conversation_history(
            channel_id, user_id, thread_ts, max_messages=15
        )
        
        # Get channel context
        channel_context = self.get_channel_context(channel_id)
        
        # Build context prompt
        prompt_parts = []
        
        # Add system prompt
        if system_prompt:
            prompt_parts.append(f"System Instructions: {system_prompt}")
        
        # Add channel context
        if channel_context:
            prompt_parts.append(f"Channel Context:")
            prompt_parts.append(f"- Channel: #{channel_context.channel_name} ({channel_context.channel_type})")
            if channel_context.topic:
                prompt_parts.append(f"- Topic: {channel_context.topic}")
            if channel_context.personality:
                prompt_parts.append(f"- Personality: {channel_context.personality}")
        
        # Add thread indicator
        if thread_ts:
            prompt_parts.append(f"This is a threaded conversation (Thread ID: {thread_ts})")
        else:
            prompt_parts.append("This is a main channel conversation")
        
        # Add conversation history
        if thread_history:
            prompt_parts.append(f"\nConversation History ({len(thread_history)} messages):")
            for msg in thread_history:
                speaker = "User" if msg["is_from_user"] else "Assistant"
                prompt_parts.append(f"{speaker}: {msg['content']}")
        
        # Add current message
        prompt_parts.append(f"\nCurrent User Message: {user_message}")
        
        # Add response instructions
        prompt_parts.append("\nInstructions:")
        prompt_parts.append("- Respond naturally as a helpful assistant")
        prompt_parts.append("- Use the conversation history to maintain context")
        prompt_parts.append("- Stay consistent with your previous responses in this thread")
        if channel_context and channel_context.personality:
            prompt_parts.append(f"- Maintain the channel personality: {channel_context.personality}")
        
        return "\n".join(prompt_parts)
    
    def _save_thread_context(self, context: ThreadContext):
        """Save thread context to database"""
        try:
            thread_memory = self.db.query(SlackThreadMemory).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.channel_id == context.channel_id,
                SlackThreadMemory.thread_ts == context.thread_id.split(":")[-1] if ":" in context.thread_id else None,
                SlackThreadMemory.user_id == context.user_id,
                SlackThreadMemory.is_active == True
            ).first()
            
            if thread_memory:
                thread_memory.conversation_context = json.dumps(context.messages)
                thread_memory.user_preferences = json.dumps(context.user_preferences or {})
                thread_memory.topic_summary = context.topic_summary
                thread_memory.message_count = len(context.messages)
                thread_memory.last_activity = context.last_activity or datetime.utcnow()
                
                self.db.commit()
                logger.debug(f"Saved thread context: {context.thread_id}")
                
        except Exception as e:
            logger.error(f"Error saving thread context: {e}")
    
    def cleanup_old_threads(self, days_old: int = 30):
        """Clean up inactive threads older than specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            old_threads = self.db.query(SlackThreadMemory).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.last_activity < cutoff_date,
                SlackThreadMemory.is_active == True
            ).all()
            
            for thread in old_threads:
                thread.is_active = False
            
            self.db.commit()
            
            # Clear from cache
            self.memory_cache.clear()
            
            logger.info(f"Cleaned up {len(old_threads)} old threads")
            return len(old_threads)
            
        except Exception as e:
            logger.error(f"Error cleaning up old threads: {e}")
            return 0
    
    def get_thread_statistics(self) -> Dict[str, Any]:
        """Get statistics about thread usage"""
        try:
            # Active threads
            active_threads = self.db.query(SlackThreadMemory).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.is_active == True
            ).count()
            
            # Threads active in last 24 hours
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent_threads = self.db.query(SlackThreadMemory).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.last_activity >= recent_cutoff,
                SlackThreadMemory.is_active == True
            ).count()
            
            # Average messages per thread
            total_messages = self.db.query(SlackThreadMemory.message_count).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.is_active == True
            ).all()
            
            avg_messages = sum(count[0] for count in total_messages) / len(total_messages) if total_messages else 0
            
            return {
                "active_threads": active_threads,
                "recent_active_threads": recent_threads,
                "average_messages_per_thread": round(avg_messages, 2),
                "cached_threads": len(self.memory_cache)
            }
            
        except Exception as e:
            logger.error(f"Error getting thread statistics: {e}")
            return {}
    
    def update_topic_summary(self, channel_id: str, user_id: str, summary: str,
                           thread_ts: Optional[str] = None) -> bool:
        """Update AI-generated topic summary for a thread"""
        try:
            context = self.get_or_create_thread_context(channel_id, user_id, thread_ts)
            context.topic_summary = summary
            self._save_thread_context(context)
            
            logger.info(f"Updated topic summary for thread {context.thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating topic summary: {e}")
            return False
    
    def get_user_preferences(self, user_id: str, channel_id: str) -> Dict[str, Any]:
        """Get user preferences across all threads in a channel"""
        try:
            user_threads = self.db.query(SlackThreadMemory).filter(
                SlackThreadMemory.tenant_id == self.tenant_id,
                SlackThreadMemory.user_id == user_id,
                SlackThreadMemory.channel_id == channel_id,
                SlackThreadMemory.is_active == True
            ).all()
            
            # Merge preferences from all threads
            merged_preferences = {}
            for thread in user_threads:
                if thread.user_preferences:
                    prefs = json.loads(thread.user_preferences)
                    merged_preferences.update(prefs)
            
            return merged_preferences
            
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return {}