#!/usr/bin/env python3
"""
Script to fix WhatsApp integration by directly modifying the code
"""
import os
import sqlite3
import re
import shutil

def get_tenant_api_key(tenant_id=1):
    """Get API key for the specified tenant"""
    try:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT api_key FROM tenants WHERE id = ?", (tenant_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        return None
    except Exception as e:
        print(f"Error getting API key: {e}")
        return None

def backup_file(file_path):
    """Create a backup of a file"""
    backup_path = f"{file_path}.bak"
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        print(f"Error creating backup: {e}")
        return False

def update_whatsapp_integration():
    """Update WhatsApp integration code to use hardcoded API key"""
    # Find the WhatsApp integration file
    app_path = os.path.join(os.getcwd(), "app")
    integration_path = os.path.join(app_path, "integrations")
    
    whatsapp_file = None
    for root, dirs, files in os.walk(integration_path):
        for file in files:
            if "whatsapp" in file.lower() and file.endswith(".py"):
                whatsapp_file = os.path.join(root, file)
                break
    
    if not whatsapp_file:
        print("WhatsApp integration file not found.")
        return False
    
    # Get tenant API key
    api_key = get_tenant_api_key()
    if not api_key:
        print("Could not get tenant API key.")
        return False
    
    print(f"Found WhatsApp integration file: {whatsapp_file}")
    print(f"Using API key: {api_key}")
    
    # Backup the file
    if not backup_file(whatsapp_file):
        return False
    
    # Read the file content
    with open(whatsapp_file, 'r') as f:
        content = f.read()
    
    # Look for the section where the API key is retrieved
    api_key_pattern = r"api_key\s*=\s*get_api_key_for_whatsapp_number\([^)]+\)"
    if re.search(api_key_pattern, content):
        # Replace with hardcoded API key
        modified_content = re.sub(
            api_key_pattern,
            f'api_key = "{api_key}"  # Hardcoded for testing',
            content
        )
        
        # Write the modified content back
        with open(whatsapp_file, 'w') as f:
            f.write(modified_content)
        
        print("WhatsApp integration updated with hardcoded API key.")
        return True
    else:
        # Try a different approach - look for the method
        func_pattern = r"def\s+get_api_key_for_whatsapp_number[^)]+\):[^}]+}"
        if re.search(func_pattern, content):
            # Replace the function implementation
            modified_content = re.sub(
                func_pattern,
                f'def get_api_key_for_whatsapp_number(phone_number: str) -> str:\n    """Get API key for a WhatsApp number"""\n    return "{api_key}"  # Hardcoded for testing',
                content
            )
            
            # Write the modified content back
            with open(whatsapp_file, 'w') as f:
                f.write(modified_content)
            
            print("WhatsApp integration function updated with hardcoded API key.")
            return True
    
    print("Could not find proper location to modify in WhatsApp integration file.")
    return False

if __name__ == "__main__":
    update_whatsapp_integration()
    print("\nDon't forget to restart your server after this change.")
