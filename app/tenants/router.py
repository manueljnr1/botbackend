import os
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import PyJWTError as JWTError
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import Request
from fastapi import File, UploadFile
from typing import List, Optional
from pydantic import BaseModel,  EmailStr
from pydantic import field_validator
from app.core.security import get_password_hash
from fastapi_limiter.depends import RateLimiter
import uuid
import time
from collections import defaultdict
import asyncio
from app.database import get_db
from app.tenants.models import Tenant
from app.admin.models import Admin
from app.auth.models import User # For admin-only endpoints
from app.auth.router import get_current_user, get_admin_user # For admin-only endpoints
from app.auth.models import TenantCredentials
from app.config import settings
from app.tenants.models import TenantPasswordReset
from app.admin.models import Admin
from base64 import b64decode
import io
from PIL import Image

from app.auth.supabase_service import supabase_auth_service
from app.services.storage import LogoUploadService
from app.tenants.api_key_service import EnhancedAPIKeyResetService, get_enhanced_api_key_reset_service
from app.tenants.secure_id_service import get_secure_tenant_id_service


import logging
logger = logging.getLogger(__name__)
rate_limit_storage = defaultdict(list)
admin_rate_limit_storage = defaultdict(list)

try:
    from app.pricing.service import PricingService
    PRICING_AVAILABLE = True
except ImportError as e:
    PRICING_AVAILABLE = False

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="tenants/login-legacy")

def get_tenant_from_api_key(api_key: str, db: Session) -> Tenant:
    """Retrieve an active tenant using the provided API key."""
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or inactive tenant")
    return tenant

router = APIRouter()

# Pydantic models
class TenantCreate(BaseModel):
    name: str
    business_name: str
    description: Optional[str] = None
    password: str
    email: str
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        if v:
            return v.lower().strip()
        return v

class TenantLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    tenant_id: Optional[int]
    tenant_name: Optional[str]
    expires_at: datetime    
    api_key: Optional[str]
    is_admin: bool = False
    admin_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    system_prompt: Optional[str] = None

class TenantOut(BaseModel):
    id: int
    name: str
    business_name: str
    description: Optional[str] = None
    api_key: str
    is_active: bool
    system_prompt: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True

class TenantForgotPasswordRequest(BaseModel):
    email: str
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        if v:
            return v.lower().strip()
        return v

class TenantResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

class MessageResponse(BaseModel):
    message: str

class TenantEmailConfig(BaseModel):
    feedback_email: Optional[str] = None
    enable_feedback_system: bool = True

class SupabaseLoginRequest(BaseModel):
    email: str
    password: str
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        if v:
            return v.lower().strip()
        return v

class SupabaseTokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime
    user_id: str
    email: str
    tenant_id: Optional[int]
    tenant_name: Optional[str]
    api_key: Optional[str]
    is_admin: Optional[bool] = False 


class TenantEmailConfigUpdate(BaseModel):
    feedback_email: Optional[EmailStr] = None
    enable_feedback_system: Optional[bool] = None
    feedback_notification_enabled: Optional[bool] = None



class BrandingUpdate(BaseModel):
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    text_color: Optional[str] = None
    background_color: Optional[str] = None
    user_bubble_color: Optional[str] = None
    bot_bubble_color: Optional[str] = None
    border_color: Optional[str] = None
    logo_image_url: Optional[str] = None
    logo_text: Optional[str] = None
    border_radius: Optional[str] = None
    widget_position: Optional[str] = None
    font_family: Optional[str] = None
    custom_css: Optional[str] = None



class LogoUploadRequest(BaseModel):
    file_data: str  # Base64 encoded file data
    filename: Optional[str] = None
    content_type: Optional[str] = None



class EnhancedAPIKeyResetRequest(BaseModel):
    current_api_key: str
    password: str  # 🔒 NEW: Account password required
    reason: Optional[str] = None

class APIKeyResetResponse(BaseModel):
    success: bool
    message: str
    new_api_key: Optional[str] = None
    old_api_key_masked: Optional[str] = None
    reset_timestamp: Optional[str] = None
    verification_method: Optional[str] = None
    error: Optional[str] = None

class APIKeyInfoResponse(BaseModel):
    success: bool
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    api_key_masked: Optional[str] = None
    last_updated: Optional[str] = None
    tenant_active: Optional[bool] = None
    authentication_methods: Optional[dict[str, bool]] = None
    error: Optional[str] = None

class HeaderBasedResetRequest(BaseModel):
    password: str  # 🔒 NEW: Password required even for header-based reset
    reason: Optional[str] = None



# Rate limiting

