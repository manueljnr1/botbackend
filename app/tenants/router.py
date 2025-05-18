from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import uuid

from app.database import get_db
from app.tenants.models import Tenant
from app.auth.models import User # For admin-only endpoints
from app.auth.router import get_current_user, get_admin_user # For admin-only endpoints

# MODIFIED HELPER FUNCTION
def get_tenant_from_api_key(api_key: str, db: Session) -> Tenant:
    """
    Retrieve an active tenant using the provided API key.
    """
    # Added Tenant.is_active == True to the filter
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key, Tenant.is_active == True).first()
    if not tenant:
        # Changed status_code to status.HTTP_403_FORBIDDEN for consistency
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or inactive tenant")
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
    system_prompt: Optional[str] = None

# MODIFIED TenantOut Pydantic model
class TenantOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None # Explicitly set default to None
    api_key: str
    is_active: bool
    system_prompt: Optional[str] = None  # Added system_prompt field

    class Config:
        from_attributes = True

# NEW ENDPOINT
@router.get("/details/by-apikey", response_model=TenantOut)
async def get_tenant_details_by_api_key(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Get current tenant's details (including name, id, and system_prompt) using their API key.
    This is useful for the frontend to configure itself for the active tenant.
    """
    tenant = get_tenant_from_api_key(api_key, db) # Uses the modified helper
    return tenant

# Existing Endpoints (kept as they were in your provided file)
@router.post("/", response_model=TenantOut)
async def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Create a new tenant (admin only)
    """
    db_tenant = db.query(Tenant).filter(Tenant.name == tenant.name).first()
    if db_tenant:
        raise HTTPException(status_code=400, detail="Tenant name already registered")
    
    new_tenant = Tenant(
        name=tenant.name,
        description=tenant.description,
        system_prompt=tenant.system_prompt,
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
    
    if not current_user.is_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this tenant")
    
    return tenant

@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(tenant_id: int, tenant_update: TenantUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    """
    Update a tenant's details, including system prompt (admin only or authorized user)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Authorization: Allow admin to update any tenant, or a user to update their own tenant.
    # This part of your original code had a slight logic issue for non-admin updates, corrected here.
    if not current_user.is_admin and (current_user.tenant_id is None or current_user.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this tenant")

    update_data = tenant_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    
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
    
    tenant.is_active = False
    db.commit()
    return {"message": "Tenant deactivated successfully"}

@router.put("/{tenant_id}/prompt", response_model=TenantOut) # Changed response_model to TenantOut for consistency
async def update_tenant_prompt(
    tenant_id: int,
    prompt_data: dict, # Expects {"system_prompt": "new prompt"}
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Update a tenant's system prompt using API key.
    Returns the updated tenant details.
    """
    tenant = get_tenant_from_api_key(api_key, db)
    
    if tenant.id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key does not match tenant ID")
    
    new_system_prompt = prompt_data.get("system_prompt")
    if new_system_prompt is None: # Check if system_prompt key exists
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system_prompt field is required in request body")

    tenant.system_prompt = new_system_prompt
    db.commit()
    db.refresh(tenant)
    return tenant
