from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings # Ensure this import is correct and settings.DATABASE_URL exists

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

engine = create_engine(
    settings.DATABASE_URL
    
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


from app.auth.models import User, PasswordReset
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ

from app.chatbot.models import ChatSession, ChatMessage



# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()