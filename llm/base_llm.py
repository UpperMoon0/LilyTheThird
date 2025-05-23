import json
import asyncio # Import asyncio for sleep
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple # Added Tuple
from datetime import datetime, timezone # Added datetime and timezone

from dotenv import load_dotenv

# Assuming components are in the same directory or adjust imports
from .history_manager import HistoryManager
from .llm_client import LLMClient
from .tool_executor import ToolExecutor
from memory.mongo_handler import MongoHandler
from tools.tools import find_tool

load_dotenv()

# Constants for retry logic
TOOL_SELECT_RETRY = 5       # Max retries for LLM failing to choose a tool (0=disable, -1=infinite)
TOOL_USE_RETRY = 10         # Max retries for LLM failing argument generation or tool execution error (0=disable, -1=infinite)
FINAL_MEMORY_RETRY = 10      # Max retries for final save/update memory step (argument/execution error)
TOOL_RETRY_DELAY_SECONDS = 2 # Delay between tool retries

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

    async def _process_message(self, user_message: str, **kwargs) -> Tuple[str, List[Dict]]: # Changed return type hint
        """
        Core logic for processing a user message, handling memory retrieval,
        tool interactions (initial fetch, main loop, final save), and final response generation.
        Returns the final text response and a list of successfully executed tool call dictionaries.
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
        successful_tool_calls = [] # Initialize list to track successful calls
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

            # --- Tool Selection with Retry ---
            select_retry_count = 0
            action_decision = None # Initialize action_decision
            while TOOL_SELECT_RETRY == -1 or select_retry_count <= TOOL_SELECT_RETRY:
                current_history_loop = self.history_manager.get_history() # Get fresh history each retry
                messages_for_loop = base_system_messages + current_history_loop

                # Add retry context if needed
                if select_retry_count > 0:
                    retry_context = (
                        f"RETRY CONTEXT: Previous attempt (attempt {select_retry_count}) to select a tool failed or returned an invalid format. "
                        f"Please review the conversation history and available tools, then choose the next appropriate action (tool or null)."
                    )
                    messages_for_loop.append({'role': 'system', 'content': retry_context})
                    print(f"[{self.__class__.__name__}] Added retry context for tool selection (Attempt {select_retry_count + 1}).")
                    await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS) # Wait before retrying

                # Ask LLM for next action from the filtered list
                action_decision = await self.llm_client.get_next_action(
                    messages_for_loop,
                    allowed_tools=main_loop_allowed_tools, # Use filtered list
                    context_type=self.context_name
                    # No force_tool_options here
                )

                # Check if the decision is valid
                if action_decision and action_decision.get("action_type") == "tool_choice":
                    # Valid decision, break the retry loop
                    break
                else:
                    # Invalid decision or error
                    print(f"[{self.__class__.__name__}] Error or invalid format in tool selection (Attempt {select_retry_count + 1}): {action_decision}.")

                    # Check if retries are exhausted or disabled
                    if TOOL_SELECT_RETRY != -1 and select_retry_count >= TOOL_SELECT_RETRY:
                        print(f"[{self.__class__.__name__}] Tool selection failed after max retries ({TOOL_SELECT_RETRY}). Breaking loop.")
                        action_decision = None # Ensure it's None to trigger break below
                        break # Break the inner while loop
                    elif TOOL_SELECT_RETRY == 0:
                        print(f"[{self.__class__.__name__}] Tool selection failed (retries disabled). Breaking loop.")
                        action_decision = None # Ensure it's None to trigger break below
                        break # Break the inner while loop
                    else:
                        # Retry tool selection
                        print(f"[{self.__class__.__name__}] Retrying tool selection (attempt {select_retry_count + 1}/{TOOL_SELECT_RETRY if TOOL_SELECT_RETRY != -1 else 'infinite'})...")
                        select_retry_count += 1
                        # Continue to the next iteration of the while loop

            # --- End Tool Selection with Retry ---

            # Check the final action_decision after the retry loop
            if not action_decision or action_decision.get("action_type") != "tool_choice":
                # This handles cases where selection failed after retries or was invalid initially (if retries disabled)
                print(f"[{self.__class__.__name__}] Failed to get a valid tool choice after retries or retries disabled. Breaking main loop.")
                break # Exit main loop on definitive failure

            tool_name = action_decision.get("tool_name")

            if tool_name is None:
                print(f"[{self.__class__.__name__}] LLM decided no further tools needed in main loop.")
                break # Exit main loop gracefully

            # --- Argument Generation & Execution with General Retry ---
            print(f"[{self.__class__.__name__}] Main loop: LLM chose tool: {tool_name}")
            use_retry_count = 0 # Renamed from retry_count
            arguments = None
            tool_result = None
            tool_definition = find_tool(tool_name)

            if not tool_definition:
                print(f"[{self.__class__.__name__}] Error: Tool '{tool_name}' definition not found.")
                tool_result = f"Error: Could not find definition for tool '{tool_name}'."
                # Add error result to history below and break outer loop
            else:
                # Loop indefinitely if TOOL_USE_RETRY is -1, otherwise loop up to TOOL_USE_RETRY times
                while TOOL_USE_RETRY == -1 or use_retry_count <= TOOL_USE_RETRY:
                    # Prepare messages for argument generation (get fresh history each time)
                    messages_for_args = base_system_messages + self.history_manager.get_history()

                    # Add retry context if this is a retry attempt
                    if use_retry_count > 0:
                        retry_context = (
                            f"RETRY CONTEXT: Previous attempt (attempt {use_retry_count}) to use tool '{tool_name}' failed with the following error: "
                            f"'{tool_result}'. Please analyze the error and the conversation history, then try generating "
                            f"the arguments for '{tool_name}' again, correcting any potential issues."
                        )
                        # Add specific guidance for update_memory failure
                        if tool_name == 'update_memory' and "memory_id" in str(tool_result) and retrieved_facts_context_string:
                             retry_context += (
                                 "\nIt seems the 'memory_id' might have been invalid. "
                                 "Please select a valid ID from the retrieved facts below to update.\n"
                                 f"{retrieved_facts_context_string}"
                             )
                        messages_for_args.append({'role': 'system', 'content': retry_context})
                        print(f"[{self.__class__.__name__}] Added retry context for {tool_name} argument generation (Attempt {use_retry_count + 1}).")
                        # Optional: Add a small delay before retrying argument generation
                        await asyncio.sleep(1) # Consider if TOOL_RETRY_DELAY_SECONDS should be used here too

                    # Get arguments
                    argument_decision = await self.llm_client.get_tool_arguments(tool_definition, messages_for_args)

                    if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                        print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for {tool_name} (Attempt {use_retry_count + 1}): {argument_decision}.")
                        # Use the specific error if available, otherwise a generic one
                        tool_result = argument_decision.get("error", f"Error: Failed to get arguments for tool '{tool_name}'.")
                        arguments = None # Ensure arguments is None if generation failed

                        # Check if retries are exhausted or disabled
                        if TOOL_USE_RETRY != -1 and use_retry_count >= TOOL_USE_RETRY:
                            print(f"[{self.__class__.__name__}] Argument generation failed after max retries ({TOOL_USE_RETRY}) for {tool_name}. Aborting tool call.")
                            break # Break the inner while loop
                        elif TOOL_USE_RETRY == 0:
                             print(f"[{self.__class__.__name__}] Argument generation failed for {tool_name} (retries disabled). Aborting tool call.")
                             break # Break the inner while loop
                        else:
                            # Retry argument generation
                            print(f"[{self.__class__.__name__}] Argument generation failed for {tool_name}. Retrying (attempt {use_retry_count + 1}/{TOOL_USE_RETRY if TOOL_USE_RETRY != -1 else 'infinite'})...")
                            use_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue # Retry argument generation

                    arguments = argument_decision.get("arguments", {})

                    # Execute the tool
                    tool_result = await self.tool_executor.execute(tool_name, arguments)
                    print(f"[{self.__class__.__name__}] Result from {tool_name} (Attempt {use_retry_count + 1}): {tool_result}")

                    # Check for execution error condition for retry
                    is_execution_error = isinstance(tool_result, str) and tool_result.startswith("Error:")

                    if is_execution_error:
                        # Check if retries are exhausted or disabled
                        if TOOL_USE_RETRY != -1 and use_retry_count >= TOOL_USE_RETRY:
                            print(f"[{self.__class__.__name__}] Tool execution failed after max retries ({TOOL_USE_RETRY}) for {tool_name}. Aborting tool call.")
                            break # Break the inner while loop (max retries reached)
                        elif TOOL_USE_RETRY == 0:
                            print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name} (retries disabled). Aborting tool call.")
                            break # Break the inner while loop (retries disabled)
                        else:
                            print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name}. Retrying (attempt {use_retry_count + 1}/{TOOL_USE_RETRY if TOOL_USE_RETRY != -1 else 'infinite'})...")
                            # Add the error result to history immediately so the LLM sees it for the next argument generation attempt
                            temp_error_message = {
                                "tool_used": tool_name,
                                "arguments": arguments,
                                "result": tool_result,
                                "status": f"Execution Failed (Attempt {use_retry_count + 1})"
                            }
                            self.history_manager.add_message('system', json.dumps(temp_error_message))
                            use_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue # Go to next iteration of while loop (will regenerate args based on error)
                    else:
                        # Success!
                        break # Exit the while loop

            # --- After the while loop (handles success, definition error, arg error after max retries, or exec error after max retries) ---
            # Add the final tool result (or error) to history
            final_tool_status = "Success" # Assume success initially
            if tool_result is None:
                tool_result = "Error: Tool execution did not produce a result or failed during argument generation."
                final_tool_status = f"Failed (Args/Definition - {use_retry_count + 1} attempts)"
            elif isinstance(tool_result, str) and tool_result.startswith("Error:"):
                # This case means it failed after the final attempt (or retries were disabled)
                final_tool_status = f"Failed (Execution - {use_retry_count + 1} attempts)" # Show final attempt count
            elif final_tool_status == "Success": # Only append if it was actually successful
                # Append full details dictionary instead of just the name
                successful_tool_call_details = {
                    "tool_name": tool_name,
                    "arguments": arguments if arguments is not None else {}, # Ensure args is a dict
                    "result": tool_result,
                    "timestamp": datetime.now(timezone.utc).isoformat() # Add timestamp
                }
                successful_tool_calls.append(successful_tool_call_details)
                print(f"[{self.__class__.__name__}] Added details for successful '{tool_name}' call to list.")

            tool_result_message_content = {
                "tool_used": tool_name,
                "arguments": arguments if arguments is not None else "N/A (argument generation failed)",
                "result": tool_result,
                "status": final_tool_status
            }
            self.history_manager.add_message('system', json.dumps(tool_result_message_content))

            # Increment tool calls *only* if execution was attempted (i.e., arguments were generated)
            if arguments is not None:
                tool_calls_made += 1
                # If the tool ultimately failed after retries, break the outer loop.
                if final_tool_status.startswith("Failed"):
                     print(f"[{self.__class__.__name__}] Tool '{tool_name}' ultimately failed after {use_retry_count + 1} attempts. Breaking main loop.")
                     break # Break outer for loop
            else:
                # Argument generation or definition finding failed definitively (or retries exhausted/disabled)
                print(f"[{self.__class__.__name__}] Argument generation or definition finding failed definitively for {tool_name}. Breaking main loop.")
                break # Break outer for loop


        # 5. Final Memory Operation Step (Optional: Save or Update)
        print(f"--- Step 5: Final Memory Save/Update Check ---")
        current_history_save = self.history_manager.get_history() # Get history before save/update check
        messages_for_save = base_system_messages + current_history_save

        # Add guidance for choosing save vs update
        memory_guidance_prompt = (
            "Based on the conversation history and retrieved facts (if any), decide if a final memory operation is needed. "
            "Use 'save_memory' for new information not previously stored. "
            "Use 'update_memory' to modify existing information, ensuring you provide a valid 'memory_id' from the retrieved facts. "
            "If no memory operation is needed, choose null."
        )
        if retrieved_facts_context_string:
            memory_guidance_prompt += f"\n\nRetrieved facts that might be relevant for updating:\n{retrieved_facts_context_string}"
        messages_for_save.append({'role': 'system', 'content': memory_guidance_prompt})
        print(f"[{self.__class__.__name__}] Added guidance prompt for final memory operation.")

        save_or_update_decision = await self.llm_client.get_next_action(
            messages_for_save,
            allowed_tools=allowed_tools_overall, # Check against all allowed tools
            context_type=self.context_name, # Pass context for potential encouragement
            force_tool_options=['save_memory', 'update_memory'] # Force choice: save, update, or null
        )

        chosen_tool_name = save_or_update_decision.get("tool_name") if save_or_update_decision else None

        if chosen_tool_name in ['save_memory', 'update_memory']:
            print(f"[{self.__class__.__name__}] LLM decided final memory operation: {chosen_tool_name}")
            # --- Argument Generation & Execution for save_memory or update_memory (with Retry) ---
            final_mem_retry_count = 0
            arguments = None
            tool_result = None
            tool_definition = find_tool(chosen_tool_name)

            if not tool_definition:
                print(f"[{self.__class__.__name__}] Error: Tool '{chosen_tool_name}' definition not found.")
                tool_result = f"Error: Could not find definition for tool '{chosen_tool_name}'."
            else:
                # Loop for retries
                while FINAL_MEMORY_RETRY == -1 or final_mem_retry_count <= FINAL_MEMORY_RETRY:
                    # Prepare messages for argument generation (use history *before* save/update check, including guidance)
                    messages_for_args = messages_for_save # Use the already prepared list

                    # Add retry context if needed
                    if final_mem_retry_count > 0:
                        retry_context = (
                            f"RETRY CONTEXT: Previous attempt (attempt {final_mem_retry_count}) to use final memory tool '{chosen_tool_name}' failed with the following error: "
                            f"'{tool_result}'. Please analyze the error and the conversation history, then try generating "
                            f"the arguments for '{chosen_tool_name}' again, correcting any potential issues."
                        )
                        # Add specific guidance for update_memory failure if ID was the issue
                        if chosen_tool_name == 'update_memory' and "memory_id" in str(tool_result) and retrieved_facts_context_string:
                             retry_context += (
                                 "\nIt seems the 'memory_id' might have been invalid. "
                                 "Please select a valid ID from the retrieved facts below to update.\n"
                                 f"{retrieved_facts_context_string}"
                             )
                        # Use a temporary list to avoid modifying messages_for_save directly if it's reused
                        messages_for_args_retry = messages_for_args + [{'role': 'system', 'content': retry_context}]
                        print(f"[{self.__class__.__name__}] Added retry context for final {chosen_tool_name} argument generation (Attempt {final_mem_retry_count + 1}).")
                        await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS) # Wait before retrying
                    else:
                        messages_for_args_retry = messages_for_args # Use original messages on first attempt

                    # Get arguments
                    argument_decision = await self.llm_client.get_tool_arguments(tool_definition, messages_for_args_retry)

                    if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                        print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for final {chosen_tool_name} (Attempt {final_mem_retry_count + 1}): {argument_decision}.")
                        tool_result = argument_decision.get("error", f"Error: Failed to get arguments for final tool '{chosen_tool_name}'.")
                        arguments = None # Ensure arguments is None

                        # Check retry limits
                        if FINAL_MEMORY_RETRY != -1 and final_mem_retry_count >= FINAL_MEMORY_RETRY:
                            print(f"[{self.__class__.__name__}] Final memory argument generation failed after max retries ({FINAL_MEMORY_RETRY}). Aborting.")
                            break # Break the inner while loop
                        elif FINAL_MEMORY_RETRY == 0:
                            print(f"[{self.__class__.__name__}] Final memory argument generation failed (retries disabled). Aborting.")
                            break # Break the inner while loop
                        else:
                            print(f"[{self.__class__.__name__}] Final memory argument generation failed. Retrying (attempt {final_mem_retry_count + 1}/{FINAL_MEMORY_RETRY if FINAL_MEMORY_RETRY != -1 else 'infinite'})...")
                            final_mem_retry_count += 1
                            continue # Retry argument generation

                    arguments = argument_decision.get("arguments", {})
                    print(f"[{self.__class__.__name__}] Arguments prepared for final {chosen_tool_name} (Attempt {final_mem_retry_count + 1}): {arguments}") # Log arguments before execution

                    # Execute the tool
                    tool_result = await self.tool_executor.execute(chosen_tool_name, arguments)
                    print(f"[{self.__class__.__name__}] Result from final {chosen_tool_name} (Attempt {final_mem_retry_count + 1}): {tool_result}")

                    # Check for execution error condition for retry
                    is_execution_error = isinstance(tool_result, str) and tool_result.startswith("Error:")

                    if is_execution_error:
                        # Check retry limits
                        if FINAL_MEMORY_RETRY != -1 and final_mem_retry_count >= FINAL_MEMORY_RETRY:
                            print(f"[{self.__class__.__name__}] Final memory execution failed after max retries ({FINAL_MEMORY_RETRY}). Aborting.")
                            break # Break the inner while loop
                        elif FINAL_MEMORY_RETRY == 0:
                            print(f"[{self.__class__.__name__}] Final memory execution failed (retries disabled). Aborting.")
                            break # Break the inner while loop
                        else:
                            print(f"[{self.__class__.__name__}] Final memory execution failed. Retrying (attempt {final_mem_retry_count + 1}/{FINAL_MEMORY_RETRY if FINAL_MEMORY_RETRY != -1 else 'infinite'})...")
                            # Add the error result to history immediately so the LLM sees it for the next argument generation attempt (if applicable)
                            # Note: This might not be strictly necessary if the retry only re-runs execution, but good for logging.
                            temp_error_message = {
                                "tool_used": chosen_tool_name,
                                "arguments": arguments,
                                "result": tool_result,
                                "status": f"Final Memory Execution Failed (Attempt {final_mem_retry_count + 1})"
                            }
                            # Avoid adding duplicate errors if arg gen fails again
                            # self.history_manager.add_message('system', json.dumps(temp_error_message))
                            final_mem_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue # Go to next iteration of while loop (will regenerate args based on error)
                    else:
                        # Success!
                        break # Exit the while loop

            # --- After the final memory while loop ---
            # Add the final tool result (or error) to history
            final_mem_status = "Success" # Assume success initially
            if tool_result is None:
                tool_result = "Error: Final memory tool execution did not produce a result or failed during argument generation."
                final_mem_status = f"Failed (Args/Definition - {final_mem_retry_count + 1} attempts)"
            elif isinstance(tool_result, str) and tool_result.startswith("Error:"):
                final_mem_status = f"Failed (Execution - {final_mem_retry_count + 1} attempts)"
            elif final_mem_status == "Success": # Only append if it was actually successful
                 # Append full details dictionary instead of just the name
                successful_tool_call_details = {
                    "tool_name": chosen_tool_name,
                    "arguments": arguments if arguments is not None else {}, # Ensure args is a dict
                    "result": tool_result,
                    "timestamp": datetime.now(timezone.utc).isoformat() # Add timestamp
                }
                successful_tool_calls.append(successful_tool_call_details)
                print(f"[{self.__class__.__name__}] Added details for successful final memory op '{chosen_tool_name}' call to list.")


            tool_result_message_content = {
                "tool_used": chosen_tool_name,
                "arguments": arguments if arguments is not None else "N/A (argument generation failed)",
                "result": tool_result,
                "status": f"Final Memory Op ({final_mem_status})" # Clarify this is the final op
            }
            # Add result here so LLM knows it happened before final response generation.
            self.history_manager.add_message('system', json.dumps(tool_result_message_content))
            # Note: We don't increment tool_calls_made for this final optional step.
        else:
            print(f"[{self.__class__.__name__}] LLM decided no final memory operation needed.")


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

        final_message = await self.llm_client.generate_final_response(
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

        return final_message, successful_tool_calls # Return both response and list

    def close(self):
        """Closes resources, like the MongoDB connection."""
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
            print(f"[{self.__class__.__name__}] MongoDB connection closed via explicit close().")
