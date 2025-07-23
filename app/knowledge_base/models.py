from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Enum, Boolean, JSON,  Float, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(enum.Enum):
    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    TXT = "txt"
    CSV = "csv"
    XLSX = "xlsx"
    WEBSITE = "website"  
    TROUBLESHOOTING = "troubleshooting"
    SALES = "sales"


class CrawlStatus(enum.Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    file_path = Column(String)  # For files, or base_url for websites
    document_type = Column(Enum(DocumentType))
    vector_store_id = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processing_status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    
    
    base_url = Column(String, nullable=True)  
    crawl_depth = Column(Integer, default=3)
    crawl_frequency_hours = Column(Integer, default=24)
    last_crawled_at = Column(DateTime, nullable=True)
    pages_crawled = Column(Integer, default=0)
    include_patterns = Column(JSON, nullable=True)  
    exclude_patterns = Column(JSON, nullable=True)  
    
    # Relationships
    tenant = relationship("Tenant", back_populates="knowledge_bases")


    # Troubleshooting-specific fields
    is_troubleshooting = Column(Boolean, default=False)
    troubleshooting_flow = Column(JSON, nullable=True)  # LLM-extracted flow structure
    flow_extraction_confidence = Column(Float, nullable=True)
    flow_extraction_status = Column(String, nullable=True)  # 'pending', 'completed', 'failed'


    # Sales-specific fields (NEW)
    is_sales = Column(Boolean, default=False)
    sales_content = Column(JSON, nullable=True)  # Extracted sales data
    sales_extraction_confidence = Column(Float, nullable=True)
    sales_extraction_status = Column(String, nullable=True)  # 'pending', 'completed', 'failed'


class FAQ(Base):
    __tablename__ = "faqs"
    
    id = Column(String(9), primary_key=True, unique=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    question = Column(Text)
    answer = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="faqs")
    __table_args__ = (
        UniqueConstraint('id', name='uq_faq_id'),
    )



class TenantIntentPattern(Base):
    __tablename__ = "tenant_intent_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    document_id = Column(Integer, ForeignKey("knowledge_bases.id"))
    intent_type = Column(String)  # "troubleshooting", "sales", "enquiry", "faq"
    pattern_data = Column(JSON)  # {"keywords": [], "questions": [], "problems": []}
    confidence = Column(Float, default=0.0)
    extracted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    tenant = relationship("Tenant")
    document = relationship("KnowledgeBase")

class CentralIntentModel(Base):
    __tablename__ = "central_intent_models"
    
    id = Column(Integer, primary_key=True, index=True)
    model_version = Column(String, unique=True)
    training_data = Column(JSON)  # Compiled patterns from all tenants
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
    trained_by_admin_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    performance_metrics = Column(JSON, nullable=True)