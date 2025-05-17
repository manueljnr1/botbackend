from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header
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
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return tenant

# Endpoints
@router.post("/upload", response_model=KnowledgeBaseOut)
async def upload_knowledge_base(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """
    Upload a knowledge base document
    """
    tenant = get_tenant_from_api_key(x_api_key, db)
    tenant_id = tenant.id
    
    # Get document type from file extension
    file_extension = file.filename.split('.')[-1].lower()
    try:
        doc_type = DocumentType(file_extension)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_extension}")
    
    # Save the uploaded file
    upload_dir = os.path.join("uploads", f"tenant_{tenant_id}")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Process the document
    processor = DocumentProcessor(tenant_id)
    try:
        vector_store_id = processor.process_document(file_path, doc_type)
    except Exception as e:
        # Clean up uploaded file on error
        os.remove(file_path)
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
    
    return db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()

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
    
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    # Delete the vector store
    processor = DocumentProcessor(tenant_id)
    processor.delete_vector_store(kb.vector_store_id)
    
    # Delete the uploaded file
    if os.path.exists(kb.file_path):
        os.remove(kb.file_path)
    
    # Delete from database
    db.delete(kb)
    db.commit()
    
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
    
    # Save the uploaded file temporarily
    upload_dir = os.path.join("temp", f"tenant_{tenant_id}")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Process FAQ sheet
    processor = DocumentProcessor(tenant_id)
    try:
        faqs_data = processor.process_faq_sheet(file_path)
    except Exception as e:
        # Clean up temp file
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Failed to process FAQ sheet: {str(e)}")
    
    # Clean up temp file
    os.remove(file_path)
    
    # Delete existing FAQs for this tenant
    db.query(FAQ).filter(FAQ.tenant_id == tenant_id).delete()
    
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
    
    return db.query(FAQ).filter(FAQ.tenant_id == tenant_id).all()

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
    
    new_faq = FAQ(
        tenant_id=tenant_id,
        question=faq.question,
        answer=faq.answer
    )
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    
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
    
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    faq.question = faq_update.question
    faq.answer = faq_update.answer
    db.commit()
    db.refresh(faq)
    
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
    
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.tenant_id == tenant_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    db.delete(faq)
    db.commit()
    
    return {"message": "FAQ deleted successfully"}