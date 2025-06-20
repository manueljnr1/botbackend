from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.tenants.models import Tenant

def get_tenant_branding(tenant_id: int, db: Session) -> Dict[str, Any]:
    """Get complete branding configuration for a tenant"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        return get_default_branding()
    
    return {
        "primary_color": tenant.primary_color or "#007bff",
        "secondary_color": tenant.secondary_color or "#f0f4ff",
        "text_color": tenant.text_color or "#222222",
        "background_color": tenant.background_color or "#ffffff",
        "user_bubble_color": tenant.user_bubble_color or "#007bff",
        "bot_bubble_color": tenant.bot_bubble_color or "#f0f4ff",
        "border_color": tenant.border_color or "#e0e0e0",
        "logo_image": tenant.logo_image_url,
        "logo_text": tenant.logo_text or (tenant.business_name or tenant.name)[:2].upper(),
        "border_radius": tenant.border_radius or "12px",
        "widget_position": tenant.widget_position or "bottom-right",
        "font_family": tenant.font_family or "Inter, sans-serif",
        "custom_css": tenant.custom_css,
        "branding_version": tenant.branding_version or 1,
        "last_updated": tenant.branding_updated_at.isoformat() if tenant.branding_updated_at else None
    }

def get_default_branding() -> Dict[str, Any]:
    """Get default branding configuration"""
    return {
        "primary_color": "#007bff",
        "secondary_color": "#f0f4ff",
        "text_color": "#222222",
        "background_color": "#ffffff",
        "user_bubble_color": "#007bff",
        "bot_bubble_color": "#f0f4ff",
        "border_color": "#e0e0e0",
        "logo_image": None,
        "logo_text": "AI",
        "border_radius": "12px",
        "widget_position": "bottom-right",
        "font_family": "Inter, sans-serif",
        "custom_css": None,
        "branding_version": 1,
        "last_updated": None
    }

def update_branding_timestamp(tenant: Tenant, db: Session) -> None:
    """Update branding timestamp and version"""
    tenant.branding_updated_at = datetime.utcnow()
    tenant.branding_version = (tenant.branding_version or 0) + 1
    db.commit()