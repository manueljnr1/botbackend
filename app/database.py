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
from sqlalchemy.pool import Pool
from sqlalchemy.exc import DisconnectionError, TimeoutError, OperationalError
from contextlib import contextmanager
import logging
import time
from typing import Optional
from app.config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
db_logger = logging.getLogger('database')

# Global variables for lazy initialization
_engine: Optional[object] = None
_SessionLocal: Optional[object] = None

def get_engine_config():
    """Get database engine configuration based on environment"""
    base_config = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,  # 1 hour
        "pool_timeout": 30,
        "connect_args": {
            "options": "-c statement_timeout=30000",
            "keepalives_idle": "600",
            "keepalives_interval": "30", 
            "keepalives_count": "3",
        }
    }
    
    if settings.is_production():
        return {
            **base_config,
            "pool_size": 5,
            "max_overflow": 10,
            "echo": False,
        }
    elif settings.is_staging():
        return {
            **base_config,
            "pool_size": 3,
            "max_overflow": 7,
            "echo": False,
        }
    else:  # development
        return {
            **base_config,
            "pool_size": 2,
            "max_overflow": 5,
            "echo": False,  # Disable SQL logging to reduce noise
        }

def initialize_database(max_retries=5):
    """Initialize database connection with retry logic"""
    global _engine, _SessionLocal
    
    if _engine is not None:
        return _engine, _SessionLocal
    
    database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
    engine_config = get_engine_config()
    
    for attempt in range(max_retries):
        try:
            db_logger.info(f"Initializing database (attempt {attempt + 1}/{max_retries})...")
            
            # Create engine without immediate connection test
            _engine = create_engine(database_url, **engine_config)
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
            
            # Test connection separately with timeout
            try:
                with _engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_logger.info("✅ Database connection established successfully")
            except Exception as conn_error:
                db_logger.warning(f"⚠️ Database connection test failed: {conn_error}")
                # Continue anyway - connection might work later
            
            return _engine, _SessionLocal
            
        except Exception as e:
            if attempt == max_retries - 1:
                db_logger.error(f"❌ Failed to initialize database after {max_retries} attempts: {e}")
                # Create a dummy engine to prevent import errors
                _engine = None
                _SessionLocal = None
                raise
            
            wait_time = 2 ** attempt
            db_logger.warning(f"⚠️ Database initialization attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
            time.sleep(wait_time)

# Initialize with fallback
try:
    engine, SessionLocal = initialize_database()
except Exception as e:
    db_logger.error(f"❌ Database initialization failed during import: {e}")
    # Create minimal objects to prevent import errors
    engine = None
    SessionLocal = None

Base = declarative_base()

# Add connection monitoring (only if engine exists)
if engine:
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
    global _engine
    
    if _engine is None:
        try:
            _engine, _ = initialize_database()
        except Exception as e:
            db_logger.error(f"Failed to initialize database: {e}")
            raise
    
    connection = None
    for attempt in range(retries):
        try:
            connection = _engine.connect()
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

# Enhanced session dependency with error handling
def get_db():
    """Enhanced database session with retry logic"""
    global _SessionLocal, _engine
    
    if _SessionLocal is None:
        try:
            _engine, _SessionLocal = initialize_database()
        except Exception as e:
            db_logger.error(f"Failed to initialize database session: {e}")
            raise
    
    db = _SessionLocal()
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
        if _engine is None:
            return {"status": "unhealthy", "error": "Database not initialized"}
            
        with get_db_connection() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy", 
            "pool_size": _engine.pool.size(),
            "checked_out": _engine.pool.checkedout(),
            "engine_initialized": _engine is not None
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Safe table creation function
def create_tables_safely():
    """Create tables with retry logic"""
    global _engine
    
    if _engine is None:
        try:
            _engine, _ = initialize_database()
        except Exception as e:
            db_logger.error(f"Cannot create tables - database not initialized: {e}")
            raise
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db_logger.info(f"Creating database tables (attempt {attempt + 1}/{max_retries})...")
            Base.metadata.create_all(bind=_engine)
            db_logger.info("✅ Database tables created successfully")
            return True
        except (OperationalError, DisconnectionError, TimeoutError) as e:
            if attempt == max_retries - 1:
                db_logger.error(f"❌ Failed to create tables after {max_retries} attempts: {e}")
                raise
            wait_time = 2 ** attempt
            db_logger.warning(f"⚠️ Table creation attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
            time.sleep(wait_time)

# Retry database initialization function for startup
async def retry_database_initialization():
    """Retry database initialization during application startup"""
    global _engine, _SessionLocal
    
    max_retries = 10
    for attempt in range(max_retries):
        try:
            db_logger.info(f"🔄 Retrying database initialization (attempt {attempt + 1}/{max_retries})...")
            _engine, _SessionLocal = initialize_database(max_retries=2)
            
            # Try to create tables
            create_tables_safely()
            
            db_logger.info("✅ Database fully initialized during startup")
            return True
            
        except Exception as e:
            if attempt == max_retries - 1:
                db_logger.error(f"❌ Database initialization failed permanently: {e}")
                return False
            
            wait_time = min(30, 5 * (attempt + 1))  # Cap at 30 seconds
            db_logger.warning(f"⚠️ Database initialization failed, retrying in {wait_time}s: {e}")
            import asyncio
            await asyncio.sleep(wait_time)

# Import your models (keep existing imports)
try:
    from app.auth.models import User, PasswordReset
    from app.tenants.models import Tenant
    from app.knowledge_base.models import KnowledgeBase, FAQ
    from app.integrations.booking_models import BookingRequest
    from app.chatbot.models import ChatSession, ChatMessage
except Exception as e:
    db_logger.warning(f"⚠️ Some models may not be available due to database issues: {e}")