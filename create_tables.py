#!/usr/bin/env python3
"""
Script to create database tables
"""
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables():
    """Create database tables"""
    from app.database import engine, Base
    
    # Import models to ensure they're registered with SQLAlchemy
    from app.tenants.models import Tenant
    from app.knowledge_base.models import KnowledgeBase, FAQ
    from app.chatbot.models import ChatSession, ChatMessage
    from app.auth.models import User, TenantCredentials
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully!")

if __name__ == "__main__":
    create_tables()