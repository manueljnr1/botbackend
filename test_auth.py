#!/usr/bin/env python3
"""
Test script for authentication endpoints (register and login)

This script tests the registration and login functionality of your API.
It will:
1. Register a new user
2. Try to login with the registered user
3. Test token validation
"""
import requests
import json
import logging
import sys
import argparse
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def test_auth_endpoints(base_url, username=None, password=None, email=None):
    """Test authentication endpoints"""
    logger.info("Starting authentication test")
    
    # Generate random credentials if not provided
    if not username:
        username = f"testuser_{uuid.uuid4().hex[:8]}"
    if not password:
        password = f"Password123_{uuid.uuid4().hex[:8]}"
    if not email:
        email = f"{username}@example.com"
    
    # 1. Register a new user
    logger.info(f"Attempting to register user: {username}")
    register_url = f"{base_url}/auth/users/"
    register_data = {
        "email": email,
        "username": username,
        "password": password
    }
    
    try:
        register_response = requests.post(
            register_url,
            json=register_data,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"Registration status code: {register_response.status_code}")
        
        # Check for successful registration
        if register_response.status_code == 200:
            logger.info("Registration successful!")
            user_data = register_response.json()
            logger.info(f"User data: {json.dumps(user_data, indent=2)}")
        else:
            logger.error(f"Registration failed: {register_response.text}")
            # If the user already exists, continue with login test
            if register_response.status_code == 400 and "already registered" in register_response.text:
                logger.info("Continuing with existing user...")
            else:
                return False
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        return False
    
    # 2. Login with registered user
    logger.info(f"Attempting to login with user: {username}")
    login_url = f"{base_url}/auth/token"
    
    try:
        # Note: For token endpoint, data must be form-encoded, not JSON
        login_response = requests.post(
            login_url,
            data={
                "username": username,
                "password": password
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        logger.info(f"Login status code: {login_response.status_code}")
        
        # Check for successful login
        if login_response.status_code == 200:
            logger.info("Login successful!")
            token_data = login_response.json()
            access_token = token_data.get("access_token")
            token_type = token_data.get("token_type")
            
            if access_token:
                logger.info(f"Received access token: {access_token[:10]}...")
                
                # 3. Test token with a protected endpoint
                logger.info("Testing token with a protected endpoint...")
                
                # Try to access user profile endpoint or any protected route
                protected_url = f"{base_url}/auth/me"
                protected_response = requests.get(
                    protected_url,
                    headers={"Authorization": f"{token_type} {access_token}"}
                )
                
                logger.info(f"Protected endpoint status code: {protected_response.status_code}")
                
                if protected_response.status_code == 200:
                    logger.info("Token validation successful!")
                    logger.info(f"User profile: {json.dumps(protected_response.json(), indent=2)}")
                    return True
                else:
                    logger.error(f"Token validation failed: {protected_response.text}")
                    return False
            else:
                logger.error("No access token received")
                return False
        else:
            logger.error(f"Login failed: {login_response.text}")
            
            # Print additional debugging info
            logger.info("Debugging info:")
            logger.info(f"Login URL: {login_url}")
            logger.info(f"Login data: username={username}, password=***")
            
            return False
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False

def run_direct_db_check(db_url, username):
    """Direct database check (use this only for debugging)"""
    try:
        import sqlalchemy
        from sqlalchemy import create_engine, text
        
        logger.info(f"Connecting to database: {db_url}")
        engine = create_engine(db_url)
        
        with engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM users WHERE username = '{username}'"))
            user = result.fetchone()
            
            if user:
                logger.info(f"User found in database: {dict(user)}")
                return True
            else:
                logger.info(f"User not found in database: {username}")
                return False
    except Exception as e:
        logger.error(f"Database check error: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test authentication endpoints')
    parser.add_argument('--url', type=str, default='http://localhost:8000', help='Base API URL')
    parser.add_argument('--username', type=str, help='Username to register/login')
    parser.add_argument('--password', type=str, help='Password to register/login')
    parser.add_argument('--email', type=str, help='Email to register')
    parser.add_argument('--db-url', type=str, help='Database URL for direct check (optional)')
    
    args = parser.parse_args()
    
    success = test_auth_endpoints(
        args.url,
        username=args.username,
        password=args.password,
        email=args.email
    )
    
    if args.db_url and not success:
        logger.info("Performing direct database check...")
        run_direct_db_check(args.db_url, args.username or f"testuser_{uuid.uuid4().hex[:8]}")
    
    sys.exit(0 if success else 1)