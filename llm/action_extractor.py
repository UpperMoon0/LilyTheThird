from pydantic import ValidationError
from typing import Dict, List, Optional

# Assuming schemas and utils are in the same directory or adjust import path
from .schemas import ActionExtractionSchema
from .llm_utils import call_llm_for_json

def extract_action(
    provider: str,
    client: object,
    model_name: str,
    user_message: str,
    assistant_message: str
) -> str:
    """
    Calls the LLM to extract the next action based on the conversation.

    Args:
        provider: The LLM provider ('openai' or 'gemini').
        client: The initialized client object for the provider.
        model_name: The specific model name (required for OpenAI).
        user_message: The user's last message.
        assistant_message: The assistant's last response.

    Returns:
        The extracted action string (e.g., "browse", "search_kg", "none"),
        defaulting to "none" if extraction fails or is invalid.
    """
    action_prompt = f'''You are Lily. Based on the user's last message and your response, determine the single most appropriate action YOU should take next. Choose from "browse", "search_kg", "none", or other relevant actions based on the conversation flow.

User Message: "{user_message}"
Your Response: "{assistant_message}"

What action should YOU take? Respond ONLY in the required JSON format.'''

    messages: List[Dict] = [{'role': 'system', 'content': action_prompt}]
    prompt_content: str = action_prompt # For Gemini

    content = call_llm_for_json(
        provider=provider,
        client=client,
        model_name=model_name,
        messages=messages,
        prompt_content=prompt_content,
        pydantic_schema=ActionExtractionSchema,
        schema_name="action_extraction",
        max_tokens=50,
        temperature=0.1
    )

    if content and isinstance(content, dict):
        try:
            # Validate the specific structure we need
            validated_data = ActionExtractionSchema(**content)
            return validated_data.action
        except ValidationError as e:
             print(f"Validation Error for Action Extraction: {e}")
             return "none" # Default action on validation error
    else:
        # Error occurred in helper or content was None/invalid type
        print("Action extraction failed or returned invalid format.")
        return "none" # Default action on failure
