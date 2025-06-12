#!/usr/bin/env python3
"""
Sample script to create a test agent
Run this after the migration is complete
"""

import sys
import os

# Add your project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import get_db
from app.live_chat.models import Agent, AgentStatus

def create_test_agent():
    """Create a test agent for testing"""
    db = next(get_db())
    
    try:
        # Check if agent already exists
        existing_agent = db.query(Agent).filter(Agent.email == "test@example.com").first()
        if existing_agent:
            print(f"✅ Test agent already exists: {existing_agent.name} (ID: {existing_agent.id})")
            return existing_agent.id
        
        # Create new agent
        agent = Agent(
            tenant_id=1,  # Update this to match your tenant ID
            name="Test Agent",
            email="test@example.com",
            department="general",
            status=AgentStatus.OFFLINE,
            is_active=True,
            max_concurrent_chats=3
        )
        
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
        print(f"✅ Test agent created: {agent.name} (ID: {agent.id})")
        print(f"   Email: {agent.email}")
        print(f"   Department: {agent.department}")
        print(f"   Status: {agent.status}")
        
        return agent.id
        
    except Exception as e:
        print(f"❌ Error creating test agent: {e}")
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    create_test_agent()
