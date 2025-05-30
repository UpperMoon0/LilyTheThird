import os
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Import the base class and necessary components
from .base_llm_orchestrator import BaseLLMOrchestrator
# HistoryManager, LLMClient, ToolExecutor, MongoHandler are initialized in Base

load_dotenv()

class ChatBoxLLMOrchestrator(BaseLLMOrchestrator):
    """
    LLM Orchestrator specifically for the ChatBox interface.
    Inherits common logic from BaseLLMOrchestrator.
    """
    def __init__(self,
                 provider: Optional[str] = None,
                 model_name: Optional[str] = None,
                 tool_use_enabled: bool = True): # Added tool_use_enabled
        """
        Initializes the ChatBoxLLMOrchestrator orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Defaults handled by Base.
            model_name: The specific model name to use. Defaults handled by Base.
            tool_use_enabled: Whether tool use is enabled. Defaults to True.
        """
        # Determine provider and model, falling back to env vars or defaults if not passed
        chatbox_provider = provider or os.getenv('CHATBOX_LLM_PROVIDER', 'openai')
        chatbox_model = model_name or os.getenv('CHATBOX_LLM_MODEL') # Let LLMClient handle default if None

        # Determine allowed tools for ChatBox (all tools by default)
        # This logic was previously in _get_allowed_tools, moving it here for __init__
        # In a more complex scenario, this might involve fetching from a config or ToolsManager
        allowed_tools_for_chatbox = None # None means all tools

        # Call the parent constructor with the determined provider, model, and tool settings
        super().__init__(
            provider=chatbox_provider,
            model_name=chatbox_model,
            tool_use_enabled=tool_use_enabled,
            allowed_tools=allowed_tools_for_chatbox
        )

        # Load personality specific to ChatBox (likely the master personality)
        self.personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful AI assistant.")
        print(f"ChatBoxLLMOrchestrator initialized. Personality loaded.")

    # --- Implement Abstract Methods from Base Class ---

    @property
    def context_name(self) -> str:
        """Identifier for the ChatBox context."""
        return "chatbox"

    def _get_base_system_messages(self, **kwargs) -> List[Dict[str, str]]:
        """Provides the base system message (personality) for the ChatBox."""
        # ChatBox doesn't have user-specific context like Discord, just the main personality.
        return [{'role': 'system', 'content': self.personality}]

    def _get_allowed_tools(self) -> Optional[List[str]]:
        """ChatBox allows all available tools."""
        return None # Returning None means all tools defined in tools/tools.py are allowed

    def _get_max_tool_calls(self) -> int:
        """Sets the maximum tool calls for the ChatBox context."""
        # Can be configured via env var or default
        try:
            return int(os.getenv('CHATBOX_MAX_TOOL_CALLS', 5))
        except ValueError:
            print("Warning: Invalid CHATBOX_MAX_TOOL_CALLS in .env, using default 5.")
            return 5

    # _prepare_user_message_for_history can use the default implementation from Base

    # --- Public Method ---

    async def get_response(self, user_message: str) -> tuple[str, List[Dict]]: # Updated return type hint
        """
        Processes the user message using the core logic from the base class.

        Args:
            user_message: The message entered by the user in the chatbox.

        Returns:
            A tuple containing the final response string and a list of dictionaries,
            each detailing a successfully executed tool call.
        """
        print(f"--- Processing ChatBox message ---")
        # _process_message now returns (final_response, successful_tool_calls)
        final_response, successful_tools = await self._process_message(user_message)
        print(f"ChatBoxLLMOrchestrator: Received response '{final_response[:50]}...' and tools: {successful_tools}")
        # Return the response and the list of tools
        return final_response, successful_tools

    # __del__ is inherited from BaseLLMOrchestrator
