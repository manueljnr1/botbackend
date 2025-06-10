#!/usr/bin/env python3
"""
Create a test feedback record in your LIVE PostgreSQL database
"""

import psycopg2
import uuid
from datetime import datetime

def create_live_test_feedback():
    """Create test feedback in live PostgreSQL database"""
    try:
        # Connect to your LIVE PostgreSQL database
        conn = psycopg2.connect(
            "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"
        )
        cursor = conn.cursor()
        
        print("🔗 Creating test feedback in LIVE database...")
        
        # Generate test feedback ID
        test_feedback_id = str(uuid.uuid4())
        
        # Create test feedback record
        insert_sql = """
        INSERT INTO pending_feedback (
            feedback_id, tenant_id, user_email, user_question, 
            bot_response, status, created_at, form_accessed, form_expired
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_sql, (
            test_feedback_id,
            1,  # Use tenant_id 1 - change if needed
            "test@example.com",
            "What are your business hours for customer support?",
            "I don't have that information available.",
            "pending",
            datetime.utcnow(),
            False,
            False
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Live test feedback created!")
        print(f"🔗 LIVE Test URL: https://botbackend-qtbf.onrender.com/chatbot/feedback/form/{test_feedback_id}")
        print(f"📋 Feedback ID: {test_feedback_id}")
        
        # Also print the curl command
        print(f"\n📱 Test with curl:")
        print(f"curl -X GET https://botbackend-qtbf.onrender.com/chatbot/feedback/form/{test_feedback_id}")
        
        return test_feedback_id
        
    except Exception as e:
        print(f"❌ Error creating live test feedback: {e}")
        return None

if __name__ == "__main__":
    print("🌍 Creating test feedback for LIVE database...")
    create_live_test_feedback()