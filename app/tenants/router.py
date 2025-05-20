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
from app.auth.models import User # For admin-only endpoints
from app.auth.router import get_current_user, get_admin_user # For admin-only endpoints
from app.auth.models import TenantCredentials
from app.config import settings
from app.tenants.models import TenantPasswordReset






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
    tenant_id: int
    tenant_name: str
    expires_at: datetime    
    api_key: str

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


    

# Login endpoint
@router.post("/login", response_model=TokenResponse)
async def login_tenant(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
   Tenant login with username/email and password
    """
    # Find tenant by name or through user
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
    
    # Create access token
    access_token, expires_at = create_access_token(
        data={"sub": str(tenant.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
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
    Tenants Registration
    """
    # Check if tenant name already exists
    db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    
   
    
    # Create new tenant (with is_active set to False initially for admin approval)
    new_tenant = Tenant(
        name=tenant.name,
        description=tenant.description,
        system_prompt=None,  
        api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}",
        contact_email=tenant.contact_email,  # Changed from admin_email
        is_active=True
    )
    
    # Add tenant to database
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    
    # Create tenant credentials with the tenant_id we now have
    hashed_password = get_password_hash(tenant.password)
    tenant_credentials = TenantCredentials(
        tenant_id=new_tenant.id,
        hashed_password=hashed_password
    )
    
    # Add credentials to database
    db.add(tenant_credentials)
    db.commit()
    
    return new_tenant





@router.get("/", response_model=List[TenantOut])
async def list_tenants(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    List all tenants (admin only)
    """
    return db.query(Tenant).all()




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
async def update_tenant(tenant_id: int, tenant_update: TenantUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Update a tenant's details, including system prompt (admin only or authorized user)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Authorization: Allow admin to update any tenant, or a user to update their own tenant.
    # This part of your original code had a slight logic issue for non-admin updates, corrected here.
    if not current_user.is_admin and (current_user.tenant_id is None or current_user.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this tenant")

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
    Send password reset email to tenant admin
    """
    # Find tenant by name
    tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
    # Always return success message, even if tenant not found (security best practice)
    if not tenant:
        return {"message": "If your tenant name exists in our system, you will receive a password reset link."}
    
    # Check if tenant already has a valid token
    existing_token = db.query(TenantPasswordReset).filter(
        TenantPasswordReset.tenant_id == tenant.id,
        TenantPasswordReset.is_used == False,
        TenantPasswordReset.expires_at > datetime.now()
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
    
    # To send an email, you need to have an email associated with the tenant
    # If you don't have tenant email, you might need to modify this part
    tenant_admin_email = tenant.admin_email  # You might need to add this field to your Tenant model
    
    if tenant_admin_email:
        # Send email
        reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password?token={reset_token}"
        
        # Prepare email content
        email_body = f"""
        <html>
        <body>
            <h2>Tenant Password Reset Request</h2>
            <p>Hello {tenant.name} Administrator,</p>
            <p>We received a request to reset your tenant password. If you didn't make this request, you can ignore this email.</p>
            <p>To reset your password, click the link below:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>This link will expire in 24 hours.</p>
            <p>Best regards,<br>Your App Team</p>
        </body>
        </html>
        """
        
        # Send email
        try:
            email_service.send_email(
                to_email=tenant_admin_email,
                subject="Tenant Password Reset Request",
                html_content=email_body
            )
        except Exception as e:
            # Log error, but don't reveal to user
            print(f"Error sending password reset email: {e}")
    
    return {"message": "If your tenant name exists in our system, you will receive a password reset link."}

@router.post("/forgot-password", response_model=MessageResponse)
async def tenant_forgot_password(request: TenantForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Send password reset email to tenant contact
    """
    # Find tenant by name
    tenant = db.query(Tenant).filter(Tenant.name == request.name).first()
    
    # Always return success message, even if tenant not found (security best practice)
    if not tenant:
        return {"message": "If your tenant name exists in our system, you will receive a password reset link."}
    
    # Check if tenant already has a valid token
    existing_token = db.query(TenantPasswordReset).filter(
        TenantPasswordReset.tenant_id == tenant.id,
        TenantPasswordReset.is_used == False,
        TenantPasswordReset.expires_at > datetime.now()
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
    tenant_contact_email = tenant.contact_email  # Changed from admin_email
    
    if tenant_contact_email:
        # Send email
        reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/tenant-reset-password?token={reset_token}"
        
        # Prepare email content
        email_body = f"""
        <html>
        <body>
            <h2>Tenant Password Reset Request</h2>
            <p>Hello {tenant.name},</p>
            <p>We received a request to reset your tenant password. If you didn't make this request, you can ignore this email.</p>
            <p>To reset your password, click the link below:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>This link will expire in 24 hours.</p>
            <p>Best regards,<br>Your App Team</p>
        </body>
        </html>
        """
        
        # Send email
        try:
            email_service.send_email(
                to_email=tenant_contact_email,  # Changed from admin_email
                subject="Tenant Password Reset Request",
                html_content=email_body
            )
        except Exception as e:
            # Log error, but don't reveal to user
            print(f"Error sending password reset email: {e}")
    
    return {"message": "If your account name exists in our system, you will receive a password reset link."}