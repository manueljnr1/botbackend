import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, HttpUrl
import os
import shutil
import uuid
from datetime import datetime 
import re

from app.database import get_db
from app.knowledge_base.models import KnowledgeBase, FAQ, DocumentType, ProcessingStatus
from app.knowledge_base.processor import DocumentProcessor
from app.tenants.models import Tenant
from app.auth.models import User
from app.auth.router import get_current_user, get_admin_user
from app.services.storage import storage_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models
class KnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None

class WebsiteKnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_url: HttpUrl
    crawl_depth: int = 3
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None

# In router.py - Replace the existing KnowledgeBaseOut class

import json
from pydantic import BaseModel, field_validator
from typing import List, Optional, Union

class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    file_path: Optional[str]
    base_url: Optional[str]
    document_type: DocumentType
    vector_store_id: str
    processing_status: ProcessingStatus
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    crawl_depth: Optional[int] = None
    pages_crawled: Optional[int] = None
    last_crawled_at: Optional[datetime] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    
    @field_validator('include_patterns', 'exclude_patterns', mode='before')
    @classmethod
    def parse_json_patterns(cls, v: Union[str, List[str], None]) -> Optional[List[str]]:
        """Parse JSON string patterns into Python lists"""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                # Try to parse as JSON
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                return None
            except (json.JSONDecodeError, TypeError):
                # If it's not valid JSON, return None
                return None
        return None
    
    class Config:
        from_attributes = True

class FAQCreate(BaseModel):
    question: str
    answer: str

class FAQOut(BaseModel):
    id: int
    question: str
    answer: str
    
    class Config:
        from_attributes = True

class CrawlStatusOut(BaseModel):
    id: int
    name: str
    base_url: str
    pages_crawled: int
    last_crawled_at: Optional[datetime]
    processing_status: ProcessingStatus
    processing_error: Optional[str] = None

# Helper function to get tenant from API key
def get_tenant_from_api_key(api_key: str, db: Session):
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    if tenant:
        logger.info(f"Found tenant: {tenant.name} (ID: {tenant.id})")
    else:
        logger.warning(f"No tenant found for API key: {api_key[:5]}...")
    
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return tenant

