# import os
# import uuid
# import pandas as pd
# from typing import List, Dict, Any, Optional
# from app.knowledge_base.models import DocumentType
# from app.config import settings
# from langchain_community.vectorstores import FAISS

# class DocumentProcessor:
#     """Process and load documents for vector storage"""
    
#     def __init__(self, tenant_id: int):
#         self.tenant_id = tenant_id
#         self.vector_store_path = os.path.join(settings.VECTOR_DB_PATH, f"tenant_{tenant_id}")
#         os.makedirs(self.vector_store_path, exist_ok=True)
    
#     def process_document(self, file_path: str, doc_type: DocumentType) -> str:
#         """Simplified document processing for deployment"""
#         # Generate a unique ID for this document
#         vector_store_id = f"kb_{self.tenant_id}_{str(uuid.uuid4())}"
        
#         # In a real implementation, this would process the document and create embeddings
#         # For now, we'll just return the ID and handle it in the simplified chatbot
#         return vector_store_id
    
#     def get_vector_store(self, vector_store_id: str):
#         """Placeholder for vector store retrieval"""
#         # In a real implementation, this would return a vector store
#         # For now, we'll just return a dummy object for the simplified chatbot
#         class DummyVectorStore:
#             def as_retriever(self, search_kwargs=None):
#                 return self
            
#             def get_relevant_documents(self, query):
#                 return []
        
#         return DummyVectorStore()
    
#     def delete_vector_store(self, vector_store_id: str):
#         """Delete a vector store by ID"""
#         vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
#         if os.path.exists(vector_store_path):
#             import shutil
#             shutil.rmtree(vector_store_path)
#             return True
#         return False

#     def process_faq_sheet(self, file_path: str) -> List[Dict[str, str]]:
#         """Process FAQ spreadsheet and return list of Q&A pairs"""
#         if file_path.endswith('.csv'):
#             df = pd.read_csv(file_path)
#         elif file_path.endswith(('.xlsx', '.xls')):
#             df = pd.read_excel(file_path)
#         else:
#             raise ValueError("FAQ file must be CSV or Excel format")
        
#         # Expected columns: question, answer
#         if 'question' not in df.columns or 'answer' not in df.columns:
#             raise ValueError("FAQ sheet must contain 'question' and 'answer' columns")
        
#         # Convert to list of dictionaries
#         faqs = []
#         for _, row in df.iterrows():
#             if pd.notna(row['question']) and pd.notna(row['answer']):
#                 faqs.append({
#                     'question': row['question'].strip(),
#                     'answer': row['answer'].strip()
#                 })
        
#         return faqs
    
#     def get_vector_store(self, vector_store_id: str):
#         """Load a vector store by ID"""
#         vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
#         print(f"Attempting to load vector store from: {vector_store_path}")
#         if not os.path.exists(vector_store_path):
#             print(f"WARNING: Vector store path does not exist: {vector_store_path}")
#             return None
#         return FAISS.load_local(vector_store_path, self.embeddings)




import os
import uuid
import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    CSVLoader,
    UnstructuredExcelLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import settings
