import os
import logging
from typing import Dict, Optional, Any
import httpx
from datetime import datetime
from supabase import create_client, Client

from dotenv import load_dotenv, dotenv_values

# Force reload the .env file
load_dotenv(dotenv_path=".env", override=True)

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
    
    def __init__(self, supabase_url: Optional[str] = None, 
                 service_key: Optional[str] = None, 
                 anon_key: Optional[str] = None):
        """
        Initialize Supabase Auth Service with dual clients
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        
        # Get both keys
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.anon_key = anon_key or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url:
            raise ValueError("SUPABASE_URL is required")
        
        if not self.service_key:
            raise ValueError("SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY is required for admin operations")
            
        if not self.anon_key:
            raise ValueError("SUPABASE_ANON_KEY is required for client operations")
        
        self.supabase_url = self.supabase_url.rstrip('/')
        
        # Create dual clients
        try:
            # Admin client - for server-side admin operations
            self.admin_client: Client = create_client(self.supabase_url, self.service_key)
            logger.info("✅ Supabase admin client initialized successfully")
            
            # Public client - for regular auth operations
            self.public_client: Client = create_client(self.supabase_url, self.anon_key)
            logger.info("✅ Supabase public client initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase clients: {e}")
            raise
        
        logger.info("Supabase auth service initialized with dual clients")

    async def get_user_from_token(self, token: str) -> Dict[str, Any]:
        """Get user information from access token - uses public client"""
        try:
            # Use the public client to get user from token
            user_response = self.public_client.auth.get_user(token)
            
            if user_response.user:
                return {
                    "success": True,
                    "user": user_response.user,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid token or user not found",
                    "user": None
                }
                
        except Exception as e:
            logger.error(f"Failed to get user from token: {e}")
            return {
                "success": False,
                "error": str(e),
                "user": None
            }

    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """
        Sign in user with email and password - uses public client
        """
        try:
            if not email or not password:
                return {
                    "success": False,
                    "error": "Email and password are required",
                    "session": None,
                    "user": None
                }
            
            # Use public client for regular sign in
            auth_response = self.public_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if auth_response.user and auth_response.session:
                return {
                    "success": True,
                    "session": auth_response.session,
                    "user": auth_response.user,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid credentials",
                    "session": None,
                    "user": None
                }
                    
        except Exception as e:
            logger.error(f"Supabase sign-in error: {e}")
            
            # Handle common Supabase errors
            error_message = str(e).lower()
            if "invalid" in error_message or "credentials" in error_message:
                friendly_error = "Invalid email or password"
            elif "rate" in error_message or "too many" in error_message:
                friendly_error = "Too many login attempts. Please try again later."
            elif "email not confirmed" in error_message:
                friendly_error = "Please confirm your email address"
            else:
                friendly_error = "Authentication failed"
            
            return {
                "success": False,
                "error": friendly_error,
                "session": None,
                "user": None
            }

    async def delete_user(self, user_id: str) -> Dict[str, Any]:
        """Delete a user from Supabase - uses admin client"""
        try:
            # Use admin client to delete user
            response = self.admin_client.auth.admin.delete_user(user_id)
            logger.info(f"✅ Deleted Supabase user: {user_id}")
            return {"success": True, "response": response}
        except Exception as e:
            logger.error(f"❌ Failed to delete Supabase user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    async def update_user_metadata(self, user_id: str, additional_metadata: dict) -> Dict[str, Any]:
        """Update user metadata in Supabase - uses admin client"""
        try:
            # Get current user metadata using admin client
            user_response = self.admin_client.auth.admin.get_user_by_id(user_id)
            
            if not user_response.user:
                return {"success": False, "error": "User not found"}
            
            # Merge existing metadata with new metadata
            current_metadata = user_response.user.user_metadata or {}
            updated_metadata = {**current_metadata, **additional_metadata}
            
            # Update user metadata using admin client
            update_response = self.admin_client.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": updated_metadata}
            )
            
            return {
                "success": True,
                "user": update_response.user,
                "metadata": updated_metadata
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to update user metadata: {e}")
            return {"success": False, "error": str(e)}
        
    async def get_user_metadata(self, user_id: str) -> Dict[str, Any]:
        """Get user metadata from Supabase - uses admin client"""
        try:
            user_response = self.admin_client.auth.admin.get_user_by_id(user_id)
            
            if not user_response.user:
                return {"success": False, "error": "User not found"}
            
            return {
                "success": True,
                "user": user_response.user,
                "metadata": user_response.user.user_metadata or {}
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get user metadata: {e}")
            return {"success": False, "error": str(e)}

    async def create_user(self, email: str, password: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create a new user account - uses admin client
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
            
            # Use admin client to create user
            auth_response = self.admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "user_metadata": metadata or {},
                "email_confirm": True  # Auto-confirm email for admin-created users
            })
            
            if auth_response.user:
                return {
                    "success": True,
                    "user": auth_response.user,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create user"
                }
                    
        except Exception as e:
            # Log the raw, detailed error message from Supabase
            logger.error(f"❌ Supabase create_user raw error: {e}")
            
            # Handle common Supabase errors
            error_message = str(e).lower()
            if "already registered" in error_message or "email" in error_message:
                friendly_error = "Email already registered"
            elif "password" in error_message:
                friendly_error = "Invalid password format"
            elif "rate" in error_message:
                friendly_error = "Too many registration attempts"
            else:
                # Pass the raw error through for better debugging
                friendly_error = str(e)
            
            return {
                "success": False,
                "error": friendly_error
            }

    # 📧 NEW: Email confirmation methods
    async def create_user_with_confirmation(
        self, 
        email: str, 
        password: str,
        confirmation_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create user with email confirmation required"""
        try:
            logger.info(f"📧 Creating user with email confirmation: {email}")
            
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
            
            # Create user with email confirmation enabled (unconfirmed initially)
            auth_response = self.admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": False,  # Important: User starts unconfirmed
                "user_metadata": metadata or {},
                "app_metadata": {
                    "provider": "email",
                    "providers": ["email"]
                }
            })
            
            if auth_response.user:
                logger.info(f"✅ User created successfully (unconfirmed): {auth_response.user.id}")
                
                # Send confirmation email
                confirmation_result = await self.send_confirmation_email(
                    email=email,
                    confirmation_url=confirmation_url
                )
                
                if not confirmation_result["success"]:
                    logger.warning(f"⚠️ User created but confirmation email failed: {confirmation_result.get('error')}")
                
                return {
                    "success": True,
                    "user": auth_response.user,
                    "confirmation_email_sent": confirmation_result["success"],
                    "message": "User created successfully. Please check your email for confirmation link."
                }
            else:
                logger.error("❌ User creation failed - no user returned")
                return {
                    "success": False,
                    "error": "User creation failed"
                }
                
        except Exception as e:
            logger.error(f"❌ Error creating user with confirmation: {str(e)}")
            
            # Handle common Supabase errors
            error_message = str(e).lower()
            if "already registered" in error_message or "email" in error_message:
                friendly_error = "Email already registered"
            elif "password" in error_message:
                friendly_error = "Invalid password format"
            elif "rate" in error_message:
                friendly_error = "Too many registration attempts"
            else:
                friendly_error = str(e)
            
            return {
                "success": False,
                "error": friendly_error
            }
    
    async def send_confirmation_email(
        self, 
        email: str, 
        confirmation_url: str
    ) -> Dict[str, Any]:
        """Send email confirmation link"""
        try:
            logger.info(f"📧 Sending confirmation email to: {email}")
            
            # Use public client to send confirmation email
            response = self.public_client.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "redirect_to": confirmation_url
                }
            })
            
            logger.info(f"✅ Confirmation email sent successfully to: {email}")
            return {
                "success": True,
                "message": "Confirmation email sent successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending confirmation email: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def resend_confirmation_email(
        self, 
        email: str, 
        confirmation_url: str
    ) -> Dict[str, Any]:
        """Resend confirmation email"""
        try:
            logger.info(f"📧 Resending confirmation email to: {email}")
            
            response = self.public_client.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "redirect_to": confirmation_url
                }
            })
            
            logger.info(f"✅ Confirmation email resent successfully to: {email}")
            return {
                "success": True,
                "message": "Confirmation email resent successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error resending confirmation email: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def verify_email_confirmation(self, token: str) -> Dict[str, Any]:
        """Verify email confirmation token and activate user"""
        try:
            logger.info(f"🔍 Verifying email confirmation token...")
            
            # Use public client to verify the token
            verification_response = self.public_client.auth.verify_otp({
                "token_hash": token,
                "type": "email"
            })
            
            if verification_response.user and verification_response.session:
                logger.info(f"✅ Email confirmation successful for user: {verification_response.user.id}")
                
                # Update user to mark as email confirmed using admin client
                try:
                    self.admin_client.auth.admin.update_user_by_id(
                        verification_response.user.id,
                        {"email_confirm": True}
                    )
                    logger.info("✅ User marked as email confirmed")
                except Exception as update_error:
                    logger.warning(f"⚠️ Failed to update email_confirm status: {update_error}")
                
                return {
                    "success": True,
                    "user": verification_response.user,
                    "session": verification_response.session,
                    "message": "Email confirmed successfully"
                }
            else:
                logger.warning("❌ Email confirmation failed - no user or session returned")
                return {
                    "success": False,
                    "error": "Email confirmation failed"
                }
                
        except Exception as e:
            logger.error(f"❌ Error verifying email confirmation: {str(e)}")
            
            # Handle common errors
            error_message = str(e).lower()
            if "invalid" in error_message or "expired" in error_message:
                friendly_error = "Invalid or expired confirmation token"
            elif "already" in error_message:
                friendly_error = "Email already confirmed"
            else:
                friendly_error = "Email confirmation failed"
            
            return {
                "success": False,
                "error": friendly_error
            }



    async def send_password_reset(self, email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
        """
        Send password reset email - uses public client
        """
        try:
            if not email:
                return {
                    "success": False,
                    "error": "Email is required"
                }
            
            # Use public client to send password reset
            options = {}
            if redirect_to:
                options["redirect_to"] = redirect_to
            
            self.public_client.auth.reset_password_for_email(email, options)
            
            return {
                "success": True,
                "error": None,
                "message": "Password reset email sent successfully"
            }
                    
        except Exception as e:
            logger.error(f"❌ Supabase password reset error: {e}")
            
            # Handle common errors
            error_message = str(e).lower()
            if "not found" in error_message:
                friendly_error = "Email not found"
            elif "rate" in error_message:
                friendly_error = "Too many password reset requests"
            else:
                friendly_error = "Failed to send password reset email"
            
            return {
                "success": False,
                "error": friendly_error
            }
        
    async def reset_password(self, email: str, redirect_to: Optional[str] = None) -> Dict[str, Any]:
        """Alias for send_password_reset for backward compatibility"""
        return await self.send_password_reset(email, redirect_to)

    async def verify_reset_token(self, token: str, new_password: str) -> Dict[str, Any]:
        """Alias for verify_password_reset for backward compatibility"""
        return await self.verify_password_reset(token, new_password)

    async def verify_password_reset(self, token: str, new_password: str):
        """
        Simple password reset using admin API - uses admin client
        """
        try:
            # Decode token to get user ID
            import jwt
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get('sub')
            user_email = decoded.get('email')
            
            if not user_id:
                return {
                    "success": False,
                    "error": "Invalid token - no user ID found"
                }
            
            logger.info(f"🔄 Updating password for user: {user_email}")
            
            # Use admin client directly
            admin_response = self.admin_client.auth.admin.update_user_by_id(
                uid=user_id,
                attributes={"password": new_password}
            )
            
            if admin_response.user:
                logger.info("✅ Password updated successfully")
                return {
                    "success": True,
                    "user": admin_response.user,
                    "message": "Password reset successful"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to update password"
                }
                
        except Exception as e:
            logger.error(f"❌ Password reset error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }



    async def create_user_with_otp(self, email: str, password: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create user and send OTP for email verification"""
        try:
            # Create user without email confirmation
            auth_response = self.admin_client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": False,
                "user_metadata": metadata or {}
            })
            
            if auth_response.user:
                # Send OTP
                otp_response = self.public_client.auth.sign_in_with_otp({
                    "email": email,
                    "options": {
                        "should_create_user": False
                    }
                })
                
                return {
                    "success": True,
                    "user": auth_response.user,
                    "message": "User created and OTP sent"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create user"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def verify_otp(self, email: str, otp: str) -> Dict[str, Any]:
        """Verify OTP and return user session"""
        try:
            verification_response = self.public_client.auth.verify_otp({
                "email": email,
                "token": otp,
                "type": "email"
            })
            
            if verification_response.user and verification_response.session:
                return {
                    "success": True,
                    "user": verification_response.user,
                    "session": verification_response.session
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid OTP"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def resend_otp(self, email: str) -> Dict[str, Any]:
        """Resend OTP to email"""
        try:
            response = self.public_client.auth.sign_in_with_otp({
                "email": email,
                "options": {"should_create_user": False}
            })
            
            return {
                "success": True,
                "message": "OTP resent successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }








def check_supabase_config() -> bool:
    """
    Check if Supabase configuration is valid
    
    Returns:
        bool: True if both URL and both keys are configured, False otherwise
    """
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    
    return bool(supabase_url and service_key and anon_key)



 


# Create the global service instance
try:
    supabase_auth_service = SupabaseAuthService()
    logger.info("✅ Supabase auth service created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create Supabase service: {e}")
    supabase_auth_service = None