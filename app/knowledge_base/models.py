from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Enum, Boolean, JSON
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


class FAQ(Base):
    __tablename__ = "faqs"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    question = Column(Text)
    answer = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="faqs")