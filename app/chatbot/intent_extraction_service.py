import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.knowledge_base.models import KnowledgeBase, TenantIntentPattern, ProcessingStatus
from app.config import settings

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

class TenantIntentExtractionService:
    """Extract tenant-specific intent patterns from uploaded documents"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_available = LLM_AVAILABLE and bool(settings.OPENAI_API_KEY)
        if self.llm_available:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.1,
                openai_api_key=settings.OPENAI_API_KEY
            )
    
    async def extract_intents_from_document(self, kb_id: int) -> Dict[str, Any]:
        """Extract intent patterns from a knowledge base document"""
        try:
            kb = self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
            if not kb or kb.processing_status != ProcessingStatus.COMPLETED:
                return {"success": False, "error": "Document not ready"}
            
            # Get document content
            from app.knowledge_base.processor import DocumentProcessor
            processor = DocumentProcessor(kb.tenant_id)
            
            try:
                vector_store = processor.get_vector_store(kb.vector_store_id)
                docs = vector_store.similarity_search("content", k=10)
                content = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                logger.error(f"Failed to load document content: {e}")
                return {"success": False, "error": "Failed to load document"}
            
            if not content or len(content.strip()) < 100:
                return {"success": False, "error": "Insufficient content"}
            
            # Extract patterns using LLM
            patterns = await self._extract_patterns_with_llm(content, kb.document_type.value)
            
            if patterns:
                # Store patterns
                await self._store_intent_patterns(kb.tenant_id, kb.id, patterns)
                return {"success": True, "patterns": patterns}
            
            return {"success": False, "error": "No patterns extracted"}
            
        except Exception as e:
            logger.error(f"Intent extraction error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _extract_patterns_with_llm(self, content: str, doc_type: str) -> Optional[Dict]:
        """Extract intent patterns using LLM"""
        if not self.llm_available:
            return None
        
        try:
            prompt = PromptTemplate(
                input_variables=["content", "doc_type"],
                template="""Analyze this {doc_type} document and extract intent patterns for routing user messages.

DOCUMENT CONTENT:
{content}

EXTRACTION TASK:
Extract patterns that would help classify when users are asking about topics in this document.

Extract:
1. QUESTION PATTERNS - How users would ask about this content
2. PROBLEM PATTERNS - How users would describe issues/problems related to this content  
3. KEYWORDS - Key terms that indicate this intent
4. INTENT TYPE - What type of document this is

RULES:
- Focus on user language, not technical terms
- Include variations (formal/casual, different phrasings)
- Extract actual user problems, not just topics
- Consider different ways to express the same intent

RESPONSE FORMAT (JSON):
{{
    "intent_type": "troubleshooting|sales|enquiry|faq",
    "confidence": 0.0-1.0,
    "keywords": ["keyword1", "keyword2", ...],
    "question_patterns": [
        "How do I...",
        "What is...",
        "Can you help me with..."
    ],
    "problem_patterns": [
        "My X is not working",
        "I'm having trouble with...",
        "X keeps failing"
    ],
    "trigger_phrases": [
        "specific phrases that indicate this intent"
    ]
}}

JSON Response:"""
            )
            
            result = self.llm.invoke(prompt.format(content=content[:8000], doc_type=doc_type))
            response_text = result.content.strip()
            
            # Parse JSON response
            import json
            import re
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    patterns = json.loads(json_match.group())
                    
                    # Validate and clean patterns
                    return self._validate_patterns(patterns)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing failed: {e}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"LLM pattern extraction error: {e}")
            return None
    
    def _validate_patterns(self, patterns: Dict) -> Optional[Dict]:
        """Validate and clean extracted patterns"""
        try:
            # Required fields
            required_fields = ['intent_type', 'keywords', 'question_patterns', 'problem_patterns']
            for field in required_fields:
                if field not in patterns:
                    return None
            
            # Validate intent type
            valid_intents = ['troubleshooting', 'sales', 'enquiry', 'faq']
            if patterns['intent_type'] not in valid_intents:
                patterns['intent_type'] = 'enquiry'  # Default
            
            # Ensure lists
            for field in ['keywords', 'question_patterns', 'problem_patterns', 'trigger_phrases']:
                if field not in patterns:
                    patterns[field] = []
                elif not isinstance(patterns[field], list):
                    patterns[field] = []
            
            # Limit sizes
            patterns['keywords'] = patterns['keywords'][:20]
            patterns['question_patterns'] = patterns['question_patterns'][:15]
            patterns['problem_patterns'] = patterns['problem_patterns'][:15]
            patterns['trigger_phrases'] = patterns.get('trigger_phrases', [])[:10]
            
            # Set confidence
            patterns['confidence'] = max(0.0, min(1.0, patterns.get('confidence', 0.7)))
            
            logger.info(f"✅ Validated patterns: {patterns['intent_type']} with {len(patterns['keywords'])} keywords")
            return patterns
            
        except Exception as e:
            logger.error(f"Pattern validation error: {e}")
            return None
    
    async def _store_intent_patterns(self, tenant_id: int, document_id: int, patterns: Dict):
        """Store extracted patterns in database"""
        try:
            # Remove existing patterns for this document
            self.db.query(TenantIntentPattern).filter(
                TenantIntentPattern.document_id == document_id
            ).delete()
            
            # Create new pattern record
            pattern_record = TenantIntentPattern(
                tenant_id=tenant_id,
                document_id=document_id,
                intent_type=patterns['intent_type'],
                pattern_data=patterns,
                confidence=patterns['confidence']
            )
            
            self.db.add(pattern_record)
            self.db.commit()
            
            logger.info(f"✅ Stored intent patterns for document {document_id}: {patterns['intent_type']}")
            
        except Exception as e:
            logger.error(f"Error storing patterns: {e}")
            self.db.rollback()
    
    def get_tenant_intent_patterns(self, tenant_id: int) -> List[Dict]:
        """Get all active intent patterns for a tenant"""
        try:
            patterns = self.db.query(TenantIntentPattern).filter(
                TenantIntentPattern.tenant_id == tenant_id,
                TenantIntentPattern.is_active == True
            ).all()
            
            return [
                {
                    "id": p.id,
                    "document_id": p.document_id,
                    "intent_type": p.intent_type,
                    "patterns": p.pattern_data,
                    "confidence": p.confidence
                }
                for p in patterns
            ]
            
        except Exception as e:
            logger.error(f"Error getting tenant patterns: {e}")
            return []
    
    def delete_document_patterns(self, document_id: int):
        """Delete patterns when document is removed"""
        try:
            deleted = self.db.query(TenantIntentPattern).filter(
                TenantIntentPattern.document_id == document_id
            ).delete()
            
            self.db.commit()
            logger.info(f"🗑️ Deleted {deleted} intent patterns for document {document_id}")
            
        except Exception as e:
            logger.error(f"Error deleting patterns: {e}")
            self.db.rollback()

def get_tenant_intent_extraction_service(db: Session) -> TenantIntentExtractionService:
    """Factory function"""
    return TenantIntentExtractionService(db)