# app/chatbot/prompts.py
from string import Template
from .security import SecurityPromptManager

# Legacy system prompt template for backward compatibility
SYSTEM_PROMPT_TEMPLATE = Template("""
You are a helpful customer support assistant for $company_name.
You should be friendly, helpful, and professional at all times.

IMPORTANT INSTRUCTIONS:
1. ALWAYS check the Frequently Asked Questions first for any user question
2. If the question matches an FAQ, provide that answer directly
3. If no FAQ matches, use the knowledge base context to answer
4. NEVER mention "context", "knowledge base", "FAQs", or any internal system details to the customer
5. NEVER say "I don't know based on the context provided" - instead say "I don't have that information available"
6. Provide helpful, natural responses as if you naturally know this information
7. Do not give answers to questions outside the scope of customer support, some people may start asking general knowledge questions, its better you just tell them you wouldnt be answering that politely. but answer if its within the scope of tenant business
8. when you are exchanging greetings, do not quote your response, just say it naturally
                                  
                                

Frequently Asked Questions:
$faq_info

Guidelines for responses:
- Be conversational and natural
- Don't reference where information comes from
- If you don't have the information, politely say so and offer to connect them with a human agent
- Stay in character as a knowledgeable support representative
- Be concise but complete in your answers
""")

def build_secure_chatbot_prompt(
    tenant_prompt: str = None,
    company_name: str = "Your Company",
    faq_info: str = "",
    knowledge_base_info: str = ""
) -> str:
    """
    Build a complete chatbot prompt with central security + tenant customization
    
    This is the main function to use for generating chatbot prompts.
    It automatically includes security protections while allowing tenant customization.
    """
    return SecurityPromptManager.build_secure_prompt(
        tenant_prompt=tenant_prompt,
        company_name=company_name,
        faq_info=faq_info,
        knowledge_base_info=knowledge_base_info
    )

def validate_and_sanitize_tenant_prompt(tenant_prompt: str) -> tuple[str, bool, list[str]]:
    """
    Validate and sanitize a tenant's custom prompt
    
    Returns:
        (sanitized_prompt, is_valid, issues_found)
    """
    if not tenant_prompt:
        return "", True, []
    
    # Validate for security issues
    is_valid, issues = SecurityPromptManager.validate_tenant_prompt(tenant_prompt)
    
    # Sanitize the prompt
    sanitized = SecurityPromptManager._sanitize_tenant_prompt(tenant_prompt)
    
    return sanitized, is_valid, issues

def check_message_security(user_message: str, company_name: str) -> tuple[bool, str]:
    """
    Check if a user message is safe to process
    
    Returns:
        (is_safe, response_if_unsafe)
    """
    is_safe, risk_type = SecurityPromptManager.check_user_message_security(user_message)
    
    if not is_safe:
        decline_message = SecurityPromptManager.get_security_decline_message(risk_type, company_name)
        return False, decline_message
    
    return True, ""