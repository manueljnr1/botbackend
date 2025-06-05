#!/usr/bin/env python3
"""
Script to debug Supabase connection and test user creation
"""
import os
import asyncio
from supabase import create_client
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_supabase_connection():
    """Test Supabase connection and permissions"""
    
    # Load environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    print("🔍 SUPABASE DEBUG TEST")
    print("=" * 50)
    
    # Check environment variables
    print("📋 Environment Check:")
    print(f"SUPABASE_URL: {'✅ Set' if supabase_url else '❌ Missing'}")
    print(f"SUPABASE_SERVICE_KEY: {'✅ Set' if supabase_service_key else '❌ Missing'}")
    
    if supabase_url:
        print(f"URL: {supabase_url[:30]}...")
    if supabase_service_key:
        print(f"Service Key: {supabase_service_key[:30]}...")
    
    if not supabase_url or not supabase_service_key:
        print("❌ Missing environment variables!")
        return
    
    try:
        # Create Supabase client
        print("\n🔄 Creating Supabase client...")
        supabase = create_client(supabase_url, supabase_service_key)
        print("✅ Client created successfully")
        
        # Test 1: List existing users (admin function)
        print("\n🔄 Testing admin permissions - listing users...")
        try:
            users_response = supabase.auth.admin.list_users()
            print(f"✅ Admin access working - found {len(users_response)} users")
            
            # Show existing users
            if hasattr(users_response, 'users') and users_response.users:
                print("📋 Existing users:")
                for user in users_response.users[:5]:  # Show first 5
                    print(f"  - {user.email} (ID: {user.id[:8]}...)")
            elif isinstance(users_response, list):
                print("📋 Existing users:")
                for user in users_response[:5]:  # Show first 5
                    email = getattr(user, 'email', 'No email')
                    user_id = getattr(user, 'id', 'No ID')
                    print(f"  - {email} (ID: {str(user_id)[:8]}...)")
            
        except Exception as e:
            print(f"❌ Admin access failed: {e}")
            return
        
        # Test 2: Try creating a test user
        print("\n🔄 Testing user creation...")
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPassword123!"
        
        try:
            create_response = supabase.auth.admin.create_user({
                "email": test_email,
                "password": test_password,
                "user_metadata": {
                    "display_name": "Test User",
                    "test_account": True
                }
            })
            
            print(f"✅ Test user creation successful!")
            test_user_id = create_response.user.id
            print(f"Test user ID: {test_user_id}")
            
            # Clean up test user
            print("🧹 Cleaning up test user...")
            delete_response = supabase.auth.admin.delete_user(test_user_id)
            print("✅ Test user cleaned up")
            
        except Exception as e:
            print(f"❌ User creation failed: {e}")
            print(f"Error type: {type(e).__name__}")
            
            # Check specific error types
            if "401" in str(e) or "Unauthorized" in str(e):
                print("🔍 This looks like an API key issue")
                print("  - Check if SUPABASE_SERVICE_KEY is correct")
                print("  - Make sure it's the SERVICE key, not the ANON key")
                print("  - Check if the key has admin permissions")
            elif "409" in str(e) or "already" in str(e).lower():
                print("🔍 User might already exist")
            elif "429" in str(e) or "rate" in str(e).lower():
                print("🔍 Rate limiting - too many requests")
        
        # Test 3: Check specific email
        print(f"\n🔄 Checking if 'Mega@gmail.com' exists in Supabase...")
        try:
            # Try to get user by email
            users = supabase.auth.admin.list_users()
            mega_user = None
            
            if hasattr(users, 'users'):
                for user in users.users:
                    if user.email == "Mega@gmail.com":
                        mega_user = user
                        break
            elif isinstance(users, list):
                for user in users:
                    if getattr(user, 'email', '') == "Mega@gmail.com":
                        mega_user = user
                        break
            
            if mega_user:
                print("⚠️ Found existing user with email 'Mega@gmail.com'")
                print(f"User ID: {mega_user.id}")
                print("This explains the 401 - email already exists!")
                
                # Offer to delete
                response = input("Delete this user? (y/n): ").lower()
                if response == 'y':
                    supabase.auth.admin.delete_user(mega_user.id)
                    print("✅ User deleted - try registration again!")
            else:
                print("✅ Email 'Mega@gmail.com' not found in Supabase")
                
        except Exception as e:
            print(f"❌ Email check failed: {e}")
            
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        print(f"Error type: {type(e).__name__}")

def check_env_file():
    """Check if .env file exists and has the right variables"""
    print("\n📁 Environment File Check:")
    
    env_files = ['.env', '.env.local', 'config/.env']
    found_env = False
    
    for env_file in env_files:
        if os.path.exists(env_file):
            print(f"✅ Found: {env_file}")
            found_env = True
            
            # Read and check contents
            try:
                with open(env_file, 'r') as f:
                    content = f.read()
                    
                if 'SUPABASE_URL' in content:
                    print("  ✅ Contains SUPABASE_URL")
                if 'SUPABASE_SERVICE_KEY' in content:
                    print("  ✅ Contains SUPABASE_SERVICE_KEY")
                if 'SUPABASE_ANON_KEY' in content:
                    print("  ℹ️ Contains SUPABASE_ANON_KEY (not needed for admin)")
                    
            except Exception as e:
                print(f"  ❌ Error reading file: {e}")
    
    if not found_env:
        print("❌ No .env file found")
        print("Create a .env file with:")
        print("SUPABASE_URL=https://your-project.supabase.co")
        print("SUPABASE_SERVICE_KEY=your_service_key_here")

async def main():
    print("🚀 Starting Supabase debugging...")
    check_env_file()
    await test_supabase_connection()
    
    print("\n" + "=" * 50)
    print("🎯 Next Steps:")
    print("1. If API key issues → Check your Supabase dashboard for the correct SERVICE key")
    print("2. If user exists → Use a different email or delete the existing user")
    print("3. If rate limited → Wait a few minutes and try again")
    print("4. If all good → Try registration again!")

if __name__ == "__main__":
    asyncio.run(main())