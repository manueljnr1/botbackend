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
from typing import List, Optional
from pydantic import BaseModel
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
from app.core.email_service import email_service
from app.auth.supabase_service import supabase_auth_service

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
    description: Optional[str] = None
    is_active: Optional[bool] = None
    system_prompt: Optional[str] = None

class TenantOut(BaseModel):
    id: int
    name: str
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
    from_email: Optional[str] = None
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





# @router.post("/register", response_model=TenantOut)
# async def register_tenant_enhanced(tenant: TenantCreate, db: Session = Depends(get_db)):
#     """Tenant Registration"""
    
#     # Start database transaction
#     db.begin()
    
#     try:
#         # Step 1: Validate inputs
#         if db.query(Tenant).filter(Tenant.email == tenant.email).first():
#             raise HTTPException(status_code=400, detail="Email already registered")
        
#         if db.query(Tenant).filter(Tenant.name == tenant.name).first():
#             raise HTTPException(status_code=400, detail="Username already taken")
        
#         # Step 2: Create Supabase user first
#         supabase_result = await supabase_auth_service.create_user(
#             email=tenant.email,
#             password=tenant.password,
#             metadata={
#                 "tenant_name": tenant.name,
#                 "role": "tenant_admin"
#             }
#         )
        
#         if not supabase_result["success"]:
#             raise HTTPException(
#                 status_code=400, 
#                 detail=f"Account creation failed: {supabase_result.get('error')}"
#             )
        
#         # Step 3: Create local tenant
#         new_tenant = Tenant(
#             name=tenant.name,
#             email=tenant.email,
#             description=tenant.description,
#             api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}",
#             is_active=True,
#             supabase_user_id=supabase_result["user"].get("id")  # Link to Supabase
#         )
        
#         db.add(new_tenant)
#         db.flush()  # Get ID without committing
        
#         # Step 4: Create subscription
#         if PRICING_AVAILABLE:
#             pricing_service = PricingService(db)
#             pricing_service.create_default_plans()
#             subscription = pricing_service.create_free_subscription_for_tenant(new_tenant.id)
            
#             if not subscription:
#                 raise Exception("Failed to create subscription")
        
#         # Step 5: Commit everything
#         db.commit()
#         db.refresh(new_tenant)
        
#         logger.info(f"✅ Successfully registered tenant: {new_tenant.name}")
#         return new_tenant
        
#     except HTTPException:
#         db.rollback()
#         raise
#     except Exception as e:
#         db.rollback()
#         logger.error(f"Registration failed: {e}")
        
#         # TODO: Cleanup orphaned Supabase user
#         raise HTTPException(
#             status_code=500,
#             detail="Registration failed. Please try again or contact support."
#         )





