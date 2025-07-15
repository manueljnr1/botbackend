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
from app.pricing.models import PricingPlan, TenantSubscription, BillingHistory, PaymentIntent
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
        try:
            from app.pricing.models import PaymentIntent
            
            payment_intent = PaymentIntent(
                tenant_id=tenant.id,
                plan_id=plan_id,
                tx_ref=result["tx_ref"],
                amount=amount,
                billing_cycle=billing_cycle,
                status="pending"
            )
            db.add(payment_intent)
            db.commit()
            
            logger.info(f"✅ Created payment intent {result['tx_ref']} for tenant {tenant.id}")
            
        except ImportError:
            # PaymentIntent model not available yet, just log
            logger.warning("PaymentIntent model not available - payment tracking limited")
        except Exception as e:
            # Don't fail payment link creation if intent storage fails
            logger.error(f"Failed to store payment intent: {e}")
        
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
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    """Enhanced webhook with proper signature verification"""
    
    try:
        payload = await request.json()
        
        # Log all webhook activity
        logger.info(f"Webhook received: {payload.get('event', 'unknown_event')}")
        
        # Verify signature
        webhook_signature = request.headers.get("verif-hash")
        if not verify_flutterwave_signature(payload, webhook_signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        result = flutterwave.handle_webhook(payload)
        
        if result["event"] == "payment_successful":
            logger.info(f"Processing successful payment: {result.get('tx_ref')}")
            success = await process_successful_payment_enhanced(result, db)
            
            if success:
                logger.info("Payment processed successfully")
                return {"status": "success"}
            else:
                logger.error("Payment processing failed")
                return {"status": "error", "message": "Processing failed"}
                
        elif result["event"] == "payment_failed":
            logger.info(f"Processing failed payment: {result.get('tx_ref')}")
            await process_failed_payment(result, db)
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


def verify_flutterwave_signature(payload: dict, signature: str) -> bool:
    """Verify Flutterwave webhook signature"""
    if not signature:
        logger.warning("No webhook signature provided")
        return False
    
    webhook_secret = os.getenv("FLUTTERWAVE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("FLUTTERWAVE_WEBHOOK_SECRET not configured")
        return False
    
    # Create expected signature
    payload_string = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


async def process_successful_payment_enhanced(payment_data: Dict[str, Any], db: Session) -> bool:
    """Enhanced payment processing with metadata support and comprehensive error handling"""
    
    try:
        tx_ref = payment_data["tx_ref"]
        
        # DUPLICATE CHECK - Prevent double processing
        existing_subscription = db.query(TenantSubscription).filter(
            TenantSubscription.flutterwave_tx_ref == tx_ref
        ).first()
        
        if existing_subscription:
            logger.info(f"Payment {tx_ref} already processed")
            return True
        
        # ENHANCED: Get tenant from metadata first, then email fallback
        meta = payment_data.get("meta", {})
        tenant_id = meta.get("tenant_id")
        
        tenant = None
        
        # PRIMARY METHOD: Direct tenant ID lookup from metadata
        if tenant_id:
            try:
                tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
                if tenant:
                    logger.info(f"✅ Found tenant by metadata ID: {tenant_id}")
                else:
                    logger.warning(f"⚠️ Tenant ID {tenant_id} not found in database")
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Invalid tenant_id format: {tenant_id} - {e}")
        
        # FALLBACK METHOD: Email lookup (existing logic)
        if not tenant:
            customer = payment_data.get("customer", {})
            customer_email = customer.get("email")
            
            if customer_email:
                tenant = db.query(Tenant).filter(Tenant.email == customer_email).first()
                if tenant:
                    logger.info(f"✅ Found tenant by email fallback: {customer_email}")
                else:
                    logger.warning(f"⚠️ No tenant found with email: {customer_email}")
        
        # VALIDATION: Ensure tenant was found
        if not tenant:
            error_msg = f"No tenant found for payment {tx_ref}. Metadata: {meta}, Customer: {payment_data.get('customer', {})}"
            logger.error(error_msg)
            await send_payment_alert("Tenant not found", payment_data)
            return False
        
        # ENHANCED: Get plan from metadata first, then amount fallback
        plan_name = meta.get("plan_name")
        billing_cycle = meta.get("billing_cycle", "monthly")
        
        plan = None
        
        # PRIMARY METHOD: Plan lookup by name from metadata
        if plan_name:
            plan = db.query(PricingPlan).filter(
                PricingPlan.name == plan_name,
                PricingPlan.is_active == True
            ).first()
            if plan:
                logger.info(f"✅ Found plan by metadata name: {plan_name}")
            else:
                logger.warning(f"⚠️ Plan '{plan_name}' not found or inactive")
        
        # FALLBACK METHOD: Determine plan by amount (existing logic)
        if not plan:
            amount = payment_data.get("amount")
            plan, billing_cycle = determine_plan_from_amount(amount, db)
            if plan:
                logger.info(f"✅ Determined plan by amount: ₦{amount} -> {plan.name} ({billing_cycle})")
            else:
                logger.error(f"❌ No plan mapping found for amount: ₦{amount}")
        
        # VALIDATION: Ensure plan was found
        if not plan:
            error_msg = f"No plan found for payment {tx_ref}. Amount: {payment_data.get('amount')}, Metadata plan: {plan_name}"
            logger.error(error_msg)
            await send_payment_alert("Plan not found", payment_data)
            return False
        
        # TRANSACTION: Wrap all database operations for atomicity
        with db.begin():
            # Upgrade the subscription
            pricing_service = PricingService(db)
            new_subscription = pricing_service.upgrade_subscription(
                tenant_id=tenant.id,
                new_plan_id=plan.id,
                billing_cycle=billing_cycle
            )
            
            if not new_subscription:
                logger.error(f"❌ Subscription upgrade failed for tenant {tenant.id}")
                return False
            
            # Store payment details
            new_subscription.flutterwave_tx_ref = payment_data["tx_ref"]
            new_subscription.flutterwave_flw_ref = payment_data["flw_ref"]
            new_subscription.status = "active"
            
            # ENHANCED: Save card details for recurring payments
            try:
                card_details = flutterwave.save_customer_card(tx_ref)
                
                if card_details["success"] and card_details.get("card_token"):
                    new_subscription.card_token = card_details["card_token"]
                    new_subscription.card_last4 = card_details["card_last4"]
                    new_subscription.card_type = card_details["card_type"]
                    new_subscription.flutterwave_customer_id = card_details["customer_id"]
                    new_subscription.payment_method_saved = True
                    new_subscription.auto_renewal_enabled = True  # Enable by default
                    
                    # Calculate next payment date
                    if billing_cycle == "monthly":
                        new_subscription.next_payment_date = new_subscription.current_period_end
                    else:  # yearly
                        new_subscription.next_payment_date = new_subscription.current_period_end
                    
                    logger.info(f"✅ Saved payment method for tenant {tenant.id} (****{card_details['card_last4']})")
                else:
                    logger.warning(f"⚠️ Could not save card details for tenant {tenant.id}: {card_details.get('error', 'Unknown error')}")
                    
            except Exception as card_error:
                logger.error(f"❌ Error saving card details: {card_error}")
                # Don't fail the entire payment processing if card saving fails
            
            # Create billing history record
            billing_record = BillingHistory(
                tenant_id=tenant.id,
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
            
            # Update payment intent status if it exists
            try:
                payment_intent = db.query(PaymentIntent).filter(
                    PaymentIntent.tx_ref == tx_ref
                ).first()
                
                if payment_intent:
                    payment_intent.status = "completed"
                    payment_intent.processed_at = datetime.utcnow()
                    logger.info(f"✅ Updated payment intent status for {tx_ref}")
            except ImportError:
                # PaymentIntent model not available yet
                pass
            except Exception as intent_error:
                logger.warning(f"⚠️ Could not update payment intent: {intent_error}")
            
            # Explicit commit of transaction
            db.commit()
        
        # Send success notifications AFTER transaction commits
        try:
            await send_upgrade_confirmation(tenant, plan, payment_data)
        except Exception as notification_error:
            logger.error(f"❌ Failed to send upgrade confirmation: {notification_error}")
            # Don't fail the payment processing if notification fails
        
        logger.info(f"🎉 Successfully upgraded tenant {tenant.id} ({tenant.email}) to {plan.name} plan")
        return True
        
    except Exception as e:
        logger.error(f"💥 Error processing payment {payment_data.get('tx_ref', 'unknown')}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        try:
            db.rollback()
        except:
            pass
        
        await send_payment_alert(f"Processing error: {str(e)}", payment_data)
        return False


def determine_plan_from_amount(amount: float, db: Session) -> tuple:
    """
    Determine plan and billing cycle from payment amount
    This is a fallback method when metadata is not available
    """
    if not amount:
        logger.error("No amount provided for plan determination")
        return None, None
    
    # Define your exact amount mappings - UPDATE THESE TO MATCH YOUR PRICES
    amount_mappings = [
        (9.99, "Basic", "monthly"),
        (99.00, "Basic", "yearly"),
        (29.00, "Growth", "monthly"),
        (290.00, "Growth", "yearly"),
        (59.00, "Pro", "monthly"),
        (590.00, "Pro", "yearly"),
        (99.00, "Agency", "monthly"),    # Note: Same price as Basic yearly
        (990.00, "Agency", "yearly"),
    ]
    
    # Find matching amount (allow small floating point differences)
    for mapped_amount, plan_name, billing_cycle in amount_mappings:
        if abs(amount - mapped_amount) < 0.01:
            plan = db.query(PricingPlan).filter(
                PricingPlan.name == plan_name,
                PricingPlan.is_active == True
            ).first()
            if plan:
                logger.info(f"✅ Mapped amount ₦{amount} to {plan_name} {billing_cycle}")
                return plan, billing_cycle
            else:
                logger.error(f"❌ Plan '{plan_name}' not found in database")
    
    logger.error(f"❌ No plan mapping found for amount: ₦{amount}")
    return None, None


    

def determine_plan_from_amount(amount: float, db: Session) -> tuple:
    """Determine plan and billing cycle from payment amount"""
    # YOUR EXACT AMOUNTS - Update these to match your Flutterwave links
    amount_mappings = [
        (9.99, "Basic", "monthly"),
        (99.00, "Basic", "yearly"),
        (29.00, "Growth", "monthly"),
        (290.00, "Growth", "yearly"),
        (59.00, "Pro", "monthly"),
        (590.00, "Pro", "yearly"),
        (99.00, "Agency", "monthly"),    # Note: Same price as Basic yearly
        (990.00, "Agency", "yearly"),
    ]
    
    for mapped_amount, plan_name, billing_cycle in amount_mappings:
        if abs(amount - mapped_amount) < 0.01:  # Handle floating point precision
            plan = db.query(PricingPlan).filter(PricingPlan.name == plan_name).first()
            if plan:
                return plan, billing_cycle
    
    logger.error(f"No plan mapping found for amount: {amount}")
    return None, None


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


@router.get("/payments/{tx_ref}/status")
async def get_payment_status(
    tx_ref: str,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get payment processing status"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    payment_intent = db.query(PaymentIntent).filter(
        PaymentIntent.tx_ref == tx_ref,
        PaymentIntent.tenant_id == tenant.id
    ).first()
    
    if not payment_intent:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return {
        "tx_ref": tx_ref,
        "status": payment_intent.status,
        "amount": payment_intent.amount,
        "created_at": payment_intent.created_at,
        "processed_at": payment_intent.processed_at
    }


# Add these endpoints at the end of router.py

@router.get("/subscription/payment-method")
async def get_payment_method(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get saved payment method details"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    subscription = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant.id,
        TenantSubscription.is_active == True
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    return {
        "has_saved_payment_method": subscription.payment_method_saved,
        "card_last4": subscription.card_last4 if subscription.payment_method_saved else None,
        "card_type": subscription.card_type if subscription.payment_method_saved else None,
        "auto_renewal_enabled": subscription.auto_renewal_enabled,
        "next_payment_date": subscription.next_payment_date
    }

@router.post("/subscription/toggle-auto-renewal")
async def toggle_auto_renewal(
    enable: bool,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Enable or disable auto-renewal"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    subscription = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant.id,
        TenantSubscription.is_active == True
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    if enable and not subscription.payment_method_saved:
        raise HTTPException(status_code=400, detail="No saved payment method found")
    
    subscription.auto_renewal_enabled = enable
    db.commit()
    
    action = "enabled" if enable else "disabled"
    return {"message": f"Auto-renewal {action} successfully"}

@router.delete("/subscription/payment-method")
async def remove_payment_method(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Remove saved payment method"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    subscription = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant.id,
        TenantSubscription.is_active == True
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    # Clear payment method details
    subscription.card_token = None
    subscription.card_last4 = None
    subscription.card_type = None
    subscription.payment_method_saved = False
    subscription.auto_renewal_enabled = False
    subscription.next_payment_date = None
    
    db.commit()
    
    return {"message": "Payment method removed successfully"}

@router.post("/subscription/charge-now")
async def charge_now(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Manually charge the saved payment method (for testing or immediate billing)"""
    tenant = get_tenant_from_api_key(api_key, db)
    
    subscription = db.query(TenantSubscription).filter(
        TenantSubscription.tenant_id == tenant.id,
        TenantSubscription.is_active == True
    ).first()
    
    if not subscription or not subscription.payment_method_saved:
        raise HTTPException(status_code=400, detail="No saved payment method found")
    
    # Calculate amount
    amount = float(
        subscription.plan.price_monthly 
        if subscription.billing_cycle == "monthly" 
        else subscription.plan.price_yearly
    )
    
    # Charge the card
    result = flutterwave.charge_saved_card(
        card_token=subscription.card_token,
        amount=amount,
        customer_email=tenant.email,
        tenant_id=tenant.id,
        description=f"Manual charge for {subscription.plan.name} plan"
    )
    
    if result["success"]:
        return {
            "success": True,
            "message": "Payment charged successfully",
            "amount": amount,
            "tx_ref": result["tx_ref"]
        }
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Payment failed: {result.get('error', 'Unknown error')}"
        )