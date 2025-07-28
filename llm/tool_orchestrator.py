import asyncio
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

from tools.tools import find_tool # find_tool is used
from .error_analyzer import ErrorAnalyzer, ErrorCategory
from .schemas import ToolCallDetails
from .logging_config import get_logging_manager


# Instructional prompt for LLM regarding tool schema adherence
INSTRUCTIONAL_PROMPT_FOR_SCHEMA = """You will be provided with a list of available tools, including their names, descriptions, and detailed argument schemas.
When you decide to use a tool, you MUST strictly adhere to its provided argument schema.
Ensure all required parameters are included, and all parameter values precisely match the specified types and formats.
Pay close attention to data types (e.g., string, number, boolean, list, object) and any constraints mentioned in the schema."""

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
                                 ) -> Tuple[Optional[str], List[Dict]]:
        """
        OPTIMIZED tool execution cycle - streamlined for maximum efficiency.
        Reduces verbose logging and eliminates redundant system messages.
        """
        successful_tool_calls_details: List[Dict] = []
        tool_calls_made = 0

        # Get allowed tools efficiently
        tools_to_exclude = ['fetch_memory', 'save_memory']
        main_loop_allowed_tool_names = self._get_allowed_tool_names(tools_to_exclude)
        
        # Prepare structured tools with minimal processing
        structured_tools_for_llm = self._prepare_structured_tools(main_loop_allowed_tool_names, context_name)

        for cycle_iteration in range(max_tool_calls):
            if tool_calls_made >= max_tool_calls:
                break

            # STREAMLINED tool selection - single attempt with minimal retry
            action_decision = await self._get_tool_decision_optimized(
                base_system_messages, structured_tools_for_llm, context_name, retrieved_facts_context_string
            )
            
            if not action_decision:
                break
            
            # Handle text response immediately
            if action_decision.get("action_type") == "text_response":
                text_content = action_decision.get('text', '')
                # The base orchestrator is now responsible for adding all messages to history.
                return text_content, successful_tool_calls_details
            
            # Handle tool call
            if action_decision.get("action_type") != "tool_call":
                break

            tool_name = action_decision.get("tool_name")
            arguments = action_decision.get("tool_args")
            tool_call_id = action_decision.get("tool_call_id")

            if not tool_name or arguments is None:
                break

            # OPTIMIZED tool execution with minimal logging
            execution_result = await self._execute_tool(
                tool_name, arguments, tool_call_id, context_name
            )
            
            if execution_result:
                successful_tool_calls_details.append(execution_result)
                tool_calls_made += 1
            else:
                break  # Stop on execution failure

        return None, successful_tool_calls_details

    def _get_allowed_tool_names(self, tools_to_exclude: List[str]) -> List[str]:
        """Efficiently get allowed tool names."""
        if self.allowed_tools is not None:
            return [tool for tool in self.allowed_tools if tool not in tools_to_exclude]
        else:
            all_tool_names = self.tool_executor.get_all_tool_names()
            return [tool for tool in all_tool_names if tool not in tools_to_exclude]

    def _prepare_structured_tools(self, tool_names: List[str], context_name: str) -> List[Dict]:
        """Prepare structured tools with minimal error handling."""
        structured_tools = []
        for tool_name in tool_names:
            tool_definition = find_tool(tool_name)
            if tool_definition and hasattr(tool_definition, 'argument_schema') and tool_definition.argument_schema:
                try:
                    schema = tool_definition.argument_schema.model_json_schema()
                    description = getattr(tool_definition, 'description', "No description available.") or "No description available."
                    
                    structured_tools.append({
                        "name": tool_name,
                        "description": description,
                        "parameters": schema
                    })
                except Exception:
                    continue  # Skip problematic tools silently
        return structured_tools

    async def _get_tool_decision_optimized(self, base_system_messages: List[Dict],
                                         structured_tools: List[Dict],
                                         context_name: str,
                                         retrieved_facts_context_string: Optional[str] = None) -> Optional[Dict]:
        """Optimized tool decision using the new tagged prompt format."""
        current_history = self.history_manager.get_history()

        # Extract personality
        personality_prompt = base_system_messages[0]['content'] if base_system_messages else "You are a helpful assistant."
        personality_tag = f"<personality_instruction>{personality_prompt}</personality_instruction>"

        # Get current time
        try:
            current_time_str = datetime.now().astimezone().isoformat()
        except Exception:
            current_time_str = "Time not available"
        time_tag = f"<time>{current_time_str}</time>"

        # Format memory
        memory_tag = ""
        if retrieved_facts_context_string:
            memory_tag = f"<retrieved_memory>\n{retrieved_facts_context_string}\n</retrieved_memory>"

        # Format available tools
        tools_str = json.dumps(structured_tools, indent=2)
        tools_tag = f"<available_tools>\n{tools_str}\n</available_tools>"

        # Format conversation history into a flat string without nested tags
        history_str = ""
        for msg in current_history:
            role = msg.get('role')
            content = msg.get('content', '')
            if role == 'user':
                history_str += f"User: {content}\n"
            elif role == 'assistant':
                if msg.get('tool_calls'):
                    # Represent tool calls in a simplified, non-tagged way
                    tool_calls = msg.get('tool_calls', [])
                    calls_str_list = []
                    for tc in tool_calls:
                        if 'function' in tc and 'name' in tc['function'] and 'arguments' in tc['function']:
                            calls_str_list.append(f"{tc['function']['name']}({tc['function']['arguments']})")
                    calls_str = ", ".join(calls_str_list)
                    history_str += f"Assistant (tool call): {calls_str}\n"
                elif content:
                    history_str += f"Assistant: {content}\n"
            elif role == 'tool':
                tool_name = msg.get('name', 'N/A')
                # Summarize long tool results for conciseness
                summary = str(content)
                if len(summary) > 500:
                    summary = summary[:500] + "... (truncated)"
                history_str += f"Tool ({tool_name}) Result: {summary}\n"
        
        history_tag = f"<conversation_history>\n{history_str.strip()}\n</conversation_history>" if history_str.strip() else ""

        # Assemble the final prompt
        final_prompt_content = (
            f"{personality_tag}\n"
            f"{time_tag}\n"
            f"{memory_tag}\n"
            f"{history_tag}\n"
            f"{tools_tag}"
        ).strip()

        messages_for_llm = [{'role': 'user', 'content': final_prompt_content}]

        # Call LLM
        action_decision = await self.llm_client.get_next_action(
            messages_for_llm,
            allowed_tools=structured_tools,
            context_type=context_name
        )
        
        if action_decision and action_decision.get("action_type") in ["tool_call", "text_response"]:
            return action_decision
        
        return None

    async def _execute_tool(self, tool_name: str, arguments: Dict,
                                    tool_call_id: str, context_name: str) -> Optional[ToolCallDetails]:
        """Optimized tool execution with minimal logging and retry."""
        tool_definition = find_tool(tool_name)
        if not tool_definition:
            return None

        try:
            tool_start_time = time.monotonic()
            tool_result = await self.tool_executor.execute(tool_name, arguments)
            execution_time = time.monotonic() - tool_start_time
            
            # Only retry once for errors, and only for specific error types
            if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                error_category, _ = self.error_analyzer.analyze_error(tool_result, tool_name, arguments)
                
                # Only retry for argument errors, not code errors
                if error_category in [ErrorCategory.INVALID_ARGUMENT, ErrorCategory.MISSING_ARGUMENT]:
                    # Single retry attempt with new arguments
                    current_history = self.history_manager.get_history()
                    messages_for_retry = current_history[-10:]  # Use only recent history
                    
                    retry_action = await self.llm_client.get_next_action(
                        messages_for_retry,
                        allowed_tools=[{"name": tool_name, "description": tool_definition.description,
                                      "parameters": tool_definition.argument_schema.model_json_schema()}],
                        context_type=context_name
                    )
                    
                    if retry_action and retry_action.get("action_type") == "tool_call":
                        new_arguments = retry_action.get("tool_args", arguments)
                        tool_result = await self.tool_executor.execute(tool_name, new_arguments)
                        arguments = new_arguments  # Update arguments for result tracking

            # Return result only if successful
            if not (isinstance(tool_result, str) and tool_result.startswith("Error:")):
                return ToolCallDetails(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=tool_result,
                    execution_time=execution_time,
                    tool_call_id=tool_call_id
                )
                
        except Exception:
            pass  # Silently handle exceptions to avoid verbose error logging
            
        return None