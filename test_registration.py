#!/usr/bin/env python3
"""
Test user registration
"""
import requests
import json

def register_user(username, email, password):
    """Register a new user"""
    url = "http://localhost:8001/auth/register"
    data = {
        "username": username,
        "email": email,
        "password": password,
        "confirm_password": password
    }
    
    print(f"Registering user: {username} ({email})")
    try:
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            print("✅ User registered successfully!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return response.json()
        else:
            print(f"❌ Registration failed with status code: {response.status_code}")
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_login(username, password):
    """Test logging in with the registered user"""
    url = "http://localhost:8001/auth/token"
    data = {
        "username": username,
        "password": password
    }
    
    print(f"\nTesting login for user: {username}")
    try:
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            print("✅ Login successful!")
            print(f"Access token: {response.json().get('access_token', '')[:20]}...")
            return response.json()
        else:
            print(f"❌ Login failed with status code: {response.status_code}")
            print(f"Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    username = input("Enter username: ")
    email = input("Enter email: ")
    password = input("Enter password: ")
    
    user = register_user(username, email, password)
    if user:
        test_login(username, password)
