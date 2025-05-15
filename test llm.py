# import os
# from openai import OpenAI

# client = OpenAI(api_key="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")

# try:
#     # Create a chat completion
#     response = client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=[{"role": "user", "content": "Hello!"}]
#     )
#     # Print the assistant's reply
#     print(response.choices[0].message.content)
# except Exception as e:
#     print(f"Error: {e}")


import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
# This is good practice for local development.
# In production, you'd typically set environment variables directly in your deployment environment.
load_dotenv()

# Retrieve the API key from an environment variable
# The variable name 'OPENAI_API_KEY' is a common convention,
# and it matches what's used in your `env.py` and potentially `app.config.settings`.
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("Error: The OPENAI_API_KEY environment variable is not set.")
    # You might want to exit or raise an exception here in a real application
    exit()

# Initialize the OpenAI client with the API key from the environment
client = OpenAI(api_key=api_key)

try:
    # Create a chat completion
    print("Sending request to OpenAI API...")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Or any other model you prefer
        messages=[{"role": "user", "content": "Hello!"}]
    )
    # Print the assistant's reply
    print("Assistant's reply:", response.choices[0].message.content)
except Exception as e:
    print(f"Error communicating with OpenAI API: {e}")