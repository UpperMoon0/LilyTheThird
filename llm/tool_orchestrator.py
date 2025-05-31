import asyncio
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

# Assuming components are in the same directory or adjust imports
# from .llm_client import LLMClient # Not directly used in this snippet, but likely needed for full class
# from .tool_executor import ToolExecutor # Not directly used in this snippet
# from .history_manager import HistoryManager # Not directly used in this snippet

from tools.tools import find_tool # find_tool is used
from .error_analyzer import ErrorAnalyzer, ErrorCategory
from .schemas import ToolCallDetails

# Constants for retry logic (copied from BaseLLMOrchestrator)
TOOL_SELECT_RETRY = 5       # Max retries for LLM failing to choose a tool (0=disable, -1=infinite)
TOOL_EXECUTION_RETRY = 3    # Max retries for tool execution failures
TOOL_RETRY_DELAY_SECONDS = 2 # Delay between tool retries

# Constants for history summarization (copied from BaseLLMOrchestrator)
MAX_ARG_SUMMARY_LEN = 150
MAX_RESULT_SUMMARY_LEN = 250

class ToolOrchestrator:
    def __init__(self, llm_client, tool_executor, history_manager, allowed_tools: Optional[List[str]]):
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.history_manager = history_manager
        self.allowed_tools = allowed_tools # This is the overall list of allowed tools for the orchestrator context
        
        # Initialize error analyzer for intelligent error handling
        self.error_analyzer = ErrorAnalyzer()
        self.tool_failure_counts = {}  # Track failures per tool
        self.recent_errors = []  # Track recent error patterns

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

    def _track_tool_failure(self, tool_name: str, error_message: str, arguments: dict, error_category: ErrorCategory) -> int:
        """Track tool failures and return the current failure count for this tool."""
        # Update failure count
        self.tool_failure_counts[tool_name] = self.tool_failure_counts.get(tool_name, 0) + 1
        
        # Track recent errors for pattern detection
        error_record = {
            "tool_name": tool_name,
            "error_category": error_category,
            "error_message": error_message,
            "arguments": arguments,
            "timestamp": datetime.now(timezone.utc)
        }
        
        self.recent_errors.append(error_record)
        # Keep only recent errors (last 10)
        if len(self.recent_errors) > 10:
            self.recent_errors.pop(0)
            
        return self.tool_failure_counts[tool_name]

    def _get_tool_schema_info(self, tool_name: str) -> str:
        """Get detailed schema information for a tool to help with argument correction."""
        tool_definition = find_tool(tool_name)
        if not tool_definition or not tool_definition.argument_schema:
            return f"Tool '{tool_name}' schema information not available."
        
        schema_info = f"Tool '{tool_name}' expected arguments:\n"
        
        # Get schema from Pydantic model
        try:
            schema = tool_definition.argument_schema.model_json_schema()
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            for field_name, field_info in properties.items():
                field_type = field_info.get('type', 'unknown')
                field_desc = field_info.get('description', 'No description')
                is_required = field_name in required
                
                schema_info += f"  - {field_name} ({field_type})"
                if is_required:
                    schema_info += " [REQUIRED]"
                schema_info += f": {field_desc}\n"
                
        except Exception as e:
            schema_info += f"Error extracting schema details: {e}"
            
        return schema_info

    def _generate_retry_message(self, tool_name: str, error_message: str, arguments: dict,
                                retry_count: int, retrieved_facts: Optional[str] = None) -> str:
        """Generate enhanced retry message with detailed guidance."""
        # Analyze the error
        error_category, specific_guidance = self.error_analyzer.analyze_error(error_message, tool_name, arguments)
        
        # Track this failure
        failure_count = self._track_tool_failure(tool_name, error_message, arguments, error_category)
        
        # Check for repeated patterns using the same error category that was just tracked
        same_pattern_count = sum(1 for error in self.recent_errors
                               if error["tool_name"] == tool_name and
                                  error["error_category"] == error_category)
        
        # Build enhanced message
        retry_message = (
            f"ENHANCED RETRY CONTEXT (Attempt {retry_count}):\n\n"
            f"Tool '{tool_name}' failed with error category: {error_category.value.upper()}\n"
            f"Tool failure count: {failure_count} (Recent similar errors: {same_pattern_count})\n\n"
            f"ERROR ANALYSIS: {specific_guidance}\n\n"
        )
        
        # Add tool schema information
        schema_info = self._get_tool_schema_info(tool_name)
        retry_message += f"TOOL SCHEMA:\n{schema_info}\n"
        
        # Add escalating guidance based on retry count and pattern
        if same_pattern_count >= 3:
            retry_message += (
                "⚠️ REPEATED ERROR PATTERN DETECTED!\n"
                "You have made this same type of error multiple times. Please:\n"
                "1. Carefully review the schema above\n"
                "2. Double-check your argument format and values\n"
                "3. Ensure all required fields are provided\n"
                "4. Verify data types match exactly\n\n"
            )
        
        if retry_count >= 2:
            retry_message += (
                "PROGRESSIVE GUIDANCE:\n"
                "This is your second or later attempt. Focus on:\n"
                "- Exact argument format as shown in the schema\n"
                "- Proper data types (string, number, boolean, etc.)\n"
                "- All required fields must be present\n"
                "- Values must meet any constraints mentioned\n\n"
            )
        
        # Add context-specific guidance
        if error_category == ErrorCategory.MEMORY_ID_ERROR and retrieved_facts:
            retry_message += (
                "MEMORY ID REFERENCE:\n"
                "Available memory facts with valid IDs:\n"
                f"{retrieved_facts}\n\n"
                "CRITICAL: Only use memory_id values that appear exactly in the facts above.\n\n"
            )
        
        # Add examples for commonly failing tools
        if retry_count >= 2 and tool_name in ["update_memory", "save_memory", "write_file"]:
            retry_message += self._get_tool_examples(tool_name)
        
        return retry_message

    def _get_tool_examples(self, tool_name: str) -> str:
        """Provide concrete examples for tools that frequently fail."""
        examples = {
            "update_memory": (
                "CORRECT EXAMPLE for update_memory:\n"
                '{\n'
                '  "memory_id": "507f1f77bcf86cd799439011",\n'
                '  "new_content": "Updated information here"\n'
                '}\n'
                "The memory_id MUST be exactly as shown in retrieved facts.\n\n"
            ),
            "save_memory": (
                "CORRECT EXAMPLE for save_memory:\n"
                '{\n'
                '  "content": "New information to remember for future reference"\n'
                '}\n'
                "Content should be descriptive and self-contained.\n\n"
            ),
            "write_file": (
                "CORRECT EXAMPLE for write_file:\n"
                '{\n'
                '  "file_path": "/full/path/to/file.txt",\n'
                '  "content": "File content here"\n'
                '}\n'
                "Use absolute paths and ensure directories exist.\n\n"
            ),
            "read_file": (
                "CORRECT EXAMPLE for read_file:\n"
                '{\n'
                '  "file_path": "/full/path/to/file.txt"\n'
                '}\n'
                "Use absolute paths to existing files.\n\n"
            ),
            "search_web": (
                "CORRECT EXAMPLE for search_web:\n"
                '{\n'
                '  "query": "specific search terms"\n'
                '}\n'
                "Use clear, specific search terms.\n\n"
            )
        }
        return examples.get(tool_name, "")

    def _should_abort_retry(self, tool_name: str, error_message: str, retry_count: int) -> bool:
        """Determine if retry should be aborted based on error analysis."""
        if retry_count >= TOOL_EXECUTION_RETRY:
            return True
            
        # Check for exact same errors
        exact_same_count = sum(1 for error in self.recent_errors[-5:]
                             if error.get("tool_name") == tool_name and
                                error.get("error_message") == error_message)
        
        if exact_same_count >= 3:
            print(f"[{self.__class__.__name__}] Aborting retry: same error repeated {exact_same_count} times")
            return True
        
        # Use error analyzer to determine if retry is worthwhile
        error_category, _ = self.error_analyzer.analyze_error(error_message, tool_name, {})
        retry_strategy = self.error_analyzer.get_retry_strategy(error_category, retry_count)
        
        return not retry_strategy.get("should_retry", True)

    async def execute_tool_cycle(self, 
                                 base_system_messages: List[Dict[str, str]], 
                                 max_tool_calls: int, 
                                 context_name: str, 
                                 retrieved_facts_context_string: Optional[str]
                                 ) -> Tuple[List[Dict[str, str]], List[Dict]]:
        """
        Executes the main tool interaction loop.
        Returns a list of tool interaction messages and a list of successful tool call details.
        """
        tool_interaction_messages: List[Dict[str, str]] = []
        successful_tool_calls_details: List[Dict] = [] # To store details of successful calls
        tool_calls_made = 0

        # Define tools to exclude from this specific loop (e.g., memory tools handled elsewhere)
        tools_to_exclude_from_main_loop = ['fetch_memory', 'save_memory'] 
        
        main_loop_allowed_tools = None
        if self.allowed_tools is not None:
            main_loop_allowed_tools = [
                tool for tool in self.allowed_tools if tool not in tools_to_exclude_from_main_loop
            ]
        elif self.allowed_tools is None: # All tools configured for the orchestrator are allowed
             all_tool_names = self.tool_executor.get_all_tool_names() 
             main_loop_allowed_tools = [
                 tool for tool in all_tool_names if tool not in tools_to_exclude_from_main_loop
             ]
        
        print(f"[{self.__class__.__name__}] Starting tool cycle. Max calls: {max_tool_calls}. Allowed in loop: {main_loop_allowed_tools}")

        for _ in range(max_tool_calls):
            if tool_calls_made >= max_tool_calls:
                print(f"[{self.__class__.__name__}] Max tool calls ({max_tool_calls}) reached for main loop.")
                break

            # --- Tool Selection with Retry ---
            select_retry_count = 0
            action_decision = None 
            while TOOL_SELECT_RETRY == -1 or select_retry_count <= TOOL_SELECT_RETRY:
                current_history_loop = self.history_manager.get_history() 
                messages_for_loop = base_system_messages + current_history_loop

                if select_retry_count > 0:
                    retry_context_content = (
                        f"RETRY CONTEXT: Previous attempt (attempt {select_retry_count}) to select a tool failed or returned an invalid format. "
                        f"Please review the conversation history and available tools, then choose the next appropriate action (tool or null)."
                    )
                    # Create the message dictionary
                    retry_context_message = {'role': 'system', 'content': retry_context_content}
                    messages_for_loop.append(retry_context_message)
                    # Also add to tool_interaction_messages for transparency
                    tool_interaction_messages.append(retry_context_message)
                    await self.history_manager.add_message('system', retry_context_content) # Keep history manager updated too
                    print(f"[{self.__class__.__name__}] Added retry context for tool selection (Attempt {select_retry_count + 1}).")
                    await asyncio.sleep(1) # Keep a small delay for retries

                action_decision = await self.llm_client.get_next_action(
                    messages_for_loop,
                    allowed_tools=main_loop_allowed_tools,
                    context_type=context_name
                )
                if action_decision and action_decision.get("action_type") in ["tool_call", "text_response"]:
                    break
                else:
                    print(f"[{self.__class__.__name__}] Error or invalid format in tool selection (Attempt {select_retry_count + 1}): {action_decision}.")
                    if TOOL_SELECT_RETRY != -1 and select_retry_count >= TOOL_SELECT_RETRY:
                        print(f"[{self.__class__.__name__}] Tool selection failed after max retries ({TOOL_SELECT_RETRY}). Breaking loop.")
                        action_decision = None 
                        break 
                    elif TOOL_SELECT_RETRY == 0:
                        print(f"[{self.__class__.__name__}] Tool selection failed (retries disabled). Breaking loop.")
                        action_decision = None 
                        break 
                    else:
                        print(f"[{self.__class__.__name__}] Retrying tool selection (attempt {select_retry_count + 1}/{TOOL_SELECT_RETRY if TOOL_SELECT_RETRY != -1 else 'infinite'})...")
                        select_retry_count += 1
            
            if not action_decision:
                print(f"[{self.__class__.__name__}] Failed to get a valid response after retries or retries disabled. Breaking main tool loop.")
                break 
            
            if action_decision.get("action_type") == "text_response":
                print(f"[{self.__class__.__name__}] LLM provided direct text response: '{action_decision.get('text', '')[:50]}...'")
                # Add to history_manager, but this is not a "tool interaction" per se for tool_interaction_messages
                # The main orchestrator will handle adding this to history if it's the final response.
                # For now, we break, and the orchestrator will pick up this text_response.
                # We can add it to tool_interaction_messages if we want to signify the loop terminated due to text response.
                text_response_message = {'role': 'assistant', 'content': action_decision.get('text', '')}
                # tool_interaction_messages.append(text_response_message) # Optional: if you want to track this termination
                await self.history_manager.add_message('assistant', action_decision.get('text', '')) # Ensure history is up-to-date
                break 
            
            # action_type "tool_choice" is now "tool_call"
            if action_decision.get("action_type") != "tool_call":
                print(f"[{self.__class__.__name__}] Unexpected action_type after validation: {action_decision.get('action_type')}. Breaking main tool loop.")
                break

            tool_name = action_decision.get("tool_name")
            # Arguments are now part of action_decision if action_type is "tool_call"
            arguments = action_decision.get("tool_args")
            # tool_call_id might be provided by OpenAI, otherwise, we'll generate one
            tool_call_id = action_decision.get("tool_call_id")

            if tool_name is None: # Should not happen if action_type is "tool_call"
                print(f"[{self.__class__.__name__}] LLM decided no further tools needed (tool_name is None despite action_type tool_call). Breaking.")
                break
            if arguments is None: # Should not happen if action_type is "tool_call" and tool_name is present
                print(f"[{self.__class__.__name__}] LLM chose tool {tool_name} but arguments are missing. Breaking.")
                # Add an error message to history?
                error_content = f"System: Tool '{tool_name}' was chosen by the LLM, but arguments were missing in the decision."
                await self.history_manager.add_message('system', error_content)
                tool_interaction_messages.append({'role': 'system', 'content': error_content})
                break

            # Get tool name and arguments from action_decision
            tool_name = action_decision.get("tool_name")
            arguments = action_decision.get("tool_args")
            
            # Setup for timing
            tool_start_time = time.monotonic()
            
            print(f"[{self.__class__.__name__}] Tool Orchestrator: Attempting tool call for '{tool_name}'.")
            tool_definition = find_tool(tool_name)
            
            if tool_definition is None:
                error_message = f"System: Error - Tool '{tool_name}' not found by ToolOrchestrator."
                print(f"[{self.__class__.__name__}] {error_message}")
                await self.history_manager.add_message("system", error_message)
                tool_interaction_messages.append({'role': 'system', 'content': error_message})
                final_tool_status = "error"
            else:
                # Execute tool with retry logic
                final_tool_status = "error"  # Default to error
                tool_result = None
                tool_retry_count = 0
                
                while tool_retry_count <= TOOL_EXECUTION_RETRY:
                    # Add system message indicating the tool call attempt
                    args_summary = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
                    if tool_retry_count == 0:
                        call_message = f"System: Calling tool '{tool_name}' with arguments: {args_summary}"
                    else:
                        call_message = f"System: Retrying tool '{tool_name}' (attempt {tool_retry_count + 1}) with arguments: {args_summary}"
                    
                    await self.history_manager.add_message("system", call_message)
                    tool_interaction_messages.append({'role': 'system', 'content': call_message})
                    
                    try:
                        # Execute the tool
                        tool_result = await self.tool_executor.execute(
                            tool_name,
                            arguments,
                            self.history_manager,
                            None  # settings_manager not available in this context
                        )
                        
                        # Check if the tool_result indicates an error
                        if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                            print(f"[{self.__class__.__name__}] Tool '{tool_name}' execution resulted in an error: {tool_result}")
                            
                            # Check if we should abort or retry
                            if self._should_abort_retry(tool_name, tool_result, tool_retry_count):
                                print(f"[{self.__class__.__name__}] Aborting retry for tool '{tool_name}' after {tool_retry_count + 1} attempts")
                                break
                            
                            # Generate enhanced retry message
                            enhanced_retry_message = self._generate_retry_message(
                                tool_name, tool_result, arguments, tool_retry_count + 1, retrieved_facts_context_string
                            )
                            
                            await self.history_manager.add_message("system", enhanced_retry_message)
                            tool_interaction_messages.append({'role': 'system', 'content': enhanced_retry_message})
                            
                            # Wait before retry
                            if tool_retry_count < TOOL_EXECUTION_RETRY:
                                await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                                
                            tool_retry_count += 1
                            
                            # For argument-related errors, we need to get new arguments from the LLM
                            error_category, _ = self.error_analyzer.analyze_error(tool_result, tool_name, arguments)
                            if error_category in [ErrorCategory.INVALID_ARGUMENT, ErrorCategory.MISSING_ARGUMENT]:
                                # Get current history for argument regeneration
                                current_history = self.history_manager.get_history()
                                messages_for_retry = base_system_messages + current_history
                                
                                # Request new action with enhanced context
                                retry_action = await self.llm_client.get_next_action(
                                    messages_for_retry,
                                    allowed_tools=[tool_name],  # Force same tool
                                    context_type=context_name
                                )
                                
                                if retry_action and retry_action.get("action_type") == "tool_call":
                                    arguments = retry_action.get("tool_args", arguments)
                                    print(f"[{self.__class__.__name__}] Regenerated arguments for '{tool_name}': {arguments}")
                                else:
                                    print(f"[{self.__class__.__name__}] Failed to regenerate arguments for '{tool_name}'")
                                    break
                            
                            continue  # Retry with same or new arguments
                        else:
                            # Success!
                            successful_tool_calls_details.append(
                                ToolCallDetails(
                                    tool_name=tool_name,
                                    arguments=arguments,
                                    result=tool_result,
                                    execution_time=time.monotonic() - tool_start_time
                                )
                            )
                            final_tool_status = "success"
                            print(f"[{self.__class__.__name__}] Tool '{tool_name}' executed successfully.")
                            break  # Exit retry loop on success
                            
                    except Exception as e:
                        # Handle exceptions during tool execution
                        exception_message = f"System: An unexpected error occurred during execution of tool '{tool_name}': {str(e)}"
                        print(f"[{self.__class__.__name__}] Exception during execution of tool '{tool_name}': {e}")
                        
                        # Check if we should retry the exception
                        if self._should_abort_retry(tool_name, str(e), tool_retry_count):
                            await self.history_manager.add_message("system", exception_message)
                            tool_interaction_messages.append({'role': 'system', 'content': exception_message})
                            break
                        
                        # Generate enhanced retry message for exception
                        enhanced_exception_message = self._generate_retry_message(
                            tool_name, str(e), arguments, tool_retry_count + 1, retrieved_facts_context_string
                        )
                        
                        await self.history_manager.add_message("system", enhanced_exception_message)
                        tool_interaction_messages.append({'role': 'system', 'content': enhanced_exception_message})
                        
                        # Wait before retry
                        if tool_retry_count < TOOL_EXECUTION_RETRY:
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            
                        tool_retry_count += 1
                        continue
                
                # Add final result message
                if final_tool_status == "success":
                    result_summary = self._summarize_for_history(str(tool_result), MAX_RESULT_SUMMARY_LEN)
                    result_message = f"System: Tool '{tool_name}' executed successfully. Result: {result_summary}"
                    await self.history_manager.add_message("system", result_message)
                    tool_interaction_messages.append({'role': 'system', 'content': result_message})
                else:
                    failure_summary = self._summarize_for_history(str(tool_result), MAX_RESULT_SUMMARY_LEN)
                    failure_message = f"System: Tool '{tool_name}' failed after {tool_retry_count} attempts. Final error: {failure_summary}"
                    await self.history_manager.add_message("system", failure_message)
                    tool_interaction_messages.append({'role': 'system', 'content': failure_message})
            
            # Increment tool_calls_made for this attempt
            tool_calls_made += 1
            
            # If this was an error, break the loop
            if final_tool_status == "error":
                print(f"[{self.__class__.__name__}] Tool '{tool_name}' failed. Breaking main tool loop.")
                break

        print(f"[{self.__class__.__name__}] Tool cycle finished. Interactions: {len(tool_interaction_messages)}, Successful calls: {len(successful_tool_calls_details)}")
        return tool_interaction_messages, successful_tool_calls_details