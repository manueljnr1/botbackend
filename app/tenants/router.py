import os
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.core.security import get_password_hash
import uuid

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

import logging
# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    pass  # Add your code here
except Exception as e:
    logger.error(f"An error occurred: {e}")
except Exception as e:
    logger.error(f"An error occurred: {e}")
    from app.pricing.service import PricingService
    PRICING_AVAILABLE = True
    print("✅ PricingService imported successfully")
except ImportError as e:
    print(f"⚠️ PricingService not available: {e}")
    PRICING_AVAILABLE = False






pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="tenants/login")




# MODIFIED HELPER FUNCTION
def get_tenant_from_api_key(api_key: str, db: Session) -> Tenant:
    """
    Retrieve an active tenant using the provided API key.
    """
    # Added Tenant.is_active == True to the filter
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    if not tenant:
        # Changed status_code to status.HTTP_403_FORBIDDEN for consistency
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or inactive tenant")
    return tenant

router = APIRouter()

# Pydantic models
class TenantCreate(BaseModel):
    name: str
    description: Optional[str] = None
    password: str
    contact_email: str


class TenantLogin(BaseModel):
    username: str  # This can be either username, email, or tenant name
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

# MODIFIED TenantOut Pydantic model
class TenantOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None # Explicitly set default to None
    api_key: str
    is_active: bool
    system_prompt: Optional[str] = None
    contact_email: Optional[str] = None   # Added system_prompt field

    class Config:
        from_attributes = True

class TenantForgotPasswordRequest(BaseModel):
    name: str  # Use tenant name instead of email

class TenantResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class MessageResponse(BaseModel):
    message: str



class TenantEmailConfig(BaseModel):
    feedback_email: Optional[str] = None
    from_email: Optional[str] = None
    enable_feedback_system: bool = True


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
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    return encoded_jwt, expire




