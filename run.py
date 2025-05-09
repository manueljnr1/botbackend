#!/usr/bin/env python3
"""
Run the chatbot application with proper Python path setup
"""
import os
import sys
import uvicorn

# Add the current directory to the Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_dir)

# Verify app module can be imported
try:
    import app
    print(f"✅ App module found at: {app.__file__}")
except ImportError as e:
    print(f"❌ Error importing app module: {e}")
    sys.exit(1)

# Verify SQLite database
if not os.path.exists("chatbot.db"):
    print("⚠️  Warning: chatbot.db not found. Make sure to run create_test_tenant.py first.")

print("📁 Project directory:", project_dir)
print("🐍 Python path:", sys.path)
print("📋 Starting application...")

# Run the application
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)