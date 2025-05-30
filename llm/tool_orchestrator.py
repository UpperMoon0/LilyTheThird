import asyncio
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

# Assuming components are in the same directory or adjust imports
# from .llm_client import LLMClient # Not directly used in this snippet, but likely needed for full class
# from .tool_executor import ToolExecutor # Not directly used in this snippet
# from .history_manager import HistoryManager # Not directly used in this snippet

from tools.tools import find_tool # find_tool is used

# Constants for retry logic (copied from BaseLLMOrchestrator)
TOOL_SELECT_RETRY = 5       # Max retries for LLM failing to choose a tool (0=disable, -1=infinite)
# TOOL_USE_RETRY and TOOL_RETRY_DELAY_SECONDS are obsolete as argument generation is now part of get_next_action.

# Constants for history summarization (copied from BaseLLMOrchestrator)
MAX_ARG_SUMMARY_LEN = 150
MAX_RESULT_SUMMARY_LEN = 250

class ToolOrchestrator:
    def __init__(self, llm_client, tool_executor, history_manager, allowed_tools: Optional[List[str]]):
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.history_manager = history_manager
        self.allowed_tools = allowed_tools # This is the overall list of allowed tools for the orchestrator context

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
            
            # Import time module and setup for timing
            import time
            from llm.schemas import ToolCallDetails
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
                # Add system message indicating the tool call
                args_summary = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
                call_message = f"System: Calling tool '{tool_name}' with arguments: {args_summary}"
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
                    
                    # Add system message summarizing the tool's result
                    result_summary = self._summarize_for_history(str(tool_result), MAX_RESULT_SUMMARY_LEN)
                    result_message = f"System: Tool '{tool_name}' executed. Result: {result_summary}"
                    await self.history_manager.add_message("system", result_message)
                    tool_interaction_messages.append({'role': 'system', 'content': result_message})
                    
                    # Check if the tool_result indicates an error
                    if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                        print(f"[{self.__class__.__name__}] Tool '{tool_name}' execution resulted in an error: {tool_result}")
                        final_tool_status = "error"
                    else:
                        # Add details to successful_tool_calls_details
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
                        
                except Exception as e:
                    # Handle exceptions during tool execution
                    error_message = f"System: An unexpected error occurred during execution of tool '{tool_name}': {str(e)}"
                    print(f"[{self.__class__.__name__}] Exception during execution of tool '{tool_name}': {e}")
                    await self.history_manager.add_message("system", error_message)
                    tool_interaction_messages.append({'role': 'system', 'content': error_message})
                    final_tool_status = "error"
            
            # Increment tool_calls_made for this attempt
            tool_calls_made += 1
            
            # If this was an error, break the loop
            if final_tool_status == "error":
                print(f"[{self.__class__.__name__}] Tool '{tool_name}' failed. Breaking main tool loop.")
                break

        print(f"[{self.__class__.__name__}] Tool cycle finished. Interactions: {len(tool_interaction_messages)}, Successful calls: {len(successful_tool_calls_details)}")
        return tool_interaction_messages, successful_tool_calls_details