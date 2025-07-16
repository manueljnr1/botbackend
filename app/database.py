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

from app.integrations.booking_models import BookingRequest

from app.chatbot.models import ChatSession, ChatMessage



# Dependency to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
# from app.config import settings
# import os

# # Get the database URL
# DATABASE_URL = settings.DATABASE_URL

# # Configure SSL for Supabase connections
# connect_args = {}
# if DATABASE_URL and "supabase.co" in DATABASE_URL:
#     connect_args = {
#         "sslmode": "require",
#         "sslcert": None,
#         "sslkey": None, 
#         "sslrootcert": None,
#         "connect_timeout": 10,
#         "application_name": "railway-app"
#     }
    
#     # Add SSL parameters to URL if not present
#     if "sslmode" not in DATABASE_URL:
#         separator = "&" if "?" in DATABASE_URL else "?"
#         DATABASE_URL += f"{separator}sslmode=require&connect_timeout=10"

# # Create engine with proper SSL and connection pooling
# engine = create_engine(
#     DATABASE_URL,
#     pool_pre_ping=True,        # Test connections before use
#     pool_recycle=300,          # Recycle connections every 5 minutes
#     pool_timeout=20,           # Connection timeout
#     max_overflow=0,            # Don't allow overflow connections
#     connect_args=connect_args
# )

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()

# # Import models (keep these at the bottom)
# from app.auth.models import User, PasswordReset
# from app.tenants.models import Tenant
# from app.knowledge_base.models import KnowledgeBase, FAQ
# from app.integrations.booking_models import BookingRequest
# from app.chatbot.models import ChatSession, ChatMessage

# # Dependency to get a DB session
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()