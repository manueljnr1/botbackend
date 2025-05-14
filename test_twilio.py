#!/usr/bin/env python3
"""
Test Twilio authentication
"""
import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def test_twilio_auth():
    """Test Twilio authentication"""
    # Get credentials from environment variables
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    print("Testing Twilio authentication...")
    print(f"Account SID: {account_sid[:5]}...{account_sid[-5:] if account_sid else ''}")
    print(f"Auth Token: {auth_token[:3]}...{auth_token[-3:] if auth_token else ''}")
    
    if not account_sid or not auth_token:
        print("ERROR: Missing Twilio credentials in environment variables!")
        return False
    
    # Try to authenticate with Twilio
    try:
        client = Client(account_sid, auth_token)
        # Just get account info to test authentication
        account = client.api.accounts(account_sid).fetch()
        print(f"Authentication successful! Account: {account.friendly_name}")
        return True
    except Exception as e:
        print(f"Authentication failed: {e}")
        return False

if __name__ == "__main__":
    test_twilio_auth()
