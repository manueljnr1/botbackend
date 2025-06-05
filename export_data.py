#!/usr/bin/env python3
"""
Export SQLite data to JSON for migration to PostgreSQL
Run this in your local environment where your SQLite database exists
"""

import json
import sys
from pathlib import Path

# Add your app directory to path
sys.path.append('.')

from app.database import SessionLocal
from app.tenants.models import Tenant
from app.auth.models import User, TenantCredentials
from app.chatbot.models import ChatSession, ChatMessage
from app.knowledge_base.models import KnowledgeBase
# Document model might not exist, we'll handle this safely
from app.admin.models import Admin

def export_data():
    db = SessionLocal()
    
    try:
        export_data = {
            'tenants': [],
            'users': [],
            'tenant_credentials': [],
            'admins': [],
            'chat_sessions': [],
            'chat_messages': [],
            'knowledge_bases': [],
            'documents': []
        }
        
        # Export Tenants
        tenants = db.query(Tenant).all()
        for tenant in tenants:
            export_data['tenants'].append({
                'id': tenant.id,
                'name': tenant.name,
                'email': tenant.email,
                'description': tenant.description,
                'api_key': tenant.api_key,
                'is_active': tenant.is_active,
                'system_prompt': tenant.system_prompt,
                'supabase_user_id': getattr(tenant, 'supabase_user_id', None),
                'feedback_email': getattr(tenant, 'feedback_email', None),
                'from_email': getattr(tenant, 'from_email', None),
                'enable_feedback_system': getattr(tenant, 'enable_feedback_system', True)
            })
        
        # Export Users
        users = db.query(User).all()
        for user in users:
            export_data['users'].append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'tenant_id': user.tenant_id,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None
            })
        
        # Export Tenant Credentials
        credentials = db.query(TenantCredentials).all()
        for cred in credentials:
            export_data['tenant_credentials'].append({
                'id': cred.id,
                'tenant_id': cred.tenant_id,
                'hashed_password': cred.hashed_password
            })
        
        # Export Admins
        admins = db.query(Admin).all()
        for admin in admins:
            export_data['admins'].append({
                'id': admin.id,
                'username': admin.username,
                'email': admin.email,
                'name': admin.name,
                'hashed_password': admin.hashed_password,
                'is_active': admin.is_active,
                'created_at': admin.created_at.isoformat() if admin.created_at else None
            })
        
        # Export Chat Sessions
        sessions = db.query(ChatSession).all()
        for session in sessions:
            export_data['chat_sessions'].append({
                'id': session.id,
                'tenant_id': session.tenant_id,
                'session_id': session.session_id,
                'created_at': session.created_at.isoformat() if session.created_at else None,
                'updated_at': session.updated_at.isoformat() if session.updated_at else None
            })
        
        # Export Chat Messages
        messages = db.query(ChatMessage).all()
        for message in messages:
            export_data['chat_messages'].append({
                'id': message.id,
                'session_id': message.session_id,
                'content': message.content,
                'role': message.role,
                'timestamp': message.timestamp.isoformat() if message.timestamp else None
            })
        
        # Export Knowledge Bases
        try:
            knowledge_bases = db.query(KnowledgeBase).all()
            for kb in knowledge_bases:
                export_data['knowledge_bases'].append({
                    'id': kb.id,
                    'tenant_id': kb.tenant_id,
                    'name': kb.name,
                    'description': kb.description,
                    'created_at': kb.created_at.isoformat() if kb.created_at else None
                })
        except Exception as e:
            print(f"Warning: Could not export knowledge bases: {e}")
        
        # Export Documents - safely handle if Document model doesn't exist
        try:
            from app.knowledge_base.models import Document
            documents = db.query(Document).all()
            for doc in documents:
                export_data['documents'].append({
                    'id': doc.id,
                    'knowledge_base_id': doc.knowledge_base_id,
                    'filename': doc.filename,
                    'content': doc.content,
                    'file_type': doc.file_type,
                    'upload_date': doc.upload_date.isoformat() if doc.upload_date else None
                })
        except (ImportError, Exception) as e:
            print(f"Info: Documents table not found or empty: {e}")
            export_data['documents'] = []
        
        # Save to file
        with open('database_export.json', 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print("✅ Data exported successfully to database_export.json")
        print(f"📊 Export summary:")
        for table, data in export_data.items():
            print(f"  - {table}: {len(data)} records")
            
    except Exception as e:
        print(f"❌ Export failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    export_data()