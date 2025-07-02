import os
import sys
sys.path.append('.')  # Add current directory to path

from app.knowledge_base.processor import DocumentProcessor
from app.database import SessionLocal
from app.knowledge_base.models import KnowledgeBase

def check_vector_store(kb_id: int, tenant_id: int):
    """Check what's in a vector store"""
    
    # Get KB details
    db = SessionLocal()
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        print(f"Knowledge base {kb_id} not found")
        return
    
    print(f"KB: {kb.name}")
    print(f"Vector Store ID: {kb.vector_store_id}")
    print(f"Pages Crawled: {kb.pages_crawled}")
    print("-" * 50)
    
    # Load vector store
    processor = DocumentProcessor(tenant_id)
    try:
        vector_store = processor.get_vector_store(kb.vector_store_id)
        
        # Get sample documents
        docs = vector_store.similarity_search("content", k=10)
        
        print(f"Found {len(docs)} document chunks in vector store")
        print("-" * 50)
        
        for i, doc in enumerate(docs):
            print(f"\nChunk {i+1}:")
            print(f"Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"Length: {len(doc.page_content)} chars")
            print(f"Content preview: {doc.page_content[:200]}...")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error loading vector store: {e}")
    
    db.close()

if __name__ == "__main__":
    # Usage: python check_vector_store.py <kb_id> <tenant_id>
    if len(sys.argv) != 3:
        print("Usage: python check_vector_store.py <kb_id> <tenant_id>")
        sys.exit(1)
    
    kb_id = int(sys.argv[1])
    tenant_id = int(sys.argv[2])
    check_vector_store(kb_id, tenant_id)