from app.knowledge_base.models import DocumentType

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process and load documents for vector storage"""
    
    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.vector_store_path = os.path.join(settings.VECTOR_DB_PATH, f"tenant_{tenant_id}")
        
        # Ensure the directory exists
        os.makedirs(self.vector_store_path, exist_ok=True)
        logger.info(f"Vector store path: {self.vector_store_path}")
    
    def _get_loader(self, file_path: str, doc_type: DocumentType):
        """Get the appropriate document loader based on file type"""
        logger.info(f"Loading document: {file_path} (type: {doc_type.value})")
        
        if doc_type == DocumentType.PDF:
            return PyPDFLoader(file_path)
        elif doc_type == DocumentType.TXT:
            return TextLoader(file_path)
        elif doc_type in [DocumentType.DOC, DocumentType.DOCX]:
            return Docx2txtLoader(file_path)
        elif doc_type == DocumentType.CSV:
            return CSVLoader(file_path)
        elif doc_type == DocumentType.XLSX:
            try:
                return UnstructuredExcelLoader(file_path)
            except Exception as e:
                logger.error(f"Error loading Excel with UnstructuredExcelLoader: {str(e)}")
                # Alternative loading using pandas
                class PandasExcelLoader:
                    def __init__(self, file_path):
                        self.file_path = file_path
                    
                    def load(self):
                        from langchain.schema import Document
                        import pandas as pd
                        df = pd.read_excel(self.file_path)
                        text = df.to_string()
                        metadata = {"source": self.file_path}
                        return [Document(page_content=text, metadata=metadata)]
                
                logger.info(f"Using PandasExcelLoader as fallback")
                return PandasExcelLoader(file_path)
        else:
            raise ValueError(f"Unsupported document type: {doc_type}")
    
    def process_document(self, file_path: str, doc_type: DocumentType) -> str:
        """Process a document and store it in the vector store"""
        logger.info(f"Processing document: {file_path}")
        
        # Load the document
        try:
            loader = self._get_loader(file_path, doc_type)
            documents = loader.load()
            logger.info(f"Loaded {len(documents)} document segments")
            
            # Log the content of the first document for debugging
            if documents:
                first_doc = documents[0]
                content_preview = first_doc.page_content[:200] if hasattr(first_doc, 'page_content') else "No content available"
                logger.info(f"First document content preview: {content_preview}...")
            
            # Split the documents into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )
            splits = text_splitter.split_documents(documents)
            logger.info(f"Split into {len(splits)} chunks")
            
            # Create a unique ID for this vector store
            vector_store_id = f"kb_{self.tenant_id}_{str(uuid.uuid4())}"
            vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
            logger.info(f"Creating vector store at: {vector_store_path}")
            
            # Create and save the vector store
            vector_store = FAISS.from_documents(documents=splits, embedding=self.embeddings)
            vector_store.save_local(vector_store_path)
            logger.info(f"Vector store saved successfully")
            
            # Verify the vector store was created
            if os.path.exists(vector_store_path):
                logger.info(f"Vector store directory exists at: {vector_store_path}")
                files = os.listdir(vector_store_path)
                logger.info(f"Vector store files: {files}")
            else:
                logger.error(f"Vector store directory was not created at: {vector_store_path}")
            
            return vector_store_id
            
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            raise
    
    def get_vector_store(self, vector_store_id: str):
        """Load a vector store by ID"""
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        logger.info(f"Attempting to load vector store from: {vector_store_path}")
        
        if not os.path.exists(vector_store_path):
            logger.warning(f"Vector store path does not exist: {vector_store_path}")
            raise FileNotFoundError(f"Vector store not found: {vector_store_id}")
        
        try:
            vector_store = FAISS.load_local(vector_store_path, self.embeddings,  allow_dangerous_deserialization=True)
            logger.info(f"Vector store loaded successfully")
            return vector_store
        except Exception as e:
            logger.error(f"Failed to load vector store: {vector_store_id}", exc_info=True)
            raise
    
    def delete_vector_store(self, vector_store_id: str):
        """Delete a vector store by ID"""
        vector_store_path = os.path.join(self.vector_store_path, vector_store_id)
        if os.path.exists(vector_store_path):
            import shutil
            shutil.rmtree(vector_store_path)
            logger.info(f"Deleted vector store: {vector_store_id}")
            return True
        else:
            logger.warning(f"Vector store not found for deletion: {vector_store_id}")
        return False

    def process_faq_sheet(self, file_path: str) -> List[Dict[str, str]]:
        """Process FAQ spreadsheet and return list of Q&A pairs"""
        logger.info(f"Processing FAQ sheet: {file_path}")
        
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                raise ValueError("FAQ file must be CSV or Excel format")
            
            # Log column names for debugging
            logger.info(f"FAQ sheet columns: {df.columns.tolist()}")
            
            # Expected columns: question, answer
            if 'question' not in df.columns or 'answer' not in df.columns:
                # Try to find close matches (case insensitive)
                column_map = {}
                for col in df.columns:
                    if col.lower() == 'question':
                        column_map['question'] = col
                    elif col.lower() == 'answer':
                        column_map['answer'] = col
                
                if len(column_map) == 2:
                    logger.info(f"Found alternate column names: {column_map}")
                    df = df.rename(columns=column_map)
                else:
                    raise ValueError("FAQ sheet must contain 'question' and 'answer' columns")
            
            # Convert to list of dictionaries
            faqs = []
            for _, row in df.iterrows():
                if pd.notna(row['question']) and pd.notna(row['answer']):
                    faqs.append({
                        'question': row['question'].strip(),
                        'answer': row['answer'].strip()
                    })
            
            logger.info(f"Processed {len(faqs)} FAQ items")
            return faqs
            
        except Exception as e:
            logger.error(f"Error processing FAQ sheet: {str(e)}", exc_info=True)
            raise