# app/auth/supabase_service.py
import os
import logging
from typing import Dict, Optional, Any
import httpx
from datetime import datetime
from supabase import create_client, Client


logger = logging.getLogger(__name__)


class SimpleSession:
    """Simple session object to hold access token and expiration"""
    def __init__(self, access_token: str, expires_at: int):
        self.access_token = access_token
        self.expires_at = expires_at


class SimpleUser:
    """Simple user object to hold user data"""
    def __init__(self, id: str, email: str):
        self.id = id
        self.email = email


class SupabaseAuthService:
    """Supabase authentication service for handling auth operations"""
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize Supabase Auth Service with environment variables as fallback
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url:
            raise ValueError("SUPABASE_URL is required")
        
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        
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


    async def delete_user(self, user_id: str):
        """Delete a user from Supabase (for cleanup)"""
        try:
            response = self.supabase.auth.admin.delete_user(user_id)
            logger.info(f"Deleted Supabase user: {user_id}")
            return {"success": True, "response": response}
        except Exception as e:
            logger.error(f"Failed to delete Supabase user {user_id}: {e}")
            return {"success": False, "error": str(e)}


    async def update_user_metadata(self, user_id: str, additional_metadata: dict):
        """Update user metadata in Supabase"""
        try:
            # Get current user metadata
            user_response = self.supabase.auth.admin.get_user_by_id(user_id)
            
            if not user_response.user:
                return {"success": False, "error": "User not found"}
            
            # Merge existing metadata with new metadata
            current_metadata = user_response.user.user_metadata or {}
            updated_metadata = {**current_metadata, **additional_metadata}
            
            # Update user metadata
            update_response = self.supabase.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": updated_metadata}
            )
            
            return {
                "success": True,
                "user": update_response.user,
                "metadata": updated_metadata
            }
            
        except Exception as e:
            logger.error(f"Failed to update user metadata: {e}")
            return {"success": False, "error": str(e)}
        
    
    async def get_user_metadata(self, user_id: str):
        """Get user metadata from Supabase"""
        try:
            user_response = self.supabase.auth.admin.get_user_by_id(user_id)
            
            if not user_response.user:
                return {"success": False, "error": "User not found"}
            
            return {
                "success": True,
                "user": user_response.user,
                "metadata": user_response.user.user_metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Failed to get user metadata: {e}")
            return {"success": False, "error": str(e)}
        

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

    async def send_password_reset(self, email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
        """
        Send password reset email using Supabase
        """
        try:
            if not email:
                return {
                    "success": False,
                    "error": "Email is required"
                }
            
            payload = {"email": email}
            if redirect_to:
                payload["redirect_to"] = redirect_to
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/recover",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "error": None,
                        "message": "Password reset email sent successfully"
                    }
                else:
                    try:
                        error_data = response.json()
                        logger.error(f"Supabase password reset error response: {error_data}")
                    except:
                        error_data = {"error": response.text}
                        logger.error(f"Supabase password reset error text: {response.text}")
                    
                    error_messages = {
                        400: "Invalid email format",
                        404: "User not found", 
                        422: "Email not found or invalid",
                        429: "Too many password reset requests - rate limited"
                    }
                    
                    friendly_error = error_messages.get(response.status_code, "Failed to send password reset email")
                    
                    return {
                        "success": False,
                        "error": friendly_error
                    }
                    
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Password reset request timed out"
            }
        except Exception as e:
            logger.error(f"Supabase password reset error: {e}")
            return {
                "success": False,
                "error": "Password reset service error"
            }
        
    async def reset_password(self, email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
        """Alias for send_password_reset for backward compatibility"""
        return await self.send_password_reset(email, redirect_to)

    async def verify_reset_token(self, token: str, new_password: str) -> Dict[str, Any]:
        """Alias for verify_password_reset for backward compatibility"""
        return await self.verify_password_reset(token, new_password)

    async def verify_password_reset(self, token: str, new_password: str) -> Dict[str, Any]:
        """
        Verify password reset token and update password
        """
        try:
            if not token or not new_password:
                return {
                    "success": False,
                    "error": "Token and new password are required"
                }
            
            if len(new_password) < 6:
                return {
                    "success": False,
                    "error": "Password must be at least 6 characters"
                }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.supabase_url}/auth/v1/verify",
                    headers={
                        "apikey": self.supabase_key,
                        "Authorization": f"Bearer {self.supabase_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "type": "recovery",
                        "token": token,
                        "password": new_password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "error": None,
                        "user": data.get("user"),
                        "session": data.get("session")
                    }
                else:
                    try:
                        error_data = response.json()
                        logger.error(f"Supabase password reset verification error: {error_data}")
                    except:
                        error_data = {"error": response.text}
                        logger.error(f"Supabase password reset verification error text: {response.text}")
                    
                    error_messages = {
                        400: "Invalid or expired token",
                        401: "Invalid or expired token",
                        422: "Invalid token or password format"
                    }
                    
                    friendly_error = error_messages.get(response.status_code, "Failed to reset password")
                    
                    return {
                        "success": False,
                        "error": friendly_error
                    }
                    
        except Exception as e:
            logger.error(f"Supabase password reset verification error: {e}")
            return {
                "success": False,
                "error": "Password reset verification service error"
            }


class DummySupabaseService:
    """Fallback service for development when Supabase is not configured"""
    
    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Dummy sign in method"""
        logger.warning("Using dummy Supabase service - sign_in")
        return {
            "success": False,
            "error": "Supabase not configured",
            "session": None,
            "user": None
        }
    
    async def create_user(self, email: str, password: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Dummy create user method"""
        logger.warning("Using dummy Supabase service - create_user")
        return {
            "success": False,
            "error": "Supabase not configured"
        }
    
    async def send_password_reset(self, email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
        """Dummy send password reset method"""
        logger.warning("Using dummy Supabase service - send_password_reset")
        return {
            "success": False,
            "error": "Supabase not configured"
        }
    
    async def verify_password_reset(self, token: str, new_password: str) -> Dict[str, Any]:
        """Dummy verify password reset method"""
        logger.warning("Using dummy Supabase service - verify_password_reset")
        return {
            "success": False,
            "error": "Supabase not configured"
        }


def check_supabase_config() -> bool:
    """
    Check if Supabase configuration is valid
    
    Returns:
        bool: True if both URL and key are configured, False otherwise
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    
    return bool(supabase_url and supabase_key)


# Create the global service instance
try:
    if check_supabase_config():
        supabase_auth_service = SupabaseAuthService()
        logger.info("Supabase auth service created successfully")
    else:
        logger.warning("Supabase not configured, using dummy service")
        supabase_auth_service = DummySupabaseService()
except Exception as e:
    logger.error(f"Failed to create Supabase service: {e}")
    supabase_auth_service = DummySupabaseService()