import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from urllib.parse import urlparse
from typing import List

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
    SMTP_USERNAME: str = "your-email@gmail.com"
    SMTP_PASSWORD: str = "your-app-password"
    FROM_EMAIL: str = "your-email@gmail.com"
    
    # Environment and Frontend Configuration
    ENVIRONMENT: str = "development"  # development, staging, production
    FRONTEND_URL: Optional[str] = None
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
                "SUPABASE_SERVICE_KEY": self.SUPABASE_SERVICE_KEY
            }
            
            missing = [key for key, value in required_fields.items() if not value]
            if missing:
                env_name = "production" if self.is_production() else "staging"
                raise ValueError(f"Missing required {env_name} config: {missing}")
            
            # Validate JWT key length
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
            
            # Validate domains only in production (staging can be more flexible)
            if self.is_production() and not self.get_allowed_domains_list():
                raise ValueError("ALLOWED_DOMAINS is required in production")
    
    def get_password_reset_url(self) -> str:
        """Get validated password reset URL"""
        frontend_url = self.FRONTEND_URL or "http://localhost:3000"
        
        # Validate domain only in production
        if self.is_production():
            allowed_domains = self.get_allowed_domains_list()
            if allowed_domains:
                parsed = urlparse(frontend_url)
                if parsed.netloc not in allowed_domains:
                    raise ValueError(f"Frontend domain {parsed.netloc} not in allowed domains: {allowed_domains}")
        
        return f"{frontend_url}/tenant-reset-password"
    
    def get_cors_origins(self) -> list:
        """Get CORS origins based on environment."""
        
        # --- Development Environment ---
        # For local testing, allow common local origins including local files (null).
        if self.is_development():
            return [
                "null",                  # For local file:// access
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:5173", # Common for ViteJS
                "http://localhost:8080", # Common for other local servers
            ]

        # --- Production & Staging Environments ---
        # For production and staging, use a strict, explicit list of domains.
        origins = []
        
        # TEMPORARY: Allow null origin for local file access
        origins.append("null")
        
        if self.FRONTEND_URL:
            origins.append(self.FRONTEND_URL)

        # Add other specific production/staging domains
        origins.extend([
            "https://frontier-j08o.onrender.com",
            "https://agentlyra.com",
            "https://www.agentlyra.com",
        ])
        
        # Add domains from the environment configuration
        for domain in self.get_allowed_domains_list():
            origins.extend([
                f"https://{domain}",
                f"https://www.{domain}",
            ])
            
        # Remove duplicates and return the final list
        return list(set(origins))


settings = Settings()