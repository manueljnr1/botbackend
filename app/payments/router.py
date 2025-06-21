import os
import json
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# FastAPI imports
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi import status

# SQLAlchemy imports
from sqlalchemy.orm import Session

# Your app imports
from app.database import get_db
from app.payments.flutterwave_service import FlutterwaveService
from app.pricing.service import PricingService
from app.pricing.models import PricingPlan, TenantSubscription, BillingHistory
from app.tenants.models import Tenant
from app.tenants.router import get_tenant_from_api_key



# Initialize
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
    """Enhanced webhook with proper signature verification"""
    
    try:
        payload = await request.json()
        
        # 🔐 CRITICAL: Verify webhook signature for security
        webhook_signature = request.headers.get("verif-hash")
        if not verify_flutterwave_signature(payload, webhook_signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        result = flutterwave.handle_webhook(payload)
        
        if result["event"] == "payment_successful":
            # Enhanced processing with better error handling
            success = await process_successful_payment_enhanced(result, db)
            if not success:
                logger.error("Failed to process successful payment")
                return {"status": "error", "message": "Processing failed"}
                
        elif result["event"] == "payment_failed":
            await process_failed_payment(result, db)
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


def verify_flutterwave_signature(payload: dict, signature: str) -> bool:
    """Verify Flutterwave webhook signature"""
    import hashlib
    import hmac
    
    if not signature:
        return False
    
    # Your webhook secret from Flutterwave dashboard
    webhook_secret = os.getenv("FLUTTERWAVE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.warning("FLUTTERWAVE_WEBHOOK_SECRET not set")
        return False
    
    # Create signature
    payload_string = json.dumps(payload, separators=(',', ':'))
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


async def process_successful_payment_enhanced(payment_data: Dict[str, Any], db: Session) -> bool:
    """Enhanced payment processing with comprehensive error handling"""
    
    try:
        meta = payment_data.get("meta", {})
        tenant_id = meta.get("tenant_id")
        plan_name = meta.get("plan_name")
        billing_cycle = meta.get("billing_cycle", "monthly")
        
        if not tenant_id or not plan_name:
            logger.error("Missing required payment metadata")
            await send_payment_alert("Missing metadata", payment_data)
            return False
        
        # Validate tenant exists
        tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
        if not tenant:
            logger.error(f"Tenant {tenant_id} not found")
            return False
        
        # Get the plan
        plan = db.query(PricingPlan).filter(PricingPlan.name == plan_name).first()
        if not plan:
            logger.error(f"Plan {plan_name} not found")
            await send_payment_alert(f"Plan {plan_name} not found", payment_data)
            return False
        
        # Upgrade the subscription
        pricing_service = PricingService(db)
        new_subscription = pricing_service.upgrade_subscription(
            tenant_id=int(tenant_id),
            new_plan_id=plan.id,
            billing_cycle=billing_cycle
        )
        
        if not new_subscription:
            logger.error("Subscription upgrade failed")
            return False
        
        # Store payment details
        new_subscription.flutterwave_tx_ref = payment_data["tx_ref"]
        new_subscription.flutterwave_flw_ref = payment_data["flw_ref"]
        new_subscription.status = "active"
        
        # Create billing history record
        billing_record = BillingHistory(
            tenant_id=int(tenant_id),
            subscription_id=new_subscription.id,
            amount=payment_data["amount"],
            currency=payment_data["currency"],
            billing_period_start=new_subscription.current_period_start,
            billing_period_end=new_subscription.current_period_end,
            plan_name=plan.name,
            conversations_included=plan.max_messages_monthly,
            payment_status="paid",
            payment_date=datetime.utcnow(),
            payment_method="flutterwave"
        )
        db.add(billing_record)
        
        db.commit()
        
        # Send success notifications
        await send_upgrade_confirmation(tenant, plan, payment_data)
        
        logger.info(f"✅ Successfully upgraded tenant {tenant_id} to {plan_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        db.rollback()
        await send_payment_alert(f"Processing error: {str(e)}", payment_data)
        return False


async def process_failed_payment(payment_data: Dict[str, Any], db: Session):
    """Handle failed payment notifications"""
    try:
        meta = payment_data.get("meta", {})
        tenant_id = meta.get("tenant_id")
        
        if tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
            if tenant:
                await send_payment_failure_notification(tenant, payment_data)
        
        logger.warning(f"Payment failed: {payment_data}")
        
    except Exception as e:
        logger.error(f"Error handling failed payment: {e}")






@router.get("/verify/{tx_ref}")
async def verify_payment_enhanced(
    tx_ref: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Enhanced payment verification with subscription update"""
    
    tenant = get_tenant_from_api_key(api_key, db)
    
    # Verify with Flutterwave
    result = flutterwave.verify_payment(tx_ref)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail="Payment verification failed")
    
    # Check if payment was successful
    if result["status"] == "successful":
        # Process the payment if not already processed
        existing_subscription = db.query(TenantSubscription).filter(
            TenantSubscription.flutterwave_tx_ref == tx_ref,
            TenantSubscription.tenant_id == tenant.id
        ).first()
        
        if not existing_subscription:
            # Payment not yet processed, trigger processing
            webhook_data = {
                "event": "payment_successful",
                "tx_ref": result["tx_ref"],
                "flw_ref": result["flw_ref"],
                "amount": result["amount"],
                "currency": result["currency"],
                "customer": result["customer"],
                "meta": result.get("meta", {}),
                "status": result["status"]
            }
            
            success = await process_successful_payment_enhanced(webhook_data, db)
            
            return {
                "status": result["status"],
                "amount": result["amount"],
                "currency": result["currency"],
                "payment_date": result["payment_date"],
                "processed": success,
                "message": "Payment verified and subscription updated" if success else "Payment verified but processing failed"
            }
        else:
            return {
                "status": result["status"],
                "amount": result["amount"],
                "currency": result["currency"],
                "payment_date": result["payment_date"],
                "processed": True,
                "message": "Payment already processed"
            }
    
    else:
        raise HTTPException(status_code=400, detail=f"Payment failed: {result['status']}")


## 3. NOTIFICATION FUNCTIONS

async def send_upgrade_confirmation(tenant: Tenant, plan: PricingPlan, payment_data: Dict):
    """Send upgrade confirmation email to tenant"""
    try:
        from app.services.email_service import EmailService
        
        email_service = EmailService()
        
        # Send to tenant
        await email_service.send_upgrade_confirmation(
            to_email=tenant.email,
            tenant_name=tenant.name,
            plan_name=plan.name,
            amount=payment_data["amount"],
            currency=payment_data["currency"],
            billing_cycle=payment_data.get("meta", {}).get("billing_cycle", "monthly")
        )
        
        logger.info(f"Upgrade confirmation sent to {tenant.email}")
        
    except Exception as e:
        logger.error(f"Failed to send upgrade confirmation: {e}")


async def send_payment_failure_notification(tenant: Tenant, payment_data: Dict):
    """Send payment failure notification"""
    try:
        from app.services.email_service import EmailService
        
        email_service = EmailService()
        
        await email_service.send_payment_failure_notification(
            to_email=tenant.email,
            tenant_name=tenant.name,
            reason=payment_data.get("reason", "Payment failed"),
            tx_ref=payment_data.get("tx_ref")
        )
        
        logger.info(f"Payment failure notification sent to {tenant.email}")
        
    except Exception as e:
        logger.error(f"Failed to send payment failure notification: {e}")


async def send_payment_alert(message: str, payment_data: Dict):
    """Send alert to admin about payment issues"""
    try:
        from app.services.email_service import EmailService
        
        email_service = EmailService()
        
        admin_email = os.getenv("ADMIN_EMAIL", "admin@yourdomain.com")
        
        await email_service.send_admin_alert(
            to_email=admin_email,
            subject="Payment Processing Alert",
            message=message,
            data=payment_data
        )
        
        logger.info("Payment alert sent to admin")
        
    except Exception as e:
        logger.error(f"Failed to send payment alert: {e}")


