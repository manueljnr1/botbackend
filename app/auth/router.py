import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from datetime import datetime
from fastapi import Form, Body
from pydantic import EmailStr
from app.auth.models import PasswordReset
from app.utils.email_service import email_service

from app.database import get_db
from app.auth.models import User
from app.tenants.models import Tenant
from app.config import settings

router = APIRouter()

# Password and token handling
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    username: str
    password: str
    is_admin: bool = False
    tenant_id: Optional[int] = None

class UserOut(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    is_admin: bool
    tenant_id: Optional[int]
    
    class Config:
        from_attributes = True

class UserRegister(BaseModel):
    email: str
    username: str
    password: str
    confirm_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class MessageResponse(BaseModel):
    message: str


# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action"
        )
    return current_user

# Endpoints
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Get an access token by providing username and password
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/users/", response_model=UserOut)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user without requiring authentication"""
    # Check if user exists
    db_user = db.query(User).filter((User.email == user.email) | (User.username == user.username)).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    # Create user
    new_user = User(
        email=user.email,
        username=user.username,
        hashed_password=get_password_hash(user.password),
        is_admin=user.is_admin,
        tenant_id=user.tenant_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/me/", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information
    """
    return current_user

@router.get("/users/", response_model=List[UserOut]) # This will be GET /api/auth/users/
async def read_all_users_for_admin(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_admin_user) # Ensures only admin access
):
    """
    Retrieve all users. Accessible only by admin users.
    """
    users = db.query(User).all()
    return users

@router.post("/register", response_model=UserOut)
async def register_user(user: UserRegister, db: Session = Depends(get_db)):
    """Public registration endpoint"""
    # Validate passwords match
    if user.password != user.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords don't match")
    
    # Check if user exists
    db_user = db.query(User).filter((User.email == user.email) | (User.username == user.username)).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    # Get default tenant for new users
    default_tenant = db.query(Tenant).filter(Tenant.is_active == True).first()
    if not default_tenant:
        raise HTTPException(status_code=500, detail="No active tenant found for user registration")
    
    # Create user
    new_user = User(
        email=user.email,
        username=user.username,
        hashed_password=get_password_hash(user.password),
        is_admin=False,
        tenant_id=default_tenant.id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Return user without password
    return new_user


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Send password reset email to user
    """
    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    
    # Always return success message, even if user not found (security best practice)
    if not user:
        return {"message": "If your email exists in our system, you will receive a password reset link."}
    
    # Check if user already has a valid token
    existing_token = db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id,
        PasswordReset.is_used == False,
        PasswordReset.expires_at > datetime.now()
    ).first()
    
    # If token exists, reuse it, otherwise create a new one
    if existing_token:
        reset_token = existing_token.token
    else:
        # Create new token
        password_reset = PasswordReset.create_token(user.id)
        db.add(password_reset)
        db.commit()
        db.refresh(password_reset)
        reset_token = password_reset.token
    
    # Send email
    reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={reset_token}"
    
    # Prepare email content
    email_body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>Hello {user.username},</p>
        <p>We received a request to reset your password. If you didn't make this request, you can ignore this email.</p>
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
            to_email=user.email,
            subject="Password Reset Request",
            html_content=email_body
        )
    except Exception as e:
        # Log error, but don't reveal to user
        print(f"Error sending password reset email: {e}")
    
    return {"message": "If your email exists in our system, you will receive a password reset link."}

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using token
    """
    # Find token
    password_reset = db.query(PasswordReset).filter(PasswordReset.token == request.token).first()
    
    # Check if token exists and is valid
    if not password_reset or not password_reset.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    # Get user
    user = db.query(User).filter(User.id == password_reset.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    
    # Mark token as used
    password_reset.is_used = True
    
    # Commit changes
    db.commit()
    
    return {"message": "Password has been reset successfully"}

@router.get("/validate-reset-token/{token}", response_model=MessageResponse)
async def validate_reset_token(token: str, db: Session = Depends(get_db)):
    """
    Validate a password reset token
    """
    # Find token
    password_reset = db.query(PasswordReset).filter(PasswordReset.token == token).first()
    
    # Check if token exists and is valid
    if not password_reset or not password_reset.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    return {"message": "Token is valid"}