from fastapi import FastAPI, Request, HTTPException
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from app.chatbot.engine import ChatbotEngine
from app.database import SessionLocal
import json
import os

def register_slack_routes(app: FastAPI):
    """Register Slack integration routes"""
    
    @app.post("/integrations/slack/events")
    async def handle_slack_events(request: Request):
        # Verify the request
        signature_verifier = SignatureVerifier(os.getenv("SLACK_SIGNING_SECRET"))
        headers = request.headers
        body = await request.body()
        
        if not signature_verifier.is_valid(body, headers.get("X-Slack-Request-Timestamp"), headers.get("X-Slack-Signature")):
            raise HTTPException(status_code=403, detail="Invalid request signature")
        
        # Parse request body
        data = json.loads(body)
        
        # Handle URL verification challenge
        if data.get("type") == "url_verification":
            return {"challenge": data.get("challenge")}
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event")
            
            # Only respond to message events from users (not bots)
            if event.get("type") == "message" and not event.get("bot_id"):
                # Get tenant API key from Slack team/app config
                api_key = get_api_key_for_slack_team(data.get("team_id"))
                if not api_key:
                    return {"error": "No API key configured for this team"}
                
                # Process the message
                db = SessionLocal()
                try:
                    engine = ChatbotEngine(db)
                    user_identifier = event.get("user")
                    message = event.get("text")
                    
                    result = engine.process_message(api_key, message, user_identifier)
                    
                    if result.get("success"):
                        # Post response back to Slack
                        client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
                        client.chat_postMessage(
                            channel=event.get("channel"),
                            thread_ts=event.get("ts"),  # Reply in thread
                            text=result.get("response")
                        )
                finally:
                    db.close()
        
        return {"status": "ok"}


def get_api_key_for_slack_team(team_id: str) -> str:
    """Get API key for a Slack team - implement based on your configuration"""
    # This should be configured per Slack team/workspace
    # You might want to store this in the database or configuration
    # For now, returning a default value
    return os.getenv(f"SLACK_TEAM_{team_id}_API_KEY", os.getenv("DEFAULT_API_KEY"))