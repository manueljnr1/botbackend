# app/models/admin.py
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, String, Integer
from sqlalchemy.sql import func

from app.database import Base

class Admin(Base):
    __tablename__ = "admins"

    # Use Integer instead of UUID for SQLite compatibility
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())