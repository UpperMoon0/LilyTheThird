import json
import os
import random
from datetime import datetime # Keep datetime import for potential future use, though not directly used now
from dotenv import load_dotenv
# Removed direct OpenAI/Gemini imports, pydantic validation
# Removed KG imports, action/knowledge extractors
# Import keyword extraction function (might be used for future Mongo search)
# from .keyword_extractor import extract_keywords
# Import tool definitions and finder
from ..tools.tools import find_tool
# Import the history manager
from .history_manager import HistoryManager
# Import the LLM client
from .llm_client import LLMClient
# Import MongoHandler
from ..memory.mongo_handler import MongoHandler
# Import settings loader
from ..settings_manager import load_settings
# Import tool implementation handlers from the tools directory
from ..tools import time_tool, file_tool # Import the moved and renamed tool modules

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
        # Load settings to check if MongoDB memory is enabled
        self.settings = load_settings()
        self.mongo_memory_enabled = self.settings.get('enable_mongo_memory', False)
        # Initialize MongoHandler only if enabled
        self.mongo_handler = MongoHandler() if self.mongo_memory_enabled else None
        if self.mongo_memory_enabled and not self.mongo_handler.is_connected():
            print("Warning: MongoDB memory is enabled in settings, but connection failed. Disabling for this session.")
            self.mongo_memory_enabled = False # Disable if connection failed

        # Map tool names to their handler functions
        self.tool_dispatcher = {
            "get_current_time": time_tool.get_current_time,
            "read_file": file_tool.read_file,
            "write_file": file_tool.write_file,
        }

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

            # Ensure result is a string for history
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
        mongo_context_sentences = []
        tool_interaction_summary = [] # To store tool calls/results for potential MongoDB logging

        # --- Retrieve Context from MongoDB (if enabled) ---
        if self.mongo_memory_enabled and self.mongo_handler:
            # (Keep existing MongoDB retrieval logic)
            recent_memories = self.mongo_handler.retrieve_recent_memories(limit=5)
            if recent_memories:
                print(f"Retrieved {len(recent_memories)} recent memories from MongoDB.")
                for mem in reversed(recent_memories):
                    mongo_context_sentences.append(f"Past interaction: User said '{mem['user_input']}', You responded '{mem['llm_response']}'")

        # --- Prepare Base System Messages ---
        # Removed manual time injection; LLM can use get_current_time tool if needed.
        base_system_messages = [
            {'role': 'system', 'content': self.personality},
            # {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"}, # Removed
        ]
        if self.mongo_memory_enabled and mongo_context_sentences:
            base_system_messages.append({'role': 'system', 'content': "Consider the following recent interactions from your long-term memory:"})
            for sentence in mongo_context_sentences:
                base_system_messages.append({'role': 'system', 'content': f"- {sentence}"})

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
            # Use a specific 'tool' role if supported, otherwise 'system' or 'assistant' context
            # OpenAI supports 'tool' role. Let's assume HistoryManager can handle it.
            # Need tool_call_id if using OpenAI's official tool format, but we are simulating.
            # Let's use a structured message in the 'assistant' or a dedicated 'tool' role.
            # For simplicity, adding result as a 'tool' message. HistoryManager needs update if it doesn't support 'tool'.
            # Assuming HistoryManager is updated or we use 'system'/'assistant' for now.
            # Let's use 'system' as a safe bet for broad compatibility.
            # self.history_manager.add_message('tool', tool_result, tool_call_id=...) # Ideal OpenAI
            self.history_manager.add_message('system', f"Tool Used: {tool_name}\nArguments: {json.dumps(arguments)}\nResult: {tool_result}") # Simple system message approach

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
            # Don't update history with the error message itself as assistant response
            # The error is already logged. Return the error or a generic message.
            final_message = final_message if final_message else "Sorry, I encountered an error generating the final response."
            # Don't save to MongoDB on final error
        else:
            # --- Update Short-Term History with Final Response ---
            self.history_manager.add_message('assistant', final_message)

            # --- Store Interaction in MongoDB (if enabled) ---
            if self.mongo_memory_enabled and self.mongo_handler:
                print("Attempting to add full conversation turn to MongoDB.")
                metadata = {
                    "provider": self.provider,
                    "model": self.model,
                    "tool_interactions": tool_interaction_summary # Store tool steps
                }
                self.mongo_handler.add_memory(
                    user_input=user_message,
                    llm_response=final_message, # Store the final response
                    metadata=metadata
                )
            elif self.mongo_memory_enabled:
                print("MongoDB memory enabled but handler not available, skipping storage.")
            else:
                print("MongoDB memory is disabled, skipping storage.")

        # --- Return Final Generated Message ---
        # The second element (action) is removed from the return tuple
        return final_message


    def __del__(self):
        # Ensure MongoDB connection is closed when the object is destroyed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
