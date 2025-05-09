from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.chatbot.engine import ChatbotEngine
from app.database import get_db
import json

def register_webhook_routes(app: FastAPI):
    """Register generic webhook routes for custom integrations"""
    
    @app.post("/integrations/webhook/chat")
    async def handle_webhook_chat(request: Request, db: Session = Depends(get_db)):
        # Parse the request
        try:
            data = await request.json()
        except:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Validate required fields
        required_fields = ["api_key", "message", "user_identifier"]
        for field in required_fields:
            if field not in data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Process the message
        engine = ChatbotEngine(db)
        result = engine.process_message(
            data["api_key"],
            data["message"],
            data["user_identifier"]
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        
        return result