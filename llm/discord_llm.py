import os
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Import the base class and necessary components
from .base_llm import BaseLLMOrchestrator
# HistoryManager, LLMClient, ToolExecutor, MongoHandler are initialized in Base

load_dotenv()

# Define the tools allowed specifically for the Discord context
DISCORD_ALLOWED_TOOLS = ['fetch_memory', 'save_memory', 'search_web', 'get_current_time']

class DiscordLLM(BaseLLMOrchestrator):
    """
    LLM Orchestrator specifically for the Discord interface.
    Inherits common logic from BaseLLMOrchestrator.
    """
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Initializes the DiscordLLM orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Defaults handled by Base.
            model: The specific model name to use. Defaults handled by Base.
        """
        # Determine provider and model using Discord-specific env vars or defaults
        discord_provider = (provider or os.getenv('DISCORD_LLM_PROVIDER', 'openai')).lower()
        discord_model = model or os.getenv('DISCORD_LLM_MODEL') # Let LLMClient handle default if None

        # Call the parent constructor
        super().__init__(provider=discord_provider, model_name=discord_model)

        # Store master ID for personality check (Discord specific)
        self.master_id = os.getenv('MASTER_DISCORD_ID')
        if self.master_id:
            try:
                self.master_id = int(self.master_id)
            except ValueError:
                print("Warning: MASTER_DISCORD_ID in .env is not a valid integer. Master check will fail.")
                self.master_id = None
        else:
            print("Warning: MASTER_DISCORD_ID not found in .env. Master check will fail.")
        print(f"DiscordLLM initialized. Master ID check configured.")


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
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_messages = [
            {'role': 'system', 'content': personality},
            {'role': 'system', 'content': f"Current date and time: {current_date_time}"},
            {'role': 'system', 'content': f"You are interacting with user '{discord_user_name}' (ID: {discord_user_id}). They are {'your Master' if is_master else 'not your Master'}."}
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

    # --- Public Method ---

    async def get_response(self, user_message: str, discord_user_id: int, discord_user_name: str) -> tuple[str, None]:
        """
        Processes the user message from Discord using the core logic from the base class.

        Args:
            user_message: The message content from Discord.
            discord_user_id: The Discord ID of the user.
            discord_user_name: The Discord display name of the user.

        Returns:
            A tuple containing the final response string and None (as expected by discord_bot.py).
        """
        print(f"--- Processing Discord message from {discord_user_name} ({discord_user_id}) ---")
        # Pass Discord-specific context to the core processing method
        final_response = await self._process_message(
            user_message,
            discord_user_id=discord_user_id,
            discord_user_name=discord_user_name
        )
        # Return format expected by discord_bot.py
        return final_response, None

    # __del__ is inherited from BaseLLMOrchestrator
