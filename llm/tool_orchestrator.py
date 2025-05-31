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
from .logging_config import get_logging_manager

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
        error_category, _ = self.error_analyzer.analyze_error(error_message, tool_name, {})
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
        
        # Log the start of tool cycle with comprehensive context
        self.orchestrator_logger.info("Starting tool execution cycle", extra={
            'context_name': context_name,
            'max_tool_calls': max_tool_calls,
            'allowed_tools': main_loop_allowed_tools,
            'has_retrieved_facts': retrieved_facts_context_string is not None,
            'current_tool_calls': tool_calls_made
        })

        for cycle_iteration in range(max_tool_calls):
            if tool_calls_made >= max_tool_calls:
                self.orchestrator_logger.info("Tool cycle terminated: max calls reached", extra={
                    'max_tool_calls': max_tool_calls,
                    'tools_called': tool_calls_made,
                    'context_name': context_name
                })
                break

            # --- Tool Selection with Retry ---
            select_retry_count = 0
            action_decision = None
            
            self.orchestrator_logger.debug("Starting tool selection phase", extra={
                'cycle_iteration': cycle_iteration,
                'available_tools': main_loop_allowed_tools,
                'context_name': context_name
            })
            
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
                    
                    self.decision_logger.warning("Tool selection retry required", extra={
                        'select_retry_count': select_retry_count,
                        'cycle_iteration': cycle_iteration,
                        'context_name': context_name,
                        'available_tools': main_loop_allowed_tools
                    })
                    await asyncio.sleep(1) # Keep a small delay for retries

                # Log the LLM decision request
                self.decision_logger.debug("Requesting LLM action decision", extra={
                    'attempt': select_retry_count + 1,
                    'message_count': len(messages_for_loop),
                    'available_tools': main_loop_allowed_tools,
                    'context_name': context_name
                })

                action_decision = await self.llm_client.get_next_action(
                    messages_for_loop,
                    allowed_tools=main_loop_allowed_tools,
                    context_type=context_name
                )
                
                # Log the LLM's decision
                if action_decision:
                    decision_type = action_decision.get("action_type", "unknown")
                    tool_name = action_decision.get("tool_name", "null")
                    
                    self.logging_manager.log_tool_decision(
                        'llm_decisions', tool_name,
                        f"Action type: {decision_type}", context_name,
                        action_decision.get("tool_args")
                    )
                    
                    if decision_type in ["tool_call", "text_response"]:
                        self.decision_logger.info("Valid LLM decision received", extra={
                            'decision_type': decision_type,
                            'tool_name': tool_name,
                            'attempt': select_retry_count + 1,
                            'context_name': context_name
                        })
                        break
                    else:
                        self.decision_logger.warning("Invalid LLM decision format", extra={
                            'decision_type': decision_type,
                            'attempt': select_retry_count + 1,
                            'full_decision': action_decision,
                            'context_name': context_name
                        })
                else:
                    self.decision_logger.error("LLM returned null decision", extra={
                        'attempt': select_retry_count + 1,
                        'context_name': context_name
                    })
                
                # Handle retry logic
                if TOOL_SELECT_RETRY != -1 and select_retry_count >= TOOL_SELECT_RETRY:
                    self.orchestrator_logger.error("Tool selection failed: max retries exceeded", extra={
                        'max_retries': TOOL_SELECT_RETRY,
                        'context_name': context_name,
                        'cycle_iteration': cycle_iteration
                    })
                    action_decision = None
                    break
                elif TOOL_SELECT_RETRY == 0:
                    self.orchestrator_logger.error("Tool selection failed: retries disabled", extra={
                        'context_name': context_name,
                        'cycle_iteration': cycle_iteration
                    })
                    action_decision = None
                    break
                else:
                    self.orchestrator_logger.debug("Retrying tool selection", extra={
                        'retry_attempt': select_retry_count + 1,
                        'max_retries': TOOL_SELECT_RETRY if TOOL_SELECT_RETRY != -1 else 'infinite',
                        'context_name': context_name
                    })
                    select_retry_count += 1
            
            if not action_decision:
                self.orchestrator_logger.error("Tool cycle terminated: no valid decision received", extra={
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration,
                    'select_retries_attempted': select_retry_count
                })
                break
            
            if action_decision.get("action_type") == "text_response":
                text_content = action_decision.get('text', '')
                self.logging_manager.log_llm_response(
                    'llm_decisions', context_name, 'text_response',
                    text_content, len(base_system_messages) + len(current_history_loop)
                )
                
                text_response_message = {'role': 'assistant', 'content': text_content}
                await self.history_manager.add_message('assistant', text_content)
                
                self.orchestrator_logger.info("Tool cycle terminated: LLM provided direct text response", extra={
                    'response_length': len(text_content),
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration
                })
                break
            
            # action_type "tool_choice" is now "tool_call"
            if action_decision.get("action_type") != "tool_call":
                self.orchestrator_logger.error("Tool cycle terminated: unexpected action type", extra={
                    'action_type': action_decision.get('action_type'),
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration,
                    'full_decision': action_decision
                })
                break

            tool_name = action_decision.get("tool_name")
            arguments = action_decision.get("tool_args")
            tool_call_id = action_decision.get("tool_call_id")

            if tool_name is None:
                self.orchestrator_logger.error("Tool cycle terminated: tool_name is None despite tool_call action_type", extra={
                    'action_decision': action_decision,
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration
                })
                break
                
            if arguments is None:
                error_content = f"System: Tool '{tool_name}' was chosen by the LLM, but arguments were missing in the decision."
                await self.history_manager.add_message('system', error_content)
                tool_interaction_messages.append({'role': 'system', 'content': error_content})
                
                self.orchestrator_logger.error("Tool cycle terminated: arguments missing for tool", extra={
                    'tool_name': tool_name,
                    'action_decision': action_decision,
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration
                })
                break

            # Setup for timing
            tool_start_time = time.monotonic()
            
            self.orchestrator_logger.info("Starting tool execution", extra={
                'tool_name': tool_name,
                'arguments': arguments,
                'tool_call_id': tool_call_id,
                'context_name': context_name,
                'cycle_iteration': cycle_iteration
            })
            tool_definition = find_tool(tool_name)
            
            if tool_definition is None:
                error_message = f"System: Error - Tool '{tool_name}' not found by ToolOrchestrator."
                
                self.orchestrator_logger.error("Tool definition not found", extra={
                    'tool_name': tool_name,
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration
                })
                
                await self.history_manager.add_message("system", error_message)
                tool_interaction_messages.append({'role': 'system', 'content': error_message})
                final_tool_status = "error"
            else:
                # Execute tool with retry logic
                final_tool_status = "error"  # Default to error
                tool_result = None
                tool_retry_count = 0
                
                self.execution_logger.info("Starting tool execution with retry logic", extra={
                    'tool_name': tool_name,
                    'max_retries': TOOL_EXECUTION_RETRY,
                    'arguments': arguments,
                    'context_name': context_name
                })
                
                while tool_retry_count <= TOOL_EXECUTION_RETRY:
                    # Add system message indicating the tool call attempt
                    args_summary = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
                    if tool_retry_count == 0:
                        call_message = f"System: Calling tool '{tool_name}' with arguments: {args_summary}"
                    else:
                        call_message = f"System: Retrying tool '{tool_name}' (attempt {tool_retry_count + 1}) with arguments: {args_summary}"
                    
                    await self.history_manager.add_message("system", call_message)
                    tool_interaction_messages.append({'role': 'system', 'content': call_message})
                    
                    # Log the execution attempt
                    self.execution_logger.debug("Tool execution attempt", extra={
                        'tool_name': tool_name,
                        'attempt': tool_retry_count + 1,
                        'arguments': arguments,
                        'context_name': context_name
                    })
                    
                    try:
                        # Execute the tool
                        execution_start = time.monotonic()
                        tool_result = await self.tool_executor.execute(
                            tool_name,
                            arguments,
                            self.history_manager,
                            None  # settings_manager not available in this context
                        )
                        execution_time = time.monotonic() - execution_start
                        
                        # Check if the tool_result indicates an error
                        if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                            # Log the tool execution error
                            self.logging_manager.log_tool_execution(
                                'tool_execution', tool_name, arguments,
                                tool_result, execution_time, success=False
                            )
                            
                            self.execution_logger.warning("Tool execution error", extra={
                                'tool_name': tool_name,
                                'attempt': tool_retry_count + 1,
                                'execution_time': execution_time,
                                'error_result': tool_result[:200],  # Truncated
                                'context_name': context_name
                            })
                            
                            # Check if we should abort or retry
                            if self._should_abort_retry(tool_name, tool_result, tool_retry_count):
                                self.retry_logger.warning("Aborting tool retry sequence", extra={
                                    'tool_name': tool_name,
                                    'attempts_made': tool_retry_count + 1,
                                    'reason': 'abort_retry_condition_met',
                                    'context_name': context_name
                                })
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
                                self.retry_logger.info("Attempting argument regeneration for tool", extra={
                                    'tool_name': tool_name,
                                    'error_category': error_category.value,
                                    'attempt': tool_retry_count + 1,
                                    'context_name': context_name
                                })
                                
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
                                    old_arguments = arguments
                                    arguments = retry_action.get("tool_args", arguments)
                                    
                                    self.retry_logger.info("Arguments regenerated successfully", extra={
                                        'tool_name': tool_name,
                                        'old_arguments': old_arguments,
                                        'new_arguments': arguments,
                                        'context_name': context_name
                                    })
                                else:
                                    self.retry_logger.error("Failed to regenerate arguments", extra={
                                        'tool_name': tool_name,
                                        'retry_action': retry_action,
                                        'context_name': context_name
                                    })
                                    break
                            
                            continue  # Retry with same or new arguments
                        else:
                            # Success!
                            execution_time = time.monotonic() - tool_start_time
                            
                            # Log successful execution
                            self.logging_manager.log_tool_execution(
                                'tool_execution', tool_name, arguments,
                                tool_result, execution_time, success=True
                            )
                            
                            successful_tool_calls_details.append(
                                ToolCallDetails(
                                    tool_name=tool_name,
                                    arguments=arguments,
                                    result=tool_result,
                                    execution_time=execution_time
                                )
                            )
                            final_tool_status = "success"
                            
                            self.execution_logger.info("Tool execution successful", extra={
                                'tool_name': tool_name,
                                'execution_time': execution_time,
                                'result_length': len(str(tool_result)),
                                'context_name': context_name,
                                'attempt': tool_retry_count + 1
                            })
                            break  # Exit retry loop on success
                            
                    except Exception as e:
                        # Handle exceptions during tool execution
                        exception_message = f"System: An unexpected error occurred during execution of tool '{tool_name}': {str(e)}"
                        
                        self.execution_logger.error("Tool execution exception", extra={
                            'tool_name': tool_name,
                            'attempt': tool_retry_count + 1,
                            'exception_type': type(e).__name__,
                            'exception_message': str(e),
                            'context_name': context_name
                        }, exc_info=True)
                        
                        # Check if we should retry the exception
                        if self._should_abort_retry(tool_name, str(e), tool_retry_count):
                            await self.history_manager.add_message("system", exception_message)
                            tool_interaction_messages.append({'role': 'system', 'content': exception_message})
                            
                            self.retry_logger.warning("Aborting retry due to exception", extra={
                                'tool_name': tool_name,
                                'attempts_made': tool_retry_count + 1,
                                'exception_type': type(e).__name__,
                                'context_name': context_name
                            })
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
                    
                    # Log the final failure
                    self.execution_logger.error("Tool execution failed permanently", extra={
                        'tool_name': tool_name,
                        'total_attempts': tool_retry_count,
                        'final_status': final_tool_status,
                        'final_error': failure_summary,
                        'context_name': context_name
                    })
            
            # Increment tool_calls_made for this attempt
            tool_calls_made += 1
            
            # If this was an error, break the loop
            if final_tool_status == "error":
                self.orchestrator_logger.warning("Tool cycle terminated due to tool failure", extra={
                    'tool_name': tool_name,
                    'context_name': context_name,
                    'cycle_iteration': cycle_iteration,
                    'tools_called': tool_calls_made
                })
                break

        # Log completion of tool cycle
        self.orchestrator_logger.info("Tool execution cycle completed", extra={
            'context_name': context_name,
            'total_interactions': len(tool_interaction_messages),
            'successful_calls': len(successful_tool_calls_details),
            'tools_called': tool_calls_made,
            'max_tool_calls': max_tool_calls,
            'cycle_completed_normally': tool_calls_made < max_tool_calls
        })
        
        return tool_interaction_messages, successful_tool_calls_details