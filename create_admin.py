#!/usr/bin/env python3
"""
Simplified script to create an admin user for the chatbot application
"""
import sqlite3
from getpass import getpass
from passlib.context import CryptContext
import os

# Initialize password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def create_admin_user():
    """Create an admin user directly in the database"""
    print("Creating admin user...")
    
    # Get user input
    email = input("Email: ")
    username = input("Username: ")
    password = getpass("Password: ")
    confirm_password = getpass("Confirm password: ")
    
    # Validate input
    if not email or not username or not password:
        print("Error: All fields are required")
        return
    
    if password != confirm_password:
        print("Error: Passwords do not match")
        return
    
    # Hash the password
    hashed_password = get_password_hash(password)
    
    # Connect to the database
    db_path = os.path.join("chatbot.db")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the users table exists, create it if it doesn't
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            is_admin BOOLEAN NOT NULL DEFAULT 0,
            tenant_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants (id)
        )
        """)
        
        # Check if user already exists
        cursor.execute(
            "SELECT * FROM users WHERE email = ? OR username = ?",
            (email, username)
        )
        existing_user = cursor.fetchone()
        
        if existing_user:
            print("Error: A user with that email or username already exists")
            return
        
        # Insert the admin user
        cursor.execute(
            """
            INSERT INTO users (email, username, hashed_password, is_active, is_admin)
            VALUES (?, ?, ?, 1, 1)
            """,
            (email, username, hashed_password)
        )
        
        conn.commit()
        print(f"Admin user '{username}' created successfully!")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error creating admin user: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_admin_user()