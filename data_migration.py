# find_agent_references.py - Run this to find all agent relationship references
import os
import re

def find_agent_references():
    """Find all files with User.agent or agent relationship references"""
    
    # Files to check
    files_to_check = [
        "app/auth/models.py",
        "app/tenants/models.py", 
        "app/chatbot/models.py",
        "app/main.py"
    ]
    
    patterns_to_find = [
        r'agent\s*=\s*relationship',
        r'relationship\(["\']Agent["\']',
        r'back_populates=["\']agent["\']',
        r'User\.agent',
        r'user\.agent'
    ]
    
    found_issues = []
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"\n🔍 Checking {file_path}...")
            
            with open(file_path, 'r') as f:
                content = f.read()
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    for pattern in patterns_to_find:
                        if re.search(pattern, line, re.IGNORECASE):
                            found_issues.append({
                                'file': file_path,
                                'line': i,
                                'content': line.strip(),
                                'pattern': pattern
                            })
                            print(f"  ❌ Line {i}: {line.strip()}")
        else:
            print(f"⚠️  File not found: {file_path}")
    
    if found_issues:
        print(f"\n💥 Found {len(found_issues)} problematic references:")
        for issue in found_issues:
            print(f"  📁 {issue['file']}:{issue['line']} - {issue['content']}")
        
        print("\n🔧 TO FIX:")
        print("1. Comment out or delete these lines")
        print("2. Make sure NO User model has 'agent = relationship(...)'")
        print("3. Make sure NO Agent model has 'user = relationship(...)'")
    else:
        print("\n✅ No problematic agent references found!")
    
    return found_issues

def create_fixed_user_model():
    """Create a clean User model without agent relationships"""
    
    fixed_content = '''# app/auth/models.py - CLEAN VERSION WITHOUT AGENT RELATIONSHIP

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Safe relationships only
    tenant = relationship("Tenant", back_populates="users")
    
    # 🚫 NO AGENT RELATIONSHIP - REMOVED FOR COMPATIBILITY

class TenantCredentials(Base):
    __tablename__ = "tenant_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="credentials")
    
    print("\n📝 FIXED USER MODEL:")
    print("="*50)
    print(fixed_content)
    print("="*50)
    
    return fixed_content

if __name__ == "__main__":
    print("🔎 SEARCHING FOR PROBLEMATIC AGENT REFERENCES...")
    issues = find_agent_references()
    
    print("\n" + "="*60)
    create_fixed_user_model()
    
    if issues:
        print(f"\n🚨 ACTION REQUIRED: Fix {len(issues)} issues above")
    else:
        print("\n✅ ALL CLEAR! No issues found.")
'''