def check_rate_limit(identifier: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    """Simple rate limiting check"""
    now = time.time()
    window_seconds = window_minutes * 60
    
    rate_limit_storage[identifier] = [
        timestamp for timestamp in rate_limit_storage[identifier] 
        if now - timestamp < window_seconds
    ]
    
    if len(rate_limit_storage[identifier]) >= max_attempts:
        return False
    
    rate_limit_storage[identifier].append(now)
    return True

def check_admin_rate_limit(email: str, max_attempts: int = 3, window_minutes: int = 10) -> bool:
    """Enhanced rate limiting specifically for admin logins"""
    now = time.time()
    window_seconds = window_minutes * 60
    
    admin_rate_limit_storage[email] = [
        timestamp for timestamp in admin_rate_limit_storage[email] 
        if now - timestamp < window_seconds
    ]
    
    if len(admin_rate_limit_storage[email]) >= max_attempts:
        return False
    
    admin_rate_limit_storage[email].append(now)
    return True


def verify_password(plain_password, hashed_password):
    """Verify password against the hashed version"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT token for the tenant"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")
    
    return encoded_jwt, expire


async def cleanup_supabase_user(user_id: str):
    """Clean up orphaned Supabase user"""
    logger.info(f"🧹 Cleaning up Supabase user: {user_id}")
    try:
        # Use the delete method if it exists, otherwise log the issue
        if hasattr(supabase_auth_service, 'delete_user'):
            result = await supabase_auth_service.delete_user(user_id)
            if result["success"]:
                logger.info("✅ Supabase user cleaned up")
            else:
                logger.error(f"❌ Failed to cleanup: {result.get('error')}")
        else:
            logger.warning("⚠️ Delete method not available - user remains in Supabase")
            logger.info(f"Manual cleanup needed for Supabase user: {user_id}")
    except Exception as cleanup_error:
        logger.error(f"❌ Failed to cleanup Supabase user: {cleanup_error}")


async def get_current_tenant(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get the current tenant from a token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        tenant_id: int = payload.get("sub")
        
        if tenant_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if tenant is None:
        raise credentials_exception
    
    return tenant

async def get_current_tenant_supabase(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """Clean Supabase auth with email field"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        if not authorization.startswith("Bearer "):
            raise credentials_exception
        
        token = authorization.split(" ")[1]
        
        supabase_result = await supabase_auth_service.get_user_from_token(token)
        
        if not supabase_result["success"]:
            raise credentials_exception
        
        user = supabase_result["user"]
        
        # Direct field access
        tenant = db.query(Tenant).filter(
            func.lower(Tenant.email) == user.email.lower(),
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tenant found for this user"
            )
        
        return tenant
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise credentials_exception

async def get_current_user_hybrid(
    authorization: str = Header(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Hybrid auth: Try Supabase first, fallback to traditional JWT"""
    if authorization and authorization.startswith("Bearer "):
        try:
            return await get_current_tenant_supabase(authorization, db)
        except HTTPException:
            pass
    
    try:
        return await get_current_user_or_admin(token, db)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user_or_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get current user (either admin or tenant)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        is_admin = payload.get("is_admin", False)
        
        if user_id is None:
            raise credentials_exception
            
        if is_admin:
            admin = db.query(Admin).filter(Admin.id == user_id, Admin.is_active == True).first()
            if admin is None:
                raise credentials_exception
            
            class AdminUser:
                def __init__(self, admin):
                    self.id = admin.id
                    self.username = admin.username
                    self.email = admin.email
                    self.is_admin = True
                    self.tenant_id = None
                    self.is_active = True
            return AdminUser(admin)
        else:
            tenant = db.query(Tenant).filter(Tenant.id == user_id, Tenant.is_active == True).first()
            if tenant is None:
                raise credentials_exception
            
            user = db.query(User).filter(User.tenant_id == tenant.id, User.is_active == True).first()
            if user is None:
                class TenantUser:
                    def __init__(self, tenant):
                        self.id = f"tenant_{tenant.id}"
                        self.username = tenant.name
                        self.email = tenant.email
                        self.is_admin = False
                        self.tenant_id = tenant.id
                        self.is_active = tenant.is_active
                return TenantUser(tenant)
            return user
            
    except JWTError:
        raise credentials_exception







@router.post("/register", response_model=TenantOut)
async def register_tenant_enhanced(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Tenant Registration with secure random ID - UPDATED VERSION"""
    
    supabase_user_id = None
    
    try:
        logger.info(f"Starting registration for: {tenant.name} ({tenant.email}) - Business: {tenant.business_name}")
        
        # Step 1: Validate inputs
        normalized_email = tenant.email.lower().strip()
        existing_email = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email
        ).first()
        if existing_email:
            logger.warning(f"Email already registered: {tenant.email}")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        existing_name = db.query(Tenant).filter(Tenant.name == tenant.name).first()
        if existing_name:
            logger.warning(f"Username already taken: {tenant.name}")
            raise HTTPException(status_code=400, detail="Username already taken")
        
        logger.info("Input validation passed")
        
        # 🔒 NEW STEP 2: Generate secure tenant ID (REPLACES automatic ID)
        secure_id_service = get_secure_tenant_id_service(db)
        secure_tenant_id = secure_id_service.generate_unique_tenant_id()
        logger.info(f"Generated secure tenant ID: {secure_tenant_id}")
        
        # Step 3: Generate API key  
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        logger.info(f"Generated API key: {api_key[:15]}...")
        
        # Step 4: Create Supabase user with business info
        logger.info("Creating Supabase user...")
        supabase_result = await supabase_auth_service.create_user(
            email=normalized_email,
            password=tenant.password,
            metadata={
                "display_name": tenant.name,
                "full_name": tenant.name,
                "tenant_name": tenant.name,
                "business_name": tenant.business_name,
                "tenant_description": tenant.description or "",
                "role": "tenant_admin",
                "account_type": "tenant",
                "api_key": api_key,
                "tenant_id": secure_tenant_id,  # 🔒 INCLUDE SECURE ID
                "registration_date": datetime.utcnow().isoformat(),
                "tenant_status": "active"
            }
        )
        
        if not supabase_result["success"]:
            logger.error(f"Supabase user creation failed: {supabase_result.get('error')}")
            raise HTTPException(
                status_code=400, 
                detail=f"Account creation failed: {supabase_result.get('error')}"
            )
        
        supabase_user_id = supabase_result["user"].id
        logger.info(f"Supabase user created: {supabase_user_id}")
        
        # 🔒 STEP 5: Create local tenant with SECURE ID (MOST IMPORTANT CHANGE)
        logger.info("Creating local tenant record...")
        new_tenant = Tenant(
            id=secure_tenant_id,  # 🔒 USE SECURE ID INSTEAD OF AUTO-INCREMENT
            name=tenant.name,
            business_name=tenant.business_name,
            email=normalized_email,
            description=tenant.description,
            api_key=api_key,
            is_active=True,
            supabase_user_id=supabase_user_id
        )
        
        db.add(new_tenant)
        db.commit()  # Commit immediately after creating tenant
        db.refresh(new_tenant)  # Refresh to get the ID
        logger.info(f"Local tenant created with SECURE ID: {new_tenant.id}")
        
        # Step 6: Update Supabase with tenant ID (separate transaction)
        logger.info("Updating Supabase with tenant ID...")
        try:
            update_result = await supabase_auth_service.update_user_metadata(
                user_id=supabase_user_id,
                additional_metadata={
                    "tenant_id": new_tenant.id,
                    "database_tenant_id": str(new_tenant.id),
                    "tenant_created_at": datetime.utcnow().isoformat()
                }
            )
            
            if update_result["success"]:
                logger.info("Supabase metadata updated")
            else:
                logger.warning(f"Failed to update Supabase metadata: {update_result.get('error')}")
        except Exception as meta_error:
            logger.warning(f"Supabase metadata update failed: {meta_error}")
        
        # Step 7: Create subscription if available (separate transaction)
        if PRICING_AVAILABLE:
            logger.info("Creating subscription...")
            try:
                pricing_service = PricingService(db)
                pricing_service.create_default_plans()
                subscription = pricing_service.create_free_subscription_for_tenant(new_tenant.id)
                
                if subscription:
                    logger.info(f"Subscription created: {subscription.id}")
                else:
                    logger.warning("Subscription creation returned None")
            except Exception as e:
                logger.error(f"Subscription creation failed: {e}")
                # Don't fail the whole registration if subscription fails
        else:
            logger.info("Pricing system not available, skipping subscription")
        
        logger.info(f"Registration successful for: {new_tenant.name} - Business: {new_tenant.business_name} (SECURE ID: {new_tenant.id})")
        return new_tenant
        
    except HTTPException as he:
        logger.error(f"HTTP Exception during registration: {he.detail}")
        db.rollback()  # Rollback on HTTP exceptions
        if supabase_user_id:
            await cleanup_supabase_user(supabase_user_id)
        raise he
        
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        db.rollback()  # Rollback on any exception
        if supabase_user_id:
            await cleanup_supabase_user(supabase_user_id)
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {str(e)}"
        )




@router.post("/login", response_model=SupabaseTokenResponse)
async def login_with_supabase(
    login_data: SupabaseLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Clean login without rate limiting for debugging"""
    try:
        normalized_email = login_data.email.lower().strip()
        client_ip = request.client.host
        
        # Check for admin login first
        admin = db.query(Admin).filter(
            (func.lower(Admin.username) == normalized_email) |
            (func.lower(Admin.email) == normalized_email),
            Admin.is_active == True
        ).first()
        
        if admin:
            logger.info(f"Admin found: {admin.username}, checking password...")
            password_valid = verify_password(login_data.password, admin.hashed_password)
            logger.info(f"Password valid: {password_valid}")
            
            if password_valid:
                logger.info(f"Admin login successful: {admin.username} ({admin.email}) from {client_ip}")
                
                access_token, expires_at = create_access_token(
                    data={
                        "sub": str(admin.id), 
                        "is_admin": True,
                        "login_ip": client_ip,
                        "login_time": datetime.utcnow().isoformat()
                    },
                    expires_delta=timedelta(minutes=30)
                )
                
                return {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_at": expires_at,
                    "user_id": str(admin.id),
                    "email": admin.email,
                    "tenant_id": None,
                    "tenant_name": None,  # Admins don't have tenant names
                    "api_key": None,
                    "is_admin": True  # Add this field for admin identification
                }
            else:
                logger.warning(f"Failed admin login (wrong password): {normalized_email} from {client_ip}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
        else:
            logger.info(f"No admin found for email: {normalized_email}")
        
        # If no admin found or admin login failed, try tenant login
        logger.info(f"Attempting tenant login for: {normalized_email}")
        
        supabase_result = await supabase_auth_service.sign_in(
            email=normalized_email,
            password=login_data.password
        )
        
        if not supabase_result["success"]:
            logger.warning(f"Failed tenant login: {normalized_email} from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        tenant = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            logger.error(f"Tenant not found after successful Supabase auth: {normalized_email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tenant found with this email address"
            )
        
        logger.info(f"Tenant login successful: {tenant.name} ({tenant.email}) from {client_ip}")
        
        session = supabase_result["session"]
        user = supabase_result["user"]
        
        return {
            "access_token": session.access_token,
            "token_type": "bearer",
            "expires_at": datetime.fromtimestamp(session.expires_at),
            "user_id": user.id,
            "email": user.email,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "api_key": tenant.api_key,
            "is_admin": False  # Add this for tenant responses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e} for {login_data.email} from {getattr(request.client, 'host', 'unknown')}")
        raise HTTPException(status_code=500, detail="Login failed")




@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password_supabase(
    request: TenantForgotPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Enhanced password reset - always try Supabase"""
    
    normalized_email = str(request.email).strip().lower()
    standard_message = "If your account exists in our system, you will receive a password reset link."
    
    try:
        # Check if tenant exists locally (for logging)
        tenant = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email,
            Tenant.is_active == True
        ).first()
        
        if tenant:
            logger.info(f"Password reset for existing tenant: {tenant.name}")
        else:
            logger.info(f"Password reset attempted for email not in tenant DB: {normalized_email[:3]}***@{normalized_email.split('@')[1]}")
        
        # ALWAYS try Supabase regardless of local tenant existence
        redirect_to = settings.get_password_reset_url()
        
        result = await supabase_auth_service.send_password_reset(
            email=request.email,  # Use original email (not normalized)
            redirect_to=redirect_to
        )
        
        if result["success"]:
            logger.info(f"✅ Supabase password reset sent for: {normalized_email[:3]}***")
        else:
            logger.warning(f"❌ Supabase password reset failed: {result.get('error')}")
        
    except Exception as e:
        logger.error(f"Password reset error: {e}")
    
    # Always return the same message for security
    return {"message": standard_message}



@router.post("/reset-password", response_model=MessageResponse)
async def tenant_reset_password_supabase(
    request: TenantResetPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Reset password using Supabase token with confirmation"""
    
    try:
        # Step 1: Validate passwords match
        if request.new_password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match."
            )
        
        # Step 2: Basic password validation
        if len(request.new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long."
            )
        
        logger.info(f"🔄 Processing password reset with token: {request.token[:20]}...")
        
        # Step 3: Call the Supabase service
        result = await supabase_auth_service.verify_password_reset(
            token=request.token, 
            new_password=request.new_password
        )
        
        if not result["success"]:
            logger.warning(f"❌ Password reset failed: {result.get('error')}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Invalid or expired reset token")
            )
        
        logger.info("✅ Password reset successful")
        
        # Step 4: Update local tenant credentials if needed
        if result.get("user"):
            user_email = result["user"].email
            if user_email:
                tenant = db.query(Tenant).filter(
                    func.lower(Tenant.email) == user_email.lower()
                ).first()
                
                if tenant:
                    # Update local credentials for legacy compatibility
                    credentials = db.query(TenantCredentials).filter(
                        TenantCredentials.tenant_id == tenant.id
                    ).first()
                    
                    if credentials:
                        credentials.hashed_password = get_password_hash(request.new_password)
                    else:
                        credentials = TenantCredentials(
                            tenant_id=tenant.id,
                            hashed_password=get_password_hash(request.new_password)
                        )
                        db.add(credentials)
                    
                    db.commit()
                    logger.info(f"✅ Local password updated for tenant: {tenant.name}")
        
        return {"message": "Password reset successfully. You can now log in with your new password."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error during password reset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed. Please try again or request a new reset link."
        )





# CRUD endpoints
@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: int, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Get a specific tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Authorization logic
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        pass
    elif hasattr(current_user, 'id') and current_user.id == tenant_id:
        pass
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view this tenant")
    
    return tenant



@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: int, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Deletes a tenant from PostgreSQL and Supabase (Admin only)"""
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Step 1: Delete the user from Supabase first
    if tenant.supabase_user_id:
        logger.info(f"Attempting to delete user {tenant.supabase_user_id} from Supabase.")
        delete_result = await supabase_auth_service.delete_user(tenant.supabase_user_id) #
        if not delete_result["success"]:
            # Decide if you want to stop or continue if Supabase deletion fails
            logger.error(f"Could not delete user from Supabase: {delete_result.get('error')}")
            # Optionally, you could raise an exception here
            # raise HTTPException(status_code=500, detail="Failed to delete user from authentication service.")
    
    # Step 2: Delete the user from your PostgreSQL database
    logger.info(f"Deleting tenant {tenant.id} from PostgreSQL.")
    db.delete(tenant)
    db.commit()

    return {"message": "Tenant permanently deleted from all systems successfully"}






# Subscription endpoints (if pricing available)
@router.post("/{tenant_id}/create-subscription")
async def create_tenant_subscription(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Manually create a Free subscription for a tenant (Admin only)"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if not PRICING_AVAILABLE:
        raise HTTPException(status_code=500, detail="Pricing system not available")
    
    try:
        pricing_service = PricingService(db)
        existing_subscription = pricing_service.get_tenant_subscription(tenant_id)
        
        if existing_subscription:
            return {
                "message": f"Tenant {tenant.name} already has an active subscription",
                "plan": existing_subscription.plan.name,
                "status": existing_subscription.status
            }
        
        subscription = pricing_service.create_free_subscription_for_tenant(tenant_id)
        
        return {
            "message": f"Successfully created Free subscription for {tenant.name}",
            "plan": subscription.plan.name,
            "conversations_limit": subscription.plan.max_messages_monthly,
            "billing_cycle": subscription.billing_cycle
        }
        
    except Exception as e:
        logger.error(f"Error creating subscription for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")

@router.get("/{tenant_id}/subscription-status")
async def get_tenant_subscription_status(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Enhanced subscription status check with detailed information"""
    if not current_user.is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    try:
        if not PRICING_AVAILABLE:
            return {
                "tenant_name": tenant.name,
                "has_subscription": False,
                "message": "Pricing system not available",
                "pricing_system_enabled": False
            }
        
        pricing_service = PricingService(db)
        subscription = pricing_service.get_tenant_subscription(tenant_id)
        
        if subscription and subscription.plan:
            usage_stats = pricing_service.get_usage_stats(tenant_id)
            return {
                "tenant_name": tenant.name,
                "tenant_id": tenant_id,
                "has_subscription": True,
                "subscription_id": subscription.id,
                "plan": {
                    "name": subscription.plan.name,
                    "type": subscription.plan.plan_type,
                    "conversations_limit": subscription.plan.max_messages_monthly,
                    "price_monthly": float(subscription.plan.price_monthly)
                },
                "status": subscription.status,
                "billing_cycle": subscription.billing_cycle,
                "usage": {
                    "conversations_used": usage_stats.messages_used,
                    "conversations_limit": usage_stats.messages_limit,
                    "conversations_remaining": usage_stats.messages_limit - usage_stats.messages_used,
                    "integrations_used": usage_stats.integrations_used,
                    "integrations_limit": usage_stats.integrations_limit,
                    "can_start_conversations": usage_stats.can_send_messages,
                    "can_add_integrations": usage_stats.can_add_integrations
                },
                "period": {
                    "start": subscription.current_period_start.isoformat(),
                    "end": subscription.current_period_end.isoformat()
                },
                "pricing_system_enabled": True
            }
        else:
            return {
                "tenant_name": tenant.name,
                "tenant_id": tenant_id,
                "has_subscription": False,
                "message": "No active subscription found",
                "pricing_system_enabled": True,
                "can_create_subscription": True
            }
            
    except Exception as e:
        logger.error(f"Error getting subscription status for tenant {tenant_id}: {e}")
        return {
            "tenant_name": tenant.name,
            "tenant_id": tenant_id,
            "has_subscription": False,
            "error": str(e),
            "pricing_system_enabled": PRICING_AVAILABLE
        }

@router.post("/fix-all-subscriptions")
async def fix_all_tenant_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Manual endpoint to fix all tenants without subscriptions (Admin only)"""
    try:
        from app.pricing.models import TenantSubscription
        
        tenants_without_subscriptions = db.query(Tenant).outerjoin(
            TenantSubscription,
            (Tenant.id == TenantSubscription.tenant_id) & (TenantSubscription.is_active == True)
        ).filter(
            TenantSubscription.id.is_(None),
            Tenant.is_active == True
        ).all()
        
        if not tenants_without_subscriptions:
            return {
                "message": "All tenants already have subscriptions",
                "tenants_fixed": 0,
                "total_tenants": db.query(Tenant).filter(Tenant.is_active == True).count()
            }
        
        if not PRICING_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="Pricing system not available"
            )
        
        pricing_service = PricingService(db)
        pricing_service.create_default_plans()
        
        fixed_tenants = []
        failed_tenants = []
        
        for tenant in tenants_without_subscriptions:
            try:
                subscription = pricing_service.create_free_subscription_for_tenant(tenant.id)
                
                if subscription:
                    fixed_tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "plan": subscription.plan.name,
                        "subscription_id": subscription.id
                    })
                else:
                    failed_tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "error": "Subscription creation returned None"
                    })
                    
            except Exception as e:
                logger.error(f"Error creating subscription for {tenant.name}: {e}")
                failed_tenants.append({
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "error": str(e)
                })
        
        return {
            "message": f"Fixed {len(fixed_tenants)} out of {len(tenants_without_subscriptions)} tenants",
            "tenants_fixed": len(fixed_tenants),
            "tenants_failed": len(failed_tenants),
            "fixed_tenants": fixed_tenants,
            "failed_tenants": failed_tenants if failed_tenants else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in fix_all_tenant_subscriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix subscriptions: {str(e)}")

# Email configuration endpoints
@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: int, 
    tenant_update: TenantUpdate, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Update tenant - clean and simple"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Authorization logic
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        pass
    elif hasattr(current_user, 'id') and current_user.id == tenant_id:
        pass
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Apply updates directly - no field mapping
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)  # Direct assignment
    
    db.commit()
    db.refresh(tenant)
    return tenant  # Direct return


