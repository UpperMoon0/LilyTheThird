import json
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from dotenv import load_dotenv

# Assuming components are in the same directory or adjust imports
from .history_manager import HistoryManager
from .llm_client import LLMClient
from .tool_executor import ToolExecutor
from memory.mongo_handler import MongoHandler
from tools.tools import find_tool

load_dotenv()

class BaseLLMOrchestrator(ABC):
    """
    Abstract base class for LLM orchestration, handling common logic like
    history management, tool execution, memory retrieval, and response generation.
    """
    def __init__(self, provider: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initializes common components. Subclasses might override provider/model defaults.
        """
        print(f"Initializing BaseLLMOrchestrator...")
        # Initialize shared components
        self.history_manager = HistoryManager()
        self.mongo_handler = MongoHandler() # Needed for ToolExecutor
        if not self.mongo_handler.is_connected():
            print(f"Warning [{self.__class__.__name__}]: MongoDB connection failed. Memory tools will not function.")

        # LLMClient handles provider/model logic and client initialization
        # Subclasses can influence provider/model before calling super().__init__ or pass them here
        self.llm_client = LLMClient(provider=provider, model_name=model_name)

        # Initialize ToolExecutor, passing dependencies
        self.tool_executor = ToolExecutor(mongo_handler=self.mongo_handler, llm_client=self.llm_client)

        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        print(f"BaseLLMOrchestrator initialized with Provider: {self.provider}, Model: {self.model}")

    @property
    @abstractmethod
    def context_name(self) -> str:
        """Returns a string identifier for the current context (e.g., 'chatbox', 'discord')."""
        pass

    @abstractmethod
    def _get_base_system_messages(self, **kwargs) -> List[Dict[str, str]]:
        """
        Subclasses must implement this to provide context-specific base system messages.
        kwargs can be used to pass context like user_id, user_name, etc.
        """
        pass

    @abstractmethod
    def _get_allowed_tools(self) -> Optional[List[str]]:
        """
        Subclasses must implement this to specify which tools are allowed.
        Return None to allow all tools.
        """
        pass

    @abstractmethod
    def _get_max_tool_calls(self) -> int:
        """
        Subclasses must implement this to specify the maximum number of tool calls per turn.
        """
        pass

    def _prepare_user_message_for_history(self, user_message: str, **kwargs) -> str:
        """
        Optional hook for subclasses to modify the user message before adding to history.
        Default implementation returns the message as is.
        kwargs can receive context like user_name.
        """
        return user_message

    async def _retrieve_and_add_memory_context(self, query_text: str, base_system_messages: List[Dict[str, str]]) -> None:
        """
        Retrieves relevant facts from memory based on query_text and adds them
        to the base_system_messages list if found.
        """
        if self.mongo_handler.is_connected() and self.mongo_handler.embedding_model:
            try:
                # Use similarity search based on the query text
                relevant_facts = self.mongo_handler.retrieve_memories_by_similarity(query_text, limit=3) # Limit to 3 for context space
                if relevant_facts:
                    print(f"[{self.__class__.__name__}] Retrieved {len(relevant_facts)} relevant facts from memory.")
                    # Add facts as system messages for context
                    facts_context = "Relevant information from memory:\n" + "\n".join([f"- {fact}" for fact in relevant_facts])
                    base_system_messages.append({'role': 'system', 'content': facts_context})
                else:
                    print(f"[{self.__class__.__name__}] No relevant facts found in memory for query: '{query_text[:50]}...'")
            except Exception as e:
                print(f"Error retrieving memories by similarity: {e}")
        else:
            print(f"[{self.__class__.__name__}] Memory retrieval skipped: MongoDB not connected or embedding model not loaded.")

    async def _execute_tool_step(self, tool_name: str, messages_for_llm: List[Dict]) -> bool:
        """
        Helper function to get arguments for and execute a specific tool.

        Args:
            tool_name: The name of the tool to execute.
            messages_for_llm: The current message history to provide context.

        Returns:
            True if the tool executed successfully, False otherwise.
        """
        print(f"[{self.__class__.__name__}] Attempting to execute tool: {tool_name}")
        tool_definition = find_tool(tool_name)
        if not tool_definition:
            print(f"[{self.__class__.__name__}] Error: Tool '{tool_name}' definition not found.")
            self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
            return False

        # Get arguments
        argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_llm)
        if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
            print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for {tool_name}: {argument_decision}.")
            self.history_manager.add_message('system', f"Error: Failed to get arguments for tool '{tool_name}'.")
            return False

        arguments = argument_decision.get("arguments", {})

        # Execute the tool
        tool_result = await self.tool_executor.execute(tool_name, arguments)
        print(f"[{self.__class__.__name__}] Result from {tool_name}: {tool_result}")

        # Add tool result to history
        tool_result_message = {
            "role": "system", # Using 'system' role for tool results
            "content": json.dumps({
                "tool_used": tool_name,
                "arguments": arguments,
                "result": tool_result
            })
        }
        self.history_manager.add_message(tool_result_message['role'], tool_result_message['content'])
        return True


    async def _process_message(self, user_message: str, **kwargs) -> str:
        """
        Core logic for processing a user message, handling memory retrieval,
        tool interactions (initial fetch, main loop, final save), and final response generation.
        kwargs are passed to hook methods like _get_base_system_messages.
        """
        # 1. Get context-specific base system messages
        base_system_messages = self._get_base_system_messages(**kwargs)

        # 2. Retrieve relevant memories automatically based on the raw user message
        #    (This provides initial context before the LLM decides on further actions)
        await self._retrieve_and_add_memory_context(user_message, base_system_messages)

        # 3. Prepare and add user message to history
        prepared_user_message = self._prepare_user_message_for_history(user_message, **kwargs)
        self.history_manager.add_message('user', prepared_user_message)

        # --- Tool Usage Flow ---
        allowed_tools_overall = self._get_allowed_tools() # Get all tools allowed in this context
        max_tool_calls = self._get_max_tool_calls()
        tool_calls_made = 0

        # Initial Fetch Memory Step removed as it's redundant with automatic context retrieval.

        # 4. Main Tool Interaction Loop (Excluding Memory Tools)
        print(f"--- Step 4: Main Tool Loop ---")
        # Determine tools allowed in the main loop (exclude memory tools)
        main_loop_allowed_tools = None
        if allowed_tools_overall is not None:
            main_loop_allowed_tools = [
                tool for tool in allowed_tools_overall if tool not in ['fetch_memory', 'save_memory']
            ]
        # If allowed_tools_overall was None (meaning all tools allowed), we need to get all tool names
        # and then filter.
        elif allowed_tools_overall is None:
             all_tool_names = self.tool_executor.get_all_tool_names() # Need a method in ToolExecutor for this
             main_loop_allowed_tools = [
                 tool for tool in all_tool_names if tool not in ['fetch_memory', 'save_memory']
             ]


        for _ in range(max_tool_calls):
            if tool_calls_made >= max_tool_calls:
                print(f"[{self.__class__.__name__}] Max tool calls ({max_tool_calls}) reached for main loop.")
                break

            current_history_loop = self.history_manager.get_history()
            messages_for_loop = base_system_messages + current_history_loop

            # Ask LLM for next action from the filtered list
            action_decision = self.llm_client.get_next_action(
                messages_for_loop,
                allowed_tools=main_loop_allowed_tools, # Use filtered list
                context_type=self.context_name
                # No force_tool_options here
            )

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print(f"[{self.__class__.__name__}] Error or invalid format in main loop action decision: {action_decision}. Breaking loop.")
                break # Exit main loop on error

            tool_name = action_decision.get("tool_name")

            if tool_name is None:
                print(f"[{self.__class__.__name__}] LLM decided no further tools needed in main loop.")
                break # Exit main loop gracefully

            # Execute the chosen tool
            print(f"[{self.__class__.__name__}] Main loop: LLM chose tool: {tool_name}")
            success = await self._execute_tool_step(tool_name, messages_for_loop)
            if success:
                tool_calls_made += 1
            else:
                print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name}. Breaking main loop.")
                break # Exit main loop on execution failure

        # 5. Final Save Memory Step (Optional)
        print(f"--- Step 5: Final Memory Save Check ---")
        current_history_save = self.history_manager.get_history()
        messages_for_save = base_system_messages + current_history_save
        save_decision = self.llm_client.get_next_action(
            messages_for_save,
            allowed_tools=allowed_tools_overall, # Check against all allowed tools
            context_type=self.context_name, # Pass context for potential encouragement
            force_tool_options=['save_memory'] # Force choice: save_memory or null
        )
        if save_decision and save_decision.get("tool_name") == 'save_memory':
            print(f"[{self.__class__.__name__}] LLM decided to save memory finally.")
            await self._execute_tool_step('save_memory', messages_for_save)
            # Note: We don't increment tool_calls_made here
        else:
             print(f"[{self.__class__.__name__}] LLM decided *not* to save memory finally.")


        # 6. Final Response Generation
        print(f"--- Step 6: Final Response Generation ---")
        final_history = self.history_manager.get_history() # Get history *after* all tool steps
        # Use only the *first* system message (primary personality) for the final generation prompt
        final_personality_prompt = base_system_messages[0]['content'] if base_system_messages else "You are a helpful assistant."

        # Prepare messages, ensuring the personality is first, then the full history
        messages_for_final_response = [{'role': 'system', 'content': final_personality_prompt}]
        # Add the rest of the history (which includes other system messages like retrieved facts, tool results)
        messages_for_final_response.extend(final_history)

        final_message = self.llm_client.generate_final_response(
            messages_for_final_response, # Pass combined list
            personality_prompt=final_personality_prompt # Pass separately for Gemini adaptation if needed
        )

        # Handle potential errors
        if final_message is None or final_message.startswith("Error:"):
            print(f"[{self.__class__.__name__}] Failed to get final response: {final_message}")
            final_message = final_message if final_message else "Sorry, I encountered an error generating the final response."
        else:
            # Update history with the final assistant message
            self.history_manager.add_message('assistant', final_message)

        # Print history for debugging (optional)
        # print(f"[{self.__class__.__name__}] Final Message History:")
        # for msg in self.history_manager.get_history():
        #     print(f"- {msg['role']}: {msg['content']}")

        return final_message


    def __del__(self):
        # Ensure MongoDB connection is closed when the object is destroyed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
            print(f"[{self.__class__.__name__}] MongoDB connection closed.")
