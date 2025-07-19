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
                    model_name="gpt-3.5-turbo",
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


    
#--------- Troubleshooting Document Processing ---------#

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
                    template="""You are an expert conversation designer. Convert this troubleshooting document into a comprehensive conversational flow that covers EVERY SINGLE ISSUE mentioned.

Document Content:
{document_content}

CRITICAL REQUIREMENTS:
1. EXTRACT ALL ISSUES - Do not skip any issue mentioned in the document
2. COUNT the issues first - if document has 10 issues, your flow must handle all 10
3. Create a branching conversation that covers every scenario
4. Include both customer-facing and technical issues with simple explanations

ANALYSIS PROCESS:
1. First, identify ALL distinct issues/problems in the document
2. Extract keywords that would trigger each issue
3. Create diagnostic questions to identify which specific issue the user has
4. Design solution paths for each issue
5. Ensure every issue mentioned gets a resolution path

CONVERSATION DESIGN RULES:
- Start with empathetic acknowledgment of the problem
- Use diagnostic questions to narrow down the specific issue
- Provide clear, actionable solutions for each issue
- Use simple language for technical concepts
- If no solution works, offer alternative approaches
- Never suggest contacting support agents (not available)

EXAMPLES OF GOOD CONVERSATIONAL FLOW PATTERNS:

Pattern 1 - Problem Acknowledgment + Diagnostic:
- Initial: "I see you're having trouble with [PROBLEM]. Let me help you figure out what's happening."
- Step 1: "First, [DIAGNOSTIC QUESTION]?"
- If YES → "[NEXT DIAGNOSTIC OR SOLUTION]"
- If NO → "[ALTERNATIVE PATH OR SOLUTION]"

Pattern 2 - Understanding + Symptom Check:
- Initial: "I understand you're experiencing [ISSUE TYPE]. Let's get this sorted out."  
- Step 1: "Are you getting any [SPECIFIC SYMPTOMS/INDICATORS]?"
- If YES → "What exactly [SPECIFIC DETAILS]?"
- If NO → "[ALTERNATIVE DIAGNOSTIC PATH]"

Pattern 3 - Direct Solution with Validation:
- Solution: "Here's how to fix [SPECIFIC ISSUE]: [STEP-BY-STEP INSTRUCTIONS]"
- Follow-up: "Did that resolve the issue for you?"
- If YES → Success message
- If NO → Alternative solution or escalation

CONVERSATION TONE GUIDELINES:
- Sound like a knowledgeable helper having a real conversation
- Be empathetic but solution-focused
- Ask specific, actionable questions
- Provide clear, step-by-step guidance
- Acknowledge user responses appropriately
- Avoid robotic or scripted language
- Use natural, friendly tone
- You can at times use  reactive language like "hmmmm" or "this is strange/odd" to make it feel more human  
- Use contractions and casual phrasing to sound more conversational

OUTPUT FORMAT (JSON):
{{
    "title": "Main problem from document title",
    "description": "Brief description covering all issues addressed",
    "keywords": ["comprehensive", "list", "of", "all", "trigger", "words", "from", "all", "issues"],
    "initial_message": "Empathetic opening acknowledging the problem and offering help",
    "steps": [
        {{
            "id": "step1",
            "type": "diagnostic_question",
            "message": "Broad diagnostic question to categorize the issue",
            "wait_for_response": true,
            "branches": {{
                "issue1_keywords|synonyms": {{"next": "issue1_solution"}},
                "issue2_keywords|synonyms": {{"next": "issue2_solution"}},
                "issue3_keywords|synonyms": {{"next": "issue3_solution"}},
                "default": {{"next": "detailed_questions"}}
            }}
        }},
        {{
            "id": "issue1_solution",
            "type": "solution",
            "message": "Here's how to resolve [specific issue 1]: [clear step-by-step solution]",
            "wait_for_response": true,
            "branches": {{
                "worked|fixed|resolved|yes": {{"next": "success"}},
                "didn't_work|still_problem|no": {{"next": "alternative_solution1"}},
                "default": {{"next": "success"}}
            }}
        }},
        {{
            "id": "issue2_solution", 
            "type": "solution",
            "message": "Here's how to resolve [specific issue 2]: [clear step-by-step solution]",
            "wait_for_response": true,
            "branches": {{
                "worked|fixed|resolved|yes": {{"next": "success"}},
                "didn't_work|still_problem|no": {{"next": "alternative_solution2"}},
                "default": {{"next": "success"}}
            }}
        }},
        {{
            "id": "detailed_questions",
            "type": "diagnostic_question", 
            "message": "Let me ask more specific questions to identify your exact issue. What symptoms are you experiencing?",
            "wait_for_response": true,
            "branches": {{
                "symptom1|indicator1": {{"next": "issue1_solution"}},
                "symptom2|indicator2": {{"next": "issue2_solution"}},
                "default": {{"next": "general_guidance"}}
            }}
        }},
        {{
            "id": "general_guidance",
            "type": "information",
            "message": "Here are the most common solutions you can try: [list main solutions from document]",
            "wait_for_response": false
        }}
    ],
    "success_message": "Excellent! I'm glad we could resolve that issue for you. Is there anything else I can help with?",
    "escalation_message": "I've provided all the available solutions. You might want to try the alternative methods mentioned or seek additional resources for this specific issue.",
    "confidence": 0.95
}}

IMPORTANT REMINDERS:
- Include ALL issues from the document, not just the first few
- Create specific solution paths for each distinct issue
- Use customer-friendly language for technical concepts
- Provide actionable steps, not just general advice
- Don't mention technical support or agents
- Make the conversation feel natural and helpful
- Follow the patterns shown in examples but adapt to your specific content

JSON Response:"""
)
                
                # Use enhanced LLM call with more tokens
                result = self.llm.invoke(prompt.format(document_content=full_content[:12000]))  # Increased limit
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





