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

    def __init__(self, tenant_id: int, llm_service: Optional[Any] = None):
        """Initialize DocumentProcessor with tenant ID and required components"""
        self.tenant_id = tenant_id
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.storage = storage_service
        self.llm_service = llm_service
        
        # Add LLM availability check
        try:
            from langchain_openai import ChatOpenAI
            self.llm_available = bool(settings.OPENAI_API_KEY)
            if self.llm_available:
                self.llm = ChatOpenAI(
                    model_name="gpt-4",
                    temperature=0.1,
                    openai_api_key=settings.OPENAI_API_KEY
                )
        except ImportError:
            self.llm_available = False
            self.llm = None
        
        logger.info(f"DocumentProcessor initialized for tenant {tenant_id} with cloud storage (LLM: {self.llm_available})")
    
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
            # Add more detailed logging for file reading
            logger.info(f"Attempting to read file: {file_path}")
            
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8-sig')
                logger.info("Successfully read CSV file")
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
                logger.info("Successfully read Excel file")
            else:
                raise ValueError("FAQ file must be CSV or Excel format")
            
            # Log dataframe info
            logger.info(f"DataFrame shape: {df.shape}")
            logger.info(f"DataFrame columns (raw): {df.columns.tolist()}")
            
            # Check if dataframe is empty
            if df.empty:
                raise ValueError("FAQ file is empty")
            
            # Clean column names - remove leading/trailing whitespace and convert to string
            df.columns = df.columns.astype(str).str.strip()
            logger.info(f"DataFrame columns (after cleaning): {df.columns.tolist()}")
            
            # Expected columns: question/questions, answer/answers
            question_col = None
            answer_col = None
            
            # Look for question and answer columns (case insensitive, singular or plural)
            for col in df.columns:
                col_lower = col.lower().strip()
                logger.info(f"Checking column: '{col}' -> '{col_lower}'")
                
                if col_lower in ['question', 'questions']:
                    question_col = col
                    logger.info(f"Found question column: '{col}'")
                elif col_lower in ['answer', 'answers']:
                    answer_col = col
                    logger.info(f"Found answer column: '{col}'")
            
            # Enhanced error reporting
            if question_col is None or answer_col is None:
                missing_cols = []
                if question_col is None:
                    missing_cols.append("'question' or 'questions'")
                    logger.error("No question column found")
                if answer_col is None:
                    missing_cols.append("'answer' or 'answers'")
                    logger.error("No answer column found")
                
                # Log each column and why it didn't match
                for col in df.columns:
                    col_lower = col.lower().strip()
                    logger.error(f"Column '{col}' (processed: '{col_lower}') - "
                            f"matches question: {col_lower in ['question', 'questions']}, "
                            f"matches answer: {col_lower in ['answer', 'answers']}")
                
                error_msg = (
                    f"FAQ sheet must contain {' and '.join(missing_cols)} columns. "
                    f"Found columns: {df.columns.tolist()}. "
                    f"Note: Column matching is case-insensitive and looks for 'question'/'questions' and 'answer'/'answers'."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            logger.info(f"Using columns: question='{question_col}', answer='{answer_col}'")
            
            # Rename columns to standardized names for processing
            df = df.rename(columns={question_col: 'question', answer_col: 'answer'})
            
            # Log sample data
            logger.info(f"Sample data (first 3 rows):")
            for i, row in df.head(3).iterrows():
                logger.info(f"Row {i}: Q='{row['question']}' A='{row['answer']}'")
            
            # Convert to list of dictionaries
            faqs = []
            skipped_rows = []
            
            for idx, row in df.iterrows():
                # Check for null values
                if pd.isna(row['question']) or pd.isna(row['answer']):
                    skipped_rows.append(f"Row {idx + 1}: null values")
                    continue
                
                # Convert to string and strip whitespace
                question_text = str(row['question']).strip()
                answer_text = str(row['answer']).strip()
                
                # Skip empty strings after stripping
                if not question_text or not answer_text:
                    skipped_rows.append(f"Row {idx + 1}: empty after stripping")
                    continue
                
                # Skip if values are just "nan" string
                if question_text.lower() == 'nan' or answer_text.lower() == 'nan':
                    skipped_rows.append(f"Row {idx + 1}: 'nan' values")
                    continue
                
                faqs.append({
                    'question': question_text,
                    'answer': answer_text
                })
            
            # Log processing results
            logger.info(f"Processed {len(faqs)} FAQ items successfully")
            if skipped_rows:
                logger.warning(f"Skipped {len(skipped_rows)} rows: {skipped_rows}")
            
            if not faqs:
                raise ValueError("No valid FAQ items found in the file")
            
            return faqs
            
        except Exception as e:
            logger.error(f"Error processing FAQ sheet: {str(e)}", exc_info=True)
            
            # Additional debugging info
            try:
                if 'df' in locals():
                    logger.error(f"DataFrame info: shape={df.shape}, columns={df.columns.tolist()}")
                else:
                    logger.error("DataFrame was not created - file reading failed")
            except:
                pass
            
            raise


    


    def process_troubleshooting_document(self, file_path: str, doc_type: DocumentType, vector_store_id: str) -> Dict[str, Any]:
        """
        Process troubleshooting document with LLM extraction
        """
        logger.info(f"Processing troubleshooting document: {file_path}")
        
        try:
            # First, process as regular document for vector storage
            self.process_document_with_id(file_path, doc_type, vector_store_id)
            
            # Now extract troubleshooting flow using LLM
            flow_data = self._extract_troubleshooting_flow(file_path, doc_type)
            
            return {
                "vector_store_id": vector_store_id,
                "flow_extracted": flow_data is not None,
                "flow_data": flow_data,
                "extraction_confidence": flow_data.get("confidence", 0) if flow_data else 0
            }
            
        except Exception as e:
            logger.error(f"Error processing troubleshooting document: {e}")
            raise

    def _extract_troubleshooting_flow(self, file_path: str, doc_type: DocumentType) -> Optional[Dict]:
        """
        Enhanced LLM extraction that converts ANY troubleshooting document into conversational flow
        """
        if not self.llm_available:
            logger.warning("LLM not available for troubleshooting extraction")
            return None
        
        try:
            # Download and load document content
            temp_file_path = None
            
            try:
                if file_path.startswith('tenant_'):
                    temp_file_path = self.storage.download_to_temp("knowledge-base-files", file_path)
                    file_to_process = temp_file_path
                else:
                    file_to_process = file_path
                
                loader = self._get_loader(file_to_process, doc_type)
                documents = loader.load()
                
                if not documents:
                    return None
                
                # Combine all document content
                full_content = "\n".join([doc.page_content for doc in documents])
                
                # Enhanced LLM prompt for smart conversion
                from langchain.prompts import PromptTemplate
                
                prompt = PromptTemplate(
                    input_variables=["document_content"],
                    template="""You are an expert conversation designer. Convert this troubleshooting document into a smart conversational flow.

    Document Content:
    {document_content}

    TASK: Transform this into a conversational troubleshooting flow where the bot guides users step-by-step.

    ANALYSIS PROCESS:
    1. Identify the main problem/issue being addressed
    2. Extract all possible causes and solutions
    3. Create a logical conversation flow that diagnoses the issue
    4. Convert static steps into bot questions and user responses

    CONVERSATION DESIGN RULES:
    - Start with an empathetic acknowledgment of the problem
    - Ask diagnostic questions to narrow down the issue
    - Provide clear next steps based on user responses
    - Include fallback options for unclear responses
    - End with either resolution or escalation

    OUTPUT FORMAT (JSON):
    {{
        "title": "Main problem title",
        "description": "Brief description of what this troubleshooting flow handles",
        "keywords": ["trigger", "words", "that", "indicate", "this", "problem"],
        "initial_message": "Empathetic opening message acknowledging the problem",
        "steps": [
            {{
                "id": "step1",
                "type": "diagnostic_question",
                "message": "First diagnostic question to narrow down the issue",
                "wait_for_response": true,
                "branches": {{
                    "option1|synonym1|related_word1": {{
                        "next": "step2",
                        "message": "Optional immediate response before next step"
                    }},
                    "option2|synonym2|related_word2": {{
                        "next": "solution_branch_a"
                    }},
                    "default": {{
                        "next": "clarification",
                        "message": "I'm not sure I understand. Could you clarify..."
                    }}
                }}
            }},
            {{
                "id": "step2",
                "type": "diagnostic_question",
                "message": "Second diagnostic question",
                "wait_for_response": true,
                "branches": {{
                    "yes|confirmed|correct": {{"next": "step3"}},
                    "no|incorrect|different": {{"next": "alternative_path"}},
                    "default": {{"next": "step2", "message": "Please answer yes or no so I can help you better."}}
                }}
            }},
            {{
                "id": "solution_branch_a",
                "type": "solution",
                "message": "Here's how to fix this specific issue: [detailed steps]",
                "wait_for_response": false,
                "branches": {{
                    "worked|fixed|solved": {{"next": "success"}},
                    "still_not_working|didn't_work": {{"next": "escalation"}},
                    "default": {{"next": "success"}}
                }}
            }}
        ],
        "success_message": "Great! I'm glad we could resolve that for you. Is there anything else I can help with?",
        "escalation_message": "I understand this is frustrating. Let me connect you with our technical support team who can provide more specialized assistance.",
        "confidence": 0.95
    }}

    EXAMPLES OF GOOD CONVERSATIONAL FLOW:

    For a "Card Declining" document:
    - Initial: "I see you're having trouble with your card being declined. Let me help you figure out what's happening."
    - Step 1: "First, do you have sufficient funds in your account?"
    - If YES → "Is your card expired? Please check the expiry date on your card."
    - If NO → "Please check your account balance or try a different card."

    For a "Login Issues" document:
    - Initial: "I understand you're having trouble logging in. Let's get this sorted out."  
    - Step 1: "Are you getting any specific error messages when you try to log in?"
    - If YES → "What does the error message say exactly?"
    - If NO → "Is your account password working, or do you think it might need to be reset?"

    IMPORTANT: Create a logical flow that feels natural and helpful, not robotic. The bot should sound like a knowledgeable support agent having a real conversation.

    JSON Response:"""
                )
                
                # Use enhanced LLM call with more tokens
                result = self.llm.invoke(prompt.format(document_content=full_content[:6000]))  # Increased limit
                response_text = result.content if hasattr(result, 'content') else str(result)
                
                # Parse JSON response with better error handling
                import json
                import re
                
                # Try to extract JSON from response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        flow_data = json.loads(json_match.group())
                        
                        # Validate the extracted flow
                        if self._validate_conversation_flow(flow_data):
                            flow_data["confidence"] = 0.95
                            flow_data["extraction_method"] = "enhanced_llm_conversion"
                            logger.info(f"✅ Successfully converted document to conversational flow: {flow_data.get('title', 'Unknown')}")
                            return flow_data
                        else:
                            logger.warning("⚠️ Extracted flow failed validation")
                            return self._create_fallback_flow(full_content)
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON parsing failed: {e}")
                        return self._create_fallback_flow(full_content)
                else:
                    logger.warning("⚠️ No JSON found in LLM response")
                    return self._create_fallback_flow(full_content)
                    
            finally:
                # Clean up temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info(f"Cleaned up temp extraction file: {temp_file_path}")
                    except:
                        pass
                    
        except Exception as e:
            logger.error(f"Error in enhanced troubleshooting extraction: {e}")
            return None

    def _validate_conversation_flow(self, flow_data: Dict) -> bool:
        """Validate that the extracted flow has proper conversational structure"""
        try:
            required_fields = ['title', 'keywords', 'initial_message', 'steps']
            
            # Check required fields
            for field in required_fields:
                if field not in flow_data:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Validate keywords
            if not isinstance(flow_data['keywords'], list) or len(flow_data['keywords']) < 2:
                logger.error("Keywords must be a list with at least 2 items")
                return False
            
            # Validate steps structure
            steps = flow_data['steps']
            if not isinstance(steps, list) or len(steps) < 1:
                logger.error("Steps must be a list with at least 1 step")
                return False
            
            # Validate each step
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    logger.error(f"Step {i} must be a dictionary")
                    return False
                
                if 'id' not in step or 'message' not in step:
                    logger.error(f"Step {i} missing required fields (id, message)")
                    return False
                
                # Check branches if step expects response
                if step.get('wait_for_response', False):
                    if 'branches' not in step or not isinstance(step['branches'], dict):
                        logger.error(f"Step {i} expects response but has no valid branches")
                        return False
            
            logger.info("✅ Conversation flow validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Flow validation error: {e}")
            return False

    def _create_fallback_flow(self, content: str) -> Dict:
        """Create a basic fallback flow when extraction fails"""
        # Extract basic info from content
        first_lines = content.split('\n')[:10]
        title = next((line.strip() for line in first_lines if len(line.strip()) > 10), "Technical Support")
        
        # Simple keyword extraction
        keywords = []
        common_issue_words = ['error', 'problem', 'issue', 'fail', 'not working', 'decline', 'login', 'access', 'payment', 'card']
        content_lower = content.lower()
        
        for word in common_issue_words:
            if word in content_lower:
                keywords.append(word)
        
        if not keywords:
            keywords = ['help', 'support', 'issue']
        
        return {
            "title": title,
            "description": "Technical support assistance",
            "keywords": keywords[:5],
            "initial_message": "I understand you're experiencing an issue. Let me help you resolve this.",
            "steps": [
                {
                    "id": "step1",
                    "type": "information_gathering",
                    "message": "Can you describe exactly what's happening when you encounter this issue?",
                    "wait_for_response": True,
                    "branches": {
                        "default": {
                            "next": "escalation",
                            "message": "Thank you for the details. Let me connect you with our technical support team."
                        }
                    }
                }
            ],
            "success_message": "I'm glad I could help resolve your issue!",
            "escalation_message": "Let me connect you with our specialized support team for further assistance.",
            "confidence": 0.3,
            "extraction_method": "fallback_creation"
        }




    async def get_crawl_metadata(self, vector_store_id: str) -> Optional[Dict]:
        """Get crawl metadata for a website knowledge base"""
        try:
            metadata_path = f"tenant_{self.tenant_id}/crawl_metadata/{vector_store_id}.json"
            metadata_content = self.storage.download_file("vector-stores", metadata_path)
            return json.loads(metadata_content.decode())
        except Exception as e:
            logger.warning(f"Could not load crawl metadata for {vector_store_id}: {e}")
            return None