import os
import random
import google.generativeai as genai
from openai import OpenAI
from typing import List, Dict, Optional

# Assuming history manager is in the same directory or adjust import path
from .history_manager import HistoryManager

class LLMClient:
    """Handles communication with the underlying LLM provider (OpenAI or Gemini)."""

    def __init__(self, provider: str, model_name: Optional[str] = None):
        """
        Initializes the LLM client based on the provider.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use.
        """
        self.provider = provider
        self.model = model_name
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Loads API keys and initializes the appropriate client."""
        openai_api_key = os.getenv('OPENAI_KEY')
        gemini_api_key = os.getenv('GEMINI_API_KEY')

        if not self.model:
            # Set default model if none provided
            if self.provider == 'openai':
                self.model = "gpt-4o-mini" # Default OpenAI model
            elif self.provider == 'gemini':
                self.model = "gemini-1.5-flash" # Default Gemini model
            else:
                # If provider is unknown and no model is given, we can't proceed
                raise ValueError(f"Model name must be provided for unsupported provider: {self.provider}")
            print(f"Warning: No model name provided, using default for {self.provider}: {self.model}")

        if self.provider == 'openai':
            if not openai_api_key:
                raise ValueError("OpenAI API key not found in environment variables.")
            self.client = OpenAI(api_key=openai_api_key)
        elif self.provider == 'gemini':
            if not gemini_api_key:
                raise ValueError("Gemini API key not found in environment variables.")
            genai.configure(api_key=gemini_api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        print(f"LLM Client initialized for provider: {self.provider}, model: {self.model}")

    def get_model_name(self) -> str:
        """Returns the name of the model being used."""
        return self.model

    def generate_message_response(self, messages: List[Dict]) -> Optional[str]:
        """
        Generates a conversational message response from the LLM.

        Args:
            messages: The list of messages (including system prompts and history)
                      in OpenAI format.

        Returns:
            The generated message string, or None if an error occurs.
        """
        if self.provider == 'openai':
            try:
                response = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    max_tokens=450,
                    temperature=random.uniform(0.2, 0.8),
                )
                message = response.choices[0].message.content.strip()
                return message
            except Exception as e:
                print(f"Error calling OpenAI API (Message Generation): {e}")
                # Return a specific error message or None
                return f"Error: Could not get message response from OpenAI. {e}"

        elif self.provider == 'gemini':
            # Adapt system prompts and history for Gemini
            system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
            # History needs adaptation (user/model roles, 'parts' structure)
            history_openai_format = [msg for msg in messages if msg['role'] != 'system']
            user_message_content = history_openai_format.pop()['content'] # Get the last user message

            # Use a temporary HistoryManager instance just for adaptation here
            # Or, ideally, the adaptation logic could be a static method or separate util
            temp_history_manager = HistoryManager()
            gemini_formatted_history = temp_history_manager.adapt_history_for_gemini(history_openai_format)

            # Combine system prompts and user message for Gemini
            prompt_parts = [f"System Instructions:\n{' '.join(system_prompts)}\n\nUser Request:\n{user_message_content}"]

            generation_config = genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=random.uniform(0.2, 0.7),
            )
            try:
                # Start a new chat session for each request for stateless interaction
                # (unless maintaining state within the client is desired)
                chat_session = self.client.start_chat(history=gemini_formatted_history)
                response = chat_session.send_message(
                    prompt_parts,
                    generation_config=generation_config,
                )
                print(f"--- Raw Gemini Message Response Text ---\n{response.text}\n----------------------------------------")
                if response.text:
                    return response.text.strip()
                else:
                    feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else "Unknown reason"
                    print(f"Gemini message response issue: {feedback}")
                    return "Error: Gemini message response was empty or blocked."
            except Exception as e:
                print(f"Error calling Gemini API (Message Generation): {e}")
                return f"Error: Could not get message response from Gemini. {e}"
        else:
            print(f"Unsupported provider '{self.provider}' for message generation.")
            return "Error: Unsupported provider."

    # Note: The call_llm_for_json function remains in llm_utils.py as it's used
    # by multiple extractors, not just the client. The client object is passed to it.