async def get_current_tenant(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get the current tenant from a token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the JWT token
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id: int = payload.get("sub")
        
        if tenant_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get the tenant from the database
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if tenant is None:
        raise credentials_exception
    
    return tenant



async def get_current_user_or_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Dependency to get current user (either admin or tenant)"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        is_admin = payload.get("is_admin", False)
        
        if user_id is None:
            raise credentials_exception
            
        if is_admin:
            # Handle admin token - find admin by ID
            admin = db.query(Admin).filter(Admin.id == user_id, Admin.is_active == True).first()
            if admin is None:
                raise credentials_exception
            # Create a mock user object with admin privileges
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
            # Handle regular tenant token
            tenant = db.query(Tenant).filter(Tenant.id == user_id, Tenant.is_active == True).first()
            if tenant is None:
                raise credentials_exception
            # Find user associated with this tenant
            user = db.query(User).filter(User.tenant_id == tenant.id, User.is_active == True).first()
            if user is None:
                # Create a mock user object for tenant
                class TenantUser:
                    def __init__(self, tenant):
                        self.id = f"tenant_{tenant.id}"
                        self.username = tenant.name
                        self.email = tenant.contact_email
                        self.is_admin = False
                        self.tenant_id = tenant.id
                        self.is_active = tenant.is_active
                return TenantUser(tenant)
            return user
            
    except JWTError:
        raise credentials_exception


    

# Login endpoint
@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Universal login endpoint for both admins and tenants
    """
    # First, try to authenticate as an admin
    admin = db.query(Admin).filter(
        (Admin.username == form_data.username) | (Admin.email == form_data.username),
        Admin.is_active == True
    ).first()
    
    if admin and verify_password(form_data.password, admin.hashed_password):
        # Admin authentication successful
        access_token, expires_at = create_access_token(
            data={
                "sub": str(admin.id),
                "is_admin": True  # Flag to indicate admin role
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        # Return admin token response
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "is_admin": True,
            "admin_id": str(admin.id),
            "name": admin.name,
            "email": admin.email,
            "expires_at": expires_at,
            # Add dummy values for required tenant fields
            "tenant_id":0,  # Dummy UUID
            "tenant_name": "ADMIN",  # Dummy name
            "api_key": None  # or provide a dummy value if required
        }
    
    # If not admin, proceed with existing tenant authentication logic
    tenant = db.query(Tenant).filter(Tenant.name == form_data.username, Tenant.is_active == True).first()
    
    if not tenant:
        # If no tenant found by name, try to find a user with this username that's linked to a tenant
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
    
    # Get tenant credentials
    credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
    
    if not credentials or not credentials.hashed_password or not verify_password(form_data.password, credentials.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token with is_admin flag set to false for tenants
    access_token, expires_at = create_access_token(
        data={
            "sub": str(tenant.id),
            "is_admin": False  # Flag to indicate this is NOT an admin
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    # Return tenant token response with is_admin field added
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "tenant_id": int(tenant.id),
        "tenant_name": str(tenant.id),
        "expires_at": expires_at,
        "api_key": tenant.api_key
    }



# NEW ENDPOINT
@router.get("/details/by-apikey", response_model=TenantOut)
async def get_tenant_details_by_api_key(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get current tenant's details (including name, id, and system_prompt) using their API key.
    This is useful for the frontend to configure itself for the active tenant.
    """
    tenant = get_tenant_from_api_key(api_key, db) # Uses the modified helper
    return tenant





# @router.post("/", response_model=TenantOut)
# async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
#     """
#     Create a new tenant (admin only)
#     """
#     db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
#     if db_tenant:
#         raise HTTPException(status_code=400, detail="Tenant name already registered")
    
#     # Generate hashed password from the required password
#     hashed_password = get_password_hash(tenant.password)
    
    # Create tenant without password information
    # new_tenant = Tenant(
    #     name=tenant.name,
    #     description=tenant.description,
    #     system_prompt=tenant.system_prompt,
    #     api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}",
    #     is_active=True
    # )
    # db.add(new_tenant)
    # db.commit()
    # db.refresh(new_tenant)
    
    # # Store password in separate credentials table
    # tenant_credentials = TenantCredentials(
    #     tenant_id=new_tenant.id,
    #     hashed_password=hashed_password
    # )
    # db.add(tenant_credentials)
    # db.commit()
    
    # return new_tenant



@router.post("/register", response_model=TenantOut)
async def register_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    """
    Enhanced Tenant Registration with bulletproof Free subscription creation
    """
    try:
        # Check if tenant name already exists
        db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
        if db_tenant:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # Create new tenant
        new_tenant = Tenant(
            name=tenant.name,
            description=tenant.description,
            system_prompt=None,  
            api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}",
            contact_email=tenant.contact_email,
            is_active=True
        )
        
        # Add tenant to database and flush to get ID
        db.add(new_tenant)
        db.flush()  # This gets the ID without committing
        
        # Create tenant credentials
        hashed_password = get_password_hash(tenant.password)
        tenant_credentials = TenantCredentials(
            tenant_id=new_tenant.id,
            hashed_password=hashed_password
        )
        db.add(tenant_credentials)
        
        # 🚀 BULLETPROOF SUBSCRIPTION CREATION
        subscription_created = False
        subscription_error = None
        
        if PRICING_AVAILABLE:
            try:
                logger.info(f"🎁 Creating Free subscription for new tenant: {new_tenant.name} (ID: {new_tenant.id})")
                pricing_service = PricingService(db)
                
                # Ensure default plans exist first
                pricing_service.create_default_plans()
                
                # Create free subscription
                subscription = pricing_service.create_free_subscription_for_tenant(new_tenant.id)
                
                if subscription and subscription.plan:
                    subscription_created = True
                    logger.info(f"✅ Successfully created Free subscription for {new_tenant.name}")
                    logger.info(f"   📊 Plan: {subscription.plan.name}")
                    logger.info(f"   💬 Conversations: {subscription.plan.max_messages_monthly}/month")
                    logger.info(f"   🆔 Subscription ID: {subscription.id}")
                else:
                    subscription_error = "Subscription creation returned None or missing plan"
                    logger.error(f"❌ Subscription creation failed for {new_tenant.name}: {subscription_error}")
                    
            except Exception as e:
                subscription_error = str(e)
                logger.error(f"💥 Failed to create subscription for new tenant {new_tenant.name}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            subscription_error = "Pricing system not available"
            logger.warning(f"⚠️ Pricing system not available, skipping subscription creation for {new_tenant.name}")
        
        # Decision: Should we fail tenant creation if subscription fails?
        # Option 1: Fail completely (recommended for production)
        if not subscription_created and PRICING_AVAILABLE:
            db.rollback()
            raise HTTPException(
                status_code=500, 
                detail=f"Tenant registration failed: Could not create subscription. Error: {subscription_error}"
            )
        
        # Option 2: Continue without subscription (use this for testing)
        # if not subscription_created:
        #     logger.warning(f"⚠️ Tenant {new_tenant.name} created without subscription: {subscription_error}")
        
        # Commit everything if we reach here
        db.commit()
        db.refresh(new_tenant)
        
        logger.info(f"🎉 Tenant registration completed: {new_tenant.name}")
        return new_tenant
        
    except HTTPException:
        # Re-raise HTTP exceptions (like duplicate tenant name)
        db.rollback()
        raise
    except Exception as e:
        # Handle any other unexpected errors
        db.rollback()
        logger.error(f"💥 Unexpected error during tenant registration: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed due to system error: {str(e)}"
        )






@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get a specific tenant
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if not current_user.is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this tenant")
    
    return tenant




@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: int, 
    tenant_update: TenantUpdate, 
    db: Session = Depends(get_db), 
    current_admin = Depends(get_admin_user)  # This can be User or Admin
):
    """
    Update a tenant's details, including system prompt (admin only or authorized user)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Authorization logic that handles both User and Admin objects
    from app.admin.models import Admin
    from app.auth.models import User
    
    # Check if current_admin is an Admin object (from admin login)
    if isinstance(current_admin, Admin):
        # Admin can update any tenant - no additional checks needed
        pass
    elif isinstance(current_admin, User):
        # User with admin privileges - check tenant ownership
        if not current_admin.is_admin and (current_admin.tenant_id is None or current_admin.tenant_id != tenant_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this tenant")
    else:
        # Should not happen, but safety check
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin credentials")

    # Apply updates
    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    
    db.commit()
    db.refresh(tenant)
    return tenant



@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Deactivate a tenant (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    tenant.is_active = False
    db.commit()
    return {"message": "Tenant deactivated successfully"}




@router.put("/{tenant_id}/prompt", response_model=TenantOut) # Changed response_model to TenantOut for consistency
async def update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict, # Expects {"system_prompt": "new prompt"}
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Update a tenant's system prompt using API key.
    Returns the updated tenant details.
    """
    tenant = get_tenant_from_api_key(api_key, db)
    
    if tenant.id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key does not match tenant ID")
    
    new_system_prompt = prompt_data.get("system_prompt")
    if new_system_prompt is None: # Check if system_prompt key exists
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system_prompt field is required in request body")

    tenant.system_prompt = new_system_prompt
    db.commit()
    db.refresh(tenant)
    return tenant




