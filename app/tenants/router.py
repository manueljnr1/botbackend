from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import uuid

from app.database import get_db
from app.tenants.models import Tenant
from app.auth.models import User
from app.auth.router import get_current_user, get_admin_user

def get_tenant_from_api_key(api_key: str, db: Session) -> Tenant:
    """
    Retrieve a tenant using the provided API key.
    """
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return tenant

router = APIRouter()

# Pydantic models
class TenantCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    system_prompt: Optional[str] = None  # Add this field

class TenantOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    api_key: str
    is_active: bool
    
    class Config:
        from_attributes = True  # For SQLAlchemy models

# Endpoints
@router.post("/", response_model=TenantOut)
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Create a new tenant (admin only)
    """
    # Check if tenant exists
    db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail="Tenant name already registered")
    
    # Create tenant with unique API key
    new_tenant = Tenant(
        name=tenant.name,
        description=tenant.description,
        system_prompt=tenant.system_prompt,  # Include system prompt
        api_key=f"sk-{str(uuid.uuid4()).replace('-', '')}"
    )
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant

@router.get("/", response_model=List[TenantOut])
async def list_tenants(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    List all tenants (admin only)
    """
    return db.query(Tenant).all()

@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(tenant_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get a specific tenant
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Users can only view their own tenant unless they're admin
    if not current_user.is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this tenant")
    
    return tenant

@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(tenant_id: int, tenant_update: TenantUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Update a tenant's system prompt
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if tenant_update.name is not None:
        tenant.name = tenant_update.name
    if tenant_update.description is not None:
        tenant.description = tenant_update.description
    if tenant_update.is_active is not None:
        tenant.is_active = tenant_update.is_active
    if tenant_update.system_prompt is not None:
        tenant.system_prompt = tenant_update.system_prompt  # Update system prompt
    if not current_user.is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this tenant")
    
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    

    tenant.system_prompt = tenant_update.system_prompt
    db.commit()
    db.refresh(tenant)
    return tenant

@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Deactivate a tenant (admin only)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Soft delete
    tenant.is_active = False
    db.commit()
    return {"message": "Tenant deactivated successfully"}

@router.put("/{tenant_id}/prompt")
async def update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Update a tenant's system prompt using API key
    """
    # Get tenant from API key
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Make sure the tenant ID matches
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this tenant")
    
    # Update the system prompt
    tenant.system_prompt = prompt_data.get("system_prompt")
    db.commit()
    
    return {"message": "System prompt updated successfully"}