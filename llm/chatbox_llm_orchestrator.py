import os
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Import Lily-Core client instead of base orchestrator
from .lily_core_client import LilyCoreChatOrchestrator

load_dotenv()

class ChatBoxLLMOrchestrator:
    """
    LLM Orchestrator specifically for the ChatBox interface.
    Now uses Lily-Core for LLM processing instead of own orchestration.
    """

    def __init__(self,
                 provider: Optional[str] = None,
                 model_name: Optional[str] = None,
                 tool_use_enabled: bool = True):
        """
        Initializes the ChatBoxLLMOrchestrator orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Kept for compatibility but not used.
            model_name: The specific model name to use. Kept for compatibility but not used.
            tool_use_enabled: Whether tool use is enabled. Defaults to True.
        """
        # Get personality for ChatBox
        self.personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful AI assistant.")
        # Store model for compatibility with UI checks
        self.model = model_name

        # Get Lily-Core URL and agent loop settings
        lily_core_url = os.getenv('LILY_CORE_URL', 'http://localhost:8000')
        use_agent_loop = tool_use_enabled and os.getenv('CHATBOX_USE_AGENT_LOOP', 'false').lower() == 'true'

        # Create Lily-Core orchestrator
        self.orchestrator = LilyCoreChatOrchestrator(
            base_url=lily_core_url,
            use_agent_loop=use_agent_loop,
            personality=self.personality
        )

        # For compatibility with existing code
        self.tool_use_enabled = tool_use_enabled

        print(f"ChatBoxLLMOrchestrator initialized using Lily-Core. Personality loaded.")
        print(f"Lily-Core URL: {lily_core_url}, Agent Loop: {use_agent_loop}")

    @property
    def context_name(self) -> str:
        """Identifier for the ChatBox context."""
        return "chatbox"

    async def initialize(self):
        """Initialize the Lily-Core orchestrator."""
        await self.orchestrator.initialize()

    async def close(self):
        """Close the orchestrator and cleanup resources."""
        if hasattr(self.orchestrator, 'close'):
            await self.orchestrator.close()

    # --- Public Method ---

    async def get_response(self, user_message: str) -> Tuple[str, List[Dict]]:
        """
        Processes the user message using Lily-Core.

        Args:
            user_message: The message entered by the user in the chatbox.

        Returns:
            A tuple containing the final response string and a list of tool call details.
        """
        print(f"--- Processing ChatBox message using Lily-Core ---")

        try:
            # Use a default user ID for chatbox (could be made configurable later)
            user_id = "chatbox_user"

            # Get response from Lily-Core
            final_response, successful_tools = await self.orchestrator.get_response(
                user_message=user_message,
                user_id=user_id
            )

            print(f"ChatBoxLLMOrchestrator: Received response from Lily-Core")
            print(f"Response length: {len(final_response)} chars, Tools used: {len(successful_tools)}")

            return final_response, successful_tools

        except Exception as e:
            error_msg = f"Error in ChatBox LLM processing: {str(e)}"
            print(error_msg)
            return error_msg, []