@router.post("/register", response_model=TenantOut)
async def register_tenant_enhanced(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Tenant Registration with Fixed Transaction Handling"""
    
    supabase_user_id = None  # Track for cleanup
    
    try:
        logger.info(f"🚀 Starting registration for: {tenant.name} ({tenant.email})")
        
        # Step 1: Validate inputs
        normalized_email = tenant.email.lower().strip()
        existing_email = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email
        ).first()
        if existing_email:
            logger.warning(f"❌ Email already registered: {tenant.email}")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        existing_name = db.query(Tenant).filter(Tenant.name == tenant.name).first()
        if existing_name:
            logger.warning(f"❌ Username already taken: {tenant.name}")
            raise HTTPException(status_code=400, detail="Username already taken")
        
        logger.info("✅ Input validation passed")
        
        # Step 2: Generate API key
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        logger.info(f"✅ Generated API key: {api_key[:15]}...")
        
        # Step 3: Create Supabase user
        logger.info("🔄 Creating Supabase user...")
        supabase_result = await supabase_auth_service.create_user(
            email=normalized_email,
            password=tenant.password,
            metadata={
                "display_name": tenant.name,
                "full_name": tenant.name,
                "tenant_name": tenant.name,
                "tenant_description": tenant.description or "",
                "role": "tenant_admin",
                "account_type": "tenant",
                "api_key": api_key,
                "registration_date": datetime.utcnow().isoformat(),
                "tenant_status": "active"
            }
        )
        
        if not supabase_result["success"]:
            logger.error(f"❌ Supabase user creation failed: {supabase_result.get('error')}")
            raise HTTPException(
                status_code=400, 
                detail=f"Account creation failed: {supabase_result.get('error')}"
            )
        
        # === THIS IS THE FIX ===
        supabase_user_id = supabase_result["user"].id
        # =======================

        logger.info(f"✅ Supabase user created: {supabase_user_id}")
        
        # Step 4: Create local tenant (no manual transaction - FastAPI handles it)
        logger.info("🔄 Creating local tenant record...")
        new_tenant = Tenant(
            name=tenant.name,
            email=normalized_email,
            description=tenant.description,
            api_key=api_key,
            is_active=True,
            supabase_user_id=supabase_user_id
        )
        
        db.add(new_tenant)
        db.flush()  # Get ID without committing
        logger.info(f"✅ Local tenant created with ID: {new_tenant.id}")
        
        # Step 5: Update Supabase with tenant ID
        logger.info("🔄 Updating Supabase with tenant ID...")
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
                logger.info("✅ Supabase metadata updated")
            else:
                logger.warning(f"⚠️ Failed to update Supabase metadata: {update_result.get('error')}")
        except Exception as meta_error:
            logger.warning(f"⚠️ Supabase metadata update failed: {meta_error}")
            # Don't fail registration for metadata issues
        
        # Step 6: Create subscription if available
        if PRICING_AVAILABLE:
            logger.info("🔄 Creating subscription...")
            try:
                pricing_service = PricingService(db)
                pricing_service.create_default_plans()
                subscription = pricing_service.create_free_subscription_for_tenant(new_tenant.id)
                
                if subscription:
                    logger.info(f"✅ Subscription created: {subscription.id}")
                else:
                    logger.warning("⚠️ Subscription creation returned None")
            except Exception as e:
                logger.error(f"❌ Subscription creation failed: {e}")
                # Don't fail registration for subscription issues
        else:
            logger.info("ℹ️ Pricing system not available, skipping subscription")
        
        # Step 7: FastAPI will auto-commit the transaction
        db.commit()
        db.refresh(new_tenant)
        
        logger.info(f"🎉 Registration successful for: {new_tenant.name} (ID: {new_tenant.id})")
        return new_tenant
        
    except HTTPException as he:
        logger.error(f"❌ HTTP Exception during registration: {he.detail}")
        
        # Cleanup orphaned Supabase user
        if supabase_user_id:
            await cleanup_supabase_user(supabase_user_id)
        
        raise he
        
    except Exception as e:
        logger.error(f"❌ Unexpected error during registration: {str(e)}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Full traceback:", exc_info=True)
        
        # Cleanup orphaned Supabase user
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
    """Clean login with enhanced security layers"""
    try:
        normalized_email = login_data.email.lower().strip()
        client_ip = request.client.host
        
        if not check_admin_rate_limit(f"admin_{normalized_email}", max_attempts=3, window_minutes=10):
            logger.warning(f"🚨 Admin rate limit exceeded: {normalized_email} from {client_ip}")
            await asyncio.sleep(2)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later."
            )
        
        admin = db.query(Admin).filter(
            (func.lower(Admin.username) == normalized_email) |
            (func.lower(Admin.email) == normalized_email),
            Admin.is_active == True
        ).first()
        
        if admin and verify_password(login_data.password, admin.hashed_password):
            logger.info(f"🔐 Admin login successful: {admin.username} ({admin.email}) from {client_ip}")
            admin_rate_limit_storage[f"admin_{normalized_email}"].clear()
            
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
                "tenant_name": "ADMIN",
                "api_key": None
            }
        
        if admin:
            logger.warning(f"🚨 Failed admin login (wrong password): {normalized_email} from {client_ip}")
        
        if not check_rate_limit(f"tenant_{normalized_email}", max_attempts=5, window_minutes=15):
            logger.warning(f"⚠️ Tenant rate limit exceeded: {normalized_email} from {client_ip}")
            await asyncio.sleep(1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later."
            )
        
        supabase_result = await supabase_auth_service.sign_in(
            email=normalized_email,
            password=login_data.password
        )
        
        if not supabase_result["success"]:
            logger.warning(f"⚠️ Failed tenant login: {normalized_email} from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        tenant = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            logger.error(f"❌ Tenant not found after successful Supabase auth: {normalized_email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tenant found with this email address"
            )
        
        logger.info(f"✅ Tenant login successful: {tenant.name} ({tenant.email}) from {client_ip}")
        
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
            "api_key": tenant.api_key
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Login error: {e} for {login_data.email} from {getattr(request.client, 'host', 'unknown')}")
        await asyncio.sleep(1)
        raise HTTPException(status_code=500, detail="Login failed")










@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password_supabase(
    request: TenantForgotPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Enhanced password reset using email with centralized configuration"""
    
    # Input validation (Pydantic handles basic validation)
    normalized_email = str(request.email).strip().lower()
    
    # Find tenant by email
    try:
        tenant = db.query(Tenant).filter(
            func.lower(Tenant.email) == normalized_email,
            Tenant.is_active == True
        ).first()
    except Exception as e:
        logger.error(f"Database error during password reset lookup: {e}")
        return {"message": "If your account exists in our system, you will receive a password reset link."}
    
    # Standard security message (same whether tenant exists or not)
    standard_message = "If your account exists in our system, you will receive a password reset link."
    
    if not tenant:
        # Log attempt for monitoring (partial email for privacy)
        logger.info(f"Password reset attempted for non-existent email: {normalized_email[:3]}***@{normalized_email.split('@')[1] if '@' in normalized_email else 'unknown'}")
        return {"message": standard_message}
    
    try:
        # Use centralized configuration
        redirect_to = settings.get_password_reset_url()
        
        # Send password reset via Supabase
        result = await supabase_auth_service.send_password_reset(
            email=tenant.email,  # Use stored email (preserves original case for display)
            redirect_to=redirect_to
        )
        
        if result["success"]:
            logger.info(f"Password reset sent successfully for tenant ID: {tenant.id}")
        else:
            logger.error(f"Password reset failed for tenant ID: {tenant.id} - Error: {result.get('error')}")
        
    except ValueError as e:
        # Configuration error
        logger.error(f"Configuration error in password reset: {e}")
    except Exception as e:
        logger.error(f"Password reset service error for tenant ID: {tenant.id} - Error: {e}")
    
    return {"message": standard_message}




@router.post("/reset-password", response_model=MessageResponse)
async def tenant_reset_password_supabase(
    request: TenantResetPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Reset password using Supabase token with confirmation"""

    # Step 1: Add validation to check if passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    # Step 2: Call the Supabase service (the rest of the logic is the same)
    result = await supabase_auth_service.verify_password_reset(
        token=request.token, 
        new_password=request.new_password
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Invalid or expired reset token")
        )
    
    # Optional: Update local tenant credentials if needed
    if result.get("user"):
        user_email = result["user"].email
        if user_email:
            tenant = db.query(Tenant).filter(Tenant.email == user_email).first()
            if tenant:
                # Update local credentials
                credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
                if credentials:
                    credentials.hashed_password = get_password_hash(request.new_password)
                else:
                    credentials = TenantCredentials(
                        tenant_id=tenant.id,
                        hashed_password=get_password_hash(request.new_password)
                    )
                    db.add(credentials)
                db.commit()
                logger.info(f"Local password updated for tenant: {tenant.name}")
    
    return {"message": "Password reset successfully. You can now log in with your new password."}





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
    """Get tenant email configuration"""
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "feedback_email": tenant.feedback_email,
        "from_email": tenant.from_email,
        "feedback_enabled": tenant.enable_feedback_system,
        "email_system_available": bool(os.getenv('EMAIL_PROVIDER'))
    }








# ----------------------------------------------------
        # Password reset endpoints
# @router.post("/forgot-password", response_model=MessageResponse)
# async def tenant_forgot_password(request: TenantForgotPasswordRequest, db: Session = Depends(get_db)):
#     """Send password reset email to tenant contact"""
#     from fastapi import Request
    
#     tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
#     if not tenant:
#         return {"message": "If your account name exists in our system, you will receive a password reset link."}
    
#     # Check for existing valid token
#     existing_token = db.query(TenantPasswordReset).filter(
#         TenantPasswordReset.tenant_id == tenant.id,
#         TenantPasswordReset.is_used == False,
#         TenantPasswordReset.expires_at > datetime.utcnow()
#     ).first()
    
#     if existing_token:
#         reset_token = existing_token.token
#     else:
#         password_reset = TenantPasswordReset.create_token(tenant.id)
#         db.add(password_reset)
#         db.commit()
#         db.refresh(password_reset)
#         reset_token = password_reset.token
    
#     if tenant.email:
#         reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password?token={reset_token}"
        
#         email_body = f"""
#         <html>
#         <body style="font-family: Arial, sans-serif;">
#             <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
#                 <h2>Password Reset Request</h2>
#                 <p>Hello <strong>{tenant.name}</strong>,</p>
#                 <p>We received a request to reset your account password.</p>
#                 <p><a href="{reset_url}" style="background-color: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
#                 <p>This link will expire in 24 hours.</p>
#             </div>
#         </body>
#         </html>
#         """
        
#         try:
#             email_service.send_email(
#                 to_email=tenant.email,
#                 subject="Password Reset Request",
#                 html_content=email_body
#             )
#         except Exception as e:
#             logger.error(f"Error sending password reset email: {e}")
    
#     return {"message": "If your account name exists in our system, you will receive a password reset link."}

# @router.post("/reset-password", response_model=MessageResponse)
# async def tenant_reset_password(request: TenantResetPasswordRequest, db: Session = Depends(get_db)):
#     """Reset tenant password using the token from email"""
#     reset_request = db.query(TenantPasswordReset).filter(
#         TenantPasswordReset.token == request.token,
#         TenantPasswordReset.is_used == False
#     ).first()
    
#     if not reset_request:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid or expired reset token"
#         )
    
#     if not reset_request.is_valid():
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Reset token has expired"
#         )
    
#     tenant = db.query(Tenant).filter(Tenant.id == reset_request.tenant_id).first()
#     if not tenant:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Tenant not found"
#         )
    
#     hashed_password = get_password_hash(request.new_password)
    
#     credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
#     if credentials:
#         credentials.hashed_password = hashed_password
#     else:
#         credentials = TenantCredentials(
#             tenant_id=tenant.id,
#             hashed_password=hashed_password
#         )
#         db.add(credentials)
    
#     reset_request.is_used = True
#     db.commit()
    
#     return {"message": "Password reset successfully. You can now log in with your new password."}





# Legacy login endpoint
# @router.post("/login-legacy", response_model=TokenResponse)
# async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     """Universal login endpoint for both admins and tenants"""
#     # Try admin authentication first
#     admin = db.query(Admin).filter(
#         (Admin.username == form_data.username) | (Admin.email == form_data.username),
#         Admin.is_active == True
#     ).first()
    
#     if admin and verify_password(form_data.password, admin.hashed_password):
#         access_token, expires_at = create_access_token(
#             data={
#                 "sub": str(admin.id),
#                 "is_admin": True
#             },
#             expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
#         )
        
#         return {
#             "access_token": access_token,
#             "token_type": "bearer",
#             "is_admin": True,
#             "admin_id": str(admin.id),
#             "name": admin.name,
#             "email": admin.email,
#             "expires_at": expires_at,
#             "tenant_id": 0,
#             "tenant_name": "ADMIN",
#             "api_key": None
#         }
    
#     # Try tenant authentication
#     tenant = db.query(Tenant).filter(Tenant.name == form_data.username, Tenant.is_active == True).first()
    
#     if not tenant:
#         user = db.query(User).filter(
#             (User.username == form_data.username) | (User.email == form_data.username),
#             User.is_active == True
#         ).first()
        
#         if user and user.tenant_id:
#             tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id, Tenant.is_active == True).first()
    
#     if not tenant:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
    
#     if not credentials or not credentials.hashed_password or not verify_password(form_data.password, credentials.hashed_password):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
    
#     access_token, expires_at = create_access_token(
#         data={
#             "sub": str(tenant.id),
#             "is_admin": False
#         },
#         expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
#     )
    
#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "tenant_id": int(tenant.id),
#         "tenant_name": str(tenant.id),
#         "expires_at": expires_at,
#         "api_key": tenant.api_key
#     }


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