@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password(request: TenantForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Send password reset email to tenant contact
    """
    # Find tenant by name
    tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
    # Always return success message, even if tenant not found (security best practice)
    if not tenant:
        return {"message": "If your account name exists in our system, you will receive a password reset link."}
    
    # Check if tenant already has a valid token
    existing_token = db.query(TenantPasswordReset).filter(
        TenantPasswordReset.tenant_id == tenant.id,
        TenantPasswordReset.is_used == False,
        TenantPasswordReset.expires_at > datetime.utcnow()
    ).first()
    
    # If token exists, reuse it, otherwise create a new one
    if existing_token:
        reset_token = existing_token.token
    else:
        # Create new token
        password_reset = TenantPasswordReset.create_token(tenant.id)
        db.add(password_reset)
        db.commit()
        db.refresh(password_reset)
        reset_token = password_reset.token
    
    # Get the contact email for the tenant
    tenant_contact_email = tenant.contact_email
    
    if tenant_contact_email:
        # Send email
        reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password?token={reset_token}"
        
        # Prepare email content
        email_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #ffffff; padding: 30px; border: 1px solid #dee2e6; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #6c757d; border-radius: 0 0 5px 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <p>Hello <strong>{tenant.name}</strong>,</p>
                    <p>We received a request to reset your account password. If you didn't make this request, you can safely ignore this email.</p>
                    <p>To reset your password, click the button below:</p>
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" class="button">Reset Password</a>
                    </p>
                    <p>Or copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 3px;">
                        {reset_url}
                    </p>
                    <p><strong>This link will expire in 24 hours.</strong></p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>Your App Team</p>
                    <p>If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send email using SendGrid
        try:
            success = email_service.send_email(
                to_email=tenant_contact_email,
                subject="Password Reset Request",
                html_content=email_body
            )
            
            if not success:
                logger.error(f"Failed to send password reset email to {tenant_contact_email}")
                
        except Exception as e:
            # Log error, but don't reveal to user
            logger.exception(f"Error sending password reset email: {e}")
    
    return {"message": "If your account name exists in our system, you will receive a password reset link."}



@router.post("/reset-password", response_model=MessageResponse)
async def tenant_reset_password(request: TenantResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset tenant password using the token from email
    """
    # Find the password reset token
    reset_request = db.query(TenantPasswordReset).filter(
        TenantPasswordReset.token == request.token,
        TenantPasswordReset.is_used == False
    ).first()
    
    if not reset_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Check if token is valid (not expired)
    if not reset_request.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    # Get the tenant
    tenant = db.query(Tenant).filter(Tenant.id == reset_request.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Update the tenant's password
    hashed_password = get_password_hash(request.new_password)
    
    # Update or create tenant credentials
    credentials = db.query(TenantCredentials).filter(TenantCredentials.tenant_id == tenant.id).first()
    if credentials:
        credentials.hashed_password = hashed_password
    else:
        credentials = TenantCredentials(
            tenant_id=tenant.id,
            hashed_password=hashed_password
        )
        db.add(credentials)
    
    # Mark the reset token as used
    reset_request.is_used = True
    
    # Commit changes
    db.commit()
    
    # Optional: Send confirmation email
    if tenant.contact_email:
        confirmation_email = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #28a745; color: white; padding: 20px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset Successful</h2>
                </div>
                <div style="padding: 20px;">
                    <p>Hello <strong>{tenant.name}</strong>,</p>
                    <p>Your password has been successfully reset.</p>
                    <p>If you didn't perform this action, please contact our support team immediately.</p>
                    <p>Best regards,<br>Your App Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        try:
            email_service.send_email(
                to_email=tenant.contact_email,
                subject="Password Reset Successful",
                html_content=confirmation_email
            )
        except Exception as e:
            logger.exception(f"Failed to send password reset confirmation email: {e}")
    
    return {"message": "Password reset successfully. You can now log in with your new password."}




@router.post("/{tenant_id}/create-subscription")
async def create_tenant_subscription(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)  # Admin only
):
    """
    Manually create a Free subscription for a tenant (Admin only)
    Useful for fixing tenants created before auto-subscription was implemented
    """
    # Check if tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Check if subscription already exists
    try:
        pricing_service = PricingService(db)
        existing_subscription = pricing_service.get_tenant_subscription(tenant_id)
        
        if existing_subscription:
            return {
                "message": f"Tenant {tenant.name} already has an active subscription",
                "plan": existing_subscription.plan.name,
                "status": existing_subscription.status
            }
        
        # Create Free subscription
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
    """
    Enhanced subscription status check with detailed information
    """
    # Authorization check
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
    """
    Manual endpoint to fix all tenants without subscriptions (Admin only)
    """
    try:
        # Find tenants without active subscriptions
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
        
        # Ensure default plans exist
        pricing_service.create_default_plans()
        
        fixed_tenants = []
        failed_tenants = []
        
        for tenant in tenants_without_subscriptions:
            try:
                logger.info(f"🔧 Creating subscription for tenant: {tenant.name}")
                
                subscription = pricing_service.create_free_subscription_for_tenant(tenant.id)
                
                if subscription:
                    fixed_tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "plan": subscription.plan.name,
                        "subscription_id": subscription.id
                    })
                    logger.info(f"✅ Fixed subscription for {tenant.name}")
                else:
                    failed_tenants.append({
                        "tenant_id": tenant.id,
                        "tenant_name": tenant.name,
                        "error": "Subscription creation returned None"
                    })
                    
            except Exception as e:
                logger.error(f"💥 Error creating subscription for {tenant.name}: {e}")
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
        logger.error(f"💥 Error in fix_all_tenant_subscriptions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix subscriptions: {str(e)}")
    


@router.put("/{tenant_id}/email-config")
async def update_tenant_email_config(
    tenant_id: int,
    email_config: TenantEmailConfig,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update tenant email configuration for feedback system"""
    
    # Verify API key belongs to this tenant
    tenant = get_tenant_from_api_key(api_key, db)
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="API key doesn't match tenant")
    
    # Update email configuration
    if email_config.feedback_email:
        tenant.feedback_email = email_config.feedback_email
    if email_config.from_email:
        tenant.from_email = email_config.from_email
    
    tenant.enable_feedback_system = email_config.enable_feedback_system
    
    db.commit()
    db.refresh(tenant)
    
    return {
        "message": "Email configuration updated successfully",
        "tenant_id": tenant_id,
        "feedback_email": tenant.feedback_email,
        "from_email": tenant.from_email,
        "feedback_enabled": tenant.enable_feedback_system
    }

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


router.post("/{tenant_id}/test-email")
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
    
    # Send test email
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