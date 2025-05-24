from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime, timedelta
import secrets





class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    api_key = Column(String, unique=True, index=True)
    # hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    contact_email = Column(String, nullable=True)
    system_prompt = Column(Text, nullable=True)  # Custom system prompt for this tenant
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()) # Added server_default for creation as well, often useful
    
    # Relationships
    users = relationship("User", back_populates="tenant") # Assuming User model has a back_populates="tenant"
    knowledge_bases = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")
    faqs = relationship("FAQ", back_populates="tenant", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="tenant", cascade="all, delete-orphan")
    tenant_credentials = relationship("TenantCredentials", back_populates="tenant", uselist=False, overlaps="tenant_credentials", cascade="all, delete-orphan")
    credentials = relationship("TenantCredentials", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    
    # Discord integration fields
    discord_bot_token = Column(String, nullable=True)
    discord_application_id = Column(String, nullable=True)
    discord_enabled = Column(Boolean, default=False)
    discord_status_message = Column(String, nullable=True, default="Chatting with customers")



class TenantPasswordReset(Base):
    __tablename__ = "tenant_password_resets"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)

    @classmethod
    def create_token(cls, tenant_id: int):
        """Create a new password reset token"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        return cls(
            tenant_id=tenant_id,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and datetime.utcnow() < self.expires_at