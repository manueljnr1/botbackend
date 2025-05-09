import os
import uuid
import pandas as pd
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    CSVLoader,
    UnstructuredExcelLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.knowledge_base.models import DocumentType

class DocumentProcessor:
    """Process and load documents for vector storage"""
    
    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.vector_store_path = os.path.join(settings.VECTOR_DB_PATH, f"tenant_{tenant_id}")
        os.makedirs(self.vector_store_path, exist_ok=True)
    
    def _get_loader(self, file_path: str, doc_type: DocumentType):
        """Get the appropriate document loader based on file type"""
        if doc_type == DocumentType.PDF:
            return PyPDFLoader(file_path)
        elif doc_type == DocumentType.TXT:
            return TextLoader(file_path)
        elif doc_type in [DocumentType.DOC, DocumentType.DOCX]:
            return Docx2txtLoader(file_path)
        elif doc_type == DocumentType.CSV:
            return CSVLoader(file_path)
        elif doc_type == DocumentType.XLSX:
            return UnstructuredExcelLoader(file_path)
        else:
            raise ValueError(f"Unsupported document type: {doc_type}")
    
    def process_document(self, file_path: str, doc_type: DocumentType) -> str:
        """Process a document and store it in the vector store"""
        # Load the document
        loader = self._get_loader(file_path, doc_type)
        documents = loader.load()
        
        # Split the documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        splits = text_splitter.split_documents(documents)
        
        # Create a unique ID for this vector store
        vector_store_id = f"kb_{self.tenant_id}_{str(uuid.uuid4())}"
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        
        # Create and save the vector store
        vector_store = FAISS.from_documents(documents=splits, embedding=self.embeddings)
        vector_store.save_local(vector_store_path)
        
        return vector_store_id
    
    def get_vector_store(self, vector_store_id: str):
        """Load a vector store by ID"""
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        return FAISS.load_local(vector_store_path, self.embeddings)
    
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