@router.get("/{tenant_id}/email-config")
async def get_tenant_email_config(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get tenant email configuration - UPDATED"""
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "feedback_email": tenant.feedback_email,
        "from_email": os.getenv("FROM_EMAIL", "feedback@agentlyra.com"),  # ✅ Centralized
        "feedback_enabled": getattr(tenant, 'enable_feedback_system', True),
        "email_system_available": bool(os.getenv('RESEND_API_KEY')),
        "note": "from_email is managed centrally"
    }

# 2. ADD this new PUT endpoint 
@router.put("/{tenant_id}/email-config")
async def update_tenant_email_config(
    tenant_id: int,
    config_update: TenantEmailConfigUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update tenant email configuration - NEW"""
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    try:
        # Update only the fields tenants can control
        if config_update.feedback_email is not None:
            tenant.feedback_email = config_update.feedback_email
        
        if config_update.enable_feedback_system is not None:
            tenant.enable_feedback_system = config_update.enable_feedback_system
        
        db.commit()
        db.refresh(tenant)
        
        return {
            "success": True,
            "message": "Email configuration updated successfully",
            "config": {
                "feedback_email": tenant.feedback_email,
                "from_email": os.getenv("FROM_EMAIL", "feedback@agentlyra.com"),  # Read-only
                "enable_feedback_system": tenant.enable_feedback_system
            }
        }
        
    except Exception as e:
        logger.error(f"Error updating email config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update configuration")


@router.put("/{tenant_id}/prompt", response_model=TenantOut)
async def update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict,  # Expects {"system_prompt": "new prompt"}
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Update a tenant's system prompt with security validation using API key.
    Returns the updated tenant details.
    """
    from app.chatbot.security import validate_and_sanitize_tenant_prompt  # Add this import
    
    tenant = get_tenant_from_api_key(api_key, db)
    
    if tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="API key does not match tenant ID"
        )
    
    new_system_prompt = prompt_data.get("system_prompt")
    if new_system_prompt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="system_prompt field is required in request body"
        )

    # 🔒 NEW: Add security validation
    sanitized_prompt, is_valid, issues = validate_and_sanitize_tenant_prompt(new_system_prompt)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt contains security issues: {', '.join(issues)}"
        )

    # Update with sanitized prompt
    tenant.system_prompt = sanitized_prompt
    tenant.system_prompt_validated = True  # Mark as validated
    tenant.system_prompt_updated_at = datetime.utcnow()  # Add timestamp
    
    db.commit()
    db.refresh(tenant)
    
    was_sanitized = sanitized_prompt != new_system_prompt
    logger.info(f"✅ Updated system prompt for tenant {tenant.name} (ID: {tenant.id}). Sanitized: {was_sanitized}")
    
    return tenant



def normalize_email(email: str) -> str:
    """Utility function to normalize email addresses"""
    if not email:
        return email
    return email.lower().strip()

def emails_match(email1: str, email2: str) -> bool:
    """Utility function to compare emails case-insensitively"""
    if not email1 or not email2:
        return False
    return normalize_email(email1) == normalize_email(email2)




@router.put("/{tenant_id}/branding")
async def update_tenant_branding(
    tenant_id: int,
    branding_update: BrandingUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update tenant branding configuration"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    # Validate colors
    color_fields = [
        'primary_color', 'secondary_color', 'text_color', 
        'background_color', 'user_bubble_color', 'bot_bubble_color', 'border_color'
    ]
    
    update_data = branding_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field in color_fields and value:
            if not validate_hex_color(value):
                raise HTTPException(status_code=400, detail=f"Invalid color format for {field}")
        
        setattr(tenant, field, value)
    
    tenant.branding_updated_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "message": "Branding updated successfully"}

def validate_hex_color(color: str) -> bool:
    """Validate hex color format"""
    import re
    return bool(re.match(r'^#[0-9A-Fa-f]{6}$', color))





@router.post("/{tenant_id}/upload-logo")
async def upload_tenant_logo(
    tenant_id: int,
    upload_data: LogoUploadRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        # Decode base64 data
        try:
            # Remove data URL prefix if present (data:image/png;base64,)
            file_data = upload_data.file_data
            if file_data.startswith('data:'):
                file_data = file_data.split(',')[1]
            
            file_content = b64decode(file_data)
            file_size = len(file_content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 data: {str(e)}")
        
        # Handle missing filename
        filename = upload_data.filename or "logo"
        
        # Handle missing content_type
        content_type = upload_data.content_type
        if not content_type:
            # Try to detect from base64 data
            if upload_data.file_data.startswith('/9j/'):
                content_type = "image/jpeg"
            elif upload_data.file_data.startswith('iVBOR'):
                content_type = "image/png"
            else:
                content_type = "image/jpeg"  # default
        
        # Validate file size
        max_size = 2 * 1024 * 1024  # 2MB
        if file_size > max_size:
            max_mb = max_size / (1024*1024)
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Maximum size: {max_mb:.1f}MB"
            )
        
        # Validate content type (only check once)
        allowed_types = [
            "image/jpeg", "image/jpg", "image/png", 
            "image/webp", "image/svg+xml"
        ]
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Validate it's actually an image (except SVG)
        if content_type != "image/svg+xml":
            try:
                Image.open(io.BytesIO(file_content))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid image file")
        
        # Create a mock UploadFile object for the service
        class MockUploadFile:
            def __init__(self, content, filename, content_type):
                self.file = io.BytesIO(content)
                self.filename = filename
                self.content_type = content_type
                self.size = len(content)
            
            async def read(self):
                self.file.seek(0)
                return self.file.read()
        
        mock_file = MockUploadFile(file_content, filename, content_type)
        
        # Initialize logo service
        logo_service = LogoUploadService()
        
        # Delete old logo if exists
        if tenant.logo_image_url:
            try:
                await logo_service.delete_logo(tenant.logo_image_url)
            except Exception as e:
                logger.warning(f"Failed to delete old logo: {e}")
        
        # Upload new logo
        success, message, logo_url = await logo_service.upload_logo(tenant_id, mock_file)
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        # Update tenant record
        tenant.logo_image_url = logo_url
        tenant.branding_updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": message,
            "logo_url": logo_url,
            "tenant_id": tenant_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logo upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/{tenant_id}/test-logo-service")
async def test_logo_service(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Test if LogoUploadService can be created"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        # Test service creation
        logger.info("Testing LogoUploadService creation...")
        logo_service = LogoUploadService()
        
        # Test settings
        settings_info = {
            "service_created": True,
            "max_size": logo_service.max_size,
            "max_size_mb": logo_service.max_size / (1024*1024),
            "allowed_types": logo_service.allowed_types,
            "bucket_name": logo_service.bucket_name,
            "supabase_url": bool(settings.SUPABASE_URL),
            "supabase_key": bool(settings.SUPABASE_SERVICE_KEY),
        }
        
        # Test Supabase connection
        try:
            buckets = logo_service.supabase.storage.list_buckets()
            settings_info["supabase_connection"] = "success"
            settings_info["buckets_listed"] = len(buckets) if buckets else 0
        except Exception as sb_error:
            settings_info["supabase_connection"] = f"failed: {str(sb_error)}"
        
        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "service_test": settings_info
        }
        
    except Exception as e:
        logger.error(f"Service test failed: {e}")
        import traceback
        logger.error(f"Service test traceback: {traceback.format_exc()}")
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "tenant_id": tenant_id
        }





@router.delete("/{tenant_id}/logo")
async def delete_tenant_logo(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Delete tenant logo - FIXED VERSION"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        if not tenant.logo_image_url:
            raise HTTPException(status_code=404, detail="No logo found to delete")
        
        logo_service = LogoUploadService()
        
        # Delete from storage
        old_url = tenant.logo_image_url
        try:
            deleted = await logo_service.delete_logo(tenant.logo_image_url)
            logger.info(f"Logo deletion from storage: {deleted}")
        except Exception as delete_error:
            logger.warning(f"Storage deletion failed: {delete_error}")
            deleted = False
        
        # Update tenant record regardless (cleanup)
        tenant.logo_image_url = None
        tenant.branding_updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": "Logo deleted successfully",
            "deleted_from_storage": deleted,
            "old_url": old_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logo deletion error: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

@router.get("/{tenant_id}/logo-info")
async def get_tenant_logo_info(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get current logo information - FIXED"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        # Get settings safely
        max_size = getattr(settings, 'MAX_LOGO_SIZE', 2 * 1024 * 1024)
        allowed_types = getattr(settings, 'ALLOWED_LOGO_TYPES', [
            "image/jpeg", "image/jpg", "image/png", 
            "image/webp", "image/svg+xml"
        ])
        
        return {
            "tenant_id": tenant_id,
            "has_logo": bool(tenant.logo_image_url),
            "logo_url": tenant.logo_image_url,
            "logo_text_fallback": tenant.logo_text or (tenant.business_name or tenant.name)[:2].upper(),
            "upload_settings": {
                "max_size_mb": max_size / (1024*1024),
                "allowed_types": allowed_types,
                "recommended_size": "512x512 pixels or smaller",
                "recommended_formats": ["PNG with transparency", "SVG for scalability", "WebP for optimization"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting logo info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get logo information")
    



@router.post("/{tenant_id}/reset-api-key", response_model=APIKeyResetResponse)
async def reset_tenant_api_key_self(
    tenant_id: int,
    reset_request: EnhancedAPIKeyResetRequest,
    db: Session = Depends(get_db)
):
    """
    Reset API key for tenant (self-service) with password verification
    Requires both current API key AND account password for security
    """
    try:
        # Initialize the enhanced service
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Perform the reset with password verification
        result = await api_service.reset_tenant_api_key_with_password(
            tenant_id=tenant_id,
            current_api_key=reset_request.current_api_key,
            password=reset_request.password,  # 🔒 Password verification
            reason=reset_request.reason,
            force=False  # Tenant must provide valid current API key AND password
        )
        
        if result["success"]:
            # Audit the reset with verification method
            api_service.audit_api_key_reset(
                tenant_id=tenant_id,
                reset_by="tenant_self",
                reason=reset_request.reason or "Self-service reset",
                verification_method=result.get("verification_method", "unknown")
            )
            
            logger.info(
                f"🔑 Tenant {tenant_id} successfully reset their API key "
                f"(verified via {result.get('verification_method')})"
            )
        
        return APIKeyResetResponse(**result)
        
    except Exception as e:
        logger.error(f"❌ Error in tenant API key reset: {str(e)}")
        return APIKeyResetResponse(
            success=False,
            error=f"API key reset failed: {str(e)}"
        )

@router.get("/{tenant_id}/api-key-info", response_model=APIKeyInfoResponse)
async def get_tenant_api_key_info_endpoint(
    tenant_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get API key information (masked) for tenant with authentication methods info
    Uses existing API key validation
    """
    try:
        # Validate API key ownership
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        # Get API key info with enhanced details
        api_service = get_enhanced_api_key_reset_service(db)
        result = api_service.get_tenant_api_key_info(tenant_id)
        
        return APIKeyInfoResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting API key info: {str(e)}")
        return APIKeyInfoResponse(
            success=False,
            error=f"Failed to get API key info: {str(e)}"
        )

@router.post("/{tenant_id}/regenerate-api-key")
async def regenerate_api_key_with_current_auth(
    tenant_id: int,
    reset_request: HeaderBasedResetRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Alternative endpoint using header authentication with password verification
    More convenient for authenticated requests but still requires password
    """
    try:
        # Validate API key ownership
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        # Initialize the enhanced service
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Perform the reset with password verification
        result = await api_service.reset_tenant_api_key_with_password(
            tenant_id=tenant_id,
            current_api_key=api_key,
            password=reset_request.password,  # 🔒 Password verification required
            reason=reset_request.reason,
            force=False
        )
        
        if result["success"]:
            # Audit the reset
            api_service.audit_api_key_reset(
                tenant_id=tenant_id,
                reset_by="tenant_self",
                reason=reset_request.reason or "API key regeneration via header auth",
                verification_method=result.get("verification_method", "unknown")
            )
            
            logger.info(
                f"🔑 Tenant {tenant_id} regenerated API key via header auth "
                f"(verified via {result.get('verification_method')})"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in API key regeneration: {str(e)}")
        return {
            "success": False,
            "error": f"API key regeneration failed: {str(e)}"
        }

@router.post("/{tenant_id}/verify-password")
async def verify_tenant_password_endpoint(
    tenant_id: int,
    password_data: dict,  # {"password": "user_password"}
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Verify tenant password without resetting API key
    Useful for pre-validation before sensitive operations
    """
    try:
        # Validate API key ownership
        tenant = get_tenant_from_api_key(api_key, db)
        
        if tenant.id != tenant_id:
            raise HTTPException(status_code=403, detail="API key doesn't match tenant")
        
        password = password_data.get("password")
        if not password:
            raise HTTPException(status_code=400, detail="Password is required")
        
        # Initialize the service
        api_service = get_enhanced_api_key_reset_service(db)
        
        # Verify password
        verification_result = await api_service.verify_tenant_password(tenant_id, password)
        
        if verification_result["success"]:
            logger.info(f"🔐 Password verification successful for tenant {tenant_id}")
            return {
                "success": True,
                "message": "Password verified successfully",
                "verification_method": verification_result.get("method")
            }
        else:
            logger.warning(f"🚨 Password verification failed for tenant {tenant_id}")
            return {
                "success": False,
                "error": "Password verification failed"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in password verification: {str(e)}")
        return {
            "success": False,
            "error": f"Password verification failed: {str(e)}"
        }