# Existing endpoints (unchanged)
@router.get("/", response_model=List[KnowledgeBaseOut])
async def list_knowledge_bases(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """List all knowledge bases for the tenant"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Listing knowledge bases for tenant: {tenant.name} (ID: {tenant_id})")
    
    knowledge_bases = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
    logger.info(f"Found {len(knowledge_bases)} knowledge bases")
    
    return knowledge_bases

@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Delete a knowledge base with cloud storage support"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Delete knowledge base requested. ID: {kb_id}, Tenant ID: {tenant_id}")
    
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id).first()
    if not kb:
        logger.warning(f"Knowledge base not found: {kb_id}")
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    # Delete the vector store from cloud
    processor = DocumentProcessor(tenant_id)
    try:
        logger.info(f"Deleting vector store from cloud: {kb.vector_store_id}")
        vector_store_deleted = processor.delete_vector_store(kb.vector_store_id)
        if vector_store_deleted:
            logger.info(f"Vector store deleted successfully from cloud")
        else:
            logger.warning(f"Vector store not found for deletion in cloud")
    except Exception as e:
        logger.error(f"Error deleting vector store from cloud: {str(e)}")
        # Continue with deletion even if vector store deletion fails
    
    # Delete the uploaded file from cloud storage (only for file-based KB)
    if kb.file_path and kb.document_type != DocumentType.WEBSITE:
        try:
            file_deleted = storage_service.delete_file("knowledge-base-files", kb.file_path)
            if file_deleted:
                logger.info(f"File deleted from cloud: {kb.file_path}")
            else:
                logger.warning(f"File not found in cloud: {kb.file_path}")
        except Exception as e:
            logger.error(f"Error deleting file from cloud: {str(e)}")
            # Continue with deletion even if file deletion fails
    
    # Delete from database
    db.delete(kb)
    db.commit()
    logger.info(f"Knowledge base deleted from database")
    
    return {"message": "Knowledge base deleted successfully"}

@router.post("/upload", response_model=KnowledgeBaseOut)
async def upload_knowledge_base(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Upload and automatically process knowledge base document with cloud storage"""
    logger.info(f"Knowledge base upload requested: {name}")
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    
    # Get document type
    file_extension = file.filename.split('.')[-1].lower()
    try:
        doc_type = DocumentType(file_extension)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
    
    # Read file content and upload to cloud storage
    try:
        file_content = await file.read()
        logger.info(f"Read {len(file_content)} bytes from uploaded file")
        
        # Upload to cloud instead of saving locally
        cloud_file_path = storage_service.upload_knowledge_base_file(
            tenant_id, file.filename, file_content
        )
        logger.info(f"Uploaded file to cloud: {cloud_file_path}")
    except Exception as e:
        logger.error(f"Failed to upload file to cloud storage: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to cloud storage")
    
    # Create database record FIRST (with pending status)
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=name,
        description=description,
        file_path=cloud_file_path,
        document_type=doc_type,
        vector_store_id=f"kb_{tenant_id}_{uuid.uuid4()}",
        processing_status=ProcessingStatus.PENDING
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    # Process document with error handling
    processor = DocumentProcessor(tenant_id)
    try:
        kb.processing_status = ProcessingStatus.PROCESSING
        db.commit()
        
        logger.info(f"Processing document for KB {kb.id}...")
        processor.process_document_with_id(cloud_file_path, doc_type, kb.vector_store_id)
        
        kb.processing_status = ProcessingStatus.COMPLETED
        kb.processed_at = datetime.utcnow()
        kb.processing_error = None
        
        logger.info(f"Document processed successfully: {kb.vector_store_id}")
        
    except Exception as e:
        kb.processing_status = ProcessingStatus.FAILED
        kb.processing_error = str(e)
        logger.error(f"Failed to process document: {e}")
        
        # Clean up uploaded file on processing failure
        try:
            storage_service.delete_file("knowledge-base-files", cloud_file_path)
            logger.info(f"Cleaned up failed upload: {cloud_file_path}")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup file after processing failure: {cleanup_error}")
        
    db.commit()
    return kb

# NEW WEBSITE CRAWLING ENDPOINTS

@router.post("/website", response_model=KnowledgeBaseOut)
async def create_website_knowledge_base(
    website_data: WebsiteKnowledgeBaseCreate,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create a website knowledge base with better error handling"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    
    logger.info(f"Website KB creation requested: {website_data.name} -> {website_data.base_url}")
    
    # Create database record first
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=website_data.name,
        description=website_data.description,
        base_url=str(website_data.base_url),
        document_type=DocumentType.WEBSITE,
        vector_store_id=f"kb_{tenant_id}_{uuid.uuid4()}",
        processing_status=ProcessingStatus.PENDING,
        crawl_depth=website_data.crawl_depth,
        include_patterns=website_data.include_patterns,
        exclude_patterns=website_data.exclude_patterns
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    # SYNCHRONOUS crawling with timeout to prevent hanging
    async def crawl_with_timeout():
        processor = DocumentProcessor(tenant_id)
        try:
            kb.processing_status = ProcessingStatus.PROCESSING
            db.commit()
            
            logger.info(f"Starting crawl for KB {kb.id}...")
            
            # Increased timeout to 5 minutes
            result = await asyncio.wait_for(
                processor.process_website(
                    base_url=str(website_data.base_url),
                    vector_store_id=kb.vector_store_id,
                    crawl_depth=website_data.crawl_depth,
                    include_patterns=website_data.include_patterns,
                    exclude_patterns=website_data.exclude_patterns
                ),
                timeout=300.0  # 5 minutes instead of 60 seconds
            )
                
            kb.processing_status = ProcessingStatus.COMPLETED
            kb.processed_at = datetime.utcnow()
            kb.last_crawled_at = datetime.utcnow()
            kb.pages_crawled = result['successful_pages']
            kb.processing_error = None
            
            logger.info(f"Website crawled successfully: {result['successful_pages']} pages")
            
        except asyncio.TimeoutError:
            kb.processing_status = ProcessingStatus.FAILED
            kb.processing_error = "Crawling timeout after 60 seconds"
            logger.error(f"Crawling timeout for KB {kb.id}")
            
        except Exception as e:
            kb.processing_status = ProcessingStatus.FAILED
            kb.processing_error = str(e)
            logger.error(f"Failed to crawl website: {e}", exc_info=True)
            
        finally:
            db.commit()
    
    # Start crawling task (don't await - let it run in background)
    asyncio.create_task(crawl_with_timeout())
    
    return kb


# Alternative: Synchronous crawling for immediate feedback
@router.post("/website/sync", response_model=KnowledgeBaseOut)
async def create_website_knowledge_base_sync(
    website_data: WebsiteKnowledgeBaseCreate,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create website KB with synchronous processing (waits for completion)"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    
    logger.info(f"Sync website KB creation: {website_data.name} -> {website_data.base_url}")
    
    # Validate patterns first
    base_url = str(website_data.base_url)
    
    # Check if include patterns would match the base URL
    if website_data.include_patterns:
        pattern_matches = any(
            re.search(pattern, base_url, re.IGNORECASE) 
            for pattern in website_data.include_patterns
        )
        if not pattern_matches:
            raise HTTPException(
                status_code=400, 
                detail=f"Include patterns {website_data.include_patterns} don't match base URL {base_url}"
            )
    
    
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=website_data.name,
        description=website_data.description,
        base_url=base_url,
        document_type=DocumentType.WEBSITE,
        vector_store_id=f"kb_{tenant_id}_{uuid.uuid4()}",
        processing_status=ProcessingStatus.PROCESSING,
        crawl_depth=website_data.crawl_depth,
        include_patterns=website_data.include_patterns,
        exclude_patterns=website_data.exclude_patterns
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    
    processor = DocumentProcessor(tenant_id)
    try:
        logger.info(f"Starting sync crawl for KB {kb.id}...")
        
       
        result = await asyncio.wait_for(
        processor.process_website(
            base_url=base_url,
            vector_store_id=kb.vector_store_id,
            crawl_depth=website_data.crawl_depth,
            include_patterns=website_data.include_patterns,
            exclude_patterns=website_data.exclude_patterns
        ),
        timeout=300.0  # 5 minutes instead of 60 seconds
    )
        
        # Update success status
        kb.processing_status = ProcessingStatus.COMPLETED
        kb.processed_at = datetime.utcnow()
        kb.last_crawled_at = datetime.utcnow()
        kb.pages_crawled = result['successful_pages']
        kb.processing_error = None
        
        logger.info(f"Sync crawl completed: {result['successful_pages']} pages")
        
    except asyncio.TimeoutError:
        kb.processing_status = ProcessingStatus.FAILED
        kb.processing_error = "Crawling timeout after 60 seconds"
        logger.error(f"Sync crawl timeout for KB {kb.id}")
        
    except Exception as e:
        kb.processing_status = ProcessingStatus.FAILED
        kb.processing_error = str(e)
        logger.error(f"Sync crawl failed: {e}", exc_info=True)
    
    finally:
        db.commit()
        db.refresh(kb)
    
    return kb


# Debug endpoint to check what's wrong with stuck crawls
@router.get("/{kb_id}/debug")
async def debug_stuck_crawl(
    kb_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Debug a stuck crawl to see what's wrong"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant.id
    ).first()
    
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    # Test the URL with the exact same patterns
    from app.knowledge_base.website_crawler import WebsiteCrawler
    
    crawler = WebsiteCrawler(max_depth=1, max_pages=5, delay=0.5, timeout=10)
    
    try:
        # Quick test crawl
        results = await asyncio.wait_for(
            crawler.crawl_website(
                base_url=kb.base_url,
                include_patterns=kb.include_patterns,
                exclude_patterns=kb.exclude_patterns
            ),
            timeout=30.0
        )
        
        return {
            "kb_id": kb_id,
            "base_url": kb.base_url,
            "include_patterns": kb.include_patterns,
            "exclude_patterns": kb.exclude_patterns,
            "test_results": {
                "success": True,
                "pages_found": len(results),
                "pages": [{"url": r.url, "content_length": len(r.content), "error": r.error} for r in results]
            }
        }
        
    except Exception as e:
        return {
            "kb_id": kb_id,
            "base_url": kb.base_url,
            "include_patterns": kb.include_patterns,
            "exclude_patterns": kb.exclude_patterns,
            "test_results": {
                "success": False,
                "error": str(e)
            }
        }

@router.post("/{kb_id}/recrawl")
async def recrawl_website(
    kb_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Manually trigger a website recrawl"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant.id,
        KnowledgeBase.document_type == DocumentType.WEBSITE
    ).first()
    
    if not kb:
        raise HTTPException(status_code=404, detail="Website knowledge base not found")
    
    if kb.processing_status == ProcessingStatus.PROCESSING:
        raise HTTPException(status_code=400, detail="Crawling already in progress")
    
    # Start recrawling
    async def recrawl_website():
        processor = DocumentProcessor(tenant.id)
        try:
            kb.processing_status = ProcessingStatus.PROCESSING
            kb.processing_error = None
            db.commit()
            
            # Clean up old vector store
            processor.delete_vector_store(kb.vector_store_id)
            
            # Recrawl
            result = await processor.process_website(
                base_url=kb.base_url,
                vector_store_id=kb.vector_store_id,
                crawl_depth=kb.crawl_depth,
                include_patterns=kb.include_patterns,
                exclude_patterns=kb.exclude_patterns
            )
            
            kb.processing_status = ProcessingStatus.COMPLETED
            kb.processed_at = datetime.utcnow()
            kb.last_crawled_at = datetime.utcnow()
            kb.pages_crawled = result['successful_pages']
            
        except Exception as e:
            kb.processing_status = ProcessingStatus.FAILED
            kb.processing_error = str(e)
            logger.error(f"Recrawling failed: {e}")
            
        db.commit()
    
    asyncio.create_task(recrawl_website())
    
    return {"message": "Recrawling started", "status": "processing"}

@router.get("/websites/status", response_model=List[CrawlStatusOut])
async def get_website_crawl_status(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get crawl status of all website knowledge bases"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    websites = db.query(KnowledgeBase).filter(
        KnowledgeBase.tenant_id == tenant.id,
        KnowledgeBase.document_type == DocumentType.WEBSITE
    ).all()
    
    return [{
        "id": kb.id,
        "name": kb.name,
        "base_url": kb.base_url,
        "pages_crawled": kb.pages_crawled or 0,
        "last_crawled_at": kb.last_crawled_at,
        "processing_status": kb.processing_status,
        "processing_error": kb.processing_error
    } for kb in websites]

@router.get("/{kb_id}/crawl-details")
async def get_crawl_details(
    kb_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get detailed crawl information for a website KB"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant.id,
        KnowledgeBase.document_type == DocumentType.WEBSITE
    ).first()
    
    if not kb:
        raise HTTPException(status_code=404, detail="Website knowledge base not found")
    
    # Get crawl metadata
    processor = DocumentProcessor(tenant.id)
    metadata = await processor.get_crawl_metadata(kb.vector_store_id)
    
    return {
        "id": kb.id,
        "name": kb.name,
        "base_url": kb.base_url,
        "crawl_depth": kb.crawl_depth,
        "include_patterns": kb.include_patterns,
        "exclude_patterns": kb.exclude_patterns,
        "pages_crawled": kb.pages_crawled,
        "last_crawled_at": kb.last_crawled_at,
        "processing_status": kb.processing_status.value,
        "processing_error": kb.processing_error,
        "metadata": metadata
    }

# Existing FAQ endpoints continue unchanged...
@router.post("/faqs/upload", response_model=List[FAQOut])
async def upload_faq_sheet(
    file: UploadFile = File(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Upload an FAQ sheet (CSV or Excel)"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"FAQ upload requested. Tenant: {tenant.name} (ID: {tenant_id})")
    
    # Save the uploaded file temporarily
    upload_dir = os.path.join("temp", f"tenant_{tenant_id}")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    logger.info(f"Saving FAQ file to: {file_path}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Process FAQ sheet
    processor = DocumentProcessor(tenant_id)
    try:
        logger.info(f"Processing FAQ sheet...")
        faqs_data = processor.process_faq_sheet(file_path)
        logger.info(f"FAQ sheet processed successfully. {len(faqs_data)} items found")
    except Exception as e:
        # Clean up temp file
        os.remove(file_path)
        logger.error(f"Failed to process FAQ sheet: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to process FAQ sheet: {str(e)}")
    
    # Clean up temp file
    os.remove(file_path)
    
    # Delete existing FAQs for this tenant
    existing_faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).count()
    db.query(FAQ).filter(FAQ.tenant_id == tenant_id).delete()
    logger.info(f"Deleted {existing_faqs} existing FAQ items")
    
    # Add new FAQs
    new_faqs = []
    for faq_data in faqs_data:
        faq = FAQ(
            tenant_id=tenant_id,
            question=faq_data['question'],
            answer=faq_data['answer']
        )
        db.add(faq)
        new_faqs.append(faq)
    
    db.commit()
    logger.info(f"Added {len(new_faqs)} new FAQ items")
    
    return new_faqs

@router.get("/faqs", response_model=List[FAQOut])
async def list_faqs(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """List all FAQs for the tenant"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Listing FAQs for tenant: {tenant.name} (ID: {tenant_id})")
    
    faqs = db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()
    logger.info(f"Found {len(faqs)} FAQs")
    
    return faqs

@router.post("/faqs", response_model=FAQOut)
async def create_faq(
    faq: FAQCreate,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create a new FAQ"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Creating new FAQ for tenant: {tenant.name} (ID: {tenant_id})")
    
    new_faq = FAQ(
        tenant_id=tenant_id,
        question=faq.question,
        answer=faq.answer
    )
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    logger.info(f"FAQ created successfully. ID: {new_faq.id}")
    
    return new_faq

@router.put("/faqs/{faq_id}", response_model=FAQOut)
async def update_faq(
    faq_id: int,
    faq_update: FAQCreate,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update an FAQ"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Updating FAQ. ID: {faq_id}, Tenant: {tenant.name} (ID: {tenant_id})")
    
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        logger.warning(f"FAQ not found: {faq_id}")
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    faq.question = faq_update.question
    faq.answer = faq_update.answer
    db.commit()
    db.refresh(faq)
    logger.info(f"FAQ updated successfully")
    
    return faq

@router.delete("/faqs/{faq_id}")
async def delete_faq(
    faq_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Delete an FAQ"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Deleting FAQ. ID: {faq_id}, Tenant: {tenant.name} (ID: {tenant_id})")
    
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        logger.warning(f"FAQ not found: {faq_id}")
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    db.delete(faq)
    db.commit()
    logger.info(f"FAQ deleted successfully")
    
    return {"message": "FAQ deleted successfully"}

@router.post("/{kb_id}/reprocess")
async def reprocess_knowledge_base(
    kb_id: int,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Reprocess a failed or pending knowledge base with cloud storage support"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant.id
    ).first()
    
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    # Handle website vs file reprocessing
    if kb.document_type == DocumentType.WEBSITE:
        # Redirect to recrawl endpoint
        return await recrawl_website(kb_id, x_api_key, db)
    
    # Check if source file exists in cloud storage
    try:
        if not storage_service.file_exists("knowledge-base-files", kb.file_path):
            raise HTTPException(status_code=400, detail="Source file no longer exists in cloud storage")
    except Exception as e:
        logger.error(f"Error checking file existence: {e}")
        raise HTTPException(status_code=400, detail="Could not verify source file existence")
    
    processor = DocumentProcessor(tenant.id)
    try:
        kb.processing_status = ProcessingStatus.PROCESSING
        kb.processing_error = None
        db.commit()
        
        # Clean up old vector store if exists
        processor.delete_vector_store(kb.vector_store_id)
        
        # Reprocess with cloud file path
        processor.process_document_with_id(kb.file_path, kb.document_type, kb.vector_store_id)
        
        kb.processing_status = ProcessingStatus.COMPLETED
        kb.processed_at = datetime.utcnow()
        
    except Exception as e:
        kb.processing_status = ProcessingStatus.FAILED
        kb.processing_error = str(e)
        logger.error(f"Reprocessing failed: {e}")
        
    db.commit()
    return {"message": "Reprocessing completed", "status": kb.processing_status.value}

@router.get("/status", response_model=List[dict])
async def get_processing_status(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get processing status of all knowledge bases"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant.id).all()
    
    return [{
        "id": kb.id,
        "name": kb.name,
        "type": kb.document_type.value,
        "status": kb.processing_status.value,
        "error": kb.processing_error,
        "processed_at": kb.processed_at.isoformat() if kb.processed_at else None,
        "pages_crawled": kb.pages_crawled if kb.document_type == DocumentType.WEBSITE else None,
        "last_crawled_at": kb.last_crawled_at.isoformat() if kb.last_crawled_at else None
    } for kb in kbs]




@router.get("/{kb_id}/vector-content")
async def get_vector_content(
    kb_id: int,
    limit: int = 5,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get sample content from vector store"""
    tenant = get_tenant_from_api_key(x_api_key, db)
    
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant.id
    ).first()
    
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    try:
        processor = DocumentProcessor(tenant.id)
        vector_store = processor.get_vector_store(kb.vector_store_id)
        
        # Get some sample documents
        docs = vector_store.similarity_search("content", k=limit)
        
        return {
            "kb_id": kb_id,
            "vector_store_id": kb.vector_store_id,
            "total_docs": len(docs),
            "documents": [
                {
                    "content": doc.page_content[:500] + ("..." if len(doc.page_content) > 500 else ""),
                    "metadata": doc.metadata,
                    "full_length": len(doc.page_content)
                } for doc in docs
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading vector store: {str(e)}")
    


# In router.py - Add this endpoint for troubleshooting document upload

@router.post("/knowledge-base/troubleshooting/upload", response_model=KnowledgeBaseOut)
async def upload_troubleshooting_guide(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """
    Upload a troubleshooting guide document
    Accepts: TXT, PDF, DOCX formats
    The system will use LLM to extract the conversation flow
    """
    logger.info(f"Troubleshooting guide upload requested: {name}")
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    
    # Get document type
    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in ['txt', 'pdf', 'docx']:
        raise HTTPException(status_code=400, detail="Troubleshooting guides must be TXT, PDF, or DOCX")
    
    try:
        doc_type = DocumentType(file_extension)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
    
    # Read and upload file
    try:
        file_content = await file.read()
        cloud_file_path = storage_service.upload_knowledge_base_file(
            tenant_id, file.filename, file_content
        )
        logger.info(f"Uploaded troubleshooting file to cloud: {cloud_file_path}")
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")
    
    # Create database record
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=name,
        description=description,
        file_path=cloud_file_path,
        document_type=DocumentType.TROUBLESHOOTING,
        vector_store_id=f"kb_{tenant_id}_{uuid.uuid4()}",
        processing_status=ProcessingStatus.PENDING,
        is_troubleshooting=True,
        flow_extraction_status="pending"
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    
    # Process document with enhanced troubleshooting extraction
    processor = DocumentProcessor(tenant_id)  # REMOVED llm_service line
    try:
        kb.processing_status = ProcessingStatus.PROCESSING
        db.commit()
        
        # Process as troubleshooting document
        result = processor.process_troubleshooting_document(
            cloud_file_path, doc_type, kb.vector_store_id
        )
        
        # Update KB with results
        kb.processing_status = ProcessingStatus.COMPLETED
        kb.processed_at = datetime.utcnow()
        kb.troubleshooting_flow = result.get("flow_data")
        kb.flow_extraction_confidence = result.get("extraction_confidence", 0)
        kb.flow_extraction_status = "completed" if result.get("flow_extracted") else "failed"
        kb.processing_error = None
        
        logger.info(f"Troubleshooting guide processed: {kb.vector_store_id}")
        
    except Exception as e:
        kb.processing_status = ProcessingStatus.FAILED
        kb.processing_error = str(e)
        kb.flow_extraction_status = "failed"
        logger.error(f"Failed to process troubleshooting guide: {e}")
    
    db.commit()
    return kb