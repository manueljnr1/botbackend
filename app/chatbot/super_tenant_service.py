# app/tenants/super_tenant_service.py
"""
Super Tenant Service - Business logic for super tenant operations
Handles impersonation, tenant management, and admin context
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.tenants.models import Tenant
from app.chatbot.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

class SuperTenantService:
    """Service for super tenant operations and tenant management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def is_super_tenant(self, tenant_id: int) -> bool:
        """Check if tenant is designated as super tenant"""
        try:
            tenant = self.db.query(Tenant).filter(
                and_(
                    Tenant.id == tenant_id,
                    Tenant.is_super_tenant == True,
                    Tenant.is_active == True
                )
            ).first()
            
            return tenant is not None
        except Exception as e:
            logger.error(f"Error checking super tenant status: {e}")
            return False
    
    def get_super_tenant(self) -> Optional[Tenant]:
        """Get the super tenant instance"""
        try:
            return self.db.query(Tenant).filter(
                and_(
                    Tenant.is_super_tenant == True,
                    Tenant.is_active == True
                )
            ).first()
        except Exception as e:
            logger.error(f"Error getting super tenant: {e}")
            return None
    
    def can_impersonate(self, tenant_id: int) -> bool:
        """Check if tenant can impersonate other tenants"""
        try:
            tenant = self.db.query(Tenant).filter(
                and_(
                    Tenant.id == tenant_id,
                    Tenant.can_impersonate == True,
                    Tenant.is_active == True
                )
            ).first()
            
            return tenant is not None
        except Exception as e:
            logger.error(f"Error checking impersonation permission: {e}")
            return False
    
    def list_available_tenants(self, requesting_tenant_id: int) -> List[Dict[str, Any]]:
        """List tenants available for impersonation or management"""
        try:
            # Only super tenants or tenants with impersonation rights can see other tenants
            if not (self.is_super_tenant(requesting_tenant_id) or self.can_impersonate(requesting_tenant_id)):
                return []
            
            tenants = self.db.query(Tenant).filter(
                and_(
                    Tenant.is_active == True,
                    Tenant.id != requesting_tenant_id  # Don't show self
                )
            ).order_by(Tenant.business_name).all()
            
            return [
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "business_name": tenant.business_name,
                    "email": tenant.email,
                    "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                    "is_super_tenant": getattr(tenant, 'is_super_tenant', False),
                    "integrations": {
                        "discord": tenant.discord_enabled,
                        "slack": tenant.slack_enabled,
                        "telegram": getattr(tenant, 'telegram_enabled', False)
                    }
                }
                for tenant in tenants
            ]
        except Exception as e:
            logger.error(f"Error listing available tenants: {e}")
            return []
    
    def start_impersonation(self, super_tenant_id: int, target_tenant_id: int) -> Dict[str, Any]:
        """Start impersonating another tenant"""
        try:
            # Validate permissions
            if not self.can_impersonate(super_tenant_id):
                return {
                    "success": False,
                    "error": "Impersonation not allowed for this tenant"
                }
            
            # Get super tenant
            super_tenant = self.db.query(Tenant).filter(Tenant.id == super_tenant_id).first()
            if not super_tenant:
                return {
                    "success": False,
                    "error": "Super tenant not found"
                }
            
            # Get target tenant
            target_tenant = self.db.query(Tenant).filter(
                and_(
                    Tenant.id == target_tenant_id,
                    Tenant.is_active == True
                )
            ).first()
            
            if not target_tenant:
                return {
                    "success": False,
                    "error": "Target tenant not found or inactive"
                }
            
            # Set impersonation
            super_tenant.impersonating_tenant_id = target_tenant_id
            self.db.commit()
            
            logger.info(f"🎭 Super tenant {super_tenant_id} started impersonating tenant {target_tenant_id}")
            
            return {
                "success": True,
                "message": f"Now impersonating {target_tenant.business_name}",
                "target_tenant": {
                    "id": target_tenant.id,
                    "name": target_tenant.name,
                    "business_name": target_tenant.business_name,
                    "email": target_tenant.email
                }
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error starting impersonation: {e}")
            return {
                "success": False,
                "error": f"Failed to start impersonation: {str(e)}"
            }
    
    def stop_impersonation(self, super_tenant_id: int) -> Dict[str, Any]:
        """Stop impersonating and return to original tenant"""
        try:
            super_tenant = self.db.query(Tenant).filter(Tenant.id == super_tenant_id).first()
            if not super_tenant:
                return {
                    "success": False,
                    "error": "Super tenant not found"
                }
            
            if not super_tenant.impersonating_tenant_id:
                return {
                    "success": False,
                    "error": "Not currently impersonating any tenant"
                }
            
            # Clear impersonation
            impersonated_id = super_tenant.impersonating_tenant_id
            super_tenant.impersonating_tenant_id = None
            self.db.commit()
            
            logger.info(f"🎭 Super tenant {super_tenant_id} stopped impersonating tenant {impersonated_id}")
            
            return {
                "success": True,
                "message": f"Stopped impersonating, returned to {super_tenant.business_name}"
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error stopping impersonation: {e}")
            return {
                "success": False,
                "error": f"Failed to stop impersonation: {str(e)}"
            }
    
    def get_impersonation_status(self, tenant_id: int) -> Dict[str, Any]:
        """Get current impersonation status"""
        try:
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return {
                    "success": False,
                    "error": "Tenant not found"
                }
            
            status = {
                "success": True,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "business_name": tenant.business_name,
                "is_super_tenant": getattr(tenant, 'is_super_tenant', False),
                "can_impersonate": getattr(tenant, 'can_impersonate', False),
                "currently_impersonating": None
            }
            
            if tenant.impersonating_tenant_id:
                impersonated_tenant = self.db.query(Tenant).filter(
                    Tenant.id == tenant.impersonating_tenant_id
                ).first()
                
                if impersonated_tenant:
                    status["currently_impersonating"] = {
                        "id": impersonated_tenant.id,
                        "name": impersonated_tenant.name,
                        "business_name": impersonated_tenant.business_name,
                        "email": impersonated_tenant.email
                    }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting impersonation status: {e}")
            return {
                "success": False,
                "error": f"Failed to get impersonation status: {str(e)}"
            }
    
    def get_tenant_overview(self, tenant_id: int) -> Dict[str, Any]:
        """Get comprehensive overview of a tenant"""
        try:
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return {
                    "success": False,
                    "error": "Tenant not found"
                }
            
            # Get basic stats
            from app.knowledge_base.models import FAQ, KnowledgeBase
            from datetime import datetime, timedelta
            
            faq_count = self.db.query(FAQ).filter(FAQ.tenant_id == tenant_id).count()
            kb_count = self.db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).count()
            
            # Get recent activity (last 30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_sessions = self.db.query(ChatSession).filter(
                and_(
                    ChatSession.tenant_id == tenant_id,
                    ChatSession.created_at >= thirty_days_ago
                )
            ).count()
            
            return {
                "success": True,
                "tenant": {
                    "id": tenant.id,
                    "name": tenant.name,
                    "business_name": tenant.business_name,
                    "email": tenant.email,
                    "is_active": tenant.is_active,
                    "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                    "system_prompt_configured": bool(tenant.system_prompt),
                    "branding_configured": bool(tenant.logo_image_url or tenant.primary_color != "#007bff")
                },
                "content_stats": {
                    "faqs": faq_count,
                    "knowledge_bases": kb_count
                },
                "activity_stats": {
                    "recent_sessions_30_days": recent_sessions
                },
                "integrations": {
                    "discord": {
                        "enabled": tenant.discord_enabled,
                        "configured": bool(tenant.discord_bot_token)
                    },
                    "slack": {
                        "enabled": tenant.slack_enabled,
                        "configured": bool(tenant.slack_bot_token)
                    },
                    "telegram": {
                        "enabled": getattr(tenant, 'telegram_enabled', False),
                        "configured": bool(getattr(tenant, 'telegram_bot_token', None))
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting tenant overview: {e}")
            return {
                "success": False,
                "error": f"Failed to get tenant overview: {str(e)}"
            }
    
    def get_admin_context_info(self, authenticated_tenant_id: int, is_super_tenant_context: bool = False) -> Dict[str, Any]:
        """
        Get admin context information for frontend
        Determines what admin capabilities are available
        """
        try:
            tenant = self.db.query(Tenant).filter(Tenant.id == authenticated_tenant_id).first()
            if not tenant:
                return {
                    "success": False,
                    "admin_mode_available": False,
                    "error": "Tenant not found"
                }
            
            # Admin mode is available when:
            # 1. Tenant is authenticated AND
            # 2. They're using the super tenant's chatbot (is_super_tenant_context=True)
            admin_available = tenant.is_active and is_super_tenant_context
            
            return {
                "success": True,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "business_name": tenant.business_name,
                "admin_mode_available": admin_available,
                "is_authenticated": True,
                "is_super_tenant_context": is_super_tenant_context,
                "capabilities": {
                    "faq_management": admin_available,
                    "settings_update": admin_available,
                    "analytics_view": admin_available,
                    "branding_update": admin_available,
                    "integration_setup": admin_available,
                    "knowledge_base_view": admin_available
                },
                "context_info": {
                    "explanation": "Admin features are available when you're logged in and using the super tenant's chatbot",
                    "current_context": "super_tenant_chat" if is_super_tenant_context else "regular_chat"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting admin context info: {e}")
            return {
                "success": False,
                "admin_mode_available": False,
                "error": f"Failed to get admin context: {str(e)}"
            }

def get_super_tenant_service(db: Session) -> SuperTenantService:
    """Factory function to create SuperTenantService"""
    return SuperTenantService(db)