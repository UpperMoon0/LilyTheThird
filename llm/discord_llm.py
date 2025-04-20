import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from .history_manager import HistoryManager
from .llm_client import LLMClient
from .tool_executor import ToolExecutor
from memory.mongo_handler import MongoHandler
from tools.tools import find_tool # Import find_tool

load_dotenv()

# Define the tools allowed for the Discord context
DISCORD_ALLOWED_TOOLS = ['fetch_memory', 'search_web', 'get_current_time']

class DiscordLLM:
    def __init__(self, provider=None, model=None):
        # Prioritize passed arguments, then environment variables, then defaults
        llm_provider = (provider or os.getenv('DISCORD_LLM_PROVIDER', 'openai')).lower()
        llm_model = model or os.getenv('DISCORD_LLM_MODEL', 'gpt-4o-mini')

        print(f"Initializing DiscordLLM - Provider: {llm_provider}, Model: {llm_model}")

        # Initialize shared components
        self.history_manager = HistoryManager()
        self.mongo_handler = MongoHandler() # Needed for ToolExecutor
        if not self.mongo_handler.is_connected():
            print("Warning: MongoDB connection failed for DiscordLLM. Memory tools will not function.")
        self.llm_client = LLMClient(provider=llm_provider, model_name=llm_model)
        self.tool_executor = ToolExecutor(mongo_handler=self.mongo_handler, llm_client=self.llm_client)

        # Store master ID for personality check
        self.master_id = os.getenv('MASTER_DISCORD_ID')
        if self.master_id:
            try:
                self.master_id = int(self.master_id)
            except ValueError:
                print("Warning: MASTER_DISCORD_ID in .env is not a valid integer. Master check will fail.")
                self.master_id = None
        else:
            print("Warning: MASTER_DISCORD_ID not found in .env. Master check will fail.")

    # Removed _adapt_history_for_gemini and update_history

    async def get_response(self, user_message, discord_user_id, discord_user_name):
        """
        Orchestrates the Discord conversation flow using shared components and restricted tools.
        """
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- Determine Personality ---
        is_master = self.master_id is not None and discord_user_id == self.master_id
        if is_master:
            personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful assistant.") # Default personality
        else:
            p1 = os.getenv('PERSONALITY_TO_STRANGER_1', "You are a polite AI. I'm ")
            p2 = os.getenv('PERSONALITY_TO_STRANGER_2', ", you will talk to me politely.")
            personality = p1 + discord_user_name + p2

        # --- Prepare Base System Messages ---
        base_system_messages = [
            {'role': 'system', 'content': personality},
            {'role': 'system', 'content': f"Current date and time: {current_date_time}"},
            # Add context about the user if needed
            {'role': 'system', 'content': f"You are interacting with user '{discord_user_name}' (ID: {discord_user_id}). They are {'your Master' if is_master else 'not your Master'}."}
        ]

        # --- Add User Message to History ---
        # Use standard 'user' role. Include user's name in the content for context.
        self.history_manager.add_message('user', f"{discord_user_name} said: {user_message}")

        # --- Tool Interaction Loop ---
        max_tool_calls = 3 # Limit tool calls for Discord context
        for _ in range(max_tool_calls):
            current_history = self.history_manager.get_history()
            messages_for_llm = base_system_messages + current_history

            # 1. Ask LLM for next action, restricting tools
            action_decision = self.llm_client.get_next_action(messages_for_llm, allowed_tools=DISCORD_ALLOWED_TOOLS)

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print(f"Error or invalid format in Discord action decision: {action_decision}. Breaking tool loop.")
                break

            tool_name = action_decision.get("tool_name")

            if tool_name is None:
                print("Discord LLM decided no tool needed. Proceeding to final response.")
                # No final save check for Discord context for simplicity
                break

            # --- If a tool was chosen ---
            print(f"Discord LLM chose tool: {tool_name}")
            tool_definition = find_tool(tool_name)
            if not tool_definition:
                print(f"Error: Discord Tool '{tool_name}' definition not found. Breaking loop.")
                self.history_manager.add_message('system', f"Error: Could not find definition for tool '{tool_name}'.")
                break

            # 2. Get arguments
            argument_decision = self.llm_client.get_tool_arguments(tool_definition, messages_for_llm)
            if not argument_decision or argument_decision.get("action_type") != "tool_arguments":
                print(f"Error or invalid format getting arguments for Discord tool {tool_name}: {argument_decision}. Breaking loop.")
                self.history_manager.add_message('system', f"Error: Failed to get arguments for tool '{tool_name}'.")
                break

            arguments = argument_decision.get("arguments", {})

            # 3. Execute the tool
            tool_result = await self.tool_executor.execute(tool_name, arguments)
            print(f"Result from Discord tool {tool_name}: {tool_result}")

            # 4. Add tool result to history
            tool_result_message = {
                "role": "system",
                "content": json.dumps({
                    "tool_used": tool_name,
                    "arguments": arguments,
                    "result": tool_result
                })
            }
            self.history_manager.add_message(tool_result_message['role'], tool_result_message['content'])
            # Loop continues

        else: # Max tool calls reached
             print("Warning: Maximum tool calls reached for Discord context.")
             self.history_manager.add_message('system', "Maximum tool calls reached. Generating response based on current information.")

        # --- Final Response Generation ---
        final_history = self.history_manager.get_history()
        messages_for_final_response = base_system_messages + final_history

        final_message = self.llm_client.generate_final_response(
            messages_for_final_response,
            personality # Pass the determined personality
        )

        # Handle potential errors
        if final_message is None or final_message.startswith("Error:"):
            print(f"Failed to get final Discord response: {final_message}")
            final_message = final_message if final_message else "Sorry, I encountered an error generating the final response."
        else:
            # Update history with the final assistant message
            self.history_manager.add_message('assistant', final_message)

        # Print history for debugging (optional)
        print("Discord Message History:")
        for msg in self.history_manager.get_history():
            print(f"- {msg['role']}: {msg['content']}")

        # Return format expected by discord_bot.py (message, None)
        return final_message, None

    def __del__(self):
        # Ensure MongoDB connection is closed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
