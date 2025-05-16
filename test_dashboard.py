"""
Test script for the dashboard endpoints
"""
import requests
import json
import sys

def test_dashboard_endpoints(base_url, access_token):
    """Test all dashboard endpoints and print the results"""
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # List of endpoints to test
    endpoints = [
        "/dashboard/metrics",
        "/dashboard/performance",
        "/dashboard/recent-conversations",
        "/dashboard/faq-metrics",
        "/dashboard/knowledge-base-metrics"
    ]
    
    print("Testing dashboard endpoints...")
    print(f"Base URL: {base_url}")
    print(f"Access token: {access_token[:10]}...\n")
    
    # Test each endpoint
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"Testing {url}...")
        
        try:
            response = requests.get(url, headers=headers)
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                # Pretty print the JSON response
                print("Response:")
                print(json.dumps(response.json(), indent=2))
                print("✅ Success!")
            else:
                print("❌ Failed!")
                print(f"Error: {response.text}")
            
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print("-" * 50)
    
    print("Dashboard endpoint testing complete!")

if __name__ == "__main__":
    # Get base URL and access token from command line arguments
    if len(sys.argv) < 3:
        print("Usage: python test_dashboard.py <base_url> <access_token>")
        print("Example: python test_dashboard.py http://localhost:8001 eyJhbGciOiJIUzI...")
        sys.exit(1)
    
    base_url = sys.argv[1]
    access_token = sys.argv[2]
    
    # Make sure the base URL has no trailing slash
    if base_url.endswith("/"):
        base_url = base_url[:-1]
    
    test_dashboard_endpoints(base_url, access_token)