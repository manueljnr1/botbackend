#!/usr/bin/env python3
"""
Test the custom WhatsApp integration
"""
import requests
import sys

def test_custom_whatsapp(message):
    """Send a test request to the custom WhatsApp endpoint"""
    url = "http://localhost:8001/custom/whatsapp"
    
    # Prepare form data
    data = {
        "From": "whatsapp:+2348162055851",
        "To": "whatsapp:+14155238886",
        "Body": message,
        "SmsStatus": "received",
        "NumSegments": "1",
        "MessageSid": "SM00000000000000000000000000000000",
        "AccountSid": "AC00000000000000000000000000000000"
    }
    
    print(f"Sending test request to: {url}")
    print(f"Message: {message}")
    
    try:
        response = requests.post(url, data=data)
        print(f"Status code: {response.status_code}")
        
        try:
            print(f"Response: {response.json()}")
            return response.json()
        except:
            print(f"Raw response: {response.text}")
            return response.text
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = sys.argv[1]
    else:
        message = input("Enter a test message: ")
    
    test_custom_whatsapp(message)
