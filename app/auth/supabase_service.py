# app/auth/supabase_service.py
import os
import logging
from typing import Dict, Optional, Any
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

class SupabaseAuthService:
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize Supabase Auth Service with environment variables as fallback
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url:
            raise ValueError("SUPABASE_URL is required")
        
        if not self.supabase_key:
            raise ValueError("SUPABASE_KEY/SUPABASE_ANON_KEY is required")
        
        self.supabase_url = self.supabase_url.rstrip('/')
        logger.info("Supabase auth service initialized")
    
    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """
        Sign in user with email and password
        """
        try:
            if not email or not password:
                return {
                    "success": False,
                    "error": "Email and password are required",
                    "session": None,
                    "user": None
                }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/token?grant_type=password",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "email": email,
                        "password": password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    session_obj = SimpleSession(
                        access_token=data.get("access_token"),
                        expires_at=data.get("expires_at")
                    )
                    
                    user_obj = SimpleUser(
                        id=data.get("user", {}).get("id"),
                        email=data.get("user", {}).get("email")
                    )
                    
                    return {
                        "success": True,
                        "session": session_obj,
                        "user": user_obj,
                        "error": None
                    }
                else:
                    try:
                        error_data = response.json()
                    except:
                        error_data = {"error": response.text}
                    
                    error_messages = {
                        400: "Invalid credentials",
                        401: "Invalid credentials",
                        422: "Email not confirmed or user doesn't exist",
                        429: "Too many requests - rate limited"
                    }
                    
                    friendly_error = error_messages.get(response.status_code, "Authentication failed")
                    
                    return {
                        "success": False,
                        "error": friendly_error,
                        "session": None,
                        "user": None
                    }
                    
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Authentication request timed out",
                "session": None,
                "user": None
            }
        except Exception as e:
            logger.error(f"Supabase sign-in error: {e}")
            return {
                "success": False,
                "error": "Authentication service error",
                "session": None,
                "user": None
            }
    
    async def create_user(self, email: str, password: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create a new user account
        """
        try:
            if not email or not password:
                return {
                    "success": False,
                    "error": "Email and password are required"
                }
            
            if len(password) < 6:
                return {
                    "success": False,
                    "error": "Password must be at least 6 characters"
                }
            
            payload = {
                "email": email,
                "password": password
            }
            
            if metadata:
                payload["data"] = metadata
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/signup",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {
                        "success": True,
                        "user": data.get("user"),
                        "session": data.get("session"),
                        "error": None
                    }
                else:
                    try:
                        error_data = response.json()
                    except:
                        error_data = {"error": response.text}
                    
                    error_messages = {
                        400: "Invalid email or password format",
                        422: "Email already registered or invalid format",
                        429: "Too many registration attempts"
                    }
                    
                    friendly_error = error_messages.get(response.status_code, "User creation failed")
                    
                    return {
                        "success": False,
                        "error": friendly_error
                    }
                    
        except Exception as e:
            logger.error(f"Supabase create_user error: {e}")
            return {
                "success": False,
                "error": "User creation service error"
            }


class SimpleSession:
    def __init__(self, access_token: str, expires_at: int):
        self.access_token = access_token
        self.expires_at = expires_at

class SimpleUser:
    def __init__(self, id: str, email: str):
        self.id = id
        self.email = email


class DummySupabaseService:
    """Fallback service for development"""
    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "Supabase not configured",
            "session": None,
            "user": None
        }
    
    async def create_user(self, email: str, password: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "Supabase not configured"
        }


def check_supabase_config() -> bool:
    """Check if Supabase configuration is valid"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    
    return bool(supabase_url and supabase_key)


# Create the global service instance
try:
    if check_supabase_config():
        supabase_auth_service = SupabaseAuthService()
    else:
        logger.warning("Supabase not configured, using dummy service")
        supabase_auth_service = DummySupabaseService()
except Exception as e:
    logger.error(f"Failed to create Supabase service: {e}")
    supabase_auth_service = DummySupabaseService()