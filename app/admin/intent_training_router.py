import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from app.database import get_db
from app.auth.router import get_admin_user
from app.knowledge_base.models import TenantIntentPattern, CentralIntentModel
from app.chatbot.intent_extraction_service import get_tenant_intent_extraction_service
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

class TrainingRequest(BaseModel):
    model_version: str
    description: str = "Central intent model training"

class TrainingResponse(BaseModel):
    success: bool
    message: str
    model_version: str
    patterns_compiled: int
    training_completed_at: str

@router.post("/train-central-model", response_model=TrainingResponse)
async def train_central_intent_model(
    training_request: TrainingRequest,
    db: Session = Depends(get_db),
    admin_user = Depends(get_admin_user)
):
    """Train central intent model using all tenant patterns"""
    try:
        # Compile patterns from all tenants
        all_patterns = db.query(TenantIntentPattern).filter(
            TenantIntentPattern.is_active == True
        ).all()
        
        if not all_patterns:
            raise HTTPException(status_code=400, detail="No tenant patterns available for training")
        
        # Compile training data
        compiled_data = {
            "troubleshooting": [],
            "sales": [],
            "enquiry": [],
            "faq": [],
            "metadata": {
                "total_patterns": len(all_patterns),
                "tenant_count": len(set(p.tenant_id for p in all_patterns)),
                "compiled_at": datetime.utcnow().isoformat()
            }
        }
        
        for pattern in all_patterns:
            intent_type = pattern.intent_type
            if intent_type in compiled_data:
                compiled_data[intent_type].append({
                    "tenant_id": pattern.tenant_id,
                    "document_id": pattern.document_id,
                    "patterns": pattern.pattern_data,
                    "confidence": pattern.confidence
                })
        
        # Deactivate old models
        db.query(CentralIntentModel).update({"is_active": False})
        
        # Create new central model
        central_model = CentralIntentModel(
            model_version=training_request.model_version,
            training_data=compiled_data,
            trained_by_admin_id=admin_user.id,
            is_active=True
        )
        
        db.add(central_model)
        db.commit()
        
        logger.info(f"🎯 Central intent model trained: {training_request.model_version} with {len(all_patterns)} patterns")
        
        return TrainingResponse(
            success=True,
            message=f"Central model trained successfully",
            model_version=training_request.model_version,
            patterns_compiled=len(all_patterns),
            training_completed_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Central training error: {e}")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@router.get("/tenant-patterns/{tenant_id}")
async def get_tenant_patterns(
    tenant_id: int,
    db: Session = Depends(get_db),
    admin_user = Depends(get_admin_user)
):
    """Get intent patterns for specific tenant"""
    patterns = db.query(TenantIntentPattern).filter(
        TenantIntentPattern.tenant_id == tenant_id,
        TenantIntentPattern.is_active == True
    ).all()
    
    return {
        "tenant_id": tenant_id,
        "pattern_count": len(patterns),
        "patterns": [
            {
                "id": p.id,
                "intent_type": p.intent_type,
                "document_id": p.document_id,
                "confidence": p.confidence,
                "pattern_data": p.pattern_data,
                "extracted_at": p.extracted_at.isoformat()
            }
            for p in patterns
        ]
    }

@router.get("/central-model/status")
async def get_central_model_status(
    db: Session = Depends(get_db),
    admin_user = Depends(get_admin_user)
):
    """Get current central model status"""
    active_model = db.query(CentralIntentModel).filter(
        CentralIntentModel.is_active == True
    ).order_by(CentralIntentModel.trained_at.desc()).first()
    
    if not active_model:
        return {
            "has_active_model": False,
            "message": "No central model trained yet"
        }
    
    return {
        "has_active_model": True,
        "model_version": active_model.model_version,
        "trained_at": active_model.trained_at.isoformat(),
        "pattern_count": active_model.training_data.get("metadata", {}).get("total_patterns", 0),
        "tenant_count": active_model.training_data.get("metadata", {}).get("tenant_count", 0)
    }

@router.post("/extract-document-intents/{kb_id}")
async def manually_extract_document_intents(
    kb_id: int,
    db: Session = Depends(get_db),
    admin_user = Depends(get_admin_user)
):
    """Manually trigger intent extraction for a document"""
    extraction_service = get_tenant_intent_extraction_service(db)
    result = await extraction_service.extract_intents_from_document(kb_id)
    
    if result["success"]:
        return {
            "success": True,
            "message": f"Intents extracted for document {kb_id}",
            "patterns": result.get("patterns")
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))