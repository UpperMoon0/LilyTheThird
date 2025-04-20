import json
import asyncio
import os
from dotenv import load_dotenv
from tools.tools import find_tool # Import find_tool
from .history_manager import HistoryManager
from .llm_client import LLMClient
from .tool_executor import ToolExecutor # Import the new executor
from memory.mongo_handler import MongoHandler
# Tool implementation imports (time_tool, file_tool, web_search_tool) are no longer needed here

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
        # Initialize managers and clients in order
        self.history_manager = HistoryManager()
        # Initialize MongoHandler first, as it's needed by ToolExecutor
        self.mongo_handler = MongoHandler()
        if not self.mongo_handler.is_connected():
            print("Warning: MongoDB connection failed. Memory tools will not function.")
        # LLMClient handles provider/model logic and client initialization
        self.llm_client = LLMClient(provider=provider, model_name=model_name)
        # Initialize ToolExecutor, passing dependencies
        self.tool_executor = ToolExecutor(mongo_handler=self.mongo_handler, llm_client=self.llm_client)
        # Store provider and model name locally (optional, could get from llm_client)
        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        # No local tool_dispatcher needed anymore

    # _execute_tool method is removed, logic moved to ToolExecutor

    async def get_response(self, user_message: str) -> str: # Make method async
        """
        Orchestrates the conversation flow: user message -> potential tool calls -> final response.
        Now uses LLMClient for decisions and ToolExecutor for execution.
        """
        # tool_interaction_summary can be removed if not used elsewhere

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

            # 1. Ask LLM for next action (tool or null) using the centralized client
            # ChatBoxLLM allows all tools, so allowed_tools=None
            action_decision = self.llm_client.get_next_action(messages_for_llm, allowed_tools=None)

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print(f"Error or invalid format in action decision: {action_decision}. Breaking tool loop.")
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
                    # Pass allowed_tools=['save_memory', None] ? Or just let it choose from all? Let's allow all for now.
                    messages_for_save_check = messages_for_llm + [save_check_prompt]
                    print("--- Added final save check prompt ---")
                    # Ask LLM again, allowing any tool (though prompt guides towards save/null)
                    save_decision = self.llm_client.get_next_action(messages_for_save_check, allowed_tools=None)

                    if save_decision and save_decision.get("tool_name") == "save_memory":
                        print("LLM decided to perform a final save.")
                        tool_name = "save_memory" # Set tool_name to proceed with save logic
                        # Fall through to the argument/execution block below
                    else:
                        print("LLM confirmed no final save needed or chose other tool unexpectedly. Proceeding to final response.")
                        break # Exit loop, ready for final response
                else:
                    # MongoDB not connected, cannot save anyway
                    print("MongoDB not connected, skipping final save check. Proceeding to final response.")
                    break # Exit loop

            # --- If a tool (including potential final save) was chosen ---
            # 2. Get arguments
            print(f"LLM chose tool: {tool_name}")
            # Find the tool definition using the centralized function
            tool_definition = find_tool(tool_name)
            if not tool_definition:
                print(f"Error: Tool '{tool_name}' definition not found. Breaking loop.")
                self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
                # tool_interaction_summary.append({"tool_name": tool_name, "error": "Definition not found"}) # Removed summary
                break

            # Get arguments using the centralized client
            argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_llm)

            if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                print(f"Error or invalid format getting arguments for {tool_name}: {argument_decision}. Breaking loop.")
                self.history_manager.add_message('system', f"Error: Failed to get arguments for tool '{tool_name}'.")
                # tool_interaction_summary.append({"tool_name": tool_name, "error": "Argument generation failed"}) # Removed summary
                break

            arguments = argument_decision.get("arguments", {})

            # 3. Execute the tool using the ToolExecutor (await the async execute method)
            tool_result = await self.tool_executor.execute(tool_name, arguments)
            print(f"Result from {tool_name}: {tool_result}")
            # tool_interaction_summary.append({"tool_name": tool_name, "arguments": arguments, "result": tool_result}) # Removed summary


            # 4. Add tool result to history
            # Use a more structured format for tool results in history if desired
            tool_result_message = {
                "role": "system", # Or maybe a dedicated 'tool' role if supported/useful
                "content": json.dumps({ # Store as JSON string for clarity
                    "tool_used": tool_name,
                    "arguments": arguments,
                    "result": tool_result
                })
            }
            self.history_manager.add_message(tool_result_message['role'], tool_result_message['content'])

            # Loop continues

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

        # --- Return Final Generated Message ---
        # Return two values as expected by chat_tab.py
        return final_message, None


    def __del__(self):
        # Ensure MongoDB connection is closed when the object is destroyed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
