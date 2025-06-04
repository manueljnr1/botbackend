import os
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import PyJWTError as JWTError
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import get_password_hash
from fastapi_limiter.depends import RateLimiter
import uuid
import time
from collections import defaultdict

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
    name: str

class TenantResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class MessageResponse(BaseModel):
    message: str

class TenantEmailConfig(BaseModel):
    feedback_email: Optional[str] = None
    from_email: Optional[str] = None
    enable_feedback_system: bool = True

class SupabaseLoginRequest(BaseModel):
    email: str
    password: str

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
            Tenant.email == user.email,  # Clean and simple
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

# Legacy login endpoint
@router.post("/login-legacy", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Universal login endpoint for both admins and tenants"""
    # Try admin authentication first
    admin = db.query(Admin).filter(
        (Admin.username == form_data.username) | (Admin.email == form_data.username),
        Admin.is_active == True
    ).first()
    
    if admin and verify_password(form_data.password, admin.hashed_password):
        access_token, expires_at = create_access_token(
            data={
                "sub": str(admin.id),
                "is_admin": True
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "is_admin": True,
            "admin_id": str(admin.id),
            "name": admin.name,
            "email": admin.email,
            "expires_at": expires_at,
            "tenant_id": 0,
            "tenant_name": "ADMIN",
            "api_key": None
        }
    
    # Try tenant authentication
    tenant = db.query(Tenant).filter(Tenant.name == form_data.username, Tenant.is_active == True).first()
    
    if not tenant:
        user = db.query(User).filter(
            (User.username == form_data.username) | (User.email == form_data.username),
            User.is_active == True
        ).first()
        
        if user and user.tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id, Tenant.is_active == True).first()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
    
    if not credentials or not credentials.hashed_password or not verify_password(form_data.password, credentials.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token, expires_at = create_access_token(
        data={
            "sub": str(tenant.id),
            "is_admin": False
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "tenant_id": int(tenant.id),
        "tenant_name": str(tenant.id),
        "expires_at": expires_at,
        "api_key": tenant.api_key
    }



# Supabase login endpoint
@router.post("/login", response_model=SupabaseTokenResponse)
async def login_with_supabase(
    login_data: SupabaseLoginRequest,
    db: Session = Depends(get_db)
):
    """Clean login with email field"""
    try:
        if not login_data.email or not login_data.password:
            raise HTTPException(status_code=400, detail="Email and password required")
        
        # Try admin authentication first
        admin = db.query(Admin).filter(
            (Admin.username == login_data.email) | (Admin.email == login_data.email),
            Admin.is_active == True
        ).first()
        
        if admin and verify_password(login_data.password, admin.hashed_password):
            access_token, expires_at = create_access_token(
                data={"sub": str(admin.id), "is_admin": True},
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
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
        
        # Try Supabase tenant authentication
        supabase_result = await supabase_auth_service.sign_in(
            email=login_data.email,
            password=login_data.password
        )
        
        if not supabase_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Find corresponding tenant
        tenant = db.query(Tenant).filter(
            Tenant.email == login_data.email,  # Direct field access
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tenant found with this email address"
            )
        
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
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

# Registration endpoint
@router.post("/register", response_model=TenantOut)
async def register_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """Simple tenant registration with email field"""
    try:
        if not tenant.name or not tenant.email or not tenant.password:
            raise HTTPException(status_code=400, detail="Name, email, and password are required")
        
        # Check if tenant name already exists
        db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
        if db_tenant:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # Check for existing email
        existing_email = db.query(Tenant).filter(Tenant.email == tenant.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user in Supabase
        supabase_result = await supabase_auth_service.create_user(
            email=tenant.email,  # Direct use - no mapping
            password=tenant.password,
            metadata={
                "tenant_name": tenant.name,
                "role": "tenant_admin"
            }
        )
        
        if not supabase_result.get("success"):
            error_msg = supabase_result.get("error", "Unknown error")
            raise HTTPException(
                status_code=400,
                detail=f"User creation failed: {error_msg}"
            )
        
        # Create local tenant record
        new_tenant = Tenant(
            name=tenant.name,
            description=tenant.description,
            system_prompt=None,  
            api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}",
            email=tenant.email,  # Direct assignment - no mapping
            is_active=True
        )
        
        db.add(new_tenant)
        db.commit()
        db.refresh(new_tenant)
        
        # Create subscription if pricing available
        if PRICING_AVAILABLE:
            try:
                pricing_service = PricingService(db)
                pricing_service.create_default_plans()
                subscription = pricing_service.create_free_subscription_for_tenant(new_tenant.id)
            except Exception as e:
                logger.error(f"Subscription creation error: {e}")
        
        return new_tenant  # Direct return - no mapping needed
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Registration failed")

        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Registration failed due to system error"
        )



@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password_supabase(
    request: TenantForgotPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Enhanced password reset using Supabase"""
    tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
    if not tenant or not tenant.email:
        return {"message": "If your account name exists in our system, you will receive a password reset link."}
    
    # Use the correct method name from your service
    result = await supabase_auth_service.send_password_reset(
        email=tenant.email,
        redirect_to=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password"
    )
    
    if result["success"]:
        logger.info(f"Supabase password reset sent for tenant: {tenant.name}")
    else:
        logger.error(f"Supabase password reset failed for {tenant.name}: {result.get('error')}")
    
    return {"message": "If your account name exists in our system, you will receive a password reset link."}





@router.post("/reset-password", response_model=MessageResponse)
async def tenant_reset_password_supabase(
    request: TenantResetPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Reset password using Supabase token"""
    # Use the correct method name from your service
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
        user_email = result["user"].get("email")
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

@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: int, 
    tenant_update: TenantUpdate, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Update a tenant's details"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Authorization logic
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        pass
    elif hasattr(current_user, 'id') and current_user.id == tenant_id:
        pass
    else:
        raise HTTPException(status_code=403, detail="Not authorized to update this tenant")

    # Apply updates
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    
    db.commit()
    db.refresh(tenant)
    return tenant

@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: int, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Deactivate a tenant (admin only)"""
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    tenant.is_active = False
    db.commit()
    return {"message": "Tenant deactivated successfully"}

@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: int, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user_hybrid)
):
    """Get tenant - no mapping needed"""
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
    
    return tenant  # Direct return




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

