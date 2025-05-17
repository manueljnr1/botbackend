import os
import uuid
import pandas as pd
from typing import List, Dict, Any, Optional
from app.knowledge_base.models import DocumentType
from app.config import settings
from langchain_community.vectorstores import FAISS

class DocumentProcessor:
    """Process and load documents for vector storage"""
    
    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.vector_store_path = os.path.join(settings.VECTOR_DB_PATH, f"tenant_{tenant_id}")
        os.makedirs(self.vector_store_path, exist_ok=True)
    
    def process_document(self, file_path: str, doc_type: DocumentType) -> str:
        """Simplified document processing for deployment"""
        # Generate a unique ID for this document
        vector_store_id = f"kb_{self.tenant_id}_{str(uuid.uuid4())}"
        
        # In a real implementation, this would process the document and create embeddings
        # For now, we'll just return the ID and handle it in the simplified chatbot
        return vector_store_id
    
    def get_vector_store(self, vector_store_id: str):
        """Placeholder for vector store retrieval"""
        # In a real implementation, this would return a vector store
        # For now, we'll just return a dummy object for the simplified chatbot
        class DummyVectorStore:
            def as_retriever(self, search_kwargs=None):
                return self
            
            def get_relevant_documents(self, query):
                return []
        
        return DummyVectorStore()
    
    def delete_vector_store(self, vector_store_id: str):
        """Delete a vector store by ID"""
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        if os.path.exists(vector_store_path):
            import shutil
            shutil.rmtree(vector_store_path)
            return True
        return False

    def process_faq_sheet(self, file_path: str) -> List[Dict[str, str]]:
        """Process FAQ spreadsheet and return list of Q&A pairs"""
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
        else:
            raise ValueError("FAQ file must be CSV or Excel format")
        
        # Expected columns: question, answer
        if 'question' not in df.columns or 'answer' not in df.columns:
            raise ValueError("FAQ sheet must contain 'question' and 'answer' columns")
        
        # Convert to list of dictionaries
        faqs = []
        for _, row in df.iterrows():
            if pd.notna(row['question']) and pd.notna(row['answer']):
                faqs.append({
                    'question': row['question'].strip(),
                    'answer': row['answer'].strip()
                })
        
        return faqs
    
    def get_vector_store(self, vector_store_id: str):
        """Load a vector store by ID"""
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        print(f"Attempting to load vector store from: {vector_store_path}")
        if not os.path.exists(vector_store_path):
            print(f"WARNING: Vector store path does not exist: {vector_store_path}")
            return None
        return FAISS.load_local(vector_store_path, self.embeddings)