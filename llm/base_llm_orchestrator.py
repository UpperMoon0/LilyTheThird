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
from .error_analyzer import ErrorAnalyzer, ErrorCategory
from .tool_orchestrator import ToolOrchestrator # Import ToolOrchestrator
from .logging_config import setup_logging, get_logging_manager
from memory.mongo_handler import MongoHandler
from tools.tools import find_tool

load_dotenv()

# Constants for retry logic
TOOL_SELECT_RETRY = 5       # Max retries for LLM failing to choose a tool (0=disable, -1=infinite)
TOOL_USE_RETRY = 10         # Max retries for LLM failing argument generation or tool execution error (0=disable, -1=infinite)
FINAL_MEMORY_RETRY = 10      # Max retries for final save/update memory step (argument/execution error)
TOOL_RETRY_DELAY_SECONDS = 2 # Delay between tool retries

# Additional constants for enhanced error handling
MAX_SAME_ERROR_RETRIES = 3   # Max retries for the exact same error pattern
ESCALATING_DELAY_FACTOR = 1.5  # Increase delay each retry
MAX_RETRY_DELAY = 10        # Maximum delay between retries

# Constants for history summarization
MAX_ARG_SUMMARY_LEN = 150
MAX_RESULT_SUMMARY_LEN = 250

