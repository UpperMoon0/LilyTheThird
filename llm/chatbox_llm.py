import json
import asyncio
import inspect
import os
import json # Added json import that was missing in the provided content but present in the original logic
from dotenv import load_dotenv
from tools.tools import find_tool # Use the unified find_tool
# Removed memory_tools import
from .history_manager import HistoryManager
from .llm_client import LLMClient
from memory.mongo_handler import MongoHandler
from tools import time_tool, file_tool
from tools.web_search_tool import perform_web_search # Import the new tool function

load_dotenv()


class ChatBoxLLM:
    def __init__(self, provider='openai', model_name=None):
        """
        Initializes the ChatBoxLLM orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use (optional, defaults handled by LLMClient).
        """
        self.personality = os.getenv('PERSONALITY_TO_MASTER')
        # Initialize managers and client
        self.history_manager = HistoryManager()
        # LLMClient handles provider/model logic and client initialization
        self.llm_client = LLMClient(provider=provider, model_name=model_name)
        # Store provider and model name locally
        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        # Initialize MongoHandler - memory is always potentially available via tools
        self.mongo_handler = MongoHandler()
        if not self.mongo_handler.is_connected():
            print("Warning: MongoDB connection failed. Memory tools will not function.")
            # We don't disable it entirely, just let tool execution fail if called

        # Map tool names to their handler functions
        self.tool_dispatcher = {
            # General tools
            "get_current_time": time_tool.get_current_time,
            "read_file": file_tool.read_file,
            "write_file": file_tool.write_file,
            # Web search tool
            "search_web": perform_web_search,
            # Memory tools (map to mongo_handler methods if connected)
            "fetch_memory": self.mongo_handler.retrieve_memories_by_query if self.mongo_handler.is_connected() else self._mongo_unavailable,
            "save_memory": self.mongo_handler.add_fact if self.mongo_handler.is_connected() else self._mongo_unavailable, # Map to add_fact for arbitrary content
        }

    def _mongo_unavailable(self, *args, **kwargs):
        """Placeholder function for when MongoDB is not connected."""
        return "Error: MongoDB connection is not available. Cannot use memory tool."

    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Executes the chosen tool and returns the result as a string."""
        if tool_name not in self.tool_dispatcher:
            return f"Error: Unknown tool '{tool_name}'."

        action_function = self.tool_dispatcher[tool_name]

        try:
            # Check if the function is async
            is_async = inspect.iscoroutinefunction(action_function)

            # Execute the function (sync or async)
            if is_async:
                # Run async function using asyncio.run()
                if arguments:
                    result = asyncio.run(action_function(**arguments))
                else:
                    result = asyncio.run(action_function())
            else:
                # Call synchronous function directly
                if arguments:
                    result = action_function(**arguments)
                else:
                    result = action_function()

            # --- Summarize Web Search Results ---
            if tool_name == "search_web" and isinstance(result, str) and result and not result.startswith("Error:"):
                print(f"--- Summarizing web search results for query: {arguments.get('query', 'N/A')} ---")
                raw_search_results = result # Keep original raw results
                # Prepare messages for summarization
                # Use a simple prompt asking for summarization.
                summarization_prompt = f"Please summarize the following web search results and make them easy to read:\n\n{raw_search_results}"
                # Use generate_final_response for summarization.
                # We pass only the summarization prompt and a neutral personality.
                summary_messages = [{'role': 'user', 'content': summarization_prompt}] # Treat prompt as user request to summarizer
                summarized_result = self.llm_client.generate_final_response(
                    messages=summary_messages,
                    personality_prompt="You are an expert summarization assistant." # Neutral personality for this task
                )

                if summarized_result and not summarized_result.startswith("Error:"):
                    print(f"Summarized Result: {summarized_result}")
                    result = summarized_result # Replace raw result with summary
                else:
                    print("Warning: Failed to summarize web search results. Using raw results.")
                    # Keep the original raw_search_results (already in 'result') if summarization fails

            # Format the result specifically for fetch_memory (remains the same)
            if tool_name == "fetch_memory" and isinstance(result, dict):
                formatted_string = "Memory Fetch Results:\n"
                if result.get("facts"):
                    formatted_string += "\nRelevant Facts (max 5):\n"
                    formatted_string += "\n---\n".join(result["facts"]) # Facts are already formatted strings
                else:
                    formatted_string += "\nNo relevant facts found.\n"

                if result.get("conversations"):
                    formatted_string += "\nRelevant Conversations (max 5):\n"
                    formatted_string += "\n\n".join(result["conversations"]) # Conversations are already formatted strings
                else:
                    formatted_string += "\nNo relevant conversations found.\n"
                return formatted_string
            else:
                # Ensure result is a string for history for other tools
                return str(result) if result is not None else "Tool executed successfully, but returned no output."
        except TypeError as e:
             # Handle cases where arguments don't match function signature
             print(f"Error calling tool '{tool_name}' with args {arguments}: {e}")
             return f"Error: Invalid arguments provided for tool '{tool_name}'. {e}"
        except Exception as e:
            print(f"Error executing tool '{tool_name}': {e}")
            import traceback
            traceback.print_exc()
            return f"Error: Failed to execute tool '{tool_name}'. {e}"


    def get_response(self, user_message: str) -> str:
        """
        Orchestrates the conversation flow: user message -> potential tool calls -> final response.
        """
        # Removed automatic MongoDB context retrieval - now handled by fetch_memory tool
        tool_interaction_summary = [] # To store tool calls/results for potential MongoDB logging

        # --- Prepare Base System Messages ---
        base_system_messages = [
            {'role': 'system', 'content': self.personality},
        ]
        # Removed automatic addition of mongo context sentences

        # --- Add User Message to History ---
        # We add it *before* the loop so the LLM sees it when deciding the first action
        self.history_manager.add_message('user', user_message)

        # --- Tool Interaction Loop ---
        max_tool_calls = 5 # Limit iterations to prevent infinite loops
        for i in range(max_tool_calls): # Use index i for first iteration check
            current_history = self.history_manager.get_history()
            # Combine base system messages with dynamic history for the LLM call
            messages_for_llm = base_system_messages + current_history

            # --- Add Memory Fetch Prompt (First Iteration Only) ---
            if i == 0 and self.mongo_handler.is_connected():
                 fetch_prompt_content = "System Instruction: Based on the user's latest message, consider if relevant information (facts or past conversation snippets) might exist in long-term memory. If so, prioritize using the 'fetch_memory' tool with an appropriate query *before* other actions. If not, proceed as normal."
                 # Insert the prompt after system messages but before the main history
                 messages_for_llm.insert(len(base_system_messages), {'role': 'system', 'content': fetch_prompt_content})
                 print("--- Added memory fetch prompt to messages_for_llm ---")

            # 1. Ask LLM for next action (tool or null)
            # The LLMClient.get_next_action method itself adds the primary tool selection prompt
            action_decision = self.llm_client.get_next_action(messages_for_llm)

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print("Error or invalid format in action decision. Breaking tool loop.")
                break # Exit loop on error or unexpected format

            tool_name = action_decision.get("tool_name")

            # --- Check if LLM wants to finish OR if it needs a final save ---
            if tool_name is None:
                print("LLM initially decided no tool needed. Checking for final save...")
                # Add specific prompt asking ONLY about saving memory now
                if self.mongo_handler.is_connected():
                    save_check_prompt = {
                        'role': 'system',
                        'content': "System Instruction: Before finishing, review the conversation. Are there any specific, concise facts derived from this exchange that absolutely *must* be saved to long-term memory using the 'save_memory' tool? Respond ONLY with the tool choice JSON ('{\"tool_name\": \"save_memory\"}' or '{\"tool_name\": null}')."
                    }
                    messages_for_save_check = messages_for_llm + [save_check_prompt]
                    print("--- Added final save check prompt ---")
                    save_decision = self.llm_client.get_next_action(messages_for_save_check)

                    if save_decision and save_decision.get("tool_name") == "save_memory":
                        print("LLM decided to perform a final save.")
                        tool_name = "save_memory" # Set tool_name to proceed with save logic
                        # Fall through to the argument/execution block below
                    else:
                        print("LLM confirmed no final save needed. Proceeding to final response.")
                        break # Exit loop, ready for final response
                else:
                    # MongoDB not connected, cannot save anyway
                    print("MongoDB not connected, skipping final save check. Proceeding to final response.")
                    break # Exit loop

            # --- If a tool (including potential final save) was chosen ---
            # 2. Get arguments
            print(f"LLM chose tool: {tool_name}")
            # Find the tool using the unified find_tool
            tool_definition = find_tool(tool_name)
            if not tool_definition:
                print(f"Error: Tool '{tool_name}' definition not found. Breaking loop.")
                # Maybe add an error message to history?
                self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
                tool_interaction_summary.append({"tool_name": tool_name, "error": "Definition not found"})
                break

            argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_llm)

            if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                print(f"Error or invalid format getting arguments for {tool_name}. Breaking loop.")
                # Add error to history?
                self.history_manager.add_message('system', f"Error: Failed to get arguments for tool '{tool_name}'.")
                tool_interaction_summary.append({"tool_name": tool_name, "error": "Argument generation failed"})
                break

            arguments = argument_decision.get("arguments", {})
            print(f"Arguments received for {tool_name}: {arguments}")

            # 3. Execute the tool
            tool_result = self._execute_tool(tool_name, arguments)
            print(f"Result from {tool_name}: {tool_result}")
            tool_interaction_summary.append({"tool_name": tool_name, "arguments": arguments, "result": tool_result})


            # 4. Add tool result to history
            self.history_manager.add_message('system', f"Tool Used: {tool_name}\nArguments: {json.dumps(arguments)}\nResult: {tool_result}")

            # Loop continues to see if another tool is needed based on the result

        else: # Executed if the loop completes without break (max_tool_calls reached)
             print("Warning: Maximum tool calls reached. Proceeding to final response.")
             self.history_manager.add_message('system', "Maximum tool calls reached. I will now generate a response based on the current information.")


        # --- Final Response Generation ---
        # This happens *after* the loop breaks (either naturally or after final save check)
        final_history = self.history_manager.get_history()
        messages_for_final_response = base_system_messages + final_history
        # No need for the extra save prompt here anymore, it's handled in the loop exit condition

        final_message = self.llm_client.generate_final_response(
            messages_for_final_response,
            self.personality # Pass the base personality prompt again for the final touch
        )

        # Handle potential errors from the final call
        if final_message is None or final_message.startswith("Error:"):
            print(f"Failed to get final response: {final_message}")
            final_message = final_message if final_message else "Sorry, I encountered an error generating the final response."
            # Don't save to MongoDB on final error
        else:
            # --- Update Short-Term History with Final Response ---
            self.history_manager.add_message('assistant', final_message)

            # --- Save Conversation Turn to Long-Term Memory (MongoDB) ---
            if self.mongo_handler.is_connected():
                try:
                    # Use the original user_message and the final_message
                    self.mongo_handler.add_memory(user_input=user_message, llm_response=final_message)
                    print("Conversation turn saved to MongoDB.")
                except Exception as e:
                    print(f"Error saving conversation turn to MongoDB: {e}")
            else:
                print("MongoDB not connected. Conversation turn not saved.")

        # --- Return Final Generated Message ---
        # Return two values as expected by chat_tab.py
        return final_message, None


    def __del__(self):
        # Ensure MongoDB connection is closed when the object is destroyed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
