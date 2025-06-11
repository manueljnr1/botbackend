from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import logging

from app.database import get_db
from app.payments.flutterwave_service import FlutterwaveService
from app.pricing.service import PricingService
from app.tenants.router import get_tenant_from_api_key
from app.pricing.models import PricingPlan, TenantSubscription

logger = logging.getLogger(__name__)
router = APIRouter()
flutterwave = FlutterwaveService()

@router.post("/create-payment-link")
async def create_payment_link(
    plan_id: int,
    billing_cycle: str = "monthly",
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create a Flutterwave payment link for subscription upgrade"""
    
    # Get tenant
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Get the plan
    plan = db.query(PricingPlan).filter(PricingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    # Determine amount based on billing cycle
    amount = float(plan.price_monthly if billing_cycle == "monthly" else plan.price_yearly)
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Cannot create payment link for free plan")
    
    # Create payment link
    result = flutterwave.create_payment_link(
        tenant_id=tenant.id,
        plan_name=plan.name,
        amount=amount,
        billing_cycle=billing_cycle,
        customer_email=getattr(tenant, 'email', None),
        customer_name=getattr(tenant, 'name', None)
    )
    
    if result["success"]:
        # Store payment intent in database for tracking
        # You might want to create a PaymentIntent model
        return {
            "payment_link": result["payment_link"],
            "tx_ref": result["tx_ref"],
            "amount": amount,
            "currency": "NGN",
            "plan": plan.name
        }
    else:
        raise HTTPException(status_code=500, detail=f"Failed to create payment link: {result['error']}")

@router.post("/webhook")
async def flutterwave_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Flutterwave webhook notifications"""
    
    try:
        payload = await request.json()
        
        # Verify webhook signature (implement this for security)
        # webhook_signature = request.headers.get("verif-hash")
        
        result = flutterwave.handle_webhook(payload)
        
        if result["event"] == "payment_successful":
            # Process successful payment
            await process_successful_payment(result, db)
            
        elif result["event"] == "payment_failed":
            # Handle failed payment
            logger.warning(f"Payment failed: {result}")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

async def process_successful_payment(payment_data: Dict[str, Any], db: Session):
    """Process successful payment and activate subscription"""
    
    try:
        meta = payment_data.get("meta", {})
        tenant_id = meta.get("tenant_id")
        plan_name = meta.get("plan_name")
        billing_cycle = meta.get("billing_cycle", "monthly")
        
        if not tenant_id or not plan_name:
            logger.error("Missing tenant_id or plan_name in payment metadata")
            return
        
        # Get the plan
        plan = db.query(PricingPlan).filter(PricingPlan.name == plan_name).first()
        if not plan:
            logger.error(f"Plan {plan_name} not found")
            return
        
        # Upgrade the subscription
        pricing_service = PricingService(db)
        new_subscription = pricing_service.upgrade_subscription(
            tenant_id=int(tenant_id),
            new_plan_id=plan.id,
            billing_cycle=billing_cycle
        )
        
        # Store payment record
        new_subscription.flutterwave_tx_ref = payment_data["tx_ref"]
        new_subscription.flutterwave_flw_ref = payment_data["flw_ref"]
        new_subscription.status = "active"
        
        db.commit()
        
        logger.info(f"Successfully processed payment for tenant {tenant_id}, plan {plan_name}")
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        db.rollback()

@router.get("/verify/{tx_ref}")
async def verify_payment(
    tx_ref: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Verify payment status"""
    
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Verify the payment with Flutterwave
    result = flutterwave.verify_payment(tx_ref)
    
    if result["success"]:
        return {
            "status": result["status"],
            "amount": result["amount"],
            "currency": result["currency"],
            "payment_date": result["payment_date"]
        }
    else:
        raise HTTPException(status_code=400, detail="Payment verification failed")