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







from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DisconnectionError, TimeoutError, OperationalError
from contextlib import contextmanager
import logging
import time
from app.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
db_logger = logging.getLogger('database')

def get_engine_config():
    """Database engine configuration for Transaction pooler"""
    base_config = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,     # 1 hour
        "pool_timeout": 30,
        "echo": False,
        "connect_args": {
            "application_name": "lyra",
            "connect_timeout": 10,
        }
    }
    
    if settings.is_production():
        return {
            **base_config,
            "pool_size": 5,           # Back to normal
            "max_overflow": 10,       # Back to normal
        }
    elif settings.is_staging():
        return {
            **base_config,
            "pool_size": 3,
            "max_overflow": 7,
        }
    else:  # development
        return {
            **base_config,
            "pool_size": 2,
            "max_overflow": 5,
            "echo": True,             # SQL logging in dev
        }

# Create engine
database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
engine = create_engine(database_url, **get_engine_config())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Add connection monitoring
@event.listens_for(engine.pool, "connect")
def log_connection(dbapi_conn, connection_record):
    db_logger.info("New database connection established")

@event.listens_for(engine.pool, "checkout")
def log_checkout(dbapi_conn, connection_record, connection_proxy):
    db_logger.debug("Connection checked out from pool")

@event.listens_for(engine.pool, "checkin")
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
        except (DisconnectionError, TimeoutError, OperationalError) as e:
            if connection:
                try:
                    connection.close()
                except:
                    pass
            if attempt == retries - 1:
                db_logger.error(f"DB connection failed after {retries} attempts: {e}")
                raise
            wait_time = 2 ** attempt
            db_logger.warning(f"DB connection attempt {attempt + 1} failed, retrying in {wait_time}s")
            time.sleep(wait_time)
        finally:
            if connection:
                try:
                    connection.close()
                except:
                    pass

# Enhanced session dependency
def get_db():
    """Database session with error handling"""
    db = SessionLocal()
    try:
        yield db
    except (DisconnectionError, TimeoutError, OperationalError) as e:
        db_logger.error(f"Database session error: {e}")
        try:
            db.rollback()
        except:
            pass
        raise
    finally:
        try:
            db.close()
        except:
            pass

# Health check function
def database_health_check():
    """Health check for monitoring"""
    try:
        with get_db_connection() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy", 
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout(),
            "overflow": engine.pool.overflow(),
            "total_connections": engine.pool.size() + engine.pool.overflow()
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Safe table creation function
def create_tables_safely():
    """Create tables with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db_logger.info(f"Creating database tables (attempt {attempt + 1}/{max_retries})...")
            Base.metadata.create_all(bind=engine)
            db_logger.info("✅ Database tables created successfully")
            return True
        except (OperationalError, DisconnectionError, TimeoutError) as e:
            if attempt == max_retries - 1:
                db_logger.error(f"❌ Failed to create tables after {max_retries} attempts: {e}")
                raise
            wait_time = 2 ** attempt
            db_logger.warning(f"⚠️ Table creation attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
            time.sleep(wait_time)

# Import your models
from app.auth.models import User, PasswordReset
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.integrations.booking_models import BookingRequest
from app.chatbot.models import ChatSession, ChatMessage