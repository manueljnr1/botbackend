#!/usr/bin/env python3
"""
Initialize the database by creating all tables
"""
from app.database import engine, Base
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.chatbot.models import ChatSession, ChatMessage
from app.auth.models import User

def init_database():
    print("Creating database tables...")
    # Import all models to ensure they're registered with SQLAlchemy
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_database()