# Replace this:
openai_api_key = "sk-..."

# With this:
import os
openai_api_key = os.getenv("OPENAI_API_KEY")
