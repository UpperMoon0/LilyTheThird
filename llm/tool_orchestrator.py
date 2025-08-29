import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

from tools.tools import find_tool # find_tool is used
from .error_analyzer import ErrorAnalyzer, ErrorCategory
from .schemas import ToolCallDetails
from .logging_config import get_logging_manager


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
        
        # Initialize comprehensive logging
        self.logging_manager = get_logging_manager()
        self.orchestrator_logger = self.logging_manager.get_logger('tool_orchestrator')
        self.execution_logger = self.logging_manager.get_logger('tool_execution')
        self.error_logger = self.logging_manager.get_logger('error_analysis')
        self.decision_logger = self.logging_manager.get_logger('llm_decisions')
        self.retry_logger = self.logging_manager.get_logger('retry_logic')
        
        self.orchestrator_logger.info("ToolOrchestrator initialized", extra={
            'allowed_tools': allowed_tools,
            'context_name': 'initialization'
        })

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
        failure_count = self.tool_failure_counts[tool_name]
        
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
        
        # Log the failure tracking
        self.error_logger.warning("Tool failure tracked", extra={
            'tool_name': tool_name,
            'error_category': error_category.value,
            'failure_count': failure_count,
            'arguments': arguments,
            'error_message': error_message[:200]  # Truncated for readability
        })
        
        # Check for patterns and log if detected
        same_pattern_count = sum(1 for error in self.recent_errors
                               if error["tool_name"] == tool_name and
                                  error["error_category"] == error_category)
        
        if same_pattern_count >= 3:
            self.logging_manager.log_error_pattern(
                'error_analysis', tool_name, error_category.value,
                same_pattern_count, self.recent_errors[-5:]
            )
            
        return failure_count

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
        
        # For code-level errors, provide immediate termination guidance
        if error_category == ErrorCategory.CODE_ERROR:
            return (
                f"CRITICAL CODE-LEVEL ERROR DETECTED:\n\n"
                f"Tool '{tool_name}' failed due to a systematic code issue:\n"
                f"Error: {error_message}\n\n"
                f"ANALYSIS: {specific_guidance}\n\n"
                f"⚠️ This is NOT a retry-able error. It indicates a programming issue\n"
                f"that requires code fixes, not argument adjustments.\n"
                f"Common causes: API signature mismatches, method call errors, missing dependencies.\n\n"
                f"IMMEDIATE ACTION REQUIRED: Review and fix the underlying code issue.\n"
                f"No further retry attempts will be made for this systematic error."
            )
        
        # Track this failure
        failure_count = self._track_tool_failure(tool_name, error_message, arguments, error_category)
        
        # Check for repeated patterns using the same error category that was just tracked
        same_pattern_count = sum(1 for error in self.recent_errors
                               if error["tool_name"] == tool_name and
                                  error["error_category"] == error_category)
        
        # Log the retry message generation
        self.logging_manager.log_retry_attempt(
            'retry_logic', tool_name, retry_count, error_category.value,
            error_message, arguments
        )
        
        self.retry_logger.debug("Generating enhanced retry message", extra={
            'tool_name': tool_name,
            'retry_count': retry_count,
            'error_category': error_category.value,
            'failure_count': failure_count,
            'same_pattern_count': same_pattern_count,
            'specific_guidance': specific_guidance[:100],  # Truncated
            'has_retrieved_facts': retrieved_facts is not None
        })
        
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

    def _get_allowed_tool_names(self, tools_to_exclude: Optional[List[str]] = None) -> List[str]:
        """
        Determines the list of tool names that can be used in the main loop.
        It starts with the context-specific allowed tools and removes any
        that are designated for exclusion.
        """
        tools_to_exclude = tools_to_exclude or []
        
        if self.allowed_tools is None:
            self.orchestrator_logger.warning("`self.allowed_tools` is None. No tools will be available for the main loop.")
            all_available_tools = []
        else:
            all_available_tools = self.allowed_tools
            
        main_loop_tools = [tool for tool in all_available_tools if tool not in tools_to_exclude]
        
        self.orchestrator_logger.info("Determined main loop tools", extra={
            'initial_allowed_tools': self.allowed_tools,
            'tools_to_exclude': tools_to_exclude,
            'final_main_loop_tools': main_loop_tools
        })
        
        return main_loop_tools

    def _prepare_structured_tools(self, tool_names: List[str], context_name: str) -> List[Dict]:
        """
        Prepares the detailed, structured tool definitions for the LLM prompt
        based on a list of tool names.
        """
        structured_tools = []
        for tool_name in tool_names:
            tool_definition = find_tool(tool_name)
            if tool_definition and tool_definition.argument_schema:
                try:
                    schema = tool_definition.argument_schema.model_json_schema()
                    
                    if 'title' in schema:
                        del schema['title']
                    
                    structured_tools.append({
                        "name": tool_definition.name,
                        "description": tool_definition.description,
                        "parameters": schema
                    })
                except Exception as e:
                    self.error_logger.error(f"Failed to generate schema for tool '{tool_name}' in context '{context_name}': {e}", exc_info=True)
            elif tool_definition:
                 structured_tools.append({
                        "name": tool_definition.name,
                        "description": tool_definition.description,
                        "parameters": {"type": "object", "properties": {}}
                    })
            else:
                self.error_logger.warning(f"Tool '{tool_name}' defined in allowed_tools for context '{context_name}' not found.")
        
        return structured_tools

    def _should_abort_retry(self, tool_name: str, error_message: str, retry_count: int) -> bool:
        """Determine if retry should be aborted based on error analysis."""
        # First, analyze the error to check for code-level issues
        error_category, _ = self.error_analyzer.analyze_error(error_message, tool_name, {})
        
        # Immediately abort for code-level errors (TypeError, API mismatches, etc.)
        if error_category == ErrorCategory.CODE_ERROR:
            self.retry_logger.warning("Aborting retry: code-level error detected", extra={
                'tool_name': tool_name,
                'error_category': error_category.value,
                'error_message': error_message[:200],  # Truncated
                'reason': 'systematic_code_issue'
            })
            return True
        
        if retry_count >= TOOL_EXECUTION_RETRY:
            self.retry_logger.info("Aborting retry: max attempts reached", extra={
                'tool_name': tool_name,
                'retry_count': retry_count,
                'max_retries': TOOL_EXECUTION_RETRY
            })
            return True
            
        # Check for exact same errors
        exact_same_count = sum(1 for error in self.recent_errors[-5:]
                             if error.get("tool_name") == tool_name and
                                error.get("error_message") == error_message)
        
        if exact_same_count >= 3:
            self.retry_logger.warning("Aborting retry: identical error repeated", extra={
                'tool_name': tool_name,
                'exact_same_count': exact_same_count,
                'error_message': error_message[:100]  # Truncated
            })
            return True
        
        # Use error analyzer to determine if retry is worthwhile
        retry_strategy = self.error_analyzer.get_retry_strategy(error_category, retry_count)
        
        should_abort = not retry_strategy.get("should_retry", True)
        if should_abort:
            self.retry_logger.info("Aborting retry: error analyzer recommendation", extra={
                'tool_name': tool_name,
                'error_category': error_category.value,
                'retry_count': retry_count,
                'retry_strategy': retry_strategy
            })
        
        return should_abort

    async def execute_tool_cycle(self,
                                 base_system_messages: List[Dict[str, str]],
                                 max_tool_calls: int,
                                 context_name: str,
                                 retrieved_facts_context_string: Optional[str]
                                 ) -> Tuple[Optional[str], List[ToolCallDetails]]:
        """
        Executes a streamlined, single-call tool cycle using native tool calling.
        """
        successful_tool_calls_details: List[ToolCallDetails] = []
        tool_calls_made = 0

        # Exclude memory tools which are handled separately
        main_loop_allowed_tool_names = self._get_allowed_tool_names(['fetch_memory', 'save_memory'])
        structured_tools_for_llm = self._prepare_structured_tools(main_loop_allowed_tool_names, context_name)

        for _ in range(max_tool_calls):
            if tool_calls_made >= max_tool_calls:
                self.orchestrator_logger.info("Max tool calls reached.", extra={'count': max_tool_calls})
                break

            current_history = self.history_manager.get_history()
            messages_for_llm = base_system_messages + current_history
            
            if retrieved_facts_context_string:
                messages_for_llm.append({'role': 'system', 'content': retrieved_facts_context_string})

            # Single call to decide action (text or tool) and get arguments
            action_decision = await self.llm_client.get_next_action(
                messages=messages_for_llm,
                allowed_tools=structured_tools_for_llm,
                context_type=context_name
            )

            if not action_decision or action_decision.get("action_type") == "error":
                error_detail = action_decision.get('error', 'No decision from LLM') if action_decision else 'No decision from LLM'
                self.error_logger.error("Aborting tool cycle due to error in action decision.", extra={'error': error_detail})
                break

            if action_decision.get("action_type") == "text_response":
                self.decision_logger.info("LLM decided to respond with text, ending tool cycle.")
                return action_decision.get('text', ''), successful_tool_calls_details

            if action_decision.get("action_type") != "tool_call":
                self.error_logger.warning(f"Unknown action type received: {action_decision.get('action_type')}. Aborting.")
                break

            tool_name = action_decision.get("tool_name")
            arguments = action_decision.get("tool_args", {})
            tool_call_id = f"call_{tool_name}_{int(time.time())}" # Create a unique ID

            if not tool_name:
                self.error_logger.warning("Tool call action received without a tool name.")
                continue

            # Add the assistant's decision to call the tool to history
            assistant_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments)
                    }
                }]
            }
            self.history_manager.add_message_to_history(assistant_message)

            # Execute the tool
            execution_result = await self._execute_tool(
                tool_name, arguments, tool_call_id, context_name
            )

            if execution_result:
                successful_tool_calls_details.append(execution_result)
                tool_calls_made += 1
                
                # Add tool result to history for the next cycle iteration
                tool_result_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": self._summarize_for_history(execution_result.result, MAX_RESULT_SUMMARY_LEN)
                }
                self.history_manager.add_message_to_history(tool_result_message)
            else:
                # Add a tool result message indicating failure
                error_result_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": "Tool execution failed."
                }
                self.history_manager.add_message_to_history(error_result_message)
                self.error_logger.error(f"Tool execution failed for '{tool_name}'. Aborting cycle.")
                break

        return None, successful_tool_calls_details

    async def _execute_tool(self, tool_name: str, arguments: Dict,
                                    tool_call_id: str, context_name: str) -> Optional[ToolCallDetails]:
        """Executes a tool with retry logic and detailed error handling."""
        for i in range(TOOL_EXECUTION_RETRY):
            retry_count = i + 1
            try:
                tool_start_time = time.monotonic()
                tool_result = await self.tool_executor.execute(tool_name, arguments)
                execution_time = time.monotonic() - tool_start_time

                if not (isinstance(tool_result, str) and tool_result.startswith("Error:")):
                    self.execution_logger.info("Tool executed successfully", extra={
                        'tool_name': tool_name, 'arguments': arguments, 'execution_time': execution_time
                    })
                    return ToolCallDetails(
                        tool_name=tool_name,
                        arguments=arguments,
                        result=tool_result,
                        execution_time=execution_time,
                        tool_call_id=tool_call_id
                    )

                # --- Error Handling & Retry Logic ---
                error_message = tool_result
                self.error_logger.warning(f"Tool execution failed (attempt {retry_count})", extra={
                    'tool_name': tool_name, 'error': error_message, 'arguments': arguments
                })

                if self._should_abort_retry(tool_name, error_message, retry_count):
                    self.error_logger.error(f"Aborting retries for tool '{tool_name}' due to non-recoverable error or max retries.", extra={'tool_name': tool_name})
                    return None

                # Generate enhanced context for the next attempt
                retry_context = self._generate_retry_message(tool_name, error_message, arguments, retry_count)
                
                # Add retry context to history
                self.history_manager.add_message_to_history({'role': 'system', 'content': retry_context})
                
                # Get new arguments from LLM for the retry
                current_history = self.history_manager.get_history()
                messages_for_retry = base_system_messages + current_history
                
                structured_tools_for_llm = self._prepare_structured_tools([tool_name], context_name)

                new_action = await self.llm_client.get_next_action(
                    messages=messages_for_retry,
                    allowed_tools=structured_tools_for_llm,
                    context_type=context_name,
                    force_tool_options=[tool_name] # Force the same tool
                )

                if new_action and new_action.get("action_type") == "tool_call":
                    arguments = new_action.get("tool_args", {}) # Update arguments for next loop
                    self.retry_logger.info(f"Retrying tool '{tool_name}' with new arguments.", extra={'new_arguments': arguments})
                else:
                    self.error_logger.error(f"Failed to get new arguments for retry on tool '{tool_name}'. Aborting.", extra={'decision': new_action})
                    return None

            except Exception as e:
                self.error_logger.critical(f"Unhandled exception during tool execution: {e}", exc_info=True)
                return None
        
        self.error_logger.error(f"Tool '{tool_name}' failed after {TOOL_EXECUTION_RETRY} retries.")
        return None