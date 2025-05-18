import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import os
import shutil
import uuid

from app.database import get_db
from app.knowledge_base.models import KnowledgeBase, FAQ, DocumentType
from app.knowledge_base.processor import DocumentProcessor
from app.tenants.models import Tenant
from app.auth.models import User
from app.auth.router import get_current_user, get_admin_user


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic models
class KnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None

class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    file_path: str
    document_type: DocumentType
    vector_store_id: str
    
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

# Endpoints
@router.post("/upload", response_model=KnowledgeBaseOut)
async def upload_knowledge_base(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """
    Upload a knowledge base document
    """
    logger.info(f"Knowledge base upload requested: {name}")
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Using tenant: {tenant.name} (ID: {tenant_id})")
    
    # Get document type from file extension
    file_extension = file.filename.split('.')[-1].lower()
    try:
        doc_type = DocumentType(file_extension)
        logger.info(f"Document type: {doc_type.value}")
    except ValueError:
        logger.error(f"Unsupported file type: {file_extension}")
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
    
    # Save the uploaded file
    upload_dir = os.path.join("uploads", f"tenant_{tenant_id}")
    os.makedirs(upload_dir, exist_ok=True)
    logger.info(f"Upload directory: {upload_dir}")
    
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")
    logger.info(f"Saving file to: {file_path}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File saved successfully")
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    # Process the document
    processor = DocumentProcessor(tenant_id)
    try:
        logger.info(f"Processing document...")
        vector_store_id = processor.process_document(file_path, doc_type)
        logger.info(f"Document processed successfully. Vector store ID: {vector_store_id}")
    except Exception as e:
        # Clean up uploaded file on error
        os.remove(file_path)
        logger.error(f"Failed to process document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    
    # Save to database
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=name,
        description=description,
        file_path=file_path,
        document_type=doc_type,
        vector_store_id=vector_store_id
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    logger.info(f"Knowledge base saved to database. ID: {kb.id}")
    
    return kb

@router.get("/", response_model=List[KnowledgeBaseOut])
async def list_knowledge_bases(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    List all knowledge bases for the tenant
    """
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
    """
    Delete a knowledge base
    """
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    logger.info(f"Delete knowledge base requested. ID: {kb_id}, Tenant ID: {tenant_id}")
    
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id).first()
    if not kb:
        logger.warning(f"Knowledge base not found: {kb_id}")
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    # Delete the vector store
    processor = DocumentProcessor(tenant_id)
    try:
        logger.info(f"Deleting vector store: {kb.vector_store_id}")
        vector_store_deleted = processor.delete_vector_store(kb.vector_store_id)
        if vector_store_deleted:
            logger.info(f"Vector store deleted successfully")
        else:
            logger.warning(f"Vector store not found for deletion")
    except Exception as e:
        logger.error(f"Error deleting vector store: {str(e)}")
        # Continue with deletion even if vector store deletion fails
    
    # Delete the uploaded file
    if os.path.exists(kb.file_path):
        try:
            os.remove(kb.file_path)
            logger.info(f"File deleted: {kb.file_path}")
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
    else:
        logger.warning(f"File not found: {kb.file_path}")
    
    # Delete from database
    db.delete(kb)
    db.commit()
    logger.info(f"Knowledge base deleted from database")
    
    return {"message": "Knowledge base deleted successfully"}

@router.post("/faqs/upload", response_model=List[FAQOut])
async def upload_faq_sheet(
    file: UploadFile = File(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Upload an FAQ sheet (CSV or Excel)
    """
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
    """
    List all FAQs for the tenant
    """
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
    """
    Create a new FAQ
    """
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
    """
    Update an FAQ
    """
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
    """
    Delete an FAQ
    """
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