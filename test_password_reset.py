#!/usr/bin/env python3
"""
Test the password reset functionality
"""
import os
import sys
from dotenv import load_dotenv
import requests
import json

# Load environment variables
load_dotenv()

def test_password_reset():
    """Test the password reset endpoints"""
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8001")
    
    # Email to test
    email = input("Enter email to test password reset: ")
    
    # Step 1: Request password reset
    print(f"\nRequesting password reset for {email}...")
    try:
        response = requests.post(
            f"{api_base_url}/auth/forgot-password",
            json={"email": email}
        )
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 200:
            print("Failed to request password reset")
            return
    except Exception as e:
        print(f"Error: {e}")
        return
    
    # Step 2: Check email and get token
    print("\nCheck your email for a password reset link.")
    print("It should contain a token in the URL like: /reset-password?token=...")
    token = input("Enter the token from the email: ")
    
    if not token:
        print("No token provided, exiting")
        return
    
    # Step 3: Validate token
    print("\nValidating token...")
    try:
        response = requests.get(
            f"{api_base_url}/auth/validate-reset-token/{token}"
        )
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 200:
            print("Invalid token")
            return
    except Exception as e:
        print(f"Error: {e}")
        return
    
    # Step 4: Reset password
    new_password = input("\nEnter new password: ")
    if not new_password:
        print("No password provided, exiting")
        return
    
    print("\nResetting password...")
    try:
        response = requests.post(
            f"{api_base_url}/auth/reset-password",
            json={"token": token, "new_password": new_password}
        )
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ Password reset successful!")
            print(f"You can now log in with email {email} and your new password")
        else:
            print("\n❌ Failed to reset password")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_password_reset()
