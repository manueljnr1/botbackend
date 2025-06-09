import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
from datetime import datetime
from fastapi import Form, Body
from app.auth.models import PasswordReset


from app.database import get_db
from app.auth.models import User
from app.tenants.models import Tenant
# Remove this line - Admin is in app.admin.models, not app.auth.models
# from app.auth.models import Admin
from app.admin.models import Admin  # Import from correct location
from app.config import settings
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter()


# Password and token handling
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str
    tenant_api_key: Optional[str] = None

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
    email: str

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

async def get_admin_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Dependency to get current admin user from JWT token
    Handles both User admins (is_admin=True) and Admin table entries
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        subject: str = payload.get("sub")
        is_admin_flag: bool = payload.get("is_admin", False)
        
        if subject is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    # Check if this is an admin token (from admin login endpoint)
    if is_admin_flag:
        # This is an admin token - look up in Admin table
        admin = db.query(Admin).filter(Admin.id == subject, Admin.is_active == True).first()
        if admin is None:
            raise credentials_exception
        return admin
    else:
        # This is a regular user token - check if user is admin
        user = db.query(User).filter(User.username == subject, User.is_active == True).first()
        if user is None or not user.is_admin:
            raise credentials_exception
        return user

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Get an access token by providing username and password
    """
    # Debug info
    logger.info(f"Login attempt for username: {form_data.username}")
    
    # Get user
    user = db.query(User).filter(User.username == form_data.username).first()
    
    # Debug user info
    if user:
        logger.info(f"User found in database: {user.username}, Active: {user.is_active}")
    else:
        logger.info(f"No user found with username: {form_data.username}")
        # List all users for debugging (be careful with this in production!)
        all_users = db.query(User).all()
        logger.info(f"All users in database: {[u.username for u in all_users]}")

    if not user:
        logger.warning(f"User not found: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the password
    is_password_correct = verify_password(form_data.password, user.hashed_password)
    if not is_password_correct:
        logger.warning(f"Invalid password for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        logger.warning(f"Inactive user attempt to login: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    logger.info(f"Successfully authenticated user: {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me/", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information
    """
    return current_user

@router.get("/users/", response_model=List[UserOut]) # This will be GET /api/auth/users/
async def read_all_users_for_admin(
    db: Session = Depends(get_db),
    current_admin = Depends(get_admin_user) # Can be either User or Admin
):
    """
    Retrieve all users. Accessible only by admin users.
    """
    users = db.query(User).all()
    return users