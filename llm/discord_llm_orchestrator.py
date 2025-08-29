import os
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Import Lily-Core client instead of base orchestrator
from .lily_core_client import LilyCoreChatOrchestrator

load_dotenv()

class DiscordLLMOrchestrator:
    """
    LLM Orchestrator specifically for the Discord interface.
    Now uses Lily-Core for LLM processing instead of own orchestration.
    """

    def __init__(self,
                 provider: Optional[str] = None,
                 model: Optional[str] = None,
                 master_id: Optional[str] = None,
                 tool_use_enabled: bool = True):
        """
        Initializes the DiscordLLMOrchestrator orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Kept for compatibility but not used.
            model: The specific model name to use. Kept for compatibility but not used.
            master_id: The Master Discord ID. For personality handling.
            tool_use_enabled: Whether tool use is enabled. Defaults to True.
        """
        # Store master ID for personality check
        if master_id:
            try:
                self.master_id = int(master_id)
                print(f"DiscordLLMOrchestrator: Master ID set to {self.master_id}.")
            except ValueError:
                print(f"Warning: Master Discord ID '{master_id}' is not a valid integer.")
                self.master_id = None
        else:
            self.master_id = None

        # Get Lily-Core URL and agent loop settings
        lily_core_url = os.getenv('LILY_CORE_URL', 'http://localhost:8000')
        use_agent_loop = tool_use_enabled and os.getenv('DISCORD_USE_AGENT_LOOP', 'false').lower() == 'true'

        # Store master_id for personality handling (it will be passed in get_response method)
        self.stored_master_id = self.master_id
        self.dynamic_personality = True  # Will be determined dynamically per user

        # Create Lily-Core orchestrator with default personality (will be overridden dynamically)
        default_personality = "You are a helpful AI assistant for Discord."
        self.orchestrator = LilyCoreChatOrchestrator(
            base_url=lily_core_url,
            use_agent_loop=use_agent_loop,
            personality=default_personality
        )

        # For compatibility with existing code
        self.tool_use_enabled = tool_use_enabled

        print(f"DiscordLLMOrchestrator initialized using Lily-Core.")
        print(f"Lily-Core URL: {lily_core_url}, Agent Loop: {use_agent_loop}")

    @property
    def context_name(self) -> str:
        """Identifier for the Discord context."""
        return "discord"

    def _get_personality_for_user(self, discord_user_id: int, discord_user_name: str) -> str:
        """Get appropriate personality based on user ID and master status."""
        is_master = self.stored_master_id is not None and discord_user_id == self.stored_master_id

        if is_master:
            personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful assistant.")
        else:
            p1 = os.getenv('PERSONALITY_TO_STRANGER_1', "You are a polite AI. I'm ")
            p2 = os.getenv('PERSONALITY_TO_STRANGER_2', ", you will talk to me politely.")
            personality = p1 + discord_user_name + p2

        return personality

    async def initialize(self):
        """Initialize the Lily-Core orchestrator."""
        await self.orchestrator.initialize()

    async def close(self):
        """Close the orchestrator and cleanup resources."""
        if hasattr(self.orchestrator, 'close'):
            await self.orchestrator.close()

    # --- Public Method ---

    async def get_response(self, user_message: str, discord_user_id: int, discord_user_name: str) -> Tuple[str, None]:
        """
        Processes the user message from Discord using Lily-Core.

        Args:
            user_message: The message content from Discord.
            discord_user_id: The Discord ID of the user.
            discord_user_name: The Discord display name of the user.

        Returns:
            A tuple containing the final response string and None (as expected by discord_bot.py).
        """
        print(f"--- Processing Discord message using Lily-Core from {discord_user_name} ({discord_user_id}) ---")

        try:
            # Create user ID for Lily-Core (using Discord ID for uniqueness)
            lily_core_user_id = f"discord_{discord_user_id}"

            # Get appropriate personality for this user
            user_personality = self._get_personality_for_user(discord_user_id, discord_user_name)

            # Update orchestrator's personality for this specific user
            self.orchestrator.personality = user_personality

            # Get response from Lily-Core
            response_text, tool_details = await self.orchestrator.get_response(
                user_message=user_message,
                user_id=lily_core_user_id
            )

            print(f"DiscordLLMOrchestrator: Received response from Lily-Core")
            print(f"Response length: {len(response_text)} chars, Tools used: {len(tool_details)}")

            # Return format expected by discord_bot.py: (string_response, None)
            return response_text, None

        except Exception as e:
            error_msg = f"Error in Discord LLM processing: {str(e)}"
            print(error_msg)
            return error_msg, None