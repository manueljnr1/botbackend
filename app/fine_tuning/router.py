# app/fine_tuning/router.py
"""
Fine-Tuning Control Endpoints
Tenant controls + Admin oversight for autonomous learning system
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, d
from pydantic import BaseModel
from datetime import datetime, date, time, timedelta

from app.database import get_db
from app.tenants.router import get_tenant_from_api_key
from app.auth.router import get_admin_user
from app.tenants.models import Tenant
from app.fine_tuning.trainer import get_background_trainer
from app.fine_tuning.models import LearningPattern, TrainingMetrics, AutoImprovement

logger = logging.getLogger(__name__)
router = APIRouter()

# Request Models
class FineTuningToggleRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = None

class TenantFineTuningControlRequest(BaseModel):
    tenant_id: int
    enabled: bool
    reason: Optional[str] = None

# Response Models  
class FineTuningStatusResponse(BaseModel):
    success: bool
    tenant_id: int
    fine_tuning_enabled: bool
    total_patterns_learned: int
    total_improvements_made: int
    last_training_cycle: Optional[str] = None
    training_status: str

class AdminFineTuningOverview(BaseModel):
    success: bool
    global_training_active: bool
    total_tenants: int
    tenants_with_fine_tuning: int
    total_patterns_learned: int
    total_improvements_made: int

# ==================== TENANT ENDPOINTS ====================

@router.get("/status")
async def get_fine_tuning_status(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get fine-tuning status for authenticated tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        trainer = get_background_trainer()
        
        # Get tenant training metrics
        status_data = trainer.get_training_status(tenant.id)
        
        # Check if fine-tuning is enabled for this tenant
        fine_tuning_enabled = getattr(tenant, 'fine_tuning_enabled', True)  # Default enabled
        
        return FineTuningStatusResponse(
            success=True,
            tenant_id=tenant.id,
            fine_tuning_enabled=fine_tuning_enabled,
            total_patterns_learned=status_data.get('total_patterns_learned', 0),
            total_improvements_made=status_data.get('total_improvements_made', 0),
            last_training_cycle=status_data.get('latest_training'),
            training_status="active" if status_data.get('is_running') and fine_tuning_enabled else "disabled"
        )
        
    except Exception as e:
        logger.error(f"Error getting fine-tuning status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get training status")

@router.post("/toggle")
async def toggle_fine_tuning(
    request: FineTuningToggleRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Enable or disable fine-tuning for authenticated tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Update tenant fine-tuning preference
        # Note: You'll need to add this column to your Tenant model
        tenant.fine_tuning_enabled = request.enabled
        
        # Log the change
        action = "enabled" if request.enabled else "disabled"
        reason = f" - Reason: {request.reason}" if request.reason else ""
        logger.info(f"🔧 Tenant {tenant.id} ({tenant.name}) {action} fine-tuning{reason}")
        
        # If disabling, deactivate existing patterns
        if not request.enabled:
            db.query(LearningPattern).filter(
                LearningPattern.tenant_id == tenant.id,
                LearningPattern.is_active == True
            ).update({"is_active": False})
            
            db.query(AutoImprovement).filter(
                AutoImprovement.tenant_id == tenant.id,
                AutoImprovement.is_active == True
            ).update({"is_active": False})
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Fine-tuning {action} successfully",
            "tenant_id": tenant.id,
            "fine_tuning_enabled": request.enabled,
            "patterns_affected": "deactivated" if not request.enabled else "will_continue_learning"
        }
        
    except Exception as e:
        logger.error(f"Error toggling fine-tuning: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update fine-tuning settings")

@router.get("/metrics")
async def get_training_metrics(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    days: int = 30
):
    """Get detailed training metrics for authenticated tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get recent training metrics
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        recent_metrics = db.query(TrainingMetrics).filter(
            TrainingMetrics.tenant_id == tenant.id,
            TrainingMetrics.training_cycle >= cutoff_date
        ).order_by(TrainingMetrics.training_cycle.desc()).all()
        
        # Get active patterns by type
        pattern_stats = db.query(
            LearningPattern.pattern_type,
            db.func.count(LearningPattern.id).label('count'),
            db.func.avg(LearningPattern.confidence_score).label('avg_confidence')
        ).filter(
            LearningPattern.tenant_id == tenant.id,
            LearningPattern.is_active == True
        ).group_by(LearningPattern.pattern_type).all()
        
        # Get recent improvements
        recent_improvements = db.query(AutoImprovement).filter(
            AutoImprovement.tenant_id == tenant.id,
            AutoImprovement.applied_at >= cutoff_date,
            AutoImprovement.is_active == True
        ).count()
        
        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "metrics_period_days": days,
            "training_cycles": len(recent_metrics),
            "total_patterns_learned": sum(m.patterns_learned for m in recent_metrics),
            "total_improvements_made": sum(m.responses_improved for m in recent_metrics),
            "recent_improvements": recent_improvements,
            "pattern_breakdown": [
                {
                    "type": stat.pattern_type,
                    "count": stat.count,
                    "avg_confidence": round(float(stat.avg_confidence), 2)
                }
                for stat in pattern_stats
            ],
            "recent_training_cycles": [
                {
                    "date": m.training_cycle.isoformat(),
                    "patterns_learned": m.patterns_learned,
                    "improvements_made": m.responses_improved
                }
                for m in recent_metrics[:10]  # Last 10 cycles
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting training metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get training metrics")

@router.delete("/reset")
async def reset_learning_data(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
    confirm: bool = False
):
    """Reset all learned patterns and improvements (DANGEROUS)"""
    try:
        if not confirm:
            raise HTTPException(
                status_code=400, 
                detail="Must set confirm=true to reset learning data"
            )
        
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Deactivate all patterns and improvements
        patterns_count = db.query(LearningPattern).filter(
            LearningPattern.tenant_id == tenant.id
        ).update({"is_active": False})
        
        improvements_count = db.query(AutoImprovement).filter(
            AutoImprovement.tenant_id == tenant.id
        ).update({"is_active": False})
        
        db.commit()
        
        logger.warning(f"🚨 Tenant {tenant.id} reset learning data: {patterns_count} patterns, {improvements_count} improvements")
        
        return {
            "success": True,
            "message": "Learning data reset successfully",
            "tenant_id": tenant.id,
            "patterns_reset": patterns_count,
            "improvements_reset": improvements_count,
            "warning": "All learned patterns have been deactivated. New learning will start fresh."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting learning data: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reset learning data")

# ==================== ADMIN ENDPOINTS ====================

@router.get("/admin/overview")
async def get_admin_fine_tuning_overview(
    current_user = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get global fine-tuning overview (Admin only)"""
    try:
        trainer = get_background_trainer()
        global_status = trainer.get_training_status()
        
        # Get tenant statistics
        total_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
        
        tenants_with_fine_tuning = db.query(Tenant).filter(
            Tenant.is_active == True,
            Tenant.fine_tuning_enabled == True
        ).count()
        
        # Get global learning statistics
        total_patterns = db.query(LearningPattern).filter(
            LearningPattern.is_active == True
        ).count()
        
        total_improvements = db.query(AutoImprovement).filter(
            AutoImprovement.is_active == True
        ).count()
        
        return AdminFineTuningOverview(
            success=True,
            global_training_active=global_status.get('is_running', False),
            total_tenants=total_tenants,
            tenants_with_fine_tuning=tenants_with_fine_tuning,
            total_patterns_learned=total_patterns,
            total_improvements_made=total_improvements
        )
        
    except Exception as e:
        logger.error(f"Error getting admin overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to get admin overview")

@router.post("/admin/control-tenant")
async def admin_control_tenant_fine_tuning(
    request: TenantFineTuningControlRequest,
    current_user = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Enable/disable fine-tuning for specific tenant (Admin only)"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == request.tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Update tenant setting
        tenant.fine_tuning_enabled = request.enabled
        
        # Log admin action
        action = "enabled" if request.enabled else "disabled"
        reason = f" - Reason: {request.reason}" if request.reason else ""
        logger.info(f"🔧 Admin {current_user.username} {action} fine-tuning for tenant {tenant.id} ({tenant.name}){reason}")
        
        # If disabling, deactivate patterns
        if not request.enabled:
            patterns_affected = db.query(LearningPattern).filter(
                LearningPattern.tenant_id == request.tenant_id,
                LearningPattern.is_active == True
            ).update({"is_active": False})
            
            improvements_affected = db.query(AutoImprovement).filter(
                AutoImprovement.tenant_id == request.tenant_id,
                AutoImprovement.is_active == True
            ).update({"is_active": False})
        else:
            patterns_affected = 0
            improvements_affected = 0
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Fine-tuning {action} for tenant {tenant.name}",
            "tenant_id": request.tenant_id,
            "tenant_name": tenant.name,
            "fine_tuning_enabled": request.enabled,
            "patterns_affected": patterns_affected,
            "improvements_affected": improvements_affected,
            "admin_user": current_user.username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin tenant control: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update tenant fine-tuning")

@router.get("/admin/tenant/{tenant_id}/metrics")
async def get_admin_tenant_metrics(
    tenant_id: int,
    current_user = Depends(get_admin_user),
    db: Session = Depends(get_db),
    days: int = 30
):
    """Get detailed metrics for specific tenant (Admin only)"""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        trainer = get_background_trainer()
        tenant_status = trainer.get_training_status(tenant_id)
        
        # Get recent training performance
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        training_cycles = db.query(TrainingMetrics).filter(
            TrainingMetrics.tenant_id == tenant_id,
            TrainingMetrics.training_cycle >= cutoff_date
        ).order_by(TrainingMetrics.training_cycle.desc()).all()
        
        # Get pattern effectiveness
        effective_patterns = db.query(LearningPattern).filter(
            LearningPattern.tenant_id == tenant_id,
            LearningPattern.is_active == True,
            LearningPattern.usage_count > 0
        ).order_by(LearningPattern.usage_count.desc()).limit(10).all()
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "fine_tuning_enabled": getattr(tenant, 'fine_tuning_enabled', True),
            "admin_viewing": current_user.username,
            "status": tenant_status,
            "training_performance": {
                "cycles_last_30_days": len(training_cycles),
                "avg_patterns_per_cycle": sum(m.patterns_learned for m in training_cycles) / max(len(training_cycles), 1),
                "avg_improvements_per_cycle": sum(m.responses_improved for m in training_cycles) / max(len(training_cycles), 1)
            },
            "top_patterns": [
                {
                    "pattern": p.user_message_pattern[:50] + "..." if len(p.user_message_pattern) > 50 else p.user_message_pattern,
                    "confidence": p.confidence_score,
                    "usage_count": p.usage_count,
                    "success_rate": p.success_rate,
                    "type": p.pattern_type
                }
                for p in effective_patterns
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin tenant metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tenant metrics")

@router.post("/admin/global/pause")
async def pause_global_training(
    current_user = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Pause global training system (Admin only)"""
    try:
        trainer = get_background_trainer()
        trainer.stop_learning()
        
        logger.warning(f"🚨 Admin {current_user.username} paused global fine-tuning system")
        
        return {
            "success": True,
            "message": "Global fine-tuning system paused",
            "admin_user": current_user.username,
            "timestamp": datetime.utcnow().isoformat(),
            "warning": "All autonomous learning has been stopped. Use /admin/global/resume to restart."
        }
        
    except Exception as e:
        logger.error(f"Error pausing global training: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause training system")

@router.post("/admin/global/resume")
async def resume_global_training(
    current_user = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Resume global training system (Admin only)"""
    try:
        trainer = get_background_trainer()
        
        # Start training in background
        import asyncio
        asyncio.create_task(trainer.start_continuous_learning())
        
        logger.info(f"✅ Admin {current_user.username} resumed global fine-tuning system")
        
        return {
            "success": True,
            "message": "Global fine-tuning system resumed",
            "admin_user": current_user.username,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "Autonomous learning restarted - 30-minute cycles active"
        }
        
    except Exception as e:
        logger.error(f"Error resuming global training: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume training system")