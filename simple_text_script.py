#!/usr/bin/env python3
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/sms", methods=['POST'])
def sms_reply():
    """Respond to incoming WhatsApp messages with a simple echo."""
    # Get the message the user sent
    body = request.values.get('Body', '')
    
    # Create a response
    resp = MessagingResponse()
    resp.message(f"You said: {body}")
    
    print(f"Received message: {body}")
    print(f"Sending response: You said: {body}")
    
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)