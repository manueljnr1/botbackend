import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from urllib.parse import urlparse
import logging
from typing import List


logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./chatbot.db"
    
    # Security
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    
    # Vector Database
    VECTOR_DB_PATH: str = "./vector_db"
    
    # Slack Integration
    SLACK_SIGNING_SECRET: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    
    # Twilio/WhatsApp Integration
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    
    # Default API key for integrations
    DEFAULT_API_KEY: Optional[str] = None
    
    # Email Configuration
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: Optional[str] = None

    RESEND_API_KEY: Optional[str] = None

    # Environment and Frontend Configuration
    ENVIRONMENT: str = "development"  # development, staging, production
    ALLOWED_DOMAINS: Optional[str] = None
    
    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


    # Supabase Storage
    SUPABASE_STORAGE_URL: str = os.getenv("SUPABASE_STORAGE_URL", "")
    SUPABASE_STORAGE_BUCKET: str = 'tenant-logos'
    
    # Logo upload settings
    MAX_LOGO_SIZE: int = 2 * 1024 * 1024  # 2MB
    ALLOWED_LOGO_TYPES: List[str] = [
    "image/jpeg", "image/jpg", "image/png", 
    "image/webp", "image/svg+xml"
    ]   


    META_API_VERSION: str = "v18.0"
    INSTAGRAM_WEBHOOK_ENDPOINT: str = "/api/instagram/webhook"
    INSTAGRAM_MAX_MESSAGE_LENGTH: int = 1000
    
    CHATBOT_WIDGET_ICON_URL = os.getenv("CHATBOT_WIDGET_ICON_URL", "/static/assets/chatbot-icon-32x32.png")


    # 📧 NEW: Frontend URL for email confirmation redirects
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # 📧 NEW: Password reset URL (can be different from main frontend)
    PASSWORD_RESET_URL: Optional [str] = os.getenv("PASSWORD_RESET_URL", None)

    PRODUCTION_DOMAINS: Optional[str] = None 
    
    def get_allowed_domains_list(self) -> list:
        """Get allowed domains as a list"""
        if not self.ALLOWED_DOMAINS:
            return []
        return [domain.strip() for domain in self.ALLOWED_DOMAINS.split(",") if domain.strip()]
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"
    
    def is_staging(self) -> bool:
        """Check if running in staging/testing"""
        return self.ENVIRONMENT in ["staging", "testing"]
    
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"
    
    def requires_security_validation(self) -> bool:
        """Check if environment requires full security validation"""
        return self.ENVIRONMENT in ["production", "staging"]
    
    def validate_production_config(self):
        """Validate required configuration for production and staging"""
        if self.requires_security_validation():
            required_fields = {
                "FRONTEND_URL": self.FRONTEND_URL,
                "JWT_SECRET_KEY": self.JWT_SECRET_KEY,
                "SUPABASE_URL": self.SUPABASE_URL,
                "SUPABASE_SERVICE_KEY": self.SUPABASE_SERVICE_KEY,
                "FROM_EMAIL": self.FROM_EMAIL,
            }
            
            missing = [key for key, value in required_fields.items() if not value]
            if missing:
                env_name = "production" if self.is_production() else "staging"
                raise ValueError(f"Missing required {env_name} config: {missing}")
            
            # Validate JWT key length
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
            
            # Validate email format
            if self.FROM_EMAIL and "@" not in self.FROM_EMAIL:
                raise ValueError("FROM_EMAIL must be a valid email address")
            
            # Require either SMTP OR Resend for email
            has_smtp = all([self.SMTP_USERNAME, self.SMTP_PASSWORD])
            has_resend = bool(self.RESEND_API_KEY)
            
            if not has_smtp and not has_resend:
                raise ValueError("Either SMTP configuration or RESEND_API_KEY is required")
            
            # Validate domains only in production
            if self.is_production() and not self.get_allowed_domains_list() and not self.PRODUCTION_DOMAINS:
                raise ValueError("ALLOWED_DOMAINS or PRODUCTION_DOMAINS is required in production")
            
            # Add database URL validation
            if not self.DATABASE_URL or "postgresql" not in self.DATABASE_URL:
                raise ValueError("DATABASE_URL must be a valid PostgreSQL connection string")
            
            # Validate database URL format
            if self.DATABASE_URL and not self.DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("DATABASE_URL must start with 'postgresql://' or 'postgresql+psycopg://'")
        
   
    
    def get_cors_origins(self) -> list:
        origins = ["null"]
        
        if self.is_development():
            origins.extend([
                "http://localhost:3000",
                "http://localhost:3001", 
                "http://localhost:5173",
                "http://localhost:8080"
            ])
        
        if self.FRONTEND_URL:
            origins.append(self.FRONTEND_URL)
        
        # Only YOUR company domains
        if self.PRODUCTION_DOMAINS:
            domains = [d.strip() for d in self.PRODUCTION_DOMAINS.split(",")]
            for domain in domains:
                origins.extend([f"https://{domain}", f"https://www.{domain}"])
        
        return list(set(origins))
    

    def get_all_cors_origins(self, db_session=None) -> list:
        """Get all CORS origins including tenant domains"""
        origins = self.get_cors_origins()
        
        if db_session:
            try:
                from app.tenants.models import Tenant
                tenants = db_session.query(Tenant).filter(
                    Tenant.allowed_origins.isnot(None)
                ).all()
                
                for tenant in tenants:
                    if tenant.allowed_origins:
                        for domain in tenant.allowed_origins.split(","):
                            domain = domain.strip()
                            origins.extend([f"https://{domain}", f"https://www.{domain}"])
            
            except Exception as e:
                # Column doesn't exist yet, just return base origins
                logger.warning(f"⚠️ Could not load tenant origins: {e}")
                pass
        
        return list(set(origins))
    


    def get_password_reset_url(self) -> str:
        """Get the password reset URL, fallback to frontend URL"""
        return self.PASSWORD_RESET_URL or f"{self.FRONTEND_URL}/auth/reset-password"
    
    def get_email_confirmation_url(self) -> str:
        """Get the email confirmation URL"""
        return f"{self.FRONTEND_URL}/auth/confirm"
    

    def get_email_config(self) -> dict:
        """Get email configuration with validation"""
        if not all([self.SMTP_USERNAME, self.SMTP_PASSWORD, self.FROM_EMAIL]):
            if self.requires_security_validation():
                raise ValueError("Email configuration incomplete for production environment")
            return None
        
        return {
            "smtp_server": self.SMTP_SERVER,
            "smtp_port": self.SMTP_PORT,
            "username": self.SMTP_USERNAME,
            "password": self.SMTP_PASSWORD,
            "from_email": self.FROM_EMAIL,
        }
    

    def get_tenant_cors_origins(self, tenant_allowed_origins: str = None) -> list:
        origins = self.get_cors_origins()  # Your company domains
        
        # Add tenant-specific domains
        if tenant_allowed_origins:
            domains = [d.strip() for d in tenant_allowed_origins.split(",")]
            for domain in domains:
                origins.extend([f"https://{domain}", f"https://www.{domain}"])
        
        return list(set(origins))
    



        
    @property
    def get_database_engine_config(self) -> dict:
        """Get database engine configuration based on environment"""
        base_config = {
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "pool_timeout": 30,
            "connect_args": {
                "application_name": "lyra",
                "connect_timeout": 10,
            }
        }
        
        if self.is_production():
            return {
                **base_config,
                "pool_size": 5,
                "max_overflow": 10,
                "echo": False,
            }
        elif self.is_staging():
            return {
                **base_config,
                "pool_size": 3,
                "max_overflow": 7,
                "echo": False,
            }
        else:  # development
            return {
                **base_config,
                "pool_size": 2,
                "max_overflow": 5,
                "echo": True,  # SQL logging in development
            }


settings = Settings()