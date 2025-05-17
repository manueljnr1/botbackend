"""
Tenant context management for the chatbot engine
"""
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

from app.tenants.models import Tenant
from app.knowledge_base.models import KnowledgeBase, FAQ
from app.knowledge_base.processor import DocumentProcessor

logger = logging.getLogger(__name__)

class TenantContext:
    """
    Manages the context for a specific tenant, including knowledge bases and FAQs
    """
    
    def __init__(self, tenant_id: int, db: Session):
        self.tenant_id = tenant_id
        self.db = db
        self.tenant = None
        self.knowledge_bases = []
        self.faqs = []
        self.vector_stores = {}
        self.is_loaded = False
    
    def load(self) -> bool:
        """
        Load all tenant-specific data including knowledge bases and FAQs
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Load tenant
            self.tenant = self.db.query(Tenant).filter(
                Tenant.id == self.tenant_id,
                Tenant.is_active == True
            ).first()
            
            if not self.tenant:
                logger.error(f"Tenant ID {self.tenant_id} not found or inactive")
                return False
            
            logger.info(f"Loaded tenant: {self.tenant.name} (ID: {self.tenant_id})")
            
            # Load knowledge bases
            self.knowledge_bases = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == self.tenant_id
            ).all()
            
            logger.info(f"Loaded {len(self.knowledge_bases)} knowledge bases for tenant {self.tenant_id}")
            
            # Load FAQs
            self.faqs = self.db.query(FAQ).filter(
                FAQ.tenant_id == self.tenant_id
            ).all()
            
            logger.info(f"Loaded {len(self.faqs)} FAQs for tenant {self.tenant_id}")
            
            # Load vector stores for each knowledge base
            processor = DocumentProcessor(self.tenant_id)
            for kb in self.knowledge_bases:
                try:
                    self.vector_stores[kb.id] = processor.get_vector_store(kb.vector_store_id)
                    logger.info(f"Loaded vector store for knowledge base {kb.id} ({kb.name})")
                except Exception as e:
                    logger.error(f"Failed to load vector store for knowledge base {kb.id}: {e}")
            
            self.is_loaded = True
            return True
        
        except Exception as e:
            logger.exception(f"Error loading tenant context for tenant {self.tenant_id}: {e}")
            return False
    
    def get_faqs_as_dict(self) -> List[Dict[str, str]]:
        """
        Get FAQs as a list of dictionaries
        
        Returns:
            List of FAQ dictionaries with question and answer keys
        """
        return [{"question": faq.question, "answer": faq.answer} for faq in self.faqs]
    
    def get_combined_vector_store(self):
        """
        Get a combined vector store from all knowledge bases
        
        Returns:
            Combined vector store or None if no vector stores are available
        """
        if not self.vector_stores:
            logger.warning(f"No vector stores available for tenant {self.tenant_id}")
            return None
        
        # If only one vector store, return it
        if len(self.vector_stores) == 1:
            return next(iter(self.vector_stores.values()))
        
        # TODO: Implement combining multiple vector stores
        # For now, return the first one
        return next(iter(self.vector_stores.values()))


class TenantContextManager:
    """
    Manages tenant contexts across the application
    """
    
    def __init__(self):
        self.tenant_contexts = {}
    
    def get_tenant_context(self, tenant_id: int, db: Session) -> Optional[TenantContext]:
        """
        Get or create and load a tenant context
        
        Args:
            tenant_id: ID of the tenant
            db: Database session
            
        Returns:
            Loaded tenant context or None if loading failed
        """
        # Check if context already exists and is loaded
        if tenant_id in self.tenant_contexts and self.tenant_contexts[tenant_id].is_loaded:
            return self.tenant_contexts[tenant_id]
        
        # Create and load new context
        context = TenantContext(tenant_id, db)
        if context.load():
            self.tenant_contexts[tenant_id] = context
            return context
        
        return None
    
    def get_tenant_context_by_api_key(self, api_key: str, db: Session) -> Optional[TenantContext]:
        """
        Get tenant context by API key
        
        Args:
            api_key: API key of the tenant
            db: Database session
            
        Returns:
            Loaded tenant context or None if tenant not found or loading failed
        """
        # Find tenant by API key
        tenant = db.query(Tenant).filter(
            Tenant.api_key == api_key,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            logger.error(f"No tenant found for API key: {api_key[:5]}...")
            return None
        
        return self.get_tenant_context(tenant.id, db)
    
    def invalidate_tenant_context(self, tenant_id: int):
        """
        Invalidate a tenant context to force reloading
        
        Args:
            tenant_id: ID of the tenant
        """
        if tenant_id in self.tenant_contexts:
            del self.tenant_contexts[tenant_id]
            logger.info(f"Invalidated context for tenant {tenant_id}")


# Global tenant context manager
tenant_context_manager = TenantContextManager()