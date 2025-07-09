from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.database import get_db
from app.chatbot.super_tenant_service import SuperTenantService
from app.tenants.router import get_tenant_from_api_key

router = APIRouter()

class ImpersonationRequest(BaseModel):
    target_tenant_id: int

class SuperTenantResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any] = {}

@router.get("/status")
async def get_super_tenant_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get super tenant status and current impersonation"""
    tenant = get_tenant_from_api_key(api_key, db)
    super_service = SuperTenantService(db)
    
    status = super_service.get_impersonation_status(tenant.id)
    
    return {
        "success": True,
        "status": status
    }

@router.get("/available-tenants")
async def list_available_tenants(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """List all tenants available for impersonation"""
    tenant = get_tenant_from_api_key(api_key, db)
    super_service = SuperTenantService(db)
    
    if not super_service.can_impersonate(tenant.id):
        raise HTTPException(status_code=403, detail="Impersonation not allowed")
    
    tenants = super_service.list_available_tenants(tenant.id)
    
    return {
        "success": True,
        "tenants": tenants,
        "count": len(tenants)
    }

@router.post("/impersonate")
async def start_impersonation(
    request: ImpersonationRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Start impersonating another tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    super_service = SuperTenantService(db)
    
    result = super_service.start_impersonation(tenant.id, request.target_tenant_id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.post("/stop-impersonation")
async def stop_impersonation(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Stop impersonating and return to original tenant"""
    tenant = get_tenant_from_api_key(api_key, db)
    super_service = SuperTenantService(db)
    
    result = super_service.stop_impersonation(tenant.id)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result
