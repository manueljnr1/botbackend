from fastapi import FastAPI

def setup_integrations(app: FastAPI):
    """Set up all integrations"""
    try:
        from app.integrations.slack import register_slack_routes
        from app.integrations.whatsapp import register_whatsapp_routes
        from app.integrations.webhook import register_webhook_routes
        
        register_slack_routes(app)
        register_whatsapp_routes(app)
        register_webhook_routes(app)
    except ImportError as e:
        print(f"Warning: Could not load all integrations: {e}")
        # Continue without failing if some integrations are missing
        pass