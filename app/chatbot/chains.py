from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from app.config import settings

def create_chatbot_chain(
    vector_store,
    tenant_name: str,
    faq_list: list = None
) -> BaseConversationalRetrievalChain:
    """Create a conversational chain using the vector store and FAQ data"""
    
    # Format FAQ data for the prompt if available
    faq_info = ""
    if faq_list:
        faq_info = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faq_list])
    
    # Initialize the LLM
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
    
    # Create the chain
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vector_store.as_retriever(search_kwargs={"k": 3}),
        memory=memory,
        verbose=True
    )
    
    return chain