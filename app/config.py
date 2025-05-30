import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

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
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    
    # Email Configuration (add to your settings class)
    SMTP_SERVER: str = "smtp.gmail.com"  # or your SMTP server
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = "your-email@gmail.com"  # Your email
    SMTP_PASSWORD: str = "your-app-password"     # App password for Gmail
    FROM_EMAIL: str = "your-email@gmail.com"     # From address
   

settings = Settings()