class BaseLLMOrchestrator(ABC):
    """
    Abstract base class for LLM orchestration, handling common logic like
    history management, tool execution, memory retrieval, and response generation.
    """
    def __init__(self,
                 provider: Optional[str] = None,
                 model_name: Optional[str] = None,
                 tool_use_enabled: bool = True,      # New parameter
                 allowed_tools: Optional[List[str]] = None): # New parameter
        """
        Initializes common components. Subclasses might override provider/model defaults.
        """
        # Initialize logging system first
        self.logging_manager = setup_logging()
        self.orchestrator_logger = self.logging_manager.get_logger('tool_orchestrator')
        
        self.orchestrator_logger.info("Initializing BaseLLMOrchestrator", extra={
            'provider': provider,
            'model_name': model_name,
            'tool_use_enabled': tool_use_enabled,
            'allowed_tools': allowed_tools
        })
        
        # Initialize shared components
        self.history_manager = HistoryManager()  # Will set LLM client later
        self.mongo_handler = MongoHandler() # Needed for ToolExecutor
        if not self.mongo_handler.is_connected():
            self.orchestrator_logger.warning("MongoDB connection failed. Memory tools will not function.")

        # LLMClient handles provider/model logic and client initialization
        # Subclasses can influence provider/model before calling super().__init__ or pass them here
        self.llm_client = LLMClient(provider=provider, model_name=model_name)        # Initialize ToolExecutor, passing dependencies
        self.tool_executor = ToolExecutor(mongo_handler=self.mongo_handler, llm_client=self.llm_client)
        
        # Store tool_use_enabled and allowed_tools
        self.tool_use_enabled = tool_use_enabled
        self.allowed_tools = allowed_tools # This is the list of tool *names* allowed.
        self.tool_orchestrator = None

        # Initialize ToolOrchestrator if enabled.
        # ToolOrchestrator itself will handle the case where self.allowed_tools is None (meaning all tools known to ToolExecutor are considered, then filtered by its internal exclusion list).
        if self.tool_use_enabled:
            print(f"[{self.__class__.__name__}] Tool use enabled. Initializing ToolOrchestrator.")
            self._initialize_tool_orchestrator()
        else:
            print(f"[{self.__class__.__name__}] Tool use disabled. ToolOrchestrator not initialized.")

        # Initialize error analyzer for enhanced retry logic
        self.error_analyzer = ErrorAnalyzer()
        self.recent_errors = []  # Track recent errors for pattern detection

        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        
        # Set the LLM client for history manager summarization
        self.history_manager.set_llm_client(self.llm_client)
        
        print(f"BaseLLMOrchestrator initialized with Provider: {self.provider}, Model: {self.model}")

    def _initialize_tool_orchestrator(self, retry_count=0):
        """
        Initialize ToolOrchestrator with retry logic and proper error handling.
        """
        max_retries = 3
        try:
            self.tool_orchestrator = ToolOrchestrator(
                llm_client=self.llm_client,
                tool_executor=self.tool_executor,
                history_manager=self.history_manager, # Shared history manager
                allowed_tools=self.allowed_tools # Pass the list of allowed tool names
            )
            print(f"[{self.__class__.__name__}] ✅ ToolOrchestrator successfully initialized.")
            if self.allowed_tools:
                print(f"[{self.__class__.__name__}] ToolOrchestrator initialized with specific allowed tools: {self.allowed_tools}")
            else:
                print(f"[{self.__class__.__name__}] ToolOrchestrator initialized. All tools known to ToolExecutor will be considered (before internal exclusions).")
        except Exception as e:
            print(f"[{self.__class__.__name__}] ❌ ToolOrchestrator initialization FAILED (attempt {retry_count + 1}): {e}")
            self.tool_orchestrator = None
            
            # Retry logic for transient failures
            if retry_count < max_retries:
                print(f"[{self.__class__.__name__}] Retrying ToolOrchestrator initialization in 1 second...")
                import time
                time.sleep(1)
                self._initialize_tool_orchestrator(retry_count + 1)
            else:
                print(f"[{self.__class__.__name__}] ❌ CRITICAL: ToolOrchestrator initialization FAILED after {max_retries + 1} attempts. Tool use will be disabled.")
                # Log the issue for debugging but continue with initialization

    def reinitialize_tool_orchestrator(self):
        """
        Public method to reinitialize ToolOrchestrator, useful after settings changes.
        """
        if self.tool_use_enabled:
            print(f"[{self.__class__.__name__}] Reinitializing ToolOrchestrator...")
            self._initialize_tool_orchestrator()
        else:
            print(f"[{self.__class__.__name__}] Tool use disabled, clearing ToolOrchestrator.")
            self.tool_orchestrator = None

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

    def _get_tools_to_exclude_from_main_loop(self) -> List[str]:
        """
        Returns a list of tool names to be excluded from the main tool interaction loop.
        Memory tools like fetch_memory and save_memory are typically excluded here
        as they are handled at specific stages (initial retrieval, final save).
        Subclasses can override this to exclude additional tools (e.g., update_memory for Discord).
        """
        return ['fetch_memory', 'save_memory']

    def _should_perform_final_memory_step(self) -> bool:
        """
        Determines if the final memory operation step (save/update memory) should be performed.
        Defaults to True. Subclasses (like DiscordLLM) can override to skip this step.
        """
        return True

    def _summarize_for_history(self, data: any, max_len: int) -> str:
        """Helper to summarize data for concise history logging."""
        if data is None:
            return "N/A"
        try:
            if isinstance(data, (dict, list)):
                # Compact JSON for dicts/lists
                s_data = json.dumps(data, separators=(',', ':'))
            else:
                s_data = str(data)
        except TypeError:
            s_data = str(data) # Fallback for non-serializable objects
        if len(s_data) > max_len:
            return s_data[:max_len-3] + "..."
        return s_data

    def _prepare_user_message_for_history(self, user_message: str, **kwargs) -> str:
        """
        Optional hook for subclasses to modify the user message before adding to history.
        Default implementation returns the message as is.
        kwargs can receive context like user_name.
        """
        return user_message

    def _track_error_pattern(self, tool_name: str, error_message: str, arguments: dict, error_category: ErrorCategory) -> bool:
        """
        Track error patterns to detect repeated mistakes.
        Returns True if this is a repeated pattern that should receive enhanced guidance.
        """
        error_record = {
            "tool_name": tool_name,
            "error_category": error_category,
            "error_message": error_message,
            "arguments": arguments,
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Keep only recent errors (last 10)
        self.recent_errors.append(error_record)
        if len(self.recent_errors) > 10:
            self.recent_errors.pop(0)
        
        # Check for repeated patterns (same tool + same error category)
        same_pattern_count = sum(1 for error in self.recent_errors 
                               if error["tool_name"] == tool_name and 
                                  error["error_category"] == error_category)
        
        return same_pattern_count >= 3  # Consider it a pattern after 3 occurrences

    def _generate_enhanced_retry_context(self, tool_name: str, error_message: str, arguments: dict, 
                                       retry_count: int, retrieved_facts: Optional[str] = None) -> str:
        """
        Generate enhanced retry context using error analysis and pattern detection.
        """
        # Analyze the error
        error_category, specific_guidance = self.error_analyzer.analyze_error(error_message, tool_name, arguments)
        
        # Track the error pattern
        is_repeated_pattern = self._track_error_pattern(tool_name, error_message, arguments, error_category)
        
        # Build enhanced context
        base_context = (
            f"RETRY CONTEXT (Attempt {retry_count}): Tool '{tool_name}' failed. "
            f"Error Category: {error_category.value.upper()}\n\n"
            f"SPECIFIC GUIDANCE: {specific_guidance}\n\n"
        )
        
        # Add pattern-specific warnings
        if is_repeated_pattern:
            base_context += (
                "⚠️ REPEATED MISTAKE DETECTED: You have made this same type of error multiple times. "
                "Please carefully review the guidance above and ensure you understand the requirements "
                "before proceeding. Take extra care with the argument format and values.\n\n"
            )
        
        # Add context for specific error types
        if error_category == ErrorCategory.MEMORY_ID_ERROR and retrieved_facts:
            base_context += (
                "MEMORY ID REFERENCE: Here are the available memory facts you can update:\n"
                f"{retrieved_facts}\n\n"
                "IMPORTANT: Only use memory_id values that appear in the facts above.\n\n"
            )
        
        # Add progressive guidance based on retry count
        if retry_count >= 3:
            base_context += (
                "PROGRESSIVE GUIDANCE: This is your third or later attempt. Consider:\n"
                "1. Double-check the tool's parameter requirements and data types\n"
                "2. Verify that all required arguments are provided\n"
                "3. Ensure argument values match the expected format exactly\n"
                "4. Review any error-specific guidance provided above\n\n"
            )
        
        # Add examples for complex tools on repeated failures
        if retry_count >= 2 and tool_name in ["update_memory", "save_memory"]:
            base_context += self._get_tool_examples(tool_name)
        
        return base_context
    
    def _get_tool_examples(self, tool_name: str) -> str:
        """Provide concrete examples for complex tools that frequently fail."""
        examples = {
            "update_memory": (
                "EXAMPLE: For update_memory, use:\n"
                '{"memory_id": "507f1f77bcf86cd799439011", "new_content": "Updated information"}\n'
                "Make sure the memory_id is EXACTLY as shown in the retrieved facts.\n\n"
            ),
            "save_memory": (
                "EXAMPLE: For save_memory, use:\n"
                '{"content": "New information to remember"}\n'
                "Content should be descriptive and self-contained.\n\n"
            ),
            "write_file": (
                "EXAMPLE: For write_file, use:\n"
                '{"file_path": "/full/path/to/file.txt", "content": "File content here"}\n'
                "Ensure the path is absolute and directory exists.\n\n"
            )
        }
        return examples.get(tool_name, "")
    
    def _should_abort_retry_sequence(self, tool_name: str, error_message: str, retry_count: int) -> bool:
        """
        Determine if retry sequence should be aborted due to futile attempts.
        """
        # Count exact same error occurrences
        exact_same_errors = sum(1 for error in self.recent_errors[-5:] 
                              if error.get("tool_name") == tool_name and 
                                 error.get("error_message") == error_message)
        
        # Abort if we've seen the exact same error too many times
        if exact_same_errors >= MAX_SAME_ERROR_RETRIES:
            return True
        
        # Abort for certain categories that are unlikely to succeed
        error_category, _ = self.error_analyzer.analyze_error(error_message, tool_name, {})
        non_retryable_on_high_count = [
            ErrorCategory.INVALID_ARGUMENT,
            ErrorCategory.MISSING_ARGUMENT,
            ErrorCategory.RESOURCE_NOT_FOUND,
            ErrorCategory.PERMISSION_DENIED
        ]
        
        if retry_count >= 4 and error_category in non_retryable_on_high_count:
            return True
        
        return False

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
        retrieved_facts_context_string = await self._retrieve_and_add_memory_context(user_message)

        # 3. Prepare and add user message to history
        prepared_user_message = self._prepare_user_message_for_history(user_message, **kwargs)
        await self.history_manager.add_message('user', prepared_user_message)

        # --- Tool Usage Flow ---
        successful_tool_calls = [] # Initialize list to track successful calls
        # allowed_tools_overall = self._get_allowed_tools() # This is now self.allowed_tools from __init__
        max_tool_calls = self._get_max_tool_calls() # FIXED: Uncommented this critical line
        # tool_calls_made = 0 # ToolOrchestrator will manage this internally

        # 4. Main Tool Interaction Loop (Excluding Memory Tools)
        print(f"--- Step 4: Main Tool Loop ---")
        # DEBUG: Add detailed logging for the condition check
        print(f"[{self.__class__.__name__}] DEBUG - Tool use condition check:")
        print(f"  self.tool_use_enabled = {self.tool_use_enabled}")
        print(f"  self.tool_orchestrator = {self.tool_orchestrator}")
        print(f"  self.tool_orchestrator is not None = {self.tool_orchestrator is not None}")
        print(f"  Condition result = {self.tool_orchestrator and self.tool_use_enabled}")
        
        if self.tool_use_enabled and self.tool_orchestrator is not None:
            print(f"[{self.__class__.__name__}] ✅ Tool use is enabled and ToolOrchestrator is initialized. Executing tool cycle.")
            # Construct the current prompt message for the tool orchestrator
            # This typically includes base system messages, history, and the current user message.
            # For simplicity, we'll pass the user_message directly for now, assuming ToolOrchestrator
            # can access history via self.history_manager.
            # A more robust approach might involve constructing a more complete prompt here.
            
            # The user_message_content_for_llm should be the actual content string.
            # The history_manager already has the user message added.
            # We need to prepare the full context for the LLM to decide on tool use.
            
            # Call execute_tool_cycle with the correct parameters
            # Note: ToolOrchestrator's execute_tool_cycle uses the shared history_manager,
            # so it will see the user message already added at the start of _process_message.
            # It also expects base_system_messages separately.
            
            # max_tool_calls was already defined earlier in _process_message
            # max_tool_calls = self._get_max_tool_calls() # This line is already present above

            tool_interaction_messages, executed_tool_calls_details = await self.tool_orchestrator.execute_tool_cycle(
                base_system_messages=base_system_messages,
                max_tool_calls=max_tool_calls, # Use the variable defined in this scope
                context_name=self.context_name,
                retrieved_facts_context_string=retrieved_facts_context_string
            )
            
            # executed_tool_calls_details is a list of dicts, each representing a successful tool call.
            # It should contain 'tool_name', 'arguments', 'result', 'timestamp'.
            if executed_tool_calls_details:
                successful_tool_calls.extend(executed_tool_calls_details)
                print(f"[{self.__class__.__name__}] Added {len(executed_tool_calls_details)} tool calls from ToolOrchestrator to successful_tool_calls.")
            
            # tool_interaction_messages contains the history of the tool interactions (tool calls, results).
            # This should already be managed by the history_manager within ToolOrchestrator.
            # We need to ensure the main history_manager here reflects these.
            # Assuming ToolOrchestrator uses the shared history_manager instance.
            # If ToolOrchestrator returns a final assistant message, we might use that.
            # For now, we assume history is updated and we proceed to final response generation if needed.

        else:
            print(f"[{self.__class__.__name__}] ❌ Tool use is disabled or ToolOrchestrator not initialized. Skipping tool cycle.")
            print(f"  Reason: tool_use_enabled={self.tool_use_enabled}, tool_orchestrator_exists={self.tool_orchestrator is not None}")
        # The main tool interaction loop has been moved to ToolOrchestrator.execute_tool_cycle()
        # This section will be updated in a subsequent task to call ToolOrchestrator.


        # 5. Final Memory Operation Step (Optional: Save or Update)
        print(f"--- Step 5: Final Memory Save/Update Check ---")
        if self._should_perform_final_memory_step(): # Use new hook
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
                allowed_tools=self.allowed_tools, # Use instance attribute for allowed tools
                context_type=self.context_name, # Pass context for potential encouragement
                force_tool_options=['save_memory', 'update_memory'] # Force choice: save, update, or null
            )

            # Handle empty or error responses from final memory check gracefully
            if not save_or_update_decision or "error" in save_or_update_decision:
                print(f"[{self.__class__.__name__}] Final memory check returned empty/error response. Treating as 'no memory operation needed'.")
                chosen_tool_name = None
            else:
                chosen_tool_name = save_or_update_decision.get("tool_name")

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
                            summarized_error_for_mem_retry_ctx = self._summarize_for_history(tool_result, MAX_RESULT_SUMMARY_LEN)
                            retry_context = (
                                f"RETRY CONTEXT: Previous attempt (attempt {final_mem_retry_count}) to use final memory tool \'{chosen_tool_name}\' failed with the following error: "
                                f"\'{summarized_error_for_mem_retry_ctx}\'. Please analyze the error and the conversation history, then try generating "
                                f"the arguments for \'{chosen_tool_name}\' again, correcting any potential issues."
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
                        "result": tool_result, # Keep full result for this tracked list
                        "timestamp": datetime.now(timezone.utc).isoformat() # Add timestamp
                    }
                    successful_tool_calls.append(successful_tool_call_details)
                    print(f"[{self.__class__.__name__}] Added details for successful final memory op \'{chosen_tool_name}\' call to list.")


                # Simplified history message for final memory tool usage
                args_summary_mem = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
                result_summary_mem = self._summarize_for_history(tool_result, MAX_RESULT_SUMMARY_LEN)
                status_for_history = f"Final Memory Op ({final_mem_status})"

                if final_mem_status.startswith("Failed"):
                    history_mem_tool_summary = f"System: Final memory tool '{chosen_tool_name}' attempt failed. Status: {status_for_history}. Arguments: {args_summary_mem}. Details: {result_summary_mem}"
                else: # Success
                    history_mem_tool_summary = f"System: Final memory tool '{chosen_tool_name}' executed successfully. Status: {status_for_history}. Arguments: {args_summary_mem}. Result: {result_summary_mem}"
                # Add result here so LLM knows it happened before final response generation.
                await self.history_manager.add_message('system', history_mem_tool_summary)
                # Note: We don\'t increment tool_calls_made for this final optional step.
            else:
                print(f"[{self.__class__.__name__}] LLM decided no final memory operation needed.")
        else:
            print(f"--- Step 5: Final Memory Save/Update Check SKIPPED (due to _should_perform_final_memory_step() returning False) ---")        # 6. Final Response Generation
        print(f"--- Step 6: Final Response Generation ---")
        final_history = self.history_manager.get_history() # Get history *after* all tool steps

        # Check if we already have a text response from the main loop
        # If the last message in history is an assistant message from a direct text response, use it
        if final_history and final_history[-1].get("role") == "assistant":
            print(f"[{self.__class__.__name__}] Using existing text response from main loop, skipping final response generation.")
            final_message = final_history[-1].get("content", "")
            return final_message, successful_tool_calls # Return both response and list

        # Prepare messages for final response generation
        messages_for_final_response = []

        # Add primary personality (first message from base_system_messages)
        if base_system_messages:
            messages_for_final_response.append(base_system_messages[0])
        else:
            # Fallback personality if none provided by subclass
            messages_for_final_response.append({'role': 'system', 'content': "You are a helpful assistant."})

        # Add the rest of the base system messages (excluding the primary personality)
        if len(base_system_messages) > 1:
             messages_for_final_response.extend(base_system_messages[1:]) # Add other base system messages

        # Add the retrieved facts context *before* the main history, if it exists
        if retrieved_facts_context_string:
            messages_for_final_response.append({'role': 'system', 'content': retrieved_facts_context_string})
            print(f"[{self.__class__.__name__}] Added retrieved facts context to final prompt before history.")

        # Add the main conversation history (user messages, previous assistant replies, tool results)
        messages_for_final_response.extend(final_history)

        # Remove the explicit date/time message if present from base_system_messages for BaseLLMOrchestrator
        # This is a more general fix. DiscordLLM specific fix is also applied.
        messages_for_final_response = [m for m in messages_for_final_response if not ("role" in m and m["role"] == "system" and m["content"].startswith("Current date and time:"))]

        # Add a general grounding instruction
        grounding_instruction = (
            "IMPORTANT: Generate your response based on the information available in the preceding conversation history, "
            "tool outputs, and provided facts. If the answer cannot be found in the provided context, "
            "use the search tools to find relevant information or state that you cannot answer based on the current context. "
        )
        messages_for_final_response.append({'role': 'system', 'content': grounding_instruction})
        print(f"[{self.__class__.__name__}] Added general grounding instruction to final prompt.")


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
            await self.history_manager.add_message('assistant', final_message)

        return final_message, successful_tool_calls # Return both response and list

    def close(self):
        """Closes resources, like the MongoDB connection."""
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
            print(f"[{self.__class__.__name__}] MongoDB connection closed via explicit close().")