#--------- Sales Document Processing ---------#

    
    def process_sales_document(self, file_path: str, doc_type: DocumentType, vector_store_id: str) -> Dict[str, Any]:
        """Process sales document with content extraction"""
        logger.info(f"Processing sales document: {file_path}")
        
        try:
            # First, process as regular document for vector storage
            self.process_document_with_id(file_path, doc_type, vector_store_id)
            
            # Now extract sales content using LLM
            sales_data = self._extract_sales_content(file_path, doc_type)
            
            return {
                "vector_store_id": vector_store_id,
                "sales_extracted": sales_data is not None,
                "sales_data": sales_data,
                "extraction_confidence": sales_data.get("confidence", 0) if sales_data else 0
            }
            
        except Exception as e:
            logger.error(f"Error processing sales document: {e}")
            raise




    def _extract_sales_content(self, file_path: str, doc_type: DocumentType) -> Optional[Dict]:
        """Extract sales information AND conversation flows from any sales document format"""
        if not self.llm_available:
            logger.warning("LLM not available for sales extraction")
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
                
                # Enhanced sales extraction prompt with conversation flows
                from langchain.prompts import PromptTemplate
                
                prompt = PromptTemplate(
                    input_variables=["document_content"],
                    template="""You are a sales expert. Extract sales information AND create conversation flows from this document.

    Document Content:
    {document_content}

    Extract EVERYTHING sales-related AND design conversation flows for different sales scenarios.

    EXTRACTION REQUIREMENTS:
    1. Extract all sales data (products, pricing, benefits, etc.)
    2. Create conversation flows that guide prospects through sales scenarios
    3. Make flows consultative, not pushy
    4. Include objection handling and value-based responses

    OUTPUT FORMAT (JSON):
    {{
        "products": [
            {{
                "name": "Product name",
                "description": "What it does",
                "price": "Any pricing info found",
                "features": ["feature1", "feature2"],
                "benefits": ["benefit1", "benefit2"],
                "target_audience": "Who it's for"
            }}
        ],
        "value_propositions": [
            {{
                "statement": "Main value proposition",
                "proof_point": "Supporting evidence",
                "target_pain": "Problem it solves"
            }}
        ],
        "pricing_structure": {{
            "main_pricing": "Primary pricing model",
            "additional_options": ["Other pricing mentioned"],
            "value_justification": "Why the price makes sense"
        }},
        "competitive_advantages": [
            "Any advantage mentioned",
            "Differentiator found"
        ],
        "objection_responses": [
            {{
                "likely_objection": "Inferred customer concern",
                "response_direction": "How to address it"
            }}
        ],
        "social_proof": [
            "Testimonials or success stories",
            "Metrics mentioned"
        ],
        "sales_keywords": ["words", "prospects", "use", "when", "asking"],
        "conversation_starters": [
            "Questions to engage prospects",
            "Conversation openers"
        ],
        
        "conversation_flows": {{
            "pricing_inquiry": {{
                "trigger_keywords": ["price", "cost", "how much", "pricing", "plan", "expensive"],
                "steps": [
                    {{
                        "id": "pricing_context",
                        "message": "I'd be happy to discuss pricing. To give you the most relevant information, what's your main use case?",
                        "wait_for_response": true,
                        "branches": {{
                            "small|startup|individual|personal": {{"next": "starter_pricing"}},
                            "enterprise|large|corporate|business": {{"next": "enterprise_pricing"}},
                            "default": {{"next": "general_pricing"}}
                        }}
                    }},
                    {{
                        "id": "starter_pricing",
                        "message": "Perfect! Based on your needs, I'd recommend our starter option at [PRICE]. This includes [FEATURES] and typically saves businesses like yours [VALUE_PROP]. Would you like to see how this works?",
                        "wait_for_response": true,
                        "branches": {{
                            "yes|sure|demo|show|trial": {{"next": "demo_offer"}},
                            "expensive|too much|budget|cost": {{"next": "roi_justification"}},
                            "features|what|how|more": {{"next": "feature_details"}},
                            "default": {{"next": "next_steps"}}
                        }}
                    }},
                    {{
                        "id": "enterprise_pricing",
                        "message": "For enterprise needs, we have custom solutions starting at [ENTERPRISE_PRICE]. This includes [ENTERPRISE_FEATURES] plus dedicated support. What's your biggest operational challenge right now?",
                        "wait_for_response": true,
                        "branches": {{
                            "scale|scaling|growth|users": {{"next": "scalability_benefits"}},
                            "integration|systems|existing": {{"next": "integration_benefits"}},
                            "security|compliance|privacy": {{"next": "security_benefits"}},
                            "default": {{"next": "custom_solution"}}
                        }}
                    }},
                    {{
                        "id": "roi_justification",
                        "message": "I understand budget is important. Let me put this in perspective: [VALUE_JUSTIFICATION]. Most clients see ROI within [TIMEFRAME]. What would saving [SPECIFIC_BENEFIT] be worth to your business?",
                        "wait_for_response": true,
                        "branches": {{
                            "interested|valuable|worth|good": {{"next": "demo_offer"}},
                            "still|expensive|much": {{"next": "alternative_options"}},
                            "default": {{"next": "follow_up"}}
                        }}
                    }}
                ]
            }},
            
            "feature_inquiry": {{
                "trigger_keywords": ["features", "what does", "how does", "capabilities", "functions"],
                "steps": [
                    {{
                        "id": "feature_discovery",
                        "message": "Great question! We have several powerful capabilities. What's your biggest challenge that you're hoping to solve?",
                        "wait_for_response": true,
                        "branches": {{
                            "time|efficiency|speed|fast|slow": {{"next": "automation_features"}},
                            "cost|money|budget|expense": {{"next": "cost_saving_features"}},
                            "quality|accuracy|error|mistake": {{"next": "quality_features"}},
                            "default": {{"next": "general_features"}}
                        }}
                    }},
                    {{
                        "id": "automation_features",
                        "message": "Perfect! Our automation features can save you significant time. [AUTOMATION_BENEFITS]. For example, [SPECIFIC_EXAMPLE]. How much time does your team currently spend on these tasks?",
                        "wait_for_response": true,
                        "branches": {{
                            "hours|lot|much|daily": {{"next": "time_savings_calculation"}},
                            "interested|more|demo": {{"next": "demo_offer"}},
                            "default": {{"next": "other_features"}}
                        }}
                    }}
                ]
            }},
            
            "comparison_inquiry": {{
                "trigger_keywords": ["vs", "compare", "better than", "alternative", "competitor"],
                "steps": [
                    {{
                        "id": "competitive_discovery",
                        "message": "I'd be happy to help you compare options. What other solutions are you considering, or what's most important to you in a solution?",
                        "wait_for_response": true,
                        "branches": {{
                            "price|cost|budget|cheap": {{"next": "price_comparison"}},
                            "features|functionality|capabilities": {{"next": "feature_comparison"}},
                            "support|service|help": {{"next": "support_comparison"}},
                            "default": {{"next": "general_comparison"}}
                        }}
                    }},
                    {{
                        "id": "feature_comparison",
                        "message": "Great point! Here's what sets us apart: [COMPETITIVE_ADVANTAGES]. Unlike other solutions, we offer [UNIQUE_FEATURES]. What specific functionality is most critical for your success?",
                        "wait_for_response": true,
                        "branches": {{
                            "integration|connect|api": {{"next": "integration_advantages"}},
                            "support|help|service": {{"next": "support_advantages"}},
                            "default": {{"next": "custom_comparison"}}
                        }}
                    }}
                ]
            }},
            
            "demo_inquiry": {{
                "trigger_keywords": ["demo", "trial", "show me", "can I try", "see it", "test"],
                "steps": [
                    {{
                        "id": "demo_qualification",
                        "message": "Absolutely! I'd love to show you how this works. To make the demo most valuable, what specific use case or challenge should we focus on?",
                        "wait_for_response": true,
                        "branches": {{
                            "workflow|process|current": {{"next": "workflow_demo"}},
                            "integration|systems|data": {{"next": "integration_demo"}},
                            "team|users|multiple": {{"next": "collaboration_demo"}},
                            "default": {{"next": "general_demo"}}
                        }}
                    }},
                    {{
                        "id": "workflow_demo",
                        "message": "Perfect! I'll show you exactly how we can streamline your workflow. The demo takes about 15 minutes and I'll customize it to your specific process. When would work best for you?",
                        "wait_for_response": true,
                        "branches": {{
                            "now|today|right now": {{"next": "immediate_demo"}},
                            "tomorrow|later|schedule": {{"next": "schedule_demo"}},
                            "default": {{"next": "demo_scheduling"}}
                        }}
                    }}
                ]
            }}
        }},
        
        "confidence": 0.85
    }}

    IMPORTANT: Extract actual content from the document. Replace placeholders like [PRICE], [FEATURES] with real information from the document. If pricing isn't mentioned, use "Contact for pricing" or similar.

    JSON Response:"""
                )
                
                # Get LLM response
                result = self.llm.invoke(prompt.format(document_content=full_content[:12000]))
                response_text = result.content if hasattr(result, 'content') else str(result)
                
                # Parse JSON response
                import json
                import re
                
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        sales_data = json.loads(json_match.group())
                        
                        # Validate the extracted data (enhanced validation)
                        if self._validate_sales_data_with_flows(sales_data):
                            sales_data["confidence"] = 0.85
                            sales_data["extraction_method"] = "llm_sales_extraction_with_flows"
                            logger.info(f"✅ Successfully extracted sales content with conversation flows")
                            return sales_data
                        else:
                            logger.warning("⚠️ Extracted sales data failed validation")
                            return self._create_fallback_sales_data_with_flows(full_content)
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON parsing failed: {e}")
                        return self._create_fallback_sales_data_with_flows(full_content)
                else:
                    logger.warning("⚠️ No JSON found in LLM response")
                    return self._create_fallback_sales_data_with_flows(full_content)
                    
            finally:
                # Clean up temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error in sales content extraction: {e}")
            return None






    def _validate_sales_data_with_flows(self, sales_data: Dict) -> bool:
        """Validate extracted sales data including conversation flows"""
        try:
            # Original validation
            required_fields = ['products', 'value_propositions', 'sales_keywords']
            
            for field in required_fields:
                if field not in sales_data:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Check if we have meaningful content
            if (len(sales_data.get('products', [])) == 0 and 
                len(sales_data.get('value_propositions', [])) == 0):
                logger.error("No meaningful sales content found")
                return False
            
            # Validate conversation flows
            conversation_flows = sales_data.get('conversation_flows', {})
            if conversation_flows:
                for flow_name, flow_data in conversation_flows.items():
                    if not self._validate_conversation_flow_structure(flow_data):
                        logger.warning(f"Invalid conversation flow structure: {flow_name}")
                        # Don't fail validation, just log warning
            
            logger.info("✅ Sales data validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Sales data validation error: {e}")
            return False

    def _validate_conversation_flow_structure(self, flow_data: Dict) -> bool:
        """Validate conversation flow structure"""
        try:
            required_flow_fields = ['trigger_keywords', 'steps']
            
            for field in required_flow_fields:
                if field not in flow_data:
                    return False
            
            steps = flow_data.get('steps', [])
            if not isinstance(steps, list) or len(steps) == 0:
                return False
            
            # Validate each step
            for step in steps:
                if not isinstance(step, dict):
                    return False
                
                required_step_fields = ['id', 'message']
                for field in required_step_fields:
                    if field not in step:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Flow structure validation error: {e}")
            return False

    def _create_fallback_sales_data_with_flows(self, content: str) -> Dict:
        """Create basic sales data with simple conversation flows when extraction fails"""
        # Extract basic keywords
        keywords = []
        common_sales_words = ['price', 'cost', 'buy', 'purchase', 'product', 'service', 'plan', 'pricing']
        content_lower = content.lower()
        
        for word in common_sales_words:
            if word in content_lower:
                keywords.append(word)
        
        if not keywords:
            keywords = ['product', 'service', 'pricing']
        
        return {
            "products": [{"name": "Main Product", "description": "Product information", "price": "Contact for pricing"}],
            "value_propositions": [{"statement": "Quality solution", "proof_point": "Customer satisfaction"}],
            "sales_keywords": keywords[:10],
            "conversation_flows": {
                "pricing_inquiry": {
                    "trigger_keywords": ["price", "cost", "pricing"],
                    "steps": [
                        {
                            "id": "basic_pricing",
                            "message": "I'd be happy to discuss pricing with you. What specific information would you like to know?",
                            "wait_for_response": True,
                            "branches": {
                                "default": {"next": "contact_sales"}
                            }
                        }
                    ]
                }
            },
            "confidence": 0.3,
            "extraction_method": "fallback_creation_with_flows"
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