@router.post("/{tenant_id}/test-email")
async def test_tenant_email(
    tenant_id: int,
    test_email: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Send a test email to verify email configuration"""
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    if not tenant.feedback_email or not tenant.from_email:
        raise HTTPException(
            status_code=400, 
            detail="Email configuration incomplete. Please set feedback_email and from_email first."
        )
    
    from app.utils.email_service import email_service
    
    subject = f"Test Email from {tenant.name} Feedback System"
    body = f"""
    <html>
    <body>
        <h2>Email Configuration Test</h2>
        <p>Hello!</p>
        <p>This is a test email from the <strong>{tenant.name}</strong> feedback system.</p>
        <p>If you received this email, your email configuration is working correctly!</p>
        <p><strong>Configuration Details:</strong></p>
        <ul>
            <li>Tenant: {tenant.name}</li>
            <li>From Email: {tenant.from_email}</li>
            <li>Feedback Email: {tenant.feedback_email}</li>
        </ul>
        <p>Best regards,<br>Your Feedback System</p>
    </body>
    </html>
    """
    
    success = email_service.send_tenant_email(
        tenant_from_email=tenant.from_email,
        tenant_to_email=test_email,
        subject=subject,
        body=body
    )
    
    return {
        "success": success,
        "message": "Test email sent successfully" if success else "Failed to send test email",
        "sent_to": test_email,
        "from_email": tenant.from_email
    }

# Supabase-specific endpoints
@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password_supabase(
    request: TenantForgotPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Enhanced password reset using Supabase"""
    tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
    if not tenant or not tenant.email:
        return {"message": "If your account name exists in our system, you will receive a password reset link."}
    
    # Use the correct method name from your service
    result = await supabase_auth_service.send_password_reset(
        email=tenant.email,
        redirect_to=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password"
    )
    
    if result["success"]:
        logger.info(f"Supabase password reset sent for tenant: {tenant.name}")
    else:
        logger.error(f"Supabase password reset failed for {tenant.name}: {result.get('error')}")
    
    return {"message": "If your account name exists in our system, you will receive a password reset link."}





@router.post("/reset-password", response_model=MessageResponse)
async def tenant_reset_password_supabase(
    request: TenantResetPasswordRequest, 
    db: Session = Depends(get_db)
):
    """Reset password using Supabase token"""
    # Use the correct method name from your service
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
        user_email = result["user"].get("email")
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


@router.post("/create-supabase-user", response_model=MessageResponse)
async def create_supabase_user_endpoint(
    data: dict,
    db: Session = Depends(get_db)
):
    """Create Supabase user for existing tenant"""
    tenant_name = data.get("tenant_name")
    if not tenant_name:
        raise HTTPException(status_code=400, detail="tenant_name is required")
    
    tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if not tenant.email:
        raise HTTPException(status_code=400, detail="Tenant has no email address")
    
    result = await supabase_auth_service.create_user(
        email=tenant.email,
        password="temp_password_123",
        metadata={
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "role": "tenant_admin"
        }
    )
    
    if result["success"]:
        return {"message": f"Supabase user created for {tenant.name}. Check Supabase dashboard."}
    else:
        logger.error(f"Failed to create Supabase user: {result.get('error')}")
        raise HTTPException(status_code=400, detail=result.get("error"))

@router.post("/create-supabase-user-by-name", response_model=MessageResponse)
async def create_supabase_user_by_name(
    request: dict,
    db: Session = Depends(get_db)
):
    """Create Supabase user for existing tenant by name"""
    tenant_name = request.get("tenant_name")
    if not tenant_name:
        raise HTTPException(status_code=400, detail="tenant_name is required")
    
    tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_name}' not found")
    
    if not tenant.email:
        raise HTTPException(status_code=400, detail="Tenant has no email address")
    
    try:
        from app.auth.supabase_service import supabase_auth_service
    except ImportError:
        raise HTTPException(status_code=500, detail="Supabase service not available")
    
    result = await supabase_auth_service.create_user(
        email=tenant.email,
        password="temp_password_123",
        metadata={
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "role": "tenant"
        }
    )
    
    if result["success"]:
        return {"message": f"Supabase user created for {tenant.name}. Check your Supabase dashboard!"}
    else:
        error_msg = result.get("error", "Unknown error")
        logger.error(f"Failed to create Supabase user: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Supabase user creation failed: {error_msg}")







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
