import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.knowledge_base.models import KnowledgeBase, DocumentType, ProcessingStatus
from app.knowledge_base.processor import DocumentProcessor

logger = logging.getLogger(__name__)

class CrawlScheduler:
    """Background scheduler for website crawling"""
    
    def __init__(self):
        self.running = False
        self.check_interval = 3600  # Check every hour
        
    async def start(self):
        """Start the background scheduler"""
        self.running = True
        logger.info("Crawl scheduler started")
        
        while self.running:
            try:
                await self._check_and_crawl()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Crawl scheduler stopped")
    
    async def _check_and_crawl(self):
        """Check for websites that need crawling"""
        db = SessionLocal()
        try:
            # Find websites that need crawling
            now = datetime.utcnow()
            
            websites_to_crawl = db.query(KnowledgeBase).filter(
                KnowledgeBase.document_type == DocumentType.WEBSITE,
                KnowledgeBase.processing_status != ProcessingStatus.PROCESSING,
                # Either never crawled or crawl interval has passed
                db.or_(
                    KnowledgeBase.last_crawled_at.is_(None),
                    KnowledgeBase.last_crawled_at < (
                        now - db.func.make_interval(0, 0, 0, 0, KnowledgeBase.crawl_frequency_hours)
                    )
                )
            ).all()
            
            if websites_to_crawl:
                logger.info(f"Found {len(websites_to_crawl)} websites to crawl")
                
                # Process each website
                for kb in websites_to_crawl:
                    try:
                        await self._crawl_website(kb, db)
                    except Exception as e:
                        logger.error(f"Failed to crawl website {kb.id}: {e}")
                        
        except Exception as e:
            logger.error(f"Error checking websites to crawl: {e}")
        finally:
            db.close()
    
    async def _crawl_website(self, kb: KnowledgeBase, db: Session):
        """Crawl a single website"""
        logger.info(f"Starting scheduled crawl for KB {kb.id}: {kb.name}")
        
        # Update status to processing
        kb.processing_status = ProcessingStatus.PROCESSING
        kb.processing_error = None
        db.commit()
        
        processor = DocumentProcessor(kb.tenant_id)
        
        try:
            # Clean up old vector store
            processor.delete_vector_store(kb.vector_store_id)
            
            # Crawl website
            result = await processor.process_website(
                base_url=kb.base_url,
                vector_store_id=kb.vector_store_id,
                crawl_depth=kb.crawl_depth or 3,
                include_patterns=kb.include_patterns,
                exclude_patterns=kb.exclude_patterns
            )
            
            # Update success status
            kb.processing_status = ProcessingStatus.COMPLETED
            kb.processed_at = datetime.utcnow()
            kb.last_crawled_at = datetime.utcnow()
            kb.pages_crawled = result['successful_pages']
            kb.processing_error = None
            
            logger.info(f"Scheduled crawl completed for KB {kb.id}: {result['successful_pages']} pages")
            
        except Exception as e:
            # Update failure status
            kb.processing_status = ProcessingStatus.FAILED
            kb.processing_error = str(e)
            logger.error(f"Scheduled crawl failed for KB {kb.id}: {e}")
        
        finally:
            db.commit()

# Global scheduler instance
scheduler = CrawlScheduler()

async def start_crawl_scheduler():
    """Start the background crawl scheduler"""
    await scheduler.start()

def stop_crawl_scheduler():
    """Stop the background crawl scheduler"""
    scheduler.stop()

# FastAPI startup/shutdown events
from fastapi import FastAPI

def setup_scheduler(app: FastAPI):
    """Setup scheduler with FastAPI app lifecycle"""
    
    @app.on_event("startup")
    async def startup_event():
        # Start scheduler in background
        asyncio.create_task(start_crawl_scheduler())
        logger.info("Background crawl scheduler initialized")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        stop_crawl_scheduler()
        logger.info("Background crawl scheduler stopped")