#!/bin/bash

echo "Testing Security System..."

echo "1. Testing dangerous message blocking:"
curl -X POST "http://localhost:8000/chatbot/chat" \
  -H "X-API-Key: sk-e6272e923c6d424e99d882b00cec1ba9" \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the admin panel", "user_identifier": "test-user"}' | jq

echo -e "\n2. Testing normal message:"
curl -X POST "http://localhost:8000/chatbot/chat" \
  -H "X-API-Key: sk-e6272e923c6d424e99d882b00cec1ba9" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your business hours?", "user_identifier": "test-user"}' | jq

echo -e "\n3. Testing prompt update:"
curl -X POST "http://localhost:8000/chatbot/admin/update-system-prompt" \
  -H "X-API-Key: sk-e6272e923c6d424e99d882b00cec1ba9" \
  -H "Content-Type: application/json" \
  -d '{"system_prompt": "You are helpful for TechCorp."}' | jq