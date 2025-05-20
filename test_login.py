import requests
import json

def test_admin_login():
    """Test admin login directly with the API"""
    base_url = input("Enter API base URL (e.g., http://localhost:8000): ")
    
    # Use the verified admin credentials
    username = "Emmanuel"  # Use the exact username we verified
    password = input("Enter admin password: ")
    
    login_url = f"{base_url.rstrip('/')}/tenants/login"
    
    # Prepare the form data (OAuth2 password flow expects form data)
    form_data = {
        'username': username,
        'password': password
    }
    
    print(f"\n🔐 Testing login for {username}...")
    print(f"📡 POST {login_url}")
    print(f"Sending data: {form_data}")
    
    try:
        # Make the login request
        response = requests.post(login_url, data=form_data)
        
        # Print full response status and headers for debugging
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
        
        # Check if request was successful
        if response.status_code == 200:
            try:
                data = response.json()
                print("\n✅ Login successful!")
                print("\n📄 Response:")
                print(json.dumps(data, indent=4, default=str))
            except json.JSONDecodeError:
                print("\n❌ Response is not valid JSON:")
                print(response.text)
        else:
            print(f"\n❌ Login failed with status code: {response.status_code}")
            print("Response:")
            print(response.text)
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request error: {e}")

if __name__ == "__main__":
    test_admin_login()