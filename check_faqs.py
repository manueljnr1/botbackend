#!/usr/bin/env python3
"""
Check if FAQs exist for a tenant
"""
import sqlite3
import os

def check_faqs():
    """Check if FAQs exist for a tenant"""
    try:
        # Connect to the database
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Get all tenants
        cursor.execute("SELECT id, name, api_key FROM tenants WHERE is_active = 1")
        tenants = cursor.fetchall()
        
        if not tenants:
            print("No active tenants found.")
            return
        
        print(f"Found {len(tenants)} active tenants:")
        
        for tenant in tenants:
            tenant_id, name, api_key = tenant
            print(f"\nTenant: {name} (ID: {tenant_id}, API Key: {api_key})")
            
            # Get FAQs for this tenant
            cursor.execute("SELECT id, question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
            faqs = cursor.fetchall()
            
            if not faqs:
                print("  No FAQs found for this tenant.")
                print("  You should add FAQs using the create_test_tenant.py script.")
            else:
                print(f"  Found {len(faqs)} FAQs:")
                for i, (faq_id, question, answer) in enumerate(faqs[:5], 1):
                    print(f"  {i}. Q: {question}")
                    print(f"     A: {answer[:50]}..." if len(answer) > 50 else f"     A: {answer}")
                
                if len(faqs) > 5:
                    print(f"  ... and {len(faqs) - 5} more")
            
            print("\nAPI Status:")
            print(f"  - This tenant {'has' if faqs else 'does not have'} FAQs")
            print(f"  - API Key to use: {api_key}")
            if faqs:
                print("  - The chatbot should work with this tenant")
            else:
                print("  - The chatbot will NOT work without FAQs")
                print("  - Run: python create_test_tenant.py")
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    check_faqs()