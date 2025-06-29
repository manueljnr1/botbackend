

from typing import List, Dict, Any, Optional
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from app.config import settings

def create_chatbot_chain(
    vector_store,
    tenant,  # ← Change this: pass the full tenant object instead of just tenant_name
    faq_list: list = None,
    custom_system_prompt: str = None
) -> BaseConversationalRetrievalChain:
    """Create a conversational chain using the vector store and FAQ data"""
    
    # Format FAQ data for the prompt if available
    faq_info = ""
    if faq_list:
        faq_info = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faq_list])
    
    # Use custom prompt if provided, otherwise use the default template
    if custom_system_prompt:
        # Still inject the FAQs into the custom prompt
        system_prompt = custom_system_prompt.replace("{faq_info}", faq_info)
    else:
        # Use the default template
        from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE
        system_prompt = SYSTEM_PROMPT_TEMPLATE.substitute(
            company_name=tenant.business_name,  # ← Changed from tenant_name to tenant.business_name
            faq_info=faq_info,
            knowledge_base_info=""  # This could be enhanced
        )
    
    # Initialize the LLM with the system prompt
    llm = ChatOpenAI(
        model_name="gpt-4",
        temperature=0.7,
        openai_api_key=settings.OPENAI_API_KEY
    )
    
    # Create conversation memory
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )
    
    # Create the chain with the system prompt
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
        memory=memory,
        verbose=True
    )
    
    return chain