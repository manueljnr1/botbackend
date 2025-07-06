import os
import uuid
import pandas as pd
import logging
import tempfile
import shutil
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
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
from app.knowledge_base.js_crawler import JSWebsiteCrawler
from app.services.storage import storage_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Enhanced processor with website crawling support"""
    
    def __init__(self, tenant_id: int):
        """Initialize DocumentProcessor with tenant ID and required components"""
        self.tenant_id = tenant_id
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.storage = storage_service
        
        logger.info(f"DocumentProcessor initialized for tenant {tenant_id} with cloud storage")
    
    def process_document(self, file_path: str, doc_type: DocumentType) -> str:
        """Process a document and store it in the vector store (original method)"""
        # Generate a unique ID for this document
        vector_store_id = f"kb_{self.tenant_id}_{str(uuid.uuid4())}"
        
        # Use the new method with the generated ID
        return self.process_document_with_id(file_path, doc_type, vector_store_id)

    def process_document_with_id(self, cloud_file_path: str, doc_type: DocumentType, vector_store_id: str) -> str:
        """Process document from cloud storage with pre-defined vector store ID"""
        logger.info(f"Processing document from cloud: {cloud_file_path} -> {vector_store_id}")
        
        # Download source file to temp location
        temp_file_path = None
        temp_vector_dir = None
        
        try:
            # Download source file
            temp_file_path = self.storage.download_to_temp("knowledge-base-files", cloud_file_path)
            logger.info(f"Downloaded source file to: {temp_file_path}")
            
            # Load and process document
            loader = self._get_loader(temp_file_path, doc_type)
            documents = loader.load()
            
            if not documents:
                raise ValueError("No content extracted from document")
            
            logger.info(f"Loaded {len(documents)} document segments")
            
            # Log the content of the first document for debugging
            if documents:
                first_doc = documents[0]
                content_preview = first_doc.page_content[:200] if hasattr(first_doc, 'page_content') else "No content available"
                logger.info(f"First document content preview: {content_preview}...")
            
            # Split into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )
            splits = text_splitter.split_documents(documents)
            
            if not splits:
                raise ValueError("No text chunks created from document")
            
            logger.info(f"Split into {len(splits)} chunks")
            
            # Create vector store in temp directory
            temp_vector_dir = tempfile.mkdtemp()
            logger.info(f"Creating vector store in temp dir: {temp_vector_dir}")
            
            # Create and save vector store locally first
            vector_store = FAISS.from_documents(documents=splits, embedding=self.embeddings)
            vector_store.save_local(temp_vector_dir)
            logger.info(f"Vector store saved to temp directory")
            
            # Verify local creation
            required_files = ["index.faiss", "index.pkl"]
            for file in required_files:
                file_path = os.path.join(temp_vector_dir, file)
                if not os.path.exists(file_path):
                    raise ValueError(f"Required vector store file not created: {file}")
            
            # Upload vector store files to cloud
            self.storage.upload_vector_store_files(self.tenant_id, vector_store_id, temp_vector_dir)
            logger.info(f"Vector store uploaded to cloud successfully")
            
            return vector_store_id
            
        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            # Clean up any partial cloud files
            try:
                self.storage.delete_vector_store(self.tenant_id, vector_store_id)
            except:
                pass  # Ignore cleanup errors
            raise
            
        finally:
            # Clean up temp files
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Cleaned up temp source file: {temp_file_path}")
                except:
                    pass
                    
            if temp_vector_dir and os.path.exists(temp_vector_dir):
                try:
                    shutil.rmtree(temp_vector_dir)
                    logger.info(f"Cleaned up temp vector dir: {temp_vector_dir}")
                except:
                    pass

    async def process_website(self, 
                            base_url: str, 
                            vector_store_id: str,
                            crawl_depth: int = 3,
                            include_patterns: List[str] = None,
                            exclude_patterns: List[str] = None) -> Dict[str, Any]:
        """Process website content and store in vector store"""
        logger.info(f"Processing website: {base_url} -> {vector_store_id}")
        
        temp_vector_dir = None
        
        try:
            # Initialize JS-enabled crawler
            crawler = JSWebsiteCrawler(
                max_depth=crawl_depth,
                max_pages=50,  # Reasonable limit
                delay=1.0,  # Be respectful
                enable_js=True  # Enable JavaScript rendering
            )
            
            # Crawl website
            crawl_results = await crawler.crawl_website(
                base_url=base_url,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns
            )
            
            if not crawl_results:
                raise ValueError("No content extracted from website")
            
            # Convert to documents
            documents = crawler.get_documents()
            
            if not documents:
                raise ValueError("No valid documents created from crawled content")
            
            logger.info(f"Created {len(documents)} documents from {len(crawl_results)} crawled pages")
            
            # Split into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )
            splits = text_splitter.split_documents(documents)
            
            if not splits:
                raise ValueError("No text chunks created from website content")
            
            logger.info(f"Split into {len(splits)} chunks")
            
            # Create vector store in temp directory
            temp_vector_dir = tempfile.mkdtemp()
            logger.info(f"Creating vector store in temp dir: {temp_vector_dir}")
            
            # Create and save vector store locally first
            vector_store = FAISS.from_documents(documents=splits, embedding=self.embeddings)
            vector_store.save_local(temp_vector_dir)
            logger.info(f"Vector store saved to temp directory")
            
            # Verify local creation
            required_files = ["index.faiss", "index.pkl"]
            for file in required_files:
                file_path = os.path.join(temp_vector_dir, file)
                if not os.path.exists(file_path):
                    raise ValueError(f"Required vector store file not created: {file}")
            
            # Upload vector store files to cloud
            self.storage.upload_vector_store_files(self.tenant_id, vector_store_id, temp_vector_dir)
            logger.info(f"Vector store uploaded to cloud successfully")
            
            # Store crawl metadata in cloud
            metadata = {
                'base_url': base_url,
                'pages_crawled': len(crawl_results),
                'successful_pages': len([r for r in crawl_results if r.content and not r.error]),
                'failed_pages': len([r for r in crawl_results if r.error]),
                'crawled_urls': [r.url for r in crawl_results if r.content and not r.error],
                'failed_urls': [{'url': r.url, 'error': r.error} for r in crawl_results if r.error],
                'crawled_at': datetime.utcnow().isoformat(),
                'include_patterns': include_patterns,
                'exclude_patterns': exclude_patterns
            }
            
            # Save metadata to cloud
            metadata_json = json.dumps(metadata, indent=2)
            metadata_path = f"tenant_{self.tenant_id}/crawl_metadata/{vector_store_id}.json"
            self.storage.upload_file("vector-stores", metadata_path, metadata_json.encode())
            
            return {
                'vector_store_id': vector_store_id,
                'pages_crawled': len(crawl_results),
                'successful_pages': len([r for r in crawl_results if r.content and not r.error]),
                'failed_pages': len([r for r in crawl_results if r.error]),
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Website processing failed: {e}")
            # Clean up any partial cloud files
            try:
                self.storage.delete_vector_store(self.tenant_id, vector_store_id)
            except:
                pass  # Ignore cleanup errors
            raise
            
        finally:
            # Clean up temp files
            if temp_vector_dir and os.path.exists(temp_vector_dir):
                try:
                    shutil.rmtree(temp_vector_dir)
                    logger.info(f"Cleaned up temp vector dir: {temp_vector_dir}")
                except:
                    pass
    
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
    
    def get_vector_store(self, vector_store_id: str):
        """Load a vector store from cloud storage"""
        logger.info(f"Loading vector store from cloud: {vector_store_id}")
        
        temp_dir = None
        try:
            # Download vector store files to temp directory
            temp_dir = self.storage.download_vector_store_files(self.tenant_id, vector_store_id)
            
            # Load FAISS from temp directory
            vector_store = FAISS.load_local(
                temp_dir, 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
            logger.info(f"Vector store loaded successfully from cloud")
            return vector_store
            
        except Exception as e:
            logger.error(f"Failed to load vector store {vector_store_id} from cloud: {e}")
            raise FileNotFoundError(f"Vector store not found: {vector_store_id}")
            
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temp vector store dir: {temp_dir}")
                except:
                    pass
    
    def delete_vector_store(self, vector_store_id: str):
        """Delete a vector store from cloud storage"""
        try:
            success = self.storage.delete_vector_store(self.tenant_id, vector_store_id)
            
            # Also delete metadata if exists
            try:
                metadata_path = f"tenant_{self.tenant_id}/crawl_metadata/{vector_store_id}.json"
                self.storage.delete_file("vector-stores", metadata_path)
            except:
                pass  # Metadata might not exist
            
            if success:
                logger.info(f"Deleted vector store from cloud: {vector_store_id}")
            else:
                logger.warning(f"Vector store not found for deletion: {vector_store_id}")
            return success
        except Exception as e:
            logger.error(f"Error deleting vector store {vector_store_id}: {e}")
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
            
            # Expected columns: question/questions, answer/answers
            question_col = None
            answer_col = None
            
            # Look for question and answer columns (case insensitive, singular or plural)
            for col in df.columns:
                col_lower = col.lower().strip()
                if col_lower in ['question', 'questions']:
                    question_col = col
                elif col_lower in ['answer', 'answers']:
                    answer_col = col
            
            if question_col is None or answer_col is None:
                missing_cols = []
                if question_col is None:
                    missing_cols.append("'question' or 'questions'")
                if answer_col is None:
                    missing_cols.append("'answer' or 'answers'")
                
                raise ValueError(
                    f"FAQ sheet must contain {' and '.join(missing_cols)} columns. "
                    f"Found columns: {df.columns.tolist()}"
                )
            
            logger.info(f"Using columns: question='{question_col}', answer='{answer_col}'")
            
            # Rename columns to standardized names for processing
            df = df.rename(columns={question_col: 'question', answer_col: 'answer'})
            
            # Convert to list of dictionaries
            faqs = []
            for idx, row in df.iterrows():
                if pd.notna(row['question']) and pd.notna(row['answer']):
                    question_text = str(row['question']).strip()
                    answer_text = str(row['answer']).strip()
                    
                    # Skip empty strings after stripping
                    if question_text and answer_text:
                        faqs.append({
                            'question': question_text,
                            'answer': answer_text
                        })
                    else:
                        logger.warning(f"Skipping row {idx + 1}: empty question or answer after stripping whitespace")
                else:
                    logger.warning(f"Skipping row {idx + 1}: missing question or answer")
            
            logger.info(f"Processed {len(faqs)} FAQ items")
            return faqs
            
        except Exception as e:
            logger.error(f"Error processing FAQ sheet: {str(e)}", exc_info=True)
            raise

    async def get_crawl_metadata(self, vector_store_id: str) -> Optional[Dict]:
        """Get crawl metadata for a website knowledge base"""
        try:
            metadata_path = f"tenant_{self.tenant_id}/crawl_metadata/{vector_store_id}.json"
            metadata_content = self.storage.download_file("vector-stores", metadata_path)
            return json.loads(metadata_content.decode())
        except Exception as e:
            logger.warning(f"Could not load crawl metadata for {vector_store_id}: {e}")
            return None