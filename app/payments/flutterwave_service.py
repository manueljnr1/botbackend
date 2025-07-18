import requests
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class FlutterwaveService:
    def __init__(self):
        self.secret_key = os.getenv("FLUTTERWAVE_SECRET_KEY")
        self.public_key = os.getenv("FLUTTERWAVE_PUBLIC_KEY")
        self.base_url = "https://api.flutterwave.com/v3"
        
        if not self.secret_key:
            raise ValueError("FLUTTERWAVE_SECRET_KEY environment variable is required")
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    def create_payment_link(self, 
                          tenant_id: int,
                          plan_name: str, 
                          amount: float, 
                          currency: str = "NGN",
                          billing_cycle: str = "monthly",
                          customer_email: str = None,
                          customer_name: str = None) -> Dict[str, Any]:
        """
        Create a Flutterwave payment link for subscription
        """
        try:
            # Generate unique transaction reference
            tx_ref = f"sub_{tenant_id}_{plan_name.lower()}_{billing_cycle}_{int(datetime.now().timestamp())}"
            
            payload = {
                "tx_ref": tx_ref,
                "amount": amount,
                "currency": currency,
                "redirect_url": f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/payment/success",
                "payment_options": "card,banktransfer,ussd",
                "customer": {
                    "email": customer_email or f"tenant_{tenant_id}@example.com",
                    "name": customer_name or f"Tenant {tenant_id}",
                },
                "customizations": {
                    "title": f"{plan_name} Plan Subscription",
                    "description": f"Monthly subscription to {plan_name} plan",
                    "logo": f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/logo.png"
                },
                "meta": {
                    "tenant_id": tenant_id,
                    "plan_name": plan_name,
                    "billing_cycle": billing_cycle,
                    "subscription_type": "new"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/payments",
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    return {
                        "success": True,
                        "payment_link": data["data"]["link"],
                        "tx_ref": tx_ref,
                        "flw_ref": data["data"]["tx_ref"]
                    }
            
            logger.error(f"Flutterwave payment link creation failed: {response.text}")
            return {"success": False, "error": response.text}
            
        except Exception as e:
            logger.error(f"Error creating Flutterwave payment link: {e}")
            return {"success": False, "error": str(e)}
    
    def verify_payment(self, transaction_id: str) -> Dict[str, Any]:
        """
        Verify payment status from Flutterwave
        """
        try:
            response = requests.get(
                f"{self.base_url}/transactions/{transaction_id}/verify",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    transaction_data = data["data"]
                    
                    return {
                        "success": True,
                        "status": transaction_data["status"],
                        "amount": transaction_data["amount"],
                        "currency": transaction_data["currency"],
                        "tx_ref": transaction_data["tx_ref"],
                        "flw_ref": transaction_data["flw_ref"],
                        "customer": transaction_data["customer"],
                        "meta": transaction_data.get("meta", {}),
                        "payment_date": transaction_data["created_at"]
                    }
            
            return {"success": False, "error": "Payment verification failed"}
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return {"success": False, "error": str(e)}
    
    def create_subscription_plan(self, 
                               plan_name: str, 
                               amount: float, 
                               interval: str = "monthly",
                               currency: str = "NGN") -> Dict[str, Any]:
        """
        Create a subscription plan in Flutterwave (for recurring payments)
        """
        try:
            payload = {
                "amount": amount,
                "name": plan_name,
                "interval": interval,  # monthly, quarterly, yearly
                "currency": currency
            }
            
            response = requests.post(
                f"{self.base_url}/payment-plans",
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    return {
                        "success": True,
                        "plan_id": data["data"]["id"],
                        "plan_name": data["data"]["name"],
                        "amount": data["data"]["amount"],
                        "interval": data["data"]["interval"]
                    }
            
            logger.error(f"Flutterwave plan creation failed: {response.text}")
            return {"success": False, "error": response.text}
            
        except Exception as e:
            logger.error(f"Error creating subscription plan: {e}")
            return {"success": False, "error": str(e)}
    
    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Flutterwave webhook notifications
        """
        try:
            event_type = payload.get("event")
            
            if event_type == "charge.completed":
                # Payment successful
                data = payload["data"]
                
                return {
                    "event": "payment_successful",
                    "tx_ref": data["tx_ref"],
                    "flw_ref": data["flw_ref"],
                    "amount": data["amount"],
                    "currency": data["currency"],
                    "customer": data["customer"],
                    "meta": data.get("meta", {}),
                    "status": data["status"]
                }
            
            elif event_type == "charge.failed":
                # Payment failed
                data = payload["data"]
                
                return {
                    "event": "payment_failed",
                    "tx_ref": data["tx_ref"],
                    "reason": data.get("processor_response", "Payment failed")
                }
            
            return {"event": "unknown", "data": payload}
            
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return {"event": "error", "error": str(e)}
        


    def verify_payment_detailed(self, transaction_id: str) -> Dict[str, Any]:
        """Enhanced payment verification with more details"""
        try:
            response = requests.get(
                f"{self.base_url}/transactions/{transaction_id}/verify",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    transaction_data = data["data"]
                    
                    return {
                        "success": True,
                        "status": transaction_data["status"],
                        "amount": transaction_data["amount"],
                        "currency": transaction_data["currency"],
                        "tx_ref": transaction_data["tx_ref"],
                        "flw_ref": transaction_data["flw_ref"],
                        "customer": transaction_data["customer"],
                        "meta": transaction_data.get("meta", {}),
                        "payment_date": transaction_data["created_at"],
                        "processor_response": transaction_data.get("processor_response"),
                        "card": transaction_data.get("card", {}),
                        "account": transaction_data.get("account", {})
                    }
            
            return {"success": False, "error": "Payment verification failed"}
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return {"success": False, "error": str(e)}
        

    

    def save_customer_card(self, tx_ref: str) -> Dict[str, Any]:
        """Get customer and card details after successful payment for future charges"""
        try:
            response = requests.get(
                f"{self.base_url}/transactions/{tx_ref}/verify",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    transaction = data["data"]
                    
                    # Check if card info is available
                    card_info = transaction.get("card", {})
                    customer_info = transaction.get("customer", {})
                    
                    return {
                        "success": True,
                        "customer_id": customer_info.get("id"),
                        "card_token": card_info.get("token"),
                        "card_last4": card_info.get("last_4digits"),
                        "card_type": card_info.get("type"),
                        "card_brand": card_info.get("issuer"),
                        "customer_email": customer_info.get("email")
                    }
            
            logger.error(f"Failed to get card details for {tx_ref}: {response.text}")
            return {"success": False, "error": "Could not retrieve card details"}
            
        except Exception as e:
            logger.error(f"Error saving card details: {e}")
            return {"success": False, "error": str(e)}

    def charge_saved_card(self, 
                        card_token: str,
                        amount: float,
                        customer_email: str,
                        tenant_id: int,
                        description: str = "Recurring subscription payment") -> Dict[str, Any]:
        """Charge a previously saved card token"""
        try:
            tx_ref = f"recurring_{tenant_id}_{int(datetime.now().timestamp())}"
            
            payload = {
                "token": card_token,
                "currency": "NGN",
                "amount": amount,
                "email": customer_email,
                "tx_ref": tx_ref,
                "narration": description,
                "meta": {
                    "tenant_id": tenant_id,
                    "charge_type": "recurring",
                    "description": description
                }
            }
            
            response = requests.post(
                f"{self.base_url}/tokenized-charges",
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": data["status"] == "success",
                    "tx_ref": tx_ref,
                    "amount": amount,
                    "status": data.get("data", {}).get("status", "failed"),
                    "flw_ref": data.get("data", {}).get("flw_ref"),
                    "charged_amount": data.get("data", {}).get("charged_amount"),
                    "response_data": data
                }
            
            logger.error(f"Card charge failed: {response.text}")
            return {"success": False, "error": response.text}
            
        except Exception as e:
            logger.error(f"Error charging saved card: {e}")
            return {"success": False, "error": str(e)}

    def validate_card_token(self, card_token: str) -> bool:
        """Check if a card token is still valid"""
        try:
            # Test with a small amount (0.50 NGN) to validate
            test_payload = {
                "token": card_token,
                "currency": "NGN",
                "amount": 0.50,
                "email": "test@validation.com",
                "tx_ref": f"validation_{int(datetime.now().timestamp())}"
            }
            
            response = requests.post(
                f"{self.base_url}/tokenized-charges",
                json=test_payload,
                headers=self._get_headers()
            )
            
            # If we get any response (even failure), token format is valid
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Card token validation error: {e}")
            return False
