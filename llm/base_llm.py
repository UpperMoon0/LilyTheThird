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

    async def _retrieve_and_add_memory_context(self, query_text: str) -> Optional[str]:
        """
        Retrieves relevant facts from memory based on query_text and returns
        a formatted string containing the facts and a prioritization instruction,
        or None if no relevant facts are found or an error occurs.
        """
        if not self.mongo_handler.is_connected() or not self.mongo_handler.embedding_model:
            print(f"[{self.__class__.__name__}] Memory retrieval skipped: MongoDB not connected or embedding model not loaded.")
            return None

        try:
            # Use similarity search based on the query text
            relevant_facts = self.mongo_handler.retrieve_memories_by_similarity(query_text, limit=3) # Limit to 3 for context space
            if relevant_facts:
                print(f"[{self.__class__.__name__}] Retrieved {len(relevant_facts)} relevant facts from memory:")
                # Log the content of each retrieved fact (Corrected indentation)
                for i, fact in enumerate(relevant_facts):
                    print(f"  Fact {i+1}: {fact}")
                # Prepare facts context string WITH STRONG INSTRUCTION (Corrected indentation)
                facts_context = (
                    "CRITICAL INSTRUCTION: The following information was retrieved from memory and is highly relevant to the user's query. "
                    "You MUST prioritize using these facts in your response if they directly answer the query. "
                    "Do NOT rely solely on your general knowledge if these facts provide the specific answer.\n\n"
                    "Relevant information from memory:\n" +
                    "\n".join([f"- {fact}" for fact in relevant_facts])
                )
                print(f"[{self.__class__.__name__}] Prepared facts context WITH integrated prioritization instruction.")
                return facts_context # Return the formatted string
            else:
                # Corrected indentation
                print(f"[{self.__class__.__name__}] No relevant facts found in memory for query: '{query_text[:50]}...'")
                return None # Return None if no facts found
        # Added missing except block
        except Exception as e:
            print(f"Error retrieving memories by similarity: {e}")
            return None # Return None on error

    # Removed _execute_tool_step as its logic is integrated into _process_message loops

    async def _process_message(self, user_message: str, **kwargs) -> str:
        """
        Core logic for processing a user message, handling memory retrieval,
        tool interactions (initial fetch, main loop, final save), and final response generation.
        kwargs are passed to hook methods like _get_base_system_messages.
        """
        # 1. Get context-specific base system messages
        base_system_messages = self._get_base_system_messages(**kwargs)

        # 2. Retrieve relevant memories automatically based on the raw user message
        #    Store the potential context string.
        retrieved_facts_context_string = await self._retrieve_and_add_memory_context(user_message)
        # Note: We no longer add it directly to base_system_messages here.

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

            # --- Argument Generation & Execution with Retry for update_memory ---
            print(f"[{self.__class__.__name__}] Main loop: LLM chose tool: {tool_name}")
            max_retries = 1 if tool_name == 'update_memory' else 0
            retry_count = 0
            arguments = None
            tool_result = None
            tool_definition = find_tool(tool_name)

            if not tool_definition:
                print(f"[{self.__class__.__name__}] Error: Tool '{tool_name}' definition not found.")
                tool_result = f"Error: Could not find definition for tool '{tool_name}'."
                # Add error result to history below and break outer loop
            else:
                while retry_count <= max_retries:
                    # Prepare messages for argument generation (get fresh history each time)
                    messages_for_args = base_system_messages + self.history_manager.get_history()
                    # Add memory context specifically for update_memory retries
                    if tool_name == 'update_memory' and retry_count > 0 and retrieved_facts_context_string:
                        retry_context = (
                            "RETRY CONTEXT: Previous attempt to update memory failed due to an invalid ID. "
                            "Please select a valid ID from the retrieved facts below to update.\n"
                            f"{retrieved_facts_context_string}" # retrieved_facts_context_string already includes header
                        )
                        messages_for_args.append({'role': 'system', 'content': retry_context})
                        print(f"[{self.__class__.__name__}] Added retry context for {tool_name} argument generation.")

                    # Get arguments
                    argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_args)

                    if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                        print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for {tool_name} (Attempt {retry_count + 1}): {argument_decision}.")
                        tool_result = f"Error: Failed to get arguments for tool '{tool_name}'."
                        arguments = None # Ensure arguments is None if generation failed
                        break # Break the while loop

                    arguments = argument_decision.get("arguments", {})

                    # Execute the tool
                    tool_result = await self.tool_executor.execute(tool_name, arguments)
                    print(f"[{self.__class__.__name__}] Result from {tool_name} (Attempt {retry_count + 1}): {tool_result}")

                    # Check for retry condition
                    is_update_memory_failure = tool_name == 'update_memory' and isinstance(tool_result, str) and "Memory replacement failed. The provided memory_id" in tool_result

                    if is_update_memory_failure and retry_count < max_retries:
                        print(f"[{self.__class__.__name__}] Retrying {tool_name} due to invalid memory ID.")
                        retry_count += 1
                        continue # Go to next iteration of while loop
                    else:
                        # Success, non-retryable failure, or max retries reached
                        break # Exit the while loop

            # --- After the while loop (or if definition not found) ---
            # Add the final tool result (or argument/definition error) to history
            tool_result_message_content = {
                "tool_used": tool_name,
                "arguments": arguments if arguments is not None else "N/A (argument generation failed)",
                "result": tool_result if tool_result is not None else "Error: Tool execution did not produce a result."
            }
            self.history_manager.add_message('system', json.dumps(tool_result_message_content))

            # Increment tool calls *only* if execution was attempted (i.e., arguments were generated)
            if arguments is not None:
                tool_calls_made += 1
                # Check if the final result was an error and break the outer loop if needed
                if tool_result and isinstance(tool_result, str) and tool_result.startswith("Error:"):
                    # Don't break on the specific retryable error if max retries were reached,
                    # allow final response generation. But break on others.
                    is_retryable_final_failure = tool_name == 'update_memory' and "Memory replacement failed. The provided memory_id" in tool_result
                    if not is_retryable_final_failure:
                        print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name}. Breaking main loop.")
                        break # Break outer for loop
            else:
                # Argument generation or definition finding failed, break outer loop
                print(f"[{self.__class__.__name__}] Argument generation or definition finding failed for {tool_name}. Breaking main loop.")
                break # Break outer for loop


        # 5. Final Save Memory Step (Optional)
        print(f"--- Step 5: Final Memory Save Check ---")
        current_history_save = self.history_manager.get_history() # Get history before save check
        messages_for_save = base_system_messages + current_history_save
        save_decision = self.llm_client.get_next_action(
            messages_for_save,
            allowed_tools=allowed_tools_overall, # Check against all allowed tools
            context_type=self.context_name, # Pass context for potential encouragement
            force_tool_options=['save_memory'] # Force choice: save_memory or null
        )
        if save_decision and save_decision.get("tool_name") == 'save_memory':
            tool_name = 'save_memory'
            print(f"[{self.__class__.__name__}] LLM decided to save memory finally.")
            # --- Argument Generation & Execution for save_memory ---
            tool_definition = find_tool(tool_name)
            if not tool_definition:
                 print(f"[{self.__class__.__name__}] Error: Tool '{tool_name}' definition not found.")
                 self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
            else:
                 # Prepare messages for argument generation (use history *before* save check)
                 messages_for_args = messages_for_save # Use the already prepared list

                 # Get arguments
                 argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_args)

                 if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                     print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for {tool_name}: {argument_decision}.")
                     tool_result = f"Error: Failed to get arguments for tool '{tool_name}'."
                     arguments = None
                 else:
                     arguments = argument_decision.get("arguments", {})
                     # Execute the tool
                     tool_result = await self.tool_executor.execute(tool_name, arguments)
                     print(f"[{self.__class__.__name__}] Result from final {tool_name}: {tool_result}")

                 # Add the final tool result (or argument/definition error) to history
                 tool_result_message_content = {
                     "tool_used": tool_name,
                     "arguments": arguments if arguments is not None else "N/A (argument generation failed)",
                     "result": tool_result if tool_result is not None else "Error: Tool execution did not produce a result."
                 }
                 # Add result AFTER the final response is generated? No, add it here so LLM knows it happened.
                 self.history_manager.add_message('system', json.dumps(tool_result_message_content))
                 # Note: We don't increment tool_calls_made for this final optional step.
        else:
             print(f"[{self.__class__.__name__}] LLM decided *not* to save memory finally.")


        # 6. Final Response Generation
        print(f"--- Step 6: Final Response Generation ---")
        final_history = self.history_manager.get_history() # Get history *after* all tool steps

        # Prepare messages for final response generation
        messages_for_final_response = []

        # Add primary personality (first message from base_system_messages)
        if base_system_messages:
            messages_for_final_response.append(base_system_messages[0])
        else:
            # Fallback personality if none provided by subclass
            messages_for_final_response.append({'role': 'system', 'content': "You are a helpful assistant."})

        # Add the rest of the base system messages (excluding the primary personality)
        # These might include things like date/time, user info, etc.
        if len(base_system_messages) > 1:
             messages_for_final_response.extend(base_system_messages[1:]) # Add other base system messages

        # Add the main conversation history (user messages, previous assistant replies, tool results)
        messages_for_final_response.extend(final_history)

        # Add the retrieved facts context *just before* the final call, if it exists
        if retrieved_facts_context_string:
            messages_for_final_response.append({'role': 'system', 'content': retrieved_facts_context_string})
            print(f"[{self.__class__.__name__}] Added retrieved facts context to final prompt.")


        # Extract original personality prompt (still needed for Gemini adaptation potentially)
        final_personality_prompt = base_system_messages[0]['content'] if base_system_messages else "You are a helpful assistant."

        final_message = self.llm_client.generate_final_response(
            messages_for_final_response, # Pass the fully constructed list
            personality_prompt=final_personality_prompt # Pass original personality separately
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
