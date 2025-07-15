
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.payments.recurring_payments import run_recurring_payments
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('recurring_payments.log'),
        logging.StreamHandler()
    ]
)

if __name__ == "__main__":
    try:
        results = run_recurring_payments()
        print(f"Recurring payments completed: {results}")
        
        # Exit with error code if there were failures
        if results["failed"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logging.error(f"Cron job failed: {e}")
        sys.exit(1)