


from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DisconnectionError, TimeoutError, OperationalError, DatabaseError
from contextlib import contextmanager
import logging
import time
from app.config import settings
from typing import Callable, Any



logger = logging.getLogger(__name__)



# Set up logging
logging.basicConfig(level=logging.INFO)
db_logger = logging.getLogger('database')

def get_engine_config():
    """Database engine configuration for Transaction pooler"""
    
    # Check if we're using PostgreSQL or SQLite
    database_url = getattr(settings, 'DATABASE_URL', 'sqlite:///./chatbot.db')
    is_postgresql = "postgresql" in database_url.lower()
    
    base_config = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,     # 1 hour
        "pool_timeout": 30,
        "echo": False,
    }
    
    # Only add PostgreSQL-specific connect_args if using PostgreSQL
    if is_postgresql:
        base_config["connect_args"] = {
            "application_name": "lyra",
            "connect_timeout": 10,
            "prepare_threshold": None,  # Disable prepared statements
        }
    else:
        # For SQLite - only use supported parameters
        base_config["connect_args"] = {
            "check_same_thread": False,  # Allow SQLite across threads
        }
    
    if settings.is_production():
        config = {
            **base_config,
            "pool_size": 20,          # Increased from 5
            "max_overflow": 30,       # Increased from 10
        }
    elif settings.is_staging():
        config = {
            **base_config,
            "pool_size": 10,          # Increased from 3
            "max_overflow": 15,       # Increased from 7
        }
    else:  # development
        config = {
            **base_config,
            "pool_size": 8,           # Increased from 2
            "max_overflow": 12,       # Increased from 5
            "echo": False,
        }
        
        # For SQLite in development, optimize for single-threaded usage
        if not is_postgresql:
            config.update({
                "poolclass": None,  # Disable connection pooling for SQLite
            })
    
    return config

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



def retry_database_initialization(
    func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Retry database initialization operations with exponential backoff.
    
    Args:
        func: The database operation to retry
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each retry
    
    Returns:
        Result of the successful function call
    
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    current_delay = delay
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Database operation attempt {attempt + 1}/{max_retries}")
            result = func()
            logger.info(f"Database operation succeeded on attempt {attempt + 1}")
            return result
            
        except (OperationalError, DatabaseError, ConnectionError) as e:
            last_exception = e
            logger.warning(
                f"Database operation failed on attempt {attempt + 1}/{max_retries}: {str(e)}"
            )
            
            if attempt < max_retries - 1:  # Don't sleep on the last attempt
                logger.info(f"Retrying in {current_delay} seconds...")
                time.sleep(current_delay)
                current_delay *= backoff_factor
            else:
                logger.error("All database operation attempts failed")
    
    # If we get here, all retries failed
    raise last_exception


def create_tables_with_retry():
    """Create database tables with retry logic"""
    from app.database import Base, engine  # Import your database objects
    
    def _create_tables():
        Base.metadata.create_all(bind=engine)
        return True
    
    return retry_database_initialization(_create_tables)


def initialize_database_with_retry():
    """Initialize database connection with retry logic"""
    from app.database import engine
    from sqlalchemy import text # Import text
    
    def _test_connection():
        # Test the database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")) # Add text() wrapper here
        return True
    
    return retry_database_initialization(_test_connection)



def reset_connection_pool():
    """Reset database connection pool"""
    try:
        engine.dispose()
        logger.info("Database connection pool reset")
    except Exception as e:
        logger.error(f"Pool reset failed: {e}")



# Import your models
from app.auth.models import User, PasswordReset
from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.integrations.booking_models import BookingRequest
from app.chatbot.models import ChatSession, ChatMessage