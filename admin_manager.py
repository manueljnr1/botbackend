#!/usr/bin/env python
import requests
import json
import argparse
import uuid
import getpass
import sys

class AdminManager:
    def __init__(self, base_url, token=None):
        """
        Initialize the AdminManager with API connection details
        
        Args:
            base_url (str): Base URL of the API
            token (str, optional): Admin access token for authorization
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
    
    def login(self, username, password):
        """
        Login to get an access token
        
        Args:
            username (str): Admin username or email
            password (str): Admin password
            
        Returns:
            bool: True if login successful, False otherwise
        """
        login_url = f"{self.base_url}/auth/login"
        
        form_data = {
            'username': username,
            'password': password
        }
        
        try:
            response = requests.post(login_url, data=form_data)
            
            if response.status_code == 200:
                data = response.json()
                
                if not data.get('is_admin', False):
                    print("❌ Login failed: User is not an admin")
                    return False
                
                self.token = data.get('access_token')
                self.headers["Authorization"] = f"Bearer {self.token}"
                print("✅ Successfully logged in as admin")
                return True
            else:
                print(f"❌ Login failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def create_admin(self, username, email, name, password):
        """
        Create a new admin user
        
        Args:
            username (str): Admin username
            email (str): Admin email
            name (str): Admin name
            password (str): Admin password
            
        Returns:
            dict: Created admin data or None if failed
        """
        create_url = f"{self.base_url}/admins"
        
        admin_data = {
            "username": username,
            "email": email,
            "name": name,
            "password": password
        }
        
        try:
            response = requests.post(create_url, json=admin_data, headers=self.headers)
            
            if response.status_code in (200, 201):
                created_admin = response.json()
                print(f"✅ Admin successfully created")
                return created_admin
            else:
                print(f"❌ Admin creation failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Admin creation error: {e}")
            return None
    
    def delete_admin(self, admin_id):
        """
        Delete an admin user by ID
        
        Args:
            admin_id (str): ID of the admin to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        delete_url = f"{self.base_url}/admins/{admin_id}"
        
        try:
            response = requests.delete(delete_url, headers=self.headers)
            
            if response.status_code in (200, 204):
                print(f"✅ Admin successfully deleted")
                return True
            else:
                print(f"❌ Admin deletion failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Admin deletion error: {e}")
            return False
    
    def list_admins(self):
        """
        List all admin users
        
        Returns:
            list: List of admin users or None if failed
        """
        list_url = f"{self.base_url}/admins"
        
        try:
            response = requests.get(list_url, headers=self.headers)
            
            if response.status_code == 200:
                admins = response.json()
                return admins
            else:
                print(f"❌ Listing admins failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Listing admins error: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="Manage admin users")
    
    # Base parameters
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    
    # Auth parameters
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument("--token", help="Admin access token (if not provided, login will be required)")
    auth_group.add_argument("--username", help="Admin username for login")
    auth_group.add_argument("--password", help="Admin password for login")
    
    # Subcommands for different operations
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create admin command
    create_parser = subparsers.add_parser("create", help="Create a new admin user")
    create_parser.add_argument("--admin-username", required=True, help="Username for the new admin")
    create_parser.add_argument("--admin-email", required=True, help="Email for the new admin")
    create_parser.add_argument("--admin-name", required=True, help="Name for the new admin")
    create_parser.add_argument("--admin-password", help="Password for the new admin (if not provided, will prompt)")
    
    # Delete admin command
    delete_parser = subparsers.add_parser("delete", help="Delete an admin user")
    delete_parser.add_argument("--admin-id", required=True, help="ID of the admin to delete")
    
    # List admins command
    list_parser = subparsers.add_parser("list", help="List all admin users")
    
    args = parser.parse_args()
    
    # Create admin manager
    admin_manager = AdminManager(args.url, args.token)
    
    # Login if token not provided
    if not args.token:
        if not args.username:
            args.username = input("Enter admin username: ")
        
        if not args.password:
            args.password = getpass.getpass("Enter admin password: ")
        
        if not admin_manager.login(args.username, args.password):
            sys.exit(1)
    
    # Execute the requested command
    if args.command == "create":
        admin_password = args.admin_password
        if not admin_password:
            admin_password = getpass.getpass("Enter password for new admin: ")
            password_confirm = getpass.getpass("Confirm password: ")
            
            if admin_password != password_confirm:
                print("❌ Passwords do not match")
                sys.exit(1)
        
        created_admin = admin_manager.create_admin(
            username=args.admin_username,
            email=args.admin_email,
            name=args.admin_name,
            password=admin_password
        )
        
        if created_admin:
            print("\n📋 Created Admin Details:")
            print(json.dumps(created_admin, indent=4))
    
    elif args.command == "delete":
        confirm = input(f"Are you sure you want to delete admin with ID {args.admin_id}? (y/N): ")
        if confirm.lower() == 'y':
            admin_manager.delete_admin(args.admin_id)
        else:
            print("Deletion cancelled")
    
    elif args.command == "list":
        admins = admin_manager.list_admins()
        if admins:
            print("\n📋 Admin Users:")
            print(json.dumps(admins, indent=4))
            print(f"\nTotal: {len(admins)} admin users")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()