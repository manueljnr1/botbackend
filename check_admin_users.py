# check_admin.py
from app.database import SessionLocal
from app.auth.models import User
from sqlalchemy import text

def check_user_admin_status(username):
    db = SessionLocal()
    try:
        # Query using SQLAlchemy ORM
        user = db.query(User).filter(User.username == username).first()
        
        if user:
            print(f"=== User: {user.username} ===")
            print(f"Admin status: {user.is_admin}")
            print(f"Active: {user.is_active}")
            print(f"Email: {user.email}")
            print(f"Tenant ID: {user.tenant_id}")
            return user.is_admin
        else:
            print(f"No user found with username: {username}")
            return False
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        db.close()

def list_all_admins():
    db = SessionLocal()
    try:
        # Query for all admin users
        admin_users = db.query(User).filter(User.is_admin == True).all()
        
        print("\n=== All Admin Users ===")
        if not admin_users:
            print("No admin users found in the database.")
            return
        
        for user in admin_users:
            print(f"Username: {user.username}, Email: {user.email}, Active: {user.is_active}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
        check_user_admin_status(username)
    else:
        print("Usage: python check_admin.py <username>")
        print("Listing all admins by default:")
        list_all_admins()