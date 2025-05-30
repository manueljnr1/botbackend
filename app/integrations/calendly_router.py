# app/integrations/calendly_router.py

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.integrations.calendly_service import CalendlyManager
from app.integrations.booking_models import BookingRequest

# Import ChatResponse from chatbot router
from app.chatbot.router import ChatResponse, SimpleChatRequest

# Import pricing dependencies
from app.pricing.integration_helpers import check_message_limit_dependency, track_message_sent

logger = logging.getLogger(__name__)

router = APIRouter()

class CalendlySetupRequest(BaseModel):
    access_token: str

class BookingResponse(BaseModel):
    success: bool
    booking_url: Optional[str] = None
    message: str

class CalendlyStatusResponse(BaseModel):
    calendly_enabled: bool
    calendar_booking_enabled: bool
    has_access_token: bool
    default_event_type: bool

class BookingToggleRequest(BaseModel):
    enabled: bool

class BookingMessageRequest(BaseModel):
    message: str

@router.post("/setup")
async def setup_calendly_integration(
    request: CalendlySetupRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Setup Calendly integration for a tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        calendar_manager = CalendlyManager(db)
        success = calendar_manager.setup_tenant_calendly(tenant.id, request.access_token)
        
        if success:
            return {"success": True, "message": "Calendly integration setup successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to setup Calendly integration")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting up Calendly: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/status", response_model=CalendlyStatusResponse)
async def get_calendly_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get Calendly integration status for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        return CalendlyStatusResponse(
            calendly_enabled=tenant.calendly_enabled or False,
            calendar_booking_enabled=tenant.calendar_booking_enabled or False,
            has_access_token=bool(tenant.calendly_access_token),
            default_event_type=bool(getattr(tenant, 'calendly_default_event_type', None))
        )
        
    except Exception as e:
        logger.error(f"Error getting Calendly status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/toggle")
async def toggle_calendar_booking(
    request: BookingToggleRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Enable/disable calendar booking for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        tenant.calendar_booking_enabled = request.enabled
        db.commit()
        
        return {
            "success": True,
            "calendar_booking_enabled": request.enabled,
            "message": f"Calendar booking {'enabled' if request.enabled else 'disabled'}"
        }
        
    except Exception as e:
        logger.error(f"Error toggling calendar booking: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/bookings")
async def get_booking_requests(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get booking requests for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        bookings = db.query(BookingRequest).filter(
            BookingRequest.tenant_id == tenant.id
        ).order_by(BookingRequest.created_at.desc()).limit(50).all()
        
        return {
            "success": True,
            "bookings": [
                {
                    "id": booking.id,
                    "user_identifier": booking.user_identifier,
                    "user_email": booking.user_email,
                    "user_name": booking.user_name,
                    "status": booking.status,
                    "booking_url": booking.booking_url,
                    "created_at": booking.created_at.isoformat() if booking.created_at else None,
                    "booking_message": booking.booking_message
                }
                for booking in bookings
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting booking requests: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/message")
async def update_booking_message(
    request: BookingMessageRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update the calendar booking message for tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        tenant.calendar_booking_message = request.message
        db.commit()
        
        return {
            "success": True,
            "message": "Booking message updated successfully",
            "new_message": request.message
        }
        
    except Exception as e:
        logger.error(f"Error updating booking message: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")