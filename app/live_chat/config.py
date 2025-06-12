# ===========================
# FIXED app/live_chat/config.py
# ===========================

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

import redis
from typing import Optional

class LiveChatSettings(BaseSettings):
    # Redis configuration - Fixed types
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None  # Allow None values
    
    # WebSocket configuration
    websocket_max_connections: int = 1000
    websocket_heartbeat_interval: int = 30
    
    # Chat configuration
    max_queue_time_minutes: int = 30
    default_agent_max_concurrent: int = 3
    auto_assign_enabled: bool = True
    
    # Notification settings
    enable_email_notifications: bool = False
    enable_push_notifications: bool = False
    
    class Config:
        env_prefix = "LIVECHAT_"

settings = LiveChatSettings()

# Redis client factory
def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True
    )