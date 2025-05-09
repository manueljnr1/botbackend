from app.config import settings
from typing import Any

def create_chatbot_chain(
    vector_store,
    tenant_name: str,
    faq_list: list = None
) -> Any:
    """Create a simplified chatbot chain for deployment"""
    
    # This is a simplified version that doesn't rely on LangChain
    # It will just use the FAQ list for answering questions
    
    class SimpleChatbotChain:
        def __init__(self, tenant_name, faq_list):
            self.tenant_name = tenant_name
            self.faq_list = faq_list or []
            self.chat_history = []
        
        def __call__(self, inputs):
            question = inputs.get("question", "")
            
            # Add to chat history
            self.chat_history.append({"question": question})
            
            # Simple FAQ matching
            response = "I'm sorry, I don't have information about that. Here are some topics I can help with:\n\n"
            
            # Add topics
            if self.faq_list:
                topics = [faq['question'] for faq in self.faq_list[:5]]
                response += "- " + "\n- ".join(topics)
            
            # Try to find a matching FAQ
            for faq in self.faq_list:
                if any(keyword.lower() in question.lower() for keyword in faq['question'].lower().split()):
                    response = faq['answer']
                    break
            
            # Add to chat history
            self.chat_history.append({"answer": response})
            
            return {"answer": response}
    
    return SimpleChatbotChain(tenant_name, faq_list)