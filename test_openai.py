import os
from openai import OpenAI
from dotenv import load_dotenv

# 1. Load environment variables (expects .env file in the same directory or project root)
load_dotenv()

# 2. Get API key; exit if not found
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    exit("Error: OPENAI_API_KEY not found in environment variables. Check your .env file.")

# 3. Initialize client and make API call
try:
    client = OpenAI(api_key=api_key)
    print("Sending a simple prompt to OpenAI...")
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo", # Or "gpt-4o-mini"
        messages=[{"role": "user", "content": "Say: Hello World"}]
    )
    # 4. Print the response
    print(f"OpenAI: {completion.choices[0].message.content}")
except Exception as e: # 5. Basic error handling
    print(f"An API error occurred: {e}")