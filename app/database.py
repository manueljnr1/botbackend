# from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import sessionmaker
# from app.config import settings # Ensure this import is correct and settings.DATABASE_URL exists

# # engine = create_engine(settings.DATABASE_URL)
# engine = create_engine(settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://"))

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




from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool
from sqlalchemy.exc import DisconnectionError, TimeoutError
from contextlib import contextmanager
import logging
import time
from app.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
db_logger = logging.getLogger('database')

# Create engine with robust configuration
database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
engine = create_engine(database_url, **settings.get_database_engine_config)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Add connection monitoring
@event.listens_for(Pool, "connect")
def log_connection(dbapi_conn, connection_record):
    db_logger.info("New database connection established")

@event.listens_for(Pool, "checkout")
def log_checkout(dbapi_conn, connection_record, connection_proxy):
    db_logger.debug("Connection checked out from pool")

@event.listens_for(Pool, "checkin")
def log_checkin(dbapi_conn, connection_record):
    db_logger.debug("Connection returned to pool")

# Robust connection context manager
@contextmanager
def get_db_connection(retries=3):
    """Context manager with automatic retry and proper cleanup"""
    connection = None
    for attempt in range(retries):
        try:
            connection = engine.connect()
            yield connection
            break
        except (DisconnectionError, TimeoutError) as e:
            if connection:
                connection.close()
            if attempt == retries - 1:
                db_logger.error(f"DB connection failed after {retries} attempts: {e}")
                raise
            wait_time = 2 ** attempt
            db_logger.warning(f"DB connection attempt {attempt + 1} failed, retrying in {wait_time}s")
            time.sleep(wait_time)
        finally:
            if connection:
                connection.close()

# Enhanced session dependency
def get_db():
    """Enhanced database session with retry logic"""
    db = SessionLocal()
    try:
        yield db
    except (DisconnectionError, TimeoutError) as e:
        db_logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

# Health check function
def database_health_check():
    """Health check for monitoring"""
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "pool_size": engine.pool.size()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Import your models (keep existing imports)
from app.auth.models import User, PasswordReset
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.integrations.booking_models import BookingRequest
from app.chatbot.models import ChatSession, ChatMessage
