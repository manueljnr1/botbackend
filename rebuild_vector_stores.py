#!/usr/bin/env python3
"""
Updated script to rebuild vector stores for existing knowledge bases
Fixed to work with current LangChain versions
"""
import os
import sys
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def rebuild_vector_stores():
    """Rebuild all vector stores for existing knowledge bases"""
    logger.info("Starting vector store rebuild")
    
    # Only import these here to avoid circular imports
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    from app.knowledge_base.models import KnowledgeBase
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import (
        PyPDFLoader,
        TextLoader,
        Docx2txtLoader,
        CSVLoader,
        UnstructuredExcelLoader
    )
    
    # Try to import from langchain_openai first (newer version)
    try:
        from langchain_openai import OpenAIEmbeddings
        logger.info("Using langchain_openai for embeddings")
    except ImportError:
        # Fall back to community package
        from langchain_community.embeddings import OpenAIEmbeddings
        logger.info("Using langchain_community for embeddings")
    
    from langchain_community.vectorstores import FAISS
    from app.config import settings
    
    # Create the database session
    db = SessionLocal()
    
    try:
        # Create vector db directory if it doesn't exist
        os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
        
        # Get all knowledge bases
        knowledge_bases = db.query(KnowledgeBase).all()
        logger.info(f"Found {len(knowledge_bases)} knowledge bases in the database")
        
        for kb in knowledge_bases:
            logger.info(f"Processing knowledge base: {kb.name} (ID: {kb.id})")
            
            # Get the tenant
            tenant = db.query(Tenant).filter(Tenant.id == kb.tenant_id).first()
            if not tenant:
                logger.error(f"Tenant not found for knowledge base {kb.id}, skipping")
                continue
            
            logger.info(f"Tenant: {tenant.name} (ID: {tenant.id})")
            
            # Check if the file exists
            if not os.path.exists(kb.file_path):
                logger.error(f"File doesn't exist: {kb.file_path}, skipping")
                continue
            
            logger.info(f"Document file exists: {kb.file_path}")
            
            # Create vector store directory
            tenant_dir = os.path.join(settings.VECTOR_DB_PATH, f"tenant_{tenant.id}")
            os.makedirs(tenant_dir, exist_ok=True)
            
            # Create a new unique vector store ID
            import uuid
            new_vector_store_id = f"kb_{tenant.id}_{str(uuid.uuid4())}"
            vector_store_path = os.path.join(tenant_dir, new_vector_store_id)
            
            # Create embeddings
            embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
            
            try:
                # Process the document based on its type
                file_extension = os.path.splitext(kb.file_path)[1].lower().replace('.', '')
                
                logger.info(f"Loading document: {kb.file_path} (type: {kb.document_type.value})")
                
                # Get the appropriate loader
                if kb.document_type.value == 'pdf':
                    loader = PyPDFLoader(kb.file_path)
                elif kb.document_type.value == 'txt':
                    loader = TextLoader(kb.file_path)
                elif kb.document_type.value in ['doc', 'docx']:
                    loader = Docx2txtLoader(kb.file_path)
                elif kb.document_type.value == 'csv':
                    loader = CSVLoader(kb.file_path)
                elif kb.document_type.value == 'xlsx':
                    try:
                        loader = UnstructuredExcelLoader(kb.file_path)
                    except Exception as e:
                        logger.error(f"Error loading Excel with UnstructuredExcelLoader: {str(e)}")
                        # Alternative loading using pandas
                        from langchain.schema import Document
                        import pandas as pd
                        
                        class PandasExcelLoader:
                            def __init__(self, file_path):
                                self.file_path = file_path
                            
                            def load(self):
                                df = pd.read_excel(self.file_path)
                                text = df.to_string()
                                metadata = {"source": self.file_path}
                                return [Document(page_content=text, metadata=metadata)]
                        
                        logger.info(f"Using PandasExcelLoader as fallback")
                        loader = PandasExcelLoader(kb.file_path)
                else:
                    logger.error(f"Unsupported document type: {kb.document_type.value}")
                    continue
                
                # Load the document
                documents = loader.load()
                logger.info(f"Loaded {len(documents)} document segments")
                
                # Split the documents into chunks
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200,
                    length_function=len,
                )
                splits = text_splitter.split_documents(documents)
                logger.info(f"Split into {len(splits)} chunks")
                
                # Create and save the vector store
                logger.info(f"Creating FAISS vector store at: {vector_store_path}")
                vector_store = FAISS.from_documents(documents=splits, embedding=embeddings)
                
                # Save the vector store without the parameter
                vector_store.save_local(vector_store_path)
                
                # Update the knowledge base with the new vector store ID
                old_id = kb.vector_store_id
                kb.vector_store_id = new_vector_store_id
                db.commit()
                
                logger.info(f"Updated vector store ID from {old_id} to {new_vector_store_id}")
                
                # Verify that the vector store directory exists
                if os.path.exists(vector_store_path):
                    logger.info(f"Vector store created successfully at: {vector_store_path}")
                    files = os.listdir(vector_store_path)
                    logger.info(f"Vector store files: {files}")
                else:
                    logger.error(f"Vector store directory doesn't exist after rebuild: {vector_store_path}")
            
            except Exception as e:
                logger.error(f"Error processing document: {e}", exc_info=True)
                continue
        
        logger.info("Vector store rebuild complete")
        
    except Exception as e:
        logger.error(f"Error during vector store rebuild: {e}", exc_info=True)
    finally:
        db.close()

if __name__ == "__main__":
    rebuild_vector_stores()