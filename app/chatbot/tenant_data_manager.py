# app/chatbot/tenant_data_manager.py
"""
Secure Tenant Data Manager for Super Tenant Admin Operations
Provides bulletproof tenant isolation and secure CRUD operations
"""

import logging
from typing import Dict, Any, Optional, List, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from app.tenants.models import Tenant
from app.knowledge_base.models import FAQ, KnowledgeBase
from app.chatbot.models import ChatSession, ChatMessage
from app.chatbot.admin_intent_parser import AdminActionType, ParsedIntent

logger = logging.getLogger(__name__)

class TenantSecurityError(Exception):
    """Raised when tenant security violation is detected"""
    pass

class TenantDataManager:
    """
    Secure manager for tenant data operations with bulletproof isolation
    CRITICAL: All operations MUST validate tenant ownership
    """
    
    def __init__(self, db: Session, authenticated_tenant_id: int):
        """
        Initialize with authenticated tenant ID - this is the SECURITY BOUNDARY
        
        Args:
            db: Database session
            authenticated_tenant_id: The ID of the tenant making the request
        """
        self.db = db
        self.tenant_id = authenticated_tenant_id
        
        # Validate tenant exists and is active
        self.tenant = self._get_and_validate_tenant()
        if not self.tenant:
            raise TenantSecurityError(f"Invalid tenant ID: {authenticated_tenant_id}")
        
        logger.info(f"🔒 TenantDataManager initialized for tenant: {self.tenant.name} (ID: {self.tenant_id})")
    
    def _get_and_validate_tenant(self) -> Tenant:
        """Validate tenant exists and is active"""
        tenant = self.db.query(Tenant).filter(
            and_(
                Tenant.id == self.tenant_id,
                Tenant.is_active == True
            )
        ).first()
        
        if not tenant:
            logger.error(f"🚨 SECURITY: Invalid tenant access attempt: {self.tenant_id}")
            raise TenantSecurityError("Tenant not found or inactive")
        
        return tenant
    
    def _validate_tenant_ownership(self, resource_tenant_id: int):
        """
        CRITICAL SECURITY: Validate resource belongs to authenticated tenant
        """
        if resource_tenant_id != self.tenant_id:
            logger.error(
                f"🚨 SECURITY VIOLATION: Tenant {self.tenant_id} attempted to access "
                f"resource belonging to tenant {resource_tenant_id}"
            )
            raise TenantSecurityError("Access denied: Resource belongs to different tenant")
    
    # =================== FAQ OPERATIONS ===================
    
    def get_faqs(self, limit: int = 100) -> List[FAQ]:
        """Get all FAQs for authenticated tenant"""
        faqs = self.db.query(FAQ).filter(
            FAQ.tenant_id == self.tenant_id
        ).limit(limit).all()
        
        logger.info(f"📋 Retrieved {len(faqs)} FAQs for tenant {self.tenant_id}")
        return faqs
    
    def get_faq_by_id(self, faq_id: int) -> Optional[FAQ]:
        """Get specific FAQ with security validation"""
        faq = self.db.query(FAQ).filter(
            and_(
                FAQ.id == faq_id,
                FAQ.tenant_id == self.tenant_id  # SECURITY: Enforce tenant ownership
            )
        ).first()
        
        if faq:
            logger.info(f"📋 Retrieved FAQ #{faq_id} for tenant {self.tenant_id}")
        else:
            logger.warning(f"📋 FAQ #{faq_id} not found for tenant {self.tenant_id}")
        
        return faq
    
    def create_faq(self, question: str, answer: str) -> FAQ:
        """Create new FAQ for authenticated tenant"""
        try:
            faq = FAQ(
                tenant_id=self.tenant_id,  # SECURITY: Always use authenticated tenant
                question=question.strip(),
                answer=answer.strip()
            )
            
            self.db.add(faq)
            self.db.commit()
            self.db.refresh(faq)
            
            logger.info(f"✅ Created FAQ #{faq.id} for tenant {self.tenant_id}")
            return faq
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to create FAQ for tenant {self.tenant_id}: {e}")
            raise
    
    def update_faq(self, faq_id: int, question: str = None, answer: str = None) -> Optional[FAQ]:
        """Update FAQ with security validation"""
        try:
            faq = self.get_faq_by_id(faq_id)  # This already validates tenant ownership
            if not faq:
                return None
            
            if question is not None:
                faq.question = question.strip()
            if answer is not None:
                faq.answer = answer.strip()
            
            self.db.commit()
            self.db.refresh(faq)
            
            logger.info(f"✅ Updated FAQ #{faq_id} for tenant {self.tenant_id}")
            return faq
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to update FAQ #{faq_id} for tenant {self.tenant_id}: {e}")
            raise
    
    def delete_faq(self, faq_id: int) -> bool:
        """Delete FAQ with security validation"""
        try:
            faq = self.get_faq_by_id(faq_id)  # This already validates tenant ownership
            if not faq:
                return False
            
            self.db.delete(faq)
            self.db.commit()
            
            logger.info(f"✅ Deleted FAQ #{faq_id} for tenant {self.tenant_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to delete FAQ #{faq_id} for tenant {self.tenant_id}: {e}")
            raise
    
    # =================== TENANT SETTINGS OPERATIONS ===================
    
    def get_tenant_settings(self) -> Dict[str, Any]:
        """Get tenant settings and configuration"""
        return {
            "tenant_id": self.tenant.id,
            "name": self.tenant.name,
            "business_name": self.tenant.business_name,
            "email": self.tenant.email,
            "system_prompt": self.tenant.system_prompt,
            "branding": {
                "primary_color": self.tenant.primary_color,
                "secondary_color": self.tenant.secondary_color,
                "text_color": self.tenant.text_color,
                "background_color": self.tenant.background_color,
                "user_bubble_color": self.tenant.user_bubble_color,
                "bot_bubble_color": self.tenant.bot_bubble_color,
                "border_color": self.tenant.border_color,
                "logo_image_url": self.tenant.logo_image_url,
                "logo_text": self.tenant.logo_text,
                "border_radius": self.tenant.border_radius,
                "widget_position": self.tenant.widget_position,
                "font_family": self.tenant.font_family
            },
            "email_config": {
                "feedback_email": self.tenant.feedback_email,
                "enable_feedback_system": getattr(self.tenant, 'enable_feedback_system', True),
                "feedback_notification_enabled": getattr(self.tenant, 'feedback_notification_enabled', True)
            },
            "integrations": {
                "discord_enabled": self.tenant.discord_enabled,
                "slack_enabled": self.tenant.slack_enabled,
                "telegram_enabled": getattr(self.tenant, 'telegram_enabled', False)
            }
        }
    
    def update_system_prompt(self, system_prompt: str) -> bool:
        """Update tenant's system prompt with security validation"""
        try:
            from app.chatbot.security import validate_and_sanitize_tenant_prompt
            
            # Security validation
            sanitized_prompt, is_valid, issues = validate_and_sanitize_tenant_prompt(system_prompt)
            
            if not is_valid:
                logger.warning(f"🔒 Prompt security validation failed for tenant {self.tenant_id}: {issues}")
                return False
            
            self.tenant.system_prompt = sanitized_prompt
            self.tenant.system_prompt_validated = True
            self.tenant.system_prompt_updated_at = datetime.utcnow()
            
            self.db.commit()
            
            logger.info(f"✅ Updated system prompt for tenant {self.tenant_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to update system prompt for tenant {self.tenant_id}: {e}")
            return False
    
    def update_branding(self, branding_data: Dict[str, Any]) -> bool:
        """Update tenant branding with validation"""
        try:
            # Valid branding fields
            valid_fields = {
                'primary_color', 'secondary_color', 'text_color', 'background_color',
                'user_bubble_color', 'bot_bubble_color', 'border_color',
                'logo_text', 'border_radius', 'widget_position', 'font_family'
            }
            
            updated_fields = []
            for field, value in branding_data.items():
                if field in valid_fields and hasattr(self.tenant, field):
                    setattr(self.tenant, field, value)
                    updated_fields.append(field)
            
            if updated_fields:
                self.tenant.branding_updated_at = datetime.utcnow()
                self.db.commit()
                
                logger.info(f"✅ Updated branding for tenant {self.tenant_id}: {updated_fields}")
                return True
            else:
                logger.warning(f"⚠️ No valid branding fields provided for tenant {self.tenant_id}")
                return False
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to update branding for tenant {self.tenant_id}: {e}")
            return False
    
    def update_email_config(self, email_config: Dict[str, Any]) -> bool:
        """Update tenant email configuration"""
        try:
            valid_fields = {
                'feedback_email', 'enable_feedback_system', 'feedback_notification_enabled'
            }
            
            updated_fields = []
            for field, value in email_config.items():
                if field in valid_fields and hasattr(self.tenant, field):
                    setattr(self.tenant, field, value)
                    updated_fields.append(field)
            
            if updated_fields:
                self.db.commit()
                logger.info(f"✅ Updated email config for tenant {self.tenant_id}: {updated_fields}")
                return True
            else:
                logger.warning(f"⚠️ No valid email config fields provided for tenant {self.tenant_id}")
                return False
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Failed to update email config for tenant {self.tenant_id}: {e}")
            return False
    
    # =================== ANALYTICS OPERATIONS ===================
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get analytics summary for tenant"""
        try:
            # Count FAQs
            faq_count = self.db.query(FAQ).filter(FAQ.tenant_id == self.tenant_id).count()
            
            # Count Knowledge Bases
            kb_count = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == self.tenant_id
            ).count()
            
            # Count Chat Sessions (last 30 days)
            from datetime import timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            recent_sessions = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatSession.created_at >= thirty_days_ago
                )
            ).count()
            
            # Count total messages (last 30 days)
            recent_messages = self.db.query(ChatMessage).join(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == self.tenant_id,
                    ChatMessage.created_at >= thirty_days_ago
                )
            ).count()
            
            return {
                "tenant_id": self.tenant_id,
                "tenant_name": self.tenant.name,
                "content_stats": {
                    "faqs": faq_count,
                    "knowledge_bases": kb_count
                },
                "usage_stats_30_days": {
                    "chat_sessions": recent_sessions,
                    "total_messages": recent_messages
                },
                "integrations": {
                    "discord": self.tenant.discord_enabled,
                    "slack": self.tenant.slack_enabled,
                    "telegram": getattr(self.tenant, 'telegram_enabled', False)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get analytics for tenant {self.tenant_id}: {e}")
            return {"error": str(e)}
    
    # =================== KNOWLEDGE BASE OPERATIONS ===================
    
    def get_knowledge_bases(self) -> List[Dict[str, Any]]:
        """Get knowledge bases for tenant"""
        try:
            kbs = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.tenant_id == self.tenant_id
            ).all()
            
            return [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "document_type": kb.document_type.value,
                    "processing_status": kb.processing_status.value,
                    "created_at": kb.created_at.isoformat() if kb.created_at else None
                }
                for kb in kbs
            ]
            
        except Exception as e:
            logger.error(f"❌ Failed to get knowledge bases for tenant {self.tenant_id}: {e}")
            return []
    
    # =================== INTEGRATION STATUS ===================
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get integration status for tenant"""
        return {
            "discord": {
                "enabled": self.tenant.discord_enabled,
                "configured": bool(self.tenant.discord_bot_token)
            },
            "slack": {
                "enabled": self.tenant.slack_enabled,
                "configured": bool(self.tenant.slack_bot_token)
            },
            "telegram": {
                "enabled": getattr(self.tenant, 'telegram_enabled', False),
                "configured": bool(getattr(self.tenant, 'telegram_bot_token', None))
            }
        }
    
    # =================== AUDIT LOGGING ===================
    
    def log_admin_action(self, action: str, details: Dict[str, Any] = None):
        """Log admin action for audit trail"""
        try:
            # This could be expanded to include a dedicated audit log table
            logger.info(
                f"🔍 ADMIN ACTION: Tenant {self.tenant_id} ({self.tenant.name}) "
                f"performed {action}. Details: {details or {}}"
            )
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")

def get_tenant_data_manager(db: Session, authenticated_tenant_id: int) -> TenantDataManager:
    """Factory function to create TenantDataManager with security validation"""
    return TenantDataManager(db, authenticated_tenant_id)