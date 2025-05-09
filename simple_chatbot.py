# simple_chatbot.py
import os
from dotenv import load_dotenv
import sqlite3
from langchain_community.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalChain
from langchain.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

# Check OpenAI API key
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("Error: OPENAI_API_KEY environment variable not set")
    exit(1)

print(f"Using OpenAI API key: {openai_api_key[:5]}...{openai_api_key[-4:]}")

# Connect to database and get FAQs
def get_faqs():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    
    # Get tenant
    cursor.execute("SELECT id, name FROM tenants WHERE name = 'Test Tenant'")
    tenant = cursor.fetchone()
    
    if not tenant:
        print("Error: Test Tenant not found")
        conn.close()
        return None, []
    
    tenant_id, tenant_name = tenant
    
    # Get FAQs
    cursor.execute("SELECT question, answer FROM faqs WHERE tenant_id = ?", (tenant_id,))
    faqs = cursor.fetchall()
    
    conn.close()
    
    return tenant_name, faqs

# Get FAQs
tenant_name, faqs = get_faqs()
if not tenant_name:
    exit(1)

print(f"Tenant: {tenant_name}")
print(f"Found {len(faqs)} FAQs")

# Format FAQs for the prompt
faq_text = ""
for question, answer in faqs:
    faq_text += f"Q: {question}\nA: {answer}\n\n"

# Create a chat model
llm = ChatOpenAI(
    model_name="gpt-4",
    temperature=0.7,
    openai_api_key=openai_api_key
)

# Create a conversation memory
memory = ConversationBufferMemory()

# Create a prompt template
template = f"""
You are a helpful customer support assistant for {tenant_name}. 
You should be friendly, helpful, and professional at all times.

Here are some frequently asked questions you can reference:
{faq_text}

If the user's question is similar to one of these FAQs, use that information.
If you don't know the answer based on the provided information, 
just say that you don't have that information.
conversation = """

while True:
    # Get user input
    user_input = input("You: ")
    
    # Check for exit command
    if user_input.lower() in ['exit', 'quit', 'bye']:
        print("Chatbot: Goodbye! Have a nice day.")
        break
    
    # Add to conversation
    conversation += f"\nHuman: {user_input}\nAssistant: "
    
    # Generate response
    try:
        # Prepare the prompt
        prompt = template + conversation
        
        # Generate response
        response = llm.predict(prompt)
        
        # Add to conversation
        conversation += response
        
        # Print response
        print(f"Chatbot: {response}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()