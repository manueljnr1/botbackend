# app/core/security.py
from datetime import datetime, timedelta
from typing import Any, Union, Optional
from passlib.context import CryptContext
import secrets
import string

# Try to import JWT dependencies
try:
    from jose import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("Warning: python-jose not installed. JWT functionality will be limited.")

# Try to get settings
try:
    from app.config import settings
    SECRET_KEY = getattr(settings, 'SECRET_KEY', 'your-secret-key-change-in-production')
    ALGORITHM = getattr(settings, 'ALGORITHM', 'HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 30)
except ImportError:
    # Fallback settings
    SECRET_KEY = 'your-secret-key-change-in-production-please'
    ALGORITHM = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt
    """
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash
    """
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(
    data: dict, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time (optional)
        
    Returns:
        Encoded JWT token string
    """
    if not JWT_AVAILABLE:
        # Fallback implementation - basic base64 encoding (NOT secure for production)
        import json
        import base64
        to_encode = data.copy()
        to_encode.update({"exp": (datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))).isoformat()})
        return base64.b64encode(json.dumps(to_encode).encode()).decode()
    
    # Proper JWT implementation
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT access token
    
    Args:
        token: JWT token string to decode
        
    Returns:
        Decoded token data or None if invalid
    """
    if not JWT_AVAILABLE:
        # Fallback implementation
        try:
            import json
            import base64
            decoded = json.loads(base64.b64decode(token.encode()).decode())
            # Check expiration
            exp_str = decoded.get('exp')
            if exp_str:
                exp_time = datetime.fromisoformat(exp_str)
                if datetime.utcnow() > exp_time:
                    return None
            return decoded
        except Exception:
            return None
    
    # Proper JWT implementation
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        return None

def generate_random_string(length: int = 32) -> str:
    """
    Generate a cryptographically secure random string
    
    Args:
        length: Length of the string to generate
        
    Returns:
        Random string
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_api_key() -> str:
    """
    Generate a secure API key
    
    Returns:
        Random API key string
    """
    return generate_random_string(64)

def verify_token(token: str) -> Optional[dict]:
    """
    Alias for decode_access_token for backward compatibility
    """
    return decode_access_token(token)