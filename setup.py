#!/usr/bin/env python3
"""
Setup script for the Multi-Tenant Chatbot project.
This script creates the necessary directories and initializes the database.
"""
import os
import sys
import shutil
from pathlib import Path
import uuid

# Create necessary directories
def create_directories():
    print("Creating necessary directories...")
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("vector_db", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

# Create .env file from example
def create_env_file():
    if not os.path.exists(".env"):
        print("Creating .env file from .env.example...")
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            print("Please edit the .env file with your actual values")
        else:
            print("Warning: .env.example not found. You'll need to create a .env file manually.")
    else:
        print(".env file already exists")

# Create a default admin API key
def create_default_api_key():
    with open(".env", "a") as f:
        api_key = f"sk-{str(uuid.uuid4()).replace('-', '')}"
        f.write(f"\n# Generated API key\nDEFAULT_API_KEY={api_key}\n")
        print(f"Generated default API key: {api_key}")

# Initialize the database
def init_database():
    print("Initializing database...")
    # This will be a sqlalchemy operation to create all tables
    # For now, just import the models to ensure they're registered
    from app.database import Base, engine
    Base.metadata.create_all(bind=engine)
    print("Database initialized")

def main():
    print("Setting up Multi-Tenant Chatbot...")
    create_directories()
    create_env_file()
    
    # Only create API key if .env exists
    if os.path.exists(".env"):
        create_default_api_key()
    
    try:
        init_database()
    except Exception as e:
        print(f"Error initializing database: {e}")
        print("Make sure you've set up your environment properly")
        sys.exit(1)
    
    print("\nSetup complete!")
    print("To start the application, run: uvicorn app.main:app --reload")

if __name__ == "__main__":
    main()