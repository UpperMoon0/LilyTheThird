import json
import os
import json # Added json import that was missing in the provided content but present in the original logic
from dotenv import load_dotenv
from tools.tools import find_tool # Use the unified find_tool
# Removed memory_tools import
from .history_manager import HistoryManager
from .llm_client import LLMClient
from memory.mongo_handler import MongoHandler
from tools import time_tool, file_tool 

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
            # Some actions might not need arguments (like get_current_time)
            if arguments:
                 # Pass arguments using **kwargs for flexibility
                result = action_function(**arguments)
            else:
                result = action_function()

            # Format the result specifically for fetch_memory
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
        for _ in range(max_tool_calls):
            current_history = self.history_manager.get_history()
            # Combine base system messages with dynamic history for the LLM call
            messages_for_llm = base_system_messages + current_history

            # 1. Ask LLM for next action (tool or null)
            action_decision = self.llm_client.get_next_action(messages_for_llm)

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print("Error or invalid format in action decision. Breaking tool loop.")
                break # Exit loop on error or unexpected format

            tool_name = action_decision.get("tool_name")

            if tool_name is None:
                print("LLM decided no tool is needed. Proceeding to final response.")
                break # Exit loop, ready for final response

            # 2. If tool chosen, get arguments
            print(f"LLM chose tool: {tool_name}")
            # Find the tool using the unified find_tool
            tool_definition = find_tool(tool_name)
            if not tool_definition:
                print(f"Error: Tool '{tool_name}' definition not found. Breaking loop.")
                # Maybe add an error message to history?
                self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
                tool_interaction_summary.append({"tool_name": tool_name, "error": "Definition not found"})
                break

            # Add the LLM's decision to use the tool to history (optional, but good for tracing)
            # self.history_manager.add_message('assistant', f"Okay, I will use the tool: {tool_name}.") # Example

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
        final_history = self.history_manager.get_history()
        messages_for_final_response = base_system_messages + final_history
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
