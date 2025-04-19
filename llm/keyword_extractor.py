from pydantic import ValidationError
from typing import Dict, List, Optional

# Assuming schemas and utils are in the same directory or adjust import path
from .schemas import KeywordSchema
from .llm_utils import call_llm_for_json

def extract_keywords(
    provider: str,
    client: object,
    model_name: str,
    user_message: str
) -> List[str]:
    """
    Calls the LLM to extract keywords from the user's message.

    Args:
        provider: The LLM provider ('openai' or 'gemini').
        client: The initialized client object for the provider.
        model_name: The specific model name (required for OpenAI).
        user_message: The user's message to extract keywords from.

    Returns:
        A list of extracted keywords, or an empty list if extraction fails.
    """
    keyword_prompt = "Do not answer the user message! Provide an array of at most 5 keywords related to the user message."
    preflight_messages: List[Dict] = [
        {'role': 'system', 'content': keyword_prompt},
        {'role': 'user', 'content': user_message},
    ]
    # Combine system and user for Gemini single prompt
    gemini_keyword_prompt: str = f"{keyword_prompt}\n\nUser Message: {user_message}"

    content = call_llm_for_json(
        provider=provider,
        client=client,
        model_name=model_name,
        messages=preflight_messages,
        prompt_content=gemini_keyword_prompt,
        pydantic_schema=KeywordSchema,
        schema_name="keyword_extraction",
        max_tokens=50,
        temperature=0.1
    )

    if content and isinstance(content, dict):
        try:
            # Validate and extract keywords
            validated_data = KeywordSchema(**content)
            print(f"Extracted Keywords: {validated_data.keywords}")
            return validated_data.keywords
        except ValidationError as e:
            print(f"Validation Error during keyword extraction: {e}")
            return [] # Fallback
    else:
        # Error occurred in helper or content was None/invalid type
        print("Failed to extract keywords or received invalid format.")
        return [] # Fallback
