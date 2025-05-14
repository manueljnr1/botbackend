#!/usr/bin/env python3
"""
Script to configure WhatsApp integration for a tenant
"""
import sqlite3
import os
import sys

def configure_whatsapp(tenant_id, phone_number):
    """Configure WhatsApp integration for a specific tenant"""
    db_path = os.path.join("chatbot.db")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenant exists
        cursor.execute("SELECT name, api_key FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"Error: Tenant with ID {tenant_id} not found")
            return False
        
        tenant_name, api_key = tenant
        
        # Create whatsapp_integrations table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_integrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            phone_number TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id),
            UNIQUE(tenant_id, phone_number)
        )
        """)
        
        # Check if integration already exists
        cursor.execute(
            "SELECT id FROM whatsapp_integrations WHERE tenant_id = ? AND phone_number = ?",
            (tenant_id, phone_number)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing integration
            cursor.execute(
                "UPDATE whatsapp_integrations SET is_active = 1 WHERE id = ?",
                (existing[0],)
            )
            print(f"Updated existing WhatsApp integration for phone {phone_number}")
        else:
            # Create new integration
            cursor.execute(
                "INSERT INTO whatsapp_integrations (tenant_id, phone_number) VALUES (?, ?)",
                (tenant_id, phone_number)
            )
            print(f"Created new WhatsApp integration for phone {phone_number}")
        
        conn.commit()
        
        # Set environment variable for Twilio integration (for the active script session)
        os.environ[f"WHATSAPP_NUMBER_{phone_number.replace('+', '')}_API_KEY"] = api_key
        
        print("\n==== WHATSAPP INTEGRATION SETUP ====")
        print(f"Tenant: {tenant_name} (ID: {tenant_id})")
        print(f"Phone Number: {phone_number}")
        print(f"API Key: {api_key}")
        print("")
        print("To complete WhatsApp setup with Twilio:")
        print("1. Create a Twilio account at https://www.twilio.com")
        print("2. Set up a WhatsApp Sandbox or Business Profile")
        print("3. Configure the Webhook URL:")
        print(f"   http://your-server-address/integrations/whatsapp/webhook")
        print("4. Add this line to your .env file:")
        print(f"   WHATSAPP_NUMBER_{phone_number.replace('+', '')}_API_KEY={api_key}")
        print("5. Set these environment variables:")
        print("   TWILIO_ACCOUNT_SID=your_account_sid")
        print("   TWILIO_AUTH_TOKEN=your_auth_token")
        print("==================================")
        
        return {
            "tenant_id": tenant_id,
            "phone_number": phone_number,
            "api_key": api_key
        }
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        return None
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python configure_whatsapp.py <tenant_id> <phone_number>")
        print("Example: python configure_whatsapp.py 1 +12025550123")
        sys.exit(1)
    
    tenant_id = int(sys.argv[1])
    phone_number = sys.argv[2]
    
    # Validate phone number format
    if not phone_number.startswith("+"):
        print("Phone number must be in international format, starting with + (e.g., +12025550123)")
        sys.exit(1)
    
    configure_whatsapp(tenant_id, phone_number)