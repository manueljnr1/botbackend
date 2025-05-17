# from langchain_community.chat_models import ChatOpenAI
# from langchain.chains import ConversationalRetrievalChain
# from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
# from langchain.memory import ConversationBufferMemory
# from langchain.prompts import PromptTemplate, ChatPromptTemplate
# from typing import Any, List, Dict

# from app.config import settings # For OPENAI_API_KEY
# from app.chatbot.prompts import SYSTEM_PROMPT_TEMPLATE # Your string.Template object

# # Standard prompt for condensing the current question and chat history into a standalone question
# _template = """Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question, in its original language.

# Chat History:
# {chat_history}
# Follow Up Input: {question}
# Standalone question:"""
# CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(_template)

# def create_chatbot_chain(
#     vector_store: Any, # Expects a LangChain VectorStore object
#     tenant_name: str,
#     faq_list: Optional[List[Dict[str, str]]] = None
# ) -> Any:
#     """
#     Create a proper LangChain RAG (Retrieval Augmented Generation) chain.
#     This chain uses a vector store for document retrieval, an LLM for generation,
#     and incorporates FAQs and tenant information into its context.
#     It also maintains conversation history.
#     """

#     # 1. Initialize the LLM (ChatOpenAI)
#     # Using settings similar to what's in your engine.py for consistency
#     llm = ChatOpenAI(
#         model_name="gpt-4",  # Or your preferred model
#         temperature=0.7,
#         openai_api_key=settings.OPENAI_API_KEY
#     )

#     # 2. Create a retriever from the vector_store
#     # You can configure search_kwargs, e.g., k=3 to retrieve top 3 documents
#     retriever = vector_store.as_retriever(search_kwargs={"k": 3})

#     # 3. Initialize ConversationBufferMemory for chat history
#     # The ConversationalRetrievalChain will use the 'answer' key for the AI's response.
#     memory = ConversationBufferMemory(
#         memory_key="chat_history",
#         return_messages=True, # Returns history as a list of messages
#         output_key='answer'   # Ensures AI's response is stored correctly in history
#     )

#     # 4. Format the FAQ list into a string for the prompt
#     if faq_list and len(faq_list) > 0:
#         faq_info_string = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faq_list])
#     else:
#         faq_info_string = "No FAQs are currently available for this topic."

#     # 5. Prepare the main QA prompt (for the combine_docs_chain part of ConversationalRetrievalChain)
#     # This prompt guides the LLM on how to answer using the retrieved documents and FAQs.
#     # We'll use your SYSTEM_PROMPT_TEMPLATE.
#     # The {context} placeholder will be filled by LangChain with retrieved documents.
#     # The {question} placeholder will be filled with the standalone question.

#     # Substitute known values into your system prompt template string
#     # $knowledge_base_info will be replaced by the {context} (retrieved documents)
#     # $faq_info is filled with our formatted FAQ string
#     # $company_name is filled with tenant_name
#     system_message_content_template = SYSTEM_PROMPT_TEMPLATE.template.replace(
#         "$company_name", tenant_name
#     ).replace(
#         "$faq_info", faq_info_string
#     ).replace(
#         "$knowledge_base_info", "{context}" # This is where retrieved docs will go
#     )
    
#     # Create the prompt template for the QA step (answering the question based on context)
#     qa_prompt = ChatPromptTemplate.from_messages([
#         ("system", system_message_content_template),
#         ("human", "{question}")
#     ])

#     # 6. Instantiate ConversationalRetrievalChain
#     # This chain handles:
#     #   - Taking user question and chat history.
#     #   - Condensing them into a standalone question (using CONDENSE_QUESTION_PROMPT).
#     #   - Retrieving relevant documents from the vector_store using the standalone question.
#     #   - Passing the documents (as 'context') and standalone question to the LLM (with qa_prompt) to generate an answer.
#     #   - Storing the interaction in memory.
#     chain = ConversationalRetrievalChain.from_llm(
#         llm=llm,
#         retriever=retriever,
#         memory=memory,
#         condense_question_prompt=CONDENSE_QUESTION_PROMPT,
#         combine_docs_chain_kwargs={"prompt": qa_prompt},
#         return_source_documents=False, # Set to True if you want to see which docs were retrieved
#         verbose=True # Set to False in production if too noisy
#     )

#     return chain


from typing import List, Dict, Any, Optional
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.conversational_retrieval.base import BaseConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from app.config import settings

def create_chatbot_chain(
    vector_store,
    tenant_name: str,
    faq_list: list = None,
    custom_system_prompt: str = None  # Add parameter for custom prompt
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
            company_name=tenant_name,
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