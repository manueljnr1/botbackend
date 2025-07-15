
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from app.database import get_db
from app.payments.flutterwave_service import FlutterwaveService
from app.pricing.models import TenantSubscription, BillingHistory
from app.pricing.service import PricingService

logger = logging.getLogger(__name__)

class RecurringPaymentProcessor:
    
    def __init__(self):
        self.flutterwave = FlutterwaveService()
    
    def process_due_payments(self) -> dict:
        """
        Process all subscriptions due for payment today
        Call this from a cron job or scheduled task
        """
        db = next(get_db())
        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # Find subscriptions due for renewal
            today = datetime.utcnow().date()
            due_subscriptions = db.query(TenantSubscription).filter(
                TenantSubscription.next_payment_date <= today,
                TenantSubscription.auto_renewal_enabled == True,
                TenantSubscription.payment_method_saved == True,
                TenantSubscription.is_active == True,
                TenantSubscription.card_token.isnot(None)
            ).all()
            
            logger.info(f"Found {len(due_subscriptions)} subscriptions due for payment")
            results["processed"] = len(due_subscriptions)
            
            for subscription in due_subscriptions:
                try:
                    success = self._process_single_payment(subscription, db)
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        
                except Exception as e:
                    error_msg = f"Error processing payment for tenant {subscription.tenant_id}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                    results["failed"] += 1
            
            db.commit()
            logger.info(f"Recurring payments processed: {results['successful']} successful, {results['failed']} failed")
            
        except Exception as e:
            logger.error(f"Error in recurring payment processing: {e}")
            db.rollback()
            results["errors"].append(str(e))
        finally:
            db.close()
        
        return results
    
    def _process_single_payment(self, subscription: TenantSubscription, db: Session) -> bool:
        """Process payment for a single subscription"""
        try:
            # Calculate amount
            amount = float(
                subscription.plan.price_monthly 
                if subscription.billing_cycle == "monthly" 
                else subscription.plan.price_yearly
            )
            
            # Attempt to charge the card
            result = self.flutterwave.charge_saved_card(
                card_token=subscription.card_token,
                amount=amount,
                customer_email=subscription.tenant.email,
                tenant_id=subscription.tenant_id,
                description=f"Recurring payment for {subscription.plan.name} plan"
            )
            
            # Update retry tracking
            subscription.last_payment_attempt = datetime.utcnow()
            subscription.payment_retry_count += 1
            
            if result["success"] and result.get("status") == "successful":
                # Payment successful - extend subscription
                self._extend_subscription(subscription, amount, result, db)
                
                # Reset retry count on success
                subscription.payment_retry_count = 0
                
                logger.info(f"✅ Recurring payment successful for tenant {subscription.tenant_id}")
                return True
                
            else:
                # Payment failed
                self._handle_payment_failure(subscription, result, db)
                logger.warning(f"❌ Recurring payment failed for tenant {subscription.tenant_id}: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing payment for tenant {subscription.tenant_id}: {e}")
            return False
    
    def _extend_subscription(self, subscription: TenantSubscription, amount: float, payment_result: dict, db: Session):
        """Extend subscription after successful payment"""
        # Extend the subscription period
        if subscription.billing_cycle == "monthly":
            subscription.current_period_end += timedelta(days=30)
            subscription.next_payment_date += timedelta(days=30)
        else:  # yearly
            subscription.current_period_end += timedelta(days=365)
            subscription.next_payment_date += timedelta(days=365)
        
        # Reset usage for new period
        subscription.messages_used_current_period = 0
        subscription.current_period_start = datetime.utcnow()
        
        # Create billing record
        billing_record = BillingHistory(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            amount=amount,
            currency="NGN",
            billing_period_start=subscription.current_period_start,
            billing_period_end=subscription.current_period_end,
            plan_name=subscription.plan.name,
            conversations_included=subscription.plan.max_messages_monthly,
            payment_status="paid",
            payment_date=datetime.utcnow(),
            payment_method="flutterwave_recurring"
        )
        db.add(billing_record)
        
        # Store the transaction reference
        subscription.flutterwave_tx_ref = payment_result.get("tx_ref")
        subscription.flutterwave_flw_ref = payment_result.get("flw_ref")
    
    def _handle_payment_failure(self, subscription: TenantSubscription, payment_result: dict, db: Session):
        """Handle failed payment attempts"""
        
        # If too many retries, disable auto-renewal
        if subscription.payment_retry_count >= 3:
            subscription.auto_renewal_enabled = False
            logger.warning(f"Disabled auto-renewal for tenant {subscription.tenant_id} after 3 failed attempts")
        
        # Schedule retry based on failure count
        retry_delays = [1, 3, 7]  # Retry after 1, 3, then 7 days
        if subscription.payment_retry_count <= len(retry_delays):
            retry_delay = retry_delays[subscription.payment_retry_count - 1]
            subscription.next_payment_date = datetime.utcnow().date() + timedelta(days=retry_delay)
            logger.info(f"Scheduled retry for tenant {subscription.tenant_id} in {retry_delay} days")
    
    def retry_failed_payments(self) -> dict:
        """Retry payments that failed earlier"""
        return self.process_due_payments()  # Same logic applies

# Function to be called by cron job
def run_recurring_payments():
    """Entry point for cron job"""
    processor = RecurringPaymentProcessor()
    return processor.process_due_payments()

if __name__ == "__main__":
    # For testing
    results = run_recurring_payments()
    print(f"Processed: {results}")