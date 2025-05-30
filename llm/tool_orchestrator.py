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
# TOOL_USE_RETRY = 10 # No longer used directly, execution failure feeds back to LLM for next action
# TOOL_RETRY_DELAY_SECONDS = 2 # No longer used directly

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
                    self.history_manager.add_message('system', retry_context_content) # Keep history manager updated too
                    print(f"[{self.__class__.__name__}] Added retry context for tool selection (Attempt {select_retry_count + 1}).")
                    await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS) 

                action_decision = await self.llm_client.get_next_action(
                    messages_for_loop,
                    allowed_tools=main_loop_allowed_tools,
                    context_type=context_name
                )
                # get_next_action now returns "tool_call", "text_response", or "error"
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
                self.history_manager.add_message('assistant', action_decision.get('text', '')) # Ensure history is up-to-date
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
                self.history_manager.add_message('system', error_content)
                tool_interaction_messages.append({'role': 'system', 'content': error_content})
                break

            # Add tool call message to history and tool_interaction_messages
            # The exact format might depend on your LLM (e.g., OpenAI's format)
            # For simplicity, let's assume a generic tool call message structure
            # If your LLM returns arguments directly with tool_choice, include them here.
            # If not, they'll be part of the argument_decision later.
            
            # Placeholder for tool call message - actual structure depends on LLM client output for tool_choice
            # For now, we'll add a system message indicating the choice, and then arguments later.
            # A more robust solution would use the LLM's specific tool_calls format.
            
            # --- Argument Generation & Execution with General Retry ---
            print(f"[{self.__class__.__name__}] Main loop: LLM chose tool: {tool_name}")
            use_retry_count = 0 
            arguments = None
            tool_result = None
            tool_definition = find_tool(tool_name)

            if not tool_definition:
                print(f"[{self.__class__.__name__}] Error: Tool '{tool_name}' definition not found.")
                tool_result = f"Error: Could not find definition for tool '{tool_name}'."
            else:
                while TOOL_USE_RETRY == -1 or use_retry_count <= TOOL_USE_RETRY:
                    messages_for_args = base_system_messages + self.history_manager.get_history()

                    if use_retry_count > 0:
                        summarized_error_for_retry_ctx = self._summarize_for_history(tool_result, MAX_RESULT_SUMMARY_LEN)
                        retry_context_content = (
                            f"RETRY CONTEXT: Previous attempt (attempt {use_retry_count}) to use tool \'{tool_name}\' failed with the following error: "
                            f"\'{summarized_error_for_retry_ctx}\'. Please analyze the error (also see system message for previous attempt) and the conversation history, then try generating "
                            f"the arguments for \'{tool_name}\' again, correcting any potential issues."
                        )
                        if tool_name == 'update_memory' and "memory_id" in str(tool_result) and retrieved_facts_context_string: # Check if this var is available
                             retry_context_content += (
                                 "\nIt seems the 'memory_id' might have been invalid. "
                                 "Please select a valid ID from the retrieved facts below to update.\n"
                                 f"{retrieved_facts_context_string}"
                             )
                        retry_context_message = {'role': 'system', 'content': retry_context_content}
                        messages_for_args.append(retry_context_message)
                        tool_interaction_messages.append(retry_context_message) # Track this system message
                        self.history_manager.add_message('system', retry_context_content)
                        print(f"[{self.__class__.__name__}] Added retry context for {tool_name} argument generation (Attempt {use_retry_count + 1}).")
                        await asyncio.sleep(1) 

                    argument_decision = await self.llm_client.get_tool_arguments(tool_definition, messages_for_args)

                    if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                        print(f"[{self.__class__.__name__}] Error or invalid format getting arguments for {tool_name} (Attempt {use_retry_count + 1}): {argument_decision}.")
                        tool_result = argument_decision.get("error", f"Error: Failed to get arguments for tool '{tool_name}'.")
                        arguments = None 
                        if TOOL_USE_RETRY != -1 and use_retry_count >= TOOL_USE_RETRY:
                            print(f"[{self.__class__.__name__}] Argument generation failed after max retries ({TOOL_USE_RETRY}) for {tool_name}. Aborting tool call.")
                            break 
                        elif TOOL_USE_RETRY == 0:
                             print(f"[{self.__class__.__name__}] Argument generation failed for {tool_name} (retries disabled). Aborting tool call.")
                             break 
                        else:
                            print(f"[{self.__class__.__name__}] Argument generation failed for {tool_name}. Retrying (attempt {use_retry_count + 1}/{TOOL_USE_RETRY if TOOL_USE_RETRY != -1 else 'infinite'})...")
                            use_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue 
                    
                    arguments = argument_decision.get("arguments", {})
                    
                    # Construct and add the tool call message (OpenAI specific format example)
                    # This should ideally happen *before* execution if your LLM expects it.
                    # For now, adding a simplified version.
                    tool_call_message_content = { # This is a simplified representation
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "id": tool_call_id if tool_call_id else f"call_{tool_name}_{datetime.now(timezone.utc).timestamp()}" # Generate an ID if not present
                    }
                    # Example OpenAI format:
                    # self.history_manager.add_message('assistant', None, tool_calls=[{"id": tool_call_id, "type": "function", "function": {"name": tool_name, "arguments": json.dumps(arguments)}}])
                    # tool_interaction_messages.append(...) # Add the actual tool_call message in LLM's expected format
                    
                    # For now, adding a system message representing the call before result
                    system_tool_call_summary = f"System: Calling tool '{tool_name}' with arguments: {self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)}"
                    self.history_manager.add_message('system', system_tool_call_summary)
                    tool_interaction_messages.append({'role': 'system', 'content': system_tool_call_summary})


                    tool_result = await self.tool_executor.execute(tool_name, arguments)
                    print(f"[{self.__class__.__name__}] Result from {tool_name} (Attempt {use_retry_count + 1}): {self._summarize_for_history(tool_result, 200)}")

                    is_execution_error = isinstance(tool_result, str) and tool_result.startswith("Error:")

                    if is_execution_error:
                        if TOOL_USE_RETRY != -1 and use_retry_count >= TOOL_USE_RETRY:
                            print(f"[{self.__class__.__name__}] Tool execution failed after max retries ({TOOL_USE_RETRY}) for {tool_name}. Aborting tool call.")
                            break 
                        elif TOOL_USE_RETRY == 0:
                            print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name} (retries disabled). Aborting tool call.")
                            break 
                        else:
                            print(f"[{self.__class__.__name__}] Tool execution failed for {tool_name}. Retrying (attempt {use_retry_count + 1}/{TOOL_USE_RETRY if TOOL_USE_RETRY != -1 else 'infinite'})...")
                            args_summary_retry = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
                            error_summary_retry = self._summarize_for_history(tool_result, MAX_RESULT_SUMMARY_LEN)
                            history_retry_error_summary_content = (
                                f"System: Tool '{tool_name}' execution failed during attempt {use_retry_count + 1}. "
                                f"Arguments: {args_summary_retry}. Error: {error_summary_retry}. "
                                f"Preparing to retry argument generation."
                            )
                            # Add to history_manager AND tool_interaction_messages
                            self.history_manager.add_message('system', history_retry_error_summary_content)
                            tool_interaction_messages.append({'role': 'system', 'content': history_retry_error_summary_content})
                            use_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue 
                    else:
                        break # Success from tool execution

            final_tool_status = "Success"
            if tool_result is None: # Could happen if arg gen failed definitively
                tool_result = "Error: Tool execution did not produce a result or failed during argument generation."
                final_tool_status = f"Failed (Args/Definition - {use_retry_count + 1} attempts)"
            elif isinstance(tool_result, str) and tool_result.startswith("Error:"):
                final_tool_status = f"Failed (Execution - {use_retry_count + 1} attempts)"
            
            if final_tool_status == "Success":
                successful_tool_call_details.append({
                    "tool_name": tool_name,
                    "arguments": arguments if arguments is not None else {},
                    "result": tool_result,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                print(f"[{self.__class__.__name__}] Added details for successful '{tool_name}' call to list.")

            args_summary = self._summarize_for_history(arguments, MAX_ARG_SUMMARY_LEN)
            result_summary = self._summarize_for_history(tool_result, MAX_RESULT_SUMMARY_LEN)

            # Construct the tool result message (OpenAI specific format example)
            # tool_result_message = {
            #     "role": "tool",
            #     "tool_call_id": tool_call_id, # from the original tool_choice
            #     "name": tool_name,
            #     "content": json.dumps(tool_result) # Or str(tool_result) if not JSON serializable
            # }
            # self.history_manager.add_raw_message(tool_result_message)
            # tool_interaction_messages.append(tool_result_message)

            # For now, using a system message to represent the tool result for history
            if final_tool_status.startswith("Failed"):
                history_tool_summary_content = f"System: Tool '{tool_name}' attempt failed. Status: {final_tool_status}. Arguments: {args_summary}. Details: {result_summary}"
            else: # Success
                history_tool_summary_content = f"System: Tool '{tool_name}' executed successfully. Arguments: {args_summary}. Result: {result_summary}"
            
            self.history_manager.add_message('system', history_tool_summary_content)
            tool_interaction_messages.append({'role': 'system', 'content': history_tool_summary_content})


            if arguments is not None: # Implies tool execution was at least attempted
                tool_calls_made += 1
                if final_tool_status.startswith("Failed"):
                     print(f"[{self.__class__.__name__}] Tool '{tool_name}' ultimately failed after {use_retry_count + 1} attempts. Breaking main tool loop.")
                     break 
            else: # Argument generation or definition finding failed definitively
                print(f"[{self.__class__.__name__}] Argument generation or definition finding failed definitively for {tool_name}. Breaking main tool loop.")
                break 
        
        print(f"[{self.__class__.__name__}] Tool cycle finished. Interactions: {len(tool_interaction_messages)}, Successful calls: {len(successful_tool_calls_details)}")
        return tool_interaction_messages, successful_tool_calls_details