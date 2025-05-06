import os
import json # Added import
import asyncio # Added import
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Import the base class and necessary components
from .base_llm import BaseLLMOrchestrator, TOOL_SELECT_RETRY, TOOL_USE_RETRY, TOOL_RETRY_DELAY_SECONDS # Import constants
from tools.tools import find_tool # Added import
# HistoryManager, LLMClient, ToolExecutor, MongoHandler are initialized in Base

load_dotenv()

# Define the tools allowed specifically for the Discord context
DISCORD_ALLOWED_TOOLS = ['fetch_memory', 'search_web', 'get_current_time']

class DiscordLLM(BaseLLMOrchestrator):
    """
    LLM Orchestrator specifically for the Discord interface.
    Inherits common logic from BaseLLMOrchestrator.
    """
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, master_id: Optional[str] = None):
        """
        Initializes the DiscordLLM orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini'). Defaults handled by Base.
            model: The specific model name to use. Defaults handled by Base.
            master_id: The Master Discord ID. Must be provided if intended to be used.
        """
        # Determine provider and model strictly from passed arguments
        # Default to 'openai' for provider if None is passed, model can be None (LLMClient handles default)
        discord_provider = provider.lower() if provider else 'openai'
        discord_model = model # Let LLMClient handle default if None

        # Call the parent constructor
        super().__init__(provider=discord_provider, model_name=discord_model)

        # Store master ID for personality check (Discord specific)
        # Use only the master_id passed to the constructor
        effective_master_id_str = master_id 
        
        if effective_master_id_str:
            try:
                self.master_id = int(effective_master_id_str)
                print(f"DiscordLLM: Master ID set to {self.master_id} (from constructor).")
            except ValueError:
                print(f"Warning: Master Discord ID '{effective_master_id_str}' (from constructor) is not a valid integer. Master check will fail.")
                self.master_id = None
        else:
            # This case implies master_id was not passed or was None/empty
            print("Warning: Master Discord ID not provided to constructor. Master check will be based on None.")
            self.master_id = None # Explicitly set to None
        
        print(f"DiscordLLM initialized with Provider: {discord_provider}, Model: {discord_model if discord_model else 'Default'}, Master ID: {self.master_id}")


    # --- Implement Abstract Methods and Hooks from Base Class ---

    @property
    def context_name(self) -> str:
        """Identifier for the Discord context."""
        return "discord"

    def _get_base_system_messages(self, **kwargs) -> List[Dict[str, str]]:
        """Provides the base system messages including personality, time, and user context."""
        discord_user_id = kwargs.get('discord_user_id')
        discord_user_name = kwargs.get('discord_user_name', 'User') # Default name if not provided

        # Determine Personality
        is_master = self.master_id is not None and discord_user_id == self.master_id
        if is_master:
            personality = os.getenv('PERSONALITY_TO_MASTER', "You are a helpful assistant.")
        else:
            p1 = os.getenv('PERSONALITY_TO_STRANGER_1', "You are a polite AI. I'm ")
            p2 = os.getenv('PERSONALITY_TO_STRANGER_2', ", you will talk to me politely.")
            personality = p1 + discord_user_name + p2

        # Prepare Base System Messages
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_messages = [
            {'role': 'system', 'content': personality},
            {'role': 'system', 'content': f"Current date and time: {current_date_time}"},
            {'role': 'system', 'content': f"You are interacting with user '{discord_user_name}' (ID: {discord_user_id}). They are {'your Master' if is_master else 'not your Master'}."}
        ]
        return base_messages

    def _get_allowed_tools(self) -> Optional[List[str]]:
        """Returns the list of tools allowed for Discord."""
        return DISCORD_ALLOWED_TOOLS

    def _get_max_tool_calls(self) -> int:
        """Sets the maximum tool calls for the Discord context."""
        # Can be configured via env var or default
        try:
            return int(os.getenv('DISCORD_MAX_TOOL_CALLS', 3))
        except ValueError:
            print("Warning: Invalid DISCORD_MAX_TOOL_CALLS in .env, using default 3.")
            return 3

    def _prepare_user_message_for_history(self, user_message: str, **kwargs) -> str:
        """Prepends the Discord user's name to the message."""
        discord_user_name = kwargs.get('discord_user_name', 'User')
        return f"{discord_user_name} said: {user_message}"

    # --- Overridden Core Logic ---

    async def _process_message(self, user_message: str, **kwargs) -> str:
        """
        Core logic for processing a user message, handling memory retrieval,
        tool interactions, and final response generation.
        Overrides BaseLLMOrchestrator._process_message to REMOVE the final
        memory save/update step (Step 5) for the Discord context.
        kwargs are passed to hook methods like _get_base_system_messages.
        """
        # 1. Get context-specific base system messages
        base_system_messages = self._get_base_system_messages(**kwargs)

        # 2. Retrieve relevant memories automatically based on the raw user message
        retrieved_facts_context_string = await self._retrieve_and_add_memory_context(user_message)

        # 3. Prepare and add user message to history
        prepared_user_message = self._prepare_user_message_for_history(user_message, **kwargs)
        self.history_manager.add_message('user', prepared_user_message)

        # --- Tool Usage Flow ---
        allowed_tools_overall = self._get_allowed_tools() # Get all tools allowed in this context
        max_tool_calls = self._get_max_tool_calls()
        tool_calls_made = 0

        # 4. Main Tool Interaction Loop (Excluding Memory Tools)
        print(f"--- Step 4: Main Tool Loop (Discord - No Final Memory Step) ---")
        # Determine tools allowed in the main loop (exclude memory tools)
        main_loop_allowed_tools = None
        if allowed_tools_overall is not None:
            main_loop_allowed_tools = [
                tool for tool in allowed_tools_overall if tool not in ['fetch_memory', 'save_memory', 'update_memory'] # Also exclude update_memory here for Discord
            ]
        # If allowed_tools_overall was None (meaning all tools allowed), we need to get all tool names
        # and then filter. (Shouldn't happen for Discord based on _get_allowed_tools)
        elif allowed_tools_overall is None:
             all_tool_names = self.tool_executor.get_all_tool_names()
             main_loop_allowed_tools = [
                 tool for tool in all_tool_names if tool not in ['fetch_memory', 'save_memory', 'update_memory']
             ]


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
                    retry_context = (
                        f"RETRY CONTEXT: Previous attempt (attempt {select_retry_count}) to select a tool failed or returned an invalid format. "
                        f"Please review the conversation history and available tools, then choose the next appropriate action (tool or null)."
                    )
                    messages_for_loop.append({'role': 'system', 'content': retry_context})
                    print(f"[{self.__class__.__name__}] Added retry context for tool selection (Attempt {select_retry_count + 1}).")
                    await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)

                action_decision = await self.llm_client.get_next_action(
                    messages_for_loop,
                    allowed_tools=main_loop_allowed_tools,
                    context_type=self.context_name
                )

                if action_decision and action_decision.get("action_type") == "tool_choice":
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

            if not action_decision or action_decision.get("action_type") != "tool_choice":
                print(f"[{self.__class__.__name__}] Failed to get a valid tool choice after retries or retries disabled. Breaking main loop.")
                break

            tool_name = action_decision.get("tool_name")

            if tool_name is None:
                print(f"[{self.__class__.__name__}] LLM decided no further tools needed in main loop.")
                break

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
                        retry_context = (
                            f"RETRY CONTEXT: Previous attempt (attempt {use_retry_count}) to use tool '{tool_name}' failed with the following error: "
                            f"'{tool_result}'. Please analyze the error and the conversation history, then try generating "
                            f"the arguments for '{tool_name}' again, correcting any potential issues."
                        )
                        # No specific update_memory guidance needed here as it's excluded
                        messages_for_args.append({'role': 'system', 'content': retry_context})
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
                    tool_result = await self.tool_executor.execute(tool_name, arguments)
                    print(f"[{self.__class__.__name__}] Result from {tool_name} (Attempt {use_retry_count + 1}): {tool_result}")

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
                            temp_error_message = {
                                "tool_used": tool_name,
                                "arguments": arguments,
                                "result": tool_result,
                                "status": f"Execution Failed (Attempt {use_retry_count + 1})"
                            }
                            self.history_manager.add_message('system', json.dumps(temp_error_message))
                            use_retry_count += 1
                            await asyncio.sleep(TOOL_RETRY_DELAY_SECONDS)
                            continue
                    else:
                        break # Success

            final_tool_status = "Success"
            if tool_result is None:
                tool_result = "Error: Tool execution did not produce a result or failed during argument generation."
                final_tool_status = f"Failed (Args/Definition - {use_retry_count + 1} attempts)"
            elif isinstance(tool_result, str) and tool_result.startswith("Error:"):
                final_tool_status = f"Failed (Execution - {use_retry_count + 1} attempts)"

            tool_result_message_content = {
                "tool_used": tool_name,
                "arguments": arguments if arguments is not None else "N/A (argument generation failed)",
                "result": tool_result,
                "status": final_tool_status
            }
            self.history_manager.add_message('system', json.dumps(tool_result_message_content))

            if arguments is not None:
                tool_calls_made += 1
                if final_tool_status.startswith("Failed"):
                     print(f"[{self.__class__.__name__}] Tool '{tool_name}' ultimately failed after {use_retry_count + 1} attempts. Breaking main loop.")
                     break
            else:
                print(f"[{self.__class__.__name__}] Argument generation or definition finding failed definitively for {tool_name}. Breaking main loop.")
                break

        # 5. Final Memory Operation Step - REMOVED FOR DISCORD
        print(f"--- Step 5: Final Memory Save/Update Check SKIPPED for Discord ---")

        # 6. Final Response Generation
        print(f"--- Step 6: Final Response Generation ---")
        final_history = self.history_manager.get_history()

        messages_for_final_response = []
        if base_system_messages:
            messages_for_final_response.append(base_system_messages[0])
        else:
            messages_for_final_response.append({'role': 'system', 'content': "You are a helpful assistant."})

        if len(base_system_messages) > 1:
             messages_for_final_response.extend(base_system_messages[1:])

        messages_for_final_response.extend(final_history)

        if retrieved_facts_context_string:
            messages_for_final_response.append({'role': 'system', 'content': retrieved_facts_context_string})
            print(f"[{self.__class__.__name__}] Added retrieved facts context to final prompt.")

        final_personality_prompt = base_system_messages[0]['content'] if base_system_messages else "You are a helpful assistant."

        final_message = await self.llm_client.generate_final_response(
            messages_for_final_response,
            personality_prompt=final_personality_prompt
        )

        if final_message is None or final_message.startswith("Error:"):
            print(f"[{self.__class__.__name__}] Failed to get final response: {final_message}")
            final_message = final_message if final_message else "Sorry, I encountered an error generating the final response."
        else:
            self.history_manager.add_message('assistant', final_message)

        return final_message


    # --- Public Method ---

    async def get_response(self, user_message: str, discord_user_id: int, discord_user_name: str) -> tuple[str, None]:
        """
        Processes the user message from Discord using the OVERRIDDEN core logic.

        Args:
            user_message: The message content from Discord.
            discord_user_id: The Discord ID of the user.
            discord_user_name: The Discord display name of the user.

        Returns:
            A tuple containing the final response string and None (as expected by discord_bot.py).
        """
        print(f"--- Processing Discord message from {discord_user_name} ({discord_user_id}) ---")
        # Pass Discord-specific context to the core processing method
        final_response = await self._process_message(
            user_message,
            discord_user_id=discord_user_id,
            discord_user_name=discord_user_name
        )
        # Return format expected by discord_bot.py
        return final_response, None

    # __del__ is inherited from BaseLLMOrchestrator
