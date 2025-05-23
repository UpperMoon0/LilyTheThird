import os
import json # Added import
import asyncio # Added import
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Import the base class and necessary components
from .base_llm import BaseLLMOrchestrator, TOOL_SELECT_RETRY, TOOL_USE_RETRY, TOOL_RETRY_DELAY_SECONDS # Import constants
from tools.tools import find_tool # Added import
# HistoryManager, LLMClient, ToolExecutor, MongoHandler are initialized in Base

load_dotenv()

# Define the tools allowed specifically for the Discord context
DISCORD_ALLOWED_TOOLS = ['fetch_memory', 'search_web', 'get_current_time']

class DiscordLLM(BaseLLMOrchestrator):
    """
    LLM Orchestrator specifically for the Discord interface.
    Inherits common logic from BaseLLMOrchestrator.
    """
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, master_id: Optional[str] = None):
        """
        Initializes the DiscordLLM orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Defaults handled by Base.
            model: The specific model name to use. Defaults handled by Base.
            master_id: The Master Discord ID. Must be provided if intended to be used.
        """
        # Determine provider and model strictly from passed arguments
        # Default to 'openai' for provider if None is passed, model can be None (LLMClient handles default)
        discord_provider = provider.lower() if provider else 'openai'
        discord_model = model # Let LLMClient handle default if None

        # Call the parent constructor
        super().__init__(provider=discord_provider, model_name=discord_model)

        # Store master ID for personality check (Discord specific)
        # Use only the master_id passed to the constructor
        effective_master_id_str = master_id 
        
        if effective_master_id_str:
            try:
                self.master_id = int(effective_master_id_str)
                print(f"DiscordLLM: Master ID set to {self.master_id} (from constructor).")
            except ValueError:
                print(f"Warning: Master Discord ID '{effective_master_id_str}' (from constructor) is not a valid integer. Master check will fail.")
                self.master_id = None
        else:
            # This case implies master_id was not passed or was None/empty
            print("Warning: Master Discord ID not provided to constructor. Master check will be based on None.")
            self.master_id = None # Explicitly set to None
        
        print(f"DiscordLLM initialized with Provider: {discord_provider}, Model: {discord_model if discord_model else 'Default'}, Master ID: {self.master_id}")


    # --- Implement Abstract Methods and Hooks from Base Class ---

    @property
    def context_name(self) -> str:
        """Identifier for the Discord context."""
        return "discord"

    def _get_base_system_messages(self, **kwargs) -> List[Dict[str, str]]:
        """Provides the base system messages including personality, time, and user context."""
        discord_user_id = kwargs.get('discord_user_id')
        discord_user_name = kwargs.get('discord_user_name', 'User') # Default name if not provided

        # Determine Personality
        is_master = self.master_id is not None and discord_user_id == self.master_id
        if is_master:
            personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful assistant.")
        else:
            p1 = os.getenv('PERSONALITY_TO_STRANGER_1', "You are a polite AI. I'm ")
            p2 = os.getenv('PERSONALITY_TO_STRANGER_2', ", you will talk to me politely.")
            personality = p1 + discord_user_name + p2

        # Prepare Base System Messages
        base_messages = [
            {'role': 'system', 'content': personality},
        ]
        return base_messages

    def _get_allowed_tools(self) -> Optional[List[str]]:
        """Returns the list of tools allowed for Discord."""
        return DISCORD_ALLOWED_TOOLS

    def _get_max_tool_calls(self) -> int:
        """Sets the maximum tool calls for the Discord context."""
        # Can be configured via env var or default
        try:
            return int(os.getenv('DISCORD_MAX_TOOL_CALLS', 3))
        except ValueError:
            print("Warning: Invalid DISCORD_MAX_TOOL_CALLS in .env, using default 3.")
            return 3

    def _prepare_user_message_for_history(self, user_message: str, **kwargs) -> str:
        """Prepends the Discord user's name to the message."""
        discord_user_name = kwargs.get('discord_user_name', 'User')
        return f"{discord_user_name} said: {user_message}"

    def _get_tools_to_exclude_from_main_loop(self) -> List[str]:
        """
        For Discord, we exclude fetch_memory, save_memory, and update_memory
        from the main tool loop.
        """
        return ['fetch_memory', 'save_memory', 'update_memory']

    def _should_perform_final_memory_step(self) -> bool:
        """
        DiscordLLM skips the final memory save/update step.
        """
        return False

    # --- Public Method ---

    async def get_response(self, user_message: str, discord_user_id: int, discord_user_name: str) -> tuple[str, None]:
        """
        Processes the user message from Discord using the OVERRIDDEN core logic.

        Args:
            user_message: The message content from Discord.
            discord_user_id: The Discord ID of the user.
            discord_user_name: The Discord display name of the user.

        Returns:
            A tuple containing the final response string and None (as expected by discord_bot.py).
        """
        print(f"--- Processing Discord message from {discord_user_name} ({discord_user_id}) ---")
        response_string, _tool_calls = await self._process_message(
            user_message,
            discord_user_id=discord_user_id,
            discord_user_name=discord_user_name
        )
        # Return format expected by discord_bot.py: (string_response, None)
        return response_string, None

    # __del__ is inherited from BaseLLMOrchestrator
