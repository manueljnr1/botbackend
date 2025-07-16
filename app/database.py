# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
# from app.config import settings # Ensure this import is correct and settings.DATABASE_URL exists

# engine = create_engine(settings.DATABASE_URL)

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()

# engine = create_engine(
#     settings.DATABASE_URL
    
# )
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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




from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings
import os

# Get the database URL
DATABASE_URL = settings.DATABASE_URL

# More aggressive SSL fix for Supabase
connect_args = {}
if DATABASE_URL and "supabase.co" in DATABASE_URL:
    # Try to use connection pooler URL format
    if "pooler.supabase.com" not in DATABASE_URL:
        print("⚠️ Warning: Using direct Supabase connection. Consider using connection pooler.")
    
    connect_args = {
        "sslmode": "require",
        "sslcert": "",
        "sslkey": "",
        "sslrootcert": "",
        "sslcrl": "",
        "connect_timeout": 30,
        "application_name": "railway-app",
        "tcp_keepalives_idle": "600",
        "tcp_keepalives_interval": "30",
        "tcp_keepalives_count": "3"
    }
    
    # Force SSL parameters in URL
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require&connect_timeout=30"
    else:
        DATABASE_URL += "?sslmode=require&connect_timeout=30"

# Create engine with aggressive connection management
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,           # Test connections before use
    pool_recycle=60,              # Recycle connections every minute (more aggressive)
    pool_timeout=30,              # Longer connection timeout
    max_overflow=0,               # No overflow connections
    pool_size=1,                  # Use only 1 connection to avoid SSL issues
    connect_args=connect_args,
    echo=False                    # Set to True for debugging SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Import models (keep these at the bottom)
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