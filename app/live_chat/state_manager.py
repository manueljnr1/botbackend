import redis
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class ChatStateManager:
    """Manages live chat state in Redis for fast access"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.session_ttl = 3600 * 24  # 24 hours
    
    # ===== CONVERSATION STATE =====
    
    def create_conversation_state(self, session_id: str, conversation_data: Dict):
        """Create conversation state in Redis"""
        key = f"conversation:{session_id}"
        data = {
            **conversation_data,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat()
        }
        self.redis.setex(key, self.session_ttl, json.dumps(data))
        logger.info(f"Created conversation state: {session_id}")
    
    def get_conversation_state(self, session_id: str) -> Optional[Dict]:
        """Get conversation state from Redis"""
        key = f"conversation:{session_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None
    
    def update_conversation_state(self, session_id: str, updates: Dict):
        """Update conversation state"""
        state = self.get_conversation_state(session_id)
        if state:
            state.update(updates)
            state["last_activity"] = datetime.utcnow().isoformat()
            key = f"conversation:{session_id}"
            self.redis.setex(key, self.session_ttl, json.dumps(state))
    
    def end_conversation_state(self, session_id: str):
        """Remove conversation from Redis"""
        key = f"conversation:{session_id}"
        self.redis.delete(key)
    
    # ===== AGENT AVAILABILITY =====
    
    def set_agent_online(self, tenant_id: int, agent_id: int, agent_data: Dict):
        """Mark agent as online"""
        key = f"agents:online:{tenant_id}"
        agent_info = {
            **agent_data,
            "status": "online",
            "last_seen": datetime.utcnow().isoformat(),
            "active_conversations": []
        }
        self.redis.hset(key, agent_id, json.dumps(agent_info))
        logger.info(f"Agent {agent_id} is now online for tenant {tenant_id}")
    
    def set_agent_offline(self, tenant_id: int, agent_id: int):
        """Mark agent as offline"""
        key = f"agents:online:{tenant_id}"
        self.redis.hdel(key, agent_id)
        logger.info(f"Agent {agent_id} is now offline for tenant {tenant_id}")
    
    def get_available_agents(self, tenant_id: int, department: str = None) -> List[Dict]:
        """Get available agents for assignment"""
        key = f"agents:online:{tenant_id}"
        agents_data = self.redis.hgetall(key)
        
        available_agents = []
        for agent_id, agent_json in agents_data.items():
            agent_info = json.loads(agent_json)
            
            # Check availability
            current_chats = len(agent_info.get("active_conversations", []))
            max_chats = agent_info.get("max_concurrent_chats", 3)
            
            if current_chats < max_chats:
                # Check department match
                if not department or department == "general" or agent_info.get("department") == department:
                    agent_info["agent_id"] = int(agent_id)
                    agent_info["current_load"] = current_chats
                    available_agents.append(agent_info)
        
        # Sort by current load (least busy first)
        return sorted(available_agents, key=lambda x: x["current_load"])
    
    def assign_conversation_to_agent(self, tenant_id: int, agent_id: int, session_id: str):
        """Assign conversation to agent"""
        key = f"agents:online:{tenant_id}"
        agent_data = self.redis.hget(key, agent_id)
        
        if agent_data:
            agent_info = json.loads(agent_data)
            conversations = agent_info.get("active_conversations", [])
            
            if session_id not in conversations:
                conversations.append(session_id)
                agent_info["active_conversations"] = conversations
                self.redis.hset(key, agent_id, json.dumps(agent_info))
    
    def remove_conversation_from_agent(self, tenant_id: int, agent_id: int, session_id: str):
        """Remove conversation from agent's active list"""
        key = f"agents:online:{tenant_id}"
        agent_data = self.redis.hget(key, agent_id)
        
        if agent_data:
            agent_info = json.loads(agent_data)
            conversations = agent_info.get("active_conversations", [])
            
            if session_id in conversations:
                conversations.remove(session_id)
                agent_info["active_conversations"] = conversations
                self.redis.hset(key, agent_id, json.dumps(agent_info))
    
    # ===== QUEUE MANAGEMENT =====
    
    def add_to_queue(self, tenant_id: int, session_id: str, priority: int = 0):
        """Add conversation to queue"""
        queue_key = f"queue:{tenant_id}"
        timestamp = datetime.utcnow().timestamp()
        # Use timestamp + priority for scoring
        score = timestamp + (priority * 1000)
        self.redis.zadd(queue_key, {session_id: score})
        logger.info(f"Added {session_id} to queue for tenant {tenant_id}")
    
    def remove_from_queue(self, tenant_id: int, session_id: str):
        """Remove conversation from queue"""
        queue_key = f"queue:{tenant_id}"
        self.redis.zrem(queue_key, session_id)
    
    def get_queue_position(self, tenant_id: int, session_id: str) -> int:
        """Get position in queue (0-indexed)"""
        queue_key = f"queue:{tenant_id}"
        rank = self.redis.zrank(queue_key, session_id)
        return rank + 1 if rank is not None else 0
    
    def get_next_in_queue(self, tenant_id: int) -> Optional[str]:
        """Get next conversation from queue"""
        queue_key = f"queue:{tenant_id}"
        result = self.redis.zpopmin(queue_key)
        return result[0][0].decode() if result else None
    
    def get_queue_length(self, tenant_id: int) -> int:
        """Get current queue length"""
        queue_key = f"queue:{tenant_id}"
        return self.redis.zcard(queue_key)