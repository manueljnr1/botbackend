#!/usr/bin/env python3
"""
Script to check existing tenants and API keys in the database
"""
import sqlite3
import os

def check_tenants():
    """List all tenants in the database with their API keys"""
    db_path = os.path.join("chatbot.db")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenants table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        if not cursor.fetchone():
            print("Error: 'tenants' table does not exist in the database.")
            return
        
        # Get all tenants
        cursor.execute("SELECT id, name, api_key, is_active FROM tenants")
        tenants = cursor.fetchall()
        
        if not tenants:
            print("No tenants found in the database.")
            print("\nYou need to create a tenant first. Try running:")
            print("curl -X POST http://127.0.0.1:8001/tenants/ -H \"Authorization: Bearer YOUR_ACCESS_TOKEN\" -H \"Content-Type: application/json\" -d '{\"name\": \"Test Tenant\", \"description\": \"Test tenant\"}'")
            return
        
        print(f"Found {len(tenants)} tenants in the database:")
        print("-" * 80)
        print(f"{'ID':<5} {'Name':<20} {'API Key':<40} {'Active':<10}")
        print("-" * 80)
        
        for tenant in tenants:
            tenant_id, name, api_key, is_active = tenant
            print(f"{tenant_id:<5} {name:<20} {api_key:<40} {'Yes' if is_active else 'No':<10}")
        
        print("\nTo use a tenant API key with the chatbot, make sure:")
        print("1. The tenant is active (is_active = 1)")
        print("2. You're using the correct API key format with the 'X-API-Key' header")
        print("3. The tenant has at least one knowledge base or FAQ entry")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_tenants()
