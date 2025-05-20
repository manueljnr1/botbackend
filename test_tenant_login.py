#!/usr/bin/env python3
"""
Script to test tenant login and verify API key is returned in the response
"""
import os
import sys
import json
import logging
import requests
from getpass import getpass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tenant_login():
    """Test tenant login and check if API key is returned in response"""
    print("=== Tenant Login API Test ===")
    
    # Get server URL
    server_url = input("Server URL (default: http://localhost:8000): ")
    if not server_url:
        server_url = "http://localhost:8000"
    
    # Remove trailing slash if present
    server_url = server_url.rstrip("/")
    
    # Get tenant credentials
    tenant_name = input("Tenant Name: ")
    password = getpass("Password: ")
    
    if not tenant_name or not password:
        print("Error: Tenant name and password are required")
        return
    
    # Prepare the request
    login_url = f"{server_url}/tenants/login"
    
    # Form data for OAuth2 login
    data = {
        "username": tenant_name,
        "password": password
    }
    
    print(f"\nSending login request to: {login_url}")
    print(f"Tenant Name: {tenant_name}")
    
    try:
        # Make the request
        response = requests.post(login_url, data=data)
        
        # Check response status
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code == 200:
            # Success - parse the response
            try:
                result = response.json()
                print("\nAuthentication successful!")
                
                # Pretty print the response
                print("\nResponse Content:")
                print(json.dumps(result, indent=2))
                
                # Check for API key
                if "api_key" in result:
                    print("\n✅ API key found in response!")
                    print(f"API Key: {result['api_key']}")
                else:
                    print("\n❌ API key NOT found in response!")
                    print("The response does not include the 'api_key' field.")
                    print("You may need to update your TokenResponse model and login_tenant function.")
                
                # Check for other expected fields
                expected_fields = ["access_token", "token_type", "tenant_id", "tenant_name", "expires_at"]
                missing_fields = [field for field in expected_fields if field not in result]
                
                if missing_fields:
                    print(f"\nWarning: Some expected fields are missing: {', '.join(missing_fields)}")
                else:
                    print("\nAll other expected fields are present in the response.")
                
            except json.JSONDecodeError:
                print("\n❌ Error: Could not parse response as JSON")
                print(f"Raw response: {response.text}")
        else:
            # Error - show the error response
            print("\n❌ Authentication failed!")
            try:
                error = response.json()
                print(f"Error: {error.get('detail', 'Unknown error')}")
            except:
                print(f"Raw error response: {response.text}")
            
            # Suggest possible solutions
            if response.status_code == 401:
                print("\nPossible issues:")
                print("1. Incorrect tenant name or password")
                print("2. Tenant is inactive")
                print("3. Tenant credentials are missing in the database")
                print("4. Password verification is failing")
            elif response.status_code == 404:
                print("\nPossible issues:")
                print("1. Incorrect API endpoint URL")
                print("2. Server not running at the specified URL")
            elif response.status_code == 422:
                print("\nPossible issues:")
                print("1. Request format is incorrect")
                print("2. Required fields are missing")
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request error: {str(e)}")
        print("\nPossible issues:")
        print("1. Server is not running")
        print("2. Server URL is incorrect")
        print("3. Network connectivity issues")

def test_raw_login():
    """Test tenant login using direct SQLAlchemy query"""
    from app.database import SessionLocal
    from app.tenants.models import Tenant
    from app.auth.models import TenantCredentials
    from app.core.security import get_password_hash, verify_password
    
    print("=== Direct Database Login Test ===")
    
    # Get tenant credentials
    tenant_name = input("Tenant Name: ")
    password = getpass("Password: ")
    
    if not tenant_name or not password:
        print("Error: Tenant name and password are required")
        return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Find tenant
        tenant = db.query(Tenant).filter(
            Tenant.name == tenant_name,
            Tenant.is_active == True
        ).first()
        
        if not tenant:
            print(f"Error: Tenant '{tenant_name}' not found or inactive")
            return
        
        print(f"\nFound tenant: {tenant.name} (ID: {tenant.id})")
        
        # Check if tenant has credentials
        credentials = db.query(TenantCredentials).filter(
            TenantCredentials.tenant_id == tenant.id
        ).first()
        
        if not credentials:
            print(f"Error: No credentials found for tenant '{tenant.name}'")
            return
        
        # Check if credentials have a password
        if not credentials.hashed_password:
            print(f"Error: No password set for tenant '{tenant.name}'")
            return
        
        # Verify password
        if verify_password(password, credentials.hashed_password):
            print(f"\n✅ Authentication successful for tenant '{tenant.name}'!")
            
            # Display tenant info
            print(f"\nTenant ID: {tenant.id}")
            print(f"Tenant Name: {tenant.name}")
            print(f"API Key: {tenant.api_key}")
            
            if hasattr(tenant, 'contact_email') and tenant.contact_email:
                print(f"Contact Email: {tenant.contact_email}")
        else:
            print(f"\n❌ Authentication failed: Invalid password for tenant '{tenant.name}'")
    
    except Exception as e:
        print(f"Error during database test: {e}")
    
    finally:
        db.close()

def main():
    """Main menu"""
    while True:
        print("\n=== Tenant Login Test ===")
        print("1. Test API login (HTTP request)")
        print("2. Test direct database login")
        print("0. Exit")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            test_tenant_login()
        elif choice == "2":
            test_raw_login()
        elif choice == "0":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()