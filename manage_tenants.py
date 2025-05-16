"""
Script to create tenants with custom details
"""
import os
import sys
import uuid
import sqlite3
import argparse
from datetime import datetime

def create_tenant(name, description=None, api_key=None, is_active=True):
    """
    Create a new tenant in the database
    
    Args:
        name: Name of the tenant
        description: Description of the tenant (optional)
        api_key: API key for the tenant (optional, auto-generated if not provided)
        is_active: Whether the tenant is active (default: True)
    
    Returns:
        dict: Tenant information
    """
    # Connect to the database
    db_path = os.path.join(os.getcwd(), "chatbot.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return None
    
    # Generate API key if not provided
    if not api_key:
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if a tenant with this name already exists
        cursor.execute("SELECT id, name, api_key FROM tenants WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            print(f"Warning: Tenant with name '{name}' already exists (ID: {existing[0]})")
            
            choice = input("Do you want to update this tenant? (y/n): ").lower()
            if choice != 'y':
                print("Operation cancelled.")
                conn.close()
                return None
            
            # Update existing tenant
            cursor.execute(
                "UPDATE tenants SET description = ?, api_key = ?, is_active = ? WHERE id = ?",
                (description, api_key, is_active, existing[0])
            )
            tenant_id = existing[0]
            print(f"Updated tenant {name} (ID: {tenant_id})")
        else:
            # Insert new tenant
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO tenants (name, description, api_key, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, description, api_key, is_active, now)
            )
            tenant_id = cursor.lastrowid
            print(f"Created new tenant {name} (ID: {tenant_id})")
        
        conn.commit()
        
        # Get tenant info
        cursor.execute("SELECT id, name, description, api_key, is_active FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        conn.close()
        
        if tenant:
            tenant_info = {
                "id": tenant[0],
                "name": tenant[1],
                "description": tenant[2],
                "api_key": tenant[3],
                "is_active": bool(tenant[4])
            }
            return tenant_info
        
        return None
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
        return None
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def list_tenants():
    """List all tenants in the database"""
    # Connect to the database
    db_path = os.path.join(os.getcwd(), "chatbot.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tenants
        cursor.execute("SELECT id, name, description, api_key, is_active FROM tenants")
        tenants = cursor.fetchall()
        conn.close()
        
        if not tenants:
            print("No tenants found in the database.")
            return []
        
        print(f"Found {len(tenants)} tenants:")
        print("-" * 90)
        print(f"{'ID':<5} {'Name':<20} {'Description':<30} {'API Key':<25} {'Active':<5}")
        print("-" * 90)
        
        tenant_list = []
        for tenant in tenants:
            tenant_id, name, description, api_key, is_active = tenant
            description = description or ""
            if len(description) > 27:
                description = description[:24] + "..."
            print(f"{tenant_id:<5} {name:<20} {description:<30} {api_key[:22]+'...':<25} {'Yes' if is_active else 'No':<5}")
            
            tenant_list.append({
                "id": tenant_id,
                "name": name,
                "description": description,
                "api_key": api_key,
                "is_active": bool(is_active)
            })
        
        return tenant_list
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def deactivate_tenant(tenant_id):
    """Deactivate a tenant by ID"""
    # Connect to the database
    db_path = os.path.join(os.getcwd(), "chatbot.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenant exists
        cursor.execute("SELECT name FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"Error: Tenant with ID {tenant_id} not found")
            return False
        
        # Deactivate tenant
        cursor.execute("UPDATE tenants SET is_active = 0 WHERE id = ?", (tenant_id,))
        conn.commit()
        
        print(f"Deactivated tenant {tenant[0]} (ID: {tenant_id})")
        return True
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def activate_tenant(tenant_id):
    """Activate a tenant by ID"""
    # Connect to the database
    db_path = os.path.join(os.getcwd(), "chatbot.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tenant exists
        cursor.execute("SELECT name FROM tenants WHERE id = ?", (tenant_id,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"Error: Tenant with ID {tenant_id} not found")
            return False
        
        # Activate tenant
        cursor.execute("UPDATE tenants SET is_active = 1 WHERE id = ?", (tenant_id,))
        conn.commit()
        
        print(f"Activated tenant {tenant[0]} (ID: {tenant_id})")
        return True
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def interactive_mode():
    """Interactive mode for tenant management"""
    print("=== Tenant Management Tool ===")
    
    while True:
        print("\nOptions:")
        print("1. List all tenants")
        print("2. Create a new tenant")
        print("3. Activate a tenant")
        print("4. Deactivate a tenant")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-4): ")
        
        if choice == "0":
            print("Exiting...")
            break
        
        elif choice == "1":
            list_tenants()
        
        elif choice == "2":
            name = input("Enter tenant name: ")
            description = input("Enter tenant description (optional): ")
            
            custom_api_key = input("Enter custom API key (leave blank for auto-generated): ")
            api_key = custom_api_key if custom_api_key else None
            
            tenant = create_tenant(name, description, api_key)
            if tenant:
                print("\nTenant created successfully:")
                print(f"ID: {tenant['id']}")
                print(f"Name: {tenant['name']}")
                print(f"Description: {tenant['description']}")
                print(f"API Key: {tenant['api_key']}")
                print(f"Active: {'Yes' if tenant['is_active'] else 'No'}")
        
        elif choice == "3":
            tenant_id = input("Enter tenant ID to activate: ")
            try:
                tenant_id = int(tenant_id)
                activate_tenant(tenant_id)
            except ValueError:
                print("Error: Tenant ID must be a number")
        
        elif choice == "4":
            tenant_id = input("Enter tenant ID to deactivate: ")
            try:
                tenant_id = int(tenant_id)
                deactivate_tenant(tenant_id)
            except ValueError:
                print("Error: Tenant ID must be a number")
        
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Tenant management tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all tenants")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new tenant")
    create_parser.add_argument("name", help="Tenant name")
    create_parser.add_argument("--description", "-d", help="Tenant description")
    create_parser.add_argument("--api-key", "-k", help="Custom API key (auto-generated if not provided)")
    create_parser.add_argument("--inactive", action="store_true", help="Create tenant as inactive")
    
    # Activate command
    activate_parser = subparsers.add_parser("activate", help="Activate a tenant")
    activate_parser.add_argument("tenant_id", type=int, help="Tenant ID")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate a tenant")
    deactivate_parser.add_argument("tenant_id", type=int, help="Tenant ID")
    
    # Interactive mode
    interactive_parser = subparsers.add_parser("interactive", help="Run in interactive mode")
    
    args = parser.parse_args()
    
    # Run appropriate command
    if args.command == "list":
        list_tenants()
    
    elif args.command == "create":
        tenant = create_tenant(
            args.name,
            args.description,
            args.api_key,
            not args.inactive
        )
        
        if tenant:
            print("\nTenant created successfully:")
            print(f"ID: {tenant['id']}")
            print(f"Name: {tenant['name']}")
            print(f"Description: {tenant['description']}")
            print(f"API Key: {tenant['api_key']}")
            print(f"Active: {'Yes' if tenant['is_active'] else 'No'}")
    
    elif args.command == "activate":
        activate_tenant(args.tenant_id)
    
    elif args.command == "deactivate":
        deactivate_tenant(args.tenant_id)
    
    elif args.command == "interactive":
        interactive_mode()
    
    else:
        # Default to interactive mode if no command specified
        interactive_mode()
