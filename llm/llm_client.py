import os
import random
import json
import asyncio # For sleep
import logging # For logging errors
# Import the updated functions from tools.py
from tools.tools import ToolDefinition, get_tool_list_for_prompt, get_tool_names, find_tool
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # For Gemini exceptions
from openai import OpenAI, RateLimitError as OpenAIRateLimitError # For OpenAI exceptions
from typing import List, Dict, Optional, Any

# Assuming history manager is in the same directory or adjust import path
from .history_manager import HistoryManager

# Constants for LLM API retry logic
MAX_LLM_API_RETRIES = 3
LLM_RETRY_DELAY_SECONDS = 60 # Wait 1 minute for rate limit errors

class LLMClient:
    """Handles communication with the underlying LLM provider (OpenAI or Gemini)."""

    def __init__(self, provider: str, model_name: Optional[str] = None):
        """
        Initializes the LLM client based on the provider.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use.
        """
        self.provider = provider
        self.model = model_name
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Loads API keys and initializes the appropriate client."""
        openai_api_key = os.getenv('OPENAI_KEY')
        gemini_api_key = os.getenv('GEMINI_API_KEY')

        if not self.model:
            # Set default model if none provided
            if self.provider == 'openai':
                self.model = "gpt-4o-mini" # Default OpenAI model
            elif self.provider == 'gemini':
                self.model = "gemini-1.5-flash" # Default Gemini model
            else:
                # If provider is unknown and no model is given, we can't proceed
                raise ValueError(f"Model name must be provided for unsupported provider: {self.provider}")
            print(f"Warning: No model name provided, using default for {self.provider}: {self.model}")

        if self.provider == 'openai':
            if not openai_api_key:
                raise ValueError("OpenAI API key not found in environment variables.")
            self.client = OpenAI(api_key=openai_api_key)
        elif self.provider == 'gemini':
            if not gemini_api_key:
                raise ValueError("Gemini API key not found in environment variables.")
            genai.configure(api_key=gemini_api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        print(f"LLM Client initialized for provider: {self.provider}, model: {self.model}")

    def get_model_name(self) -> str:
        """Returns the name of the model being used."""
        return self.model

    # --- Core LLM Call for JSON ---
    async def _call_llm_for_json(self, messages: List[Dict], purpose: str) -> Optional[Dict]:
        """
        Internal helper to call the LLM and expect a JSON response, with retries for rate limits and JSON errors.

        Args:
            messages: The list of messages for the prompt.
            purpose: A string describing the purpose (e.g., "Tool Selection", "Argument Generation") for logging.

        Returns:
            A dictionary parsed from the JSON response, or an error dictionary if all retries fail.
        """
        # Combined retry loop for API errors (like rate limits) and JSON parsing issues
        # Use MAX_LLM_API_RETRIES for consistency, as API errors are the primary target
        for attempt in range(MAX_LLM_API_RETRIES):
            print(f"--- Attempt {attempt + 1}/{MAX_LLM_API_RETRIES} for {purpose} JSON ---")
            # print(f"Messages sent for JSON:\n{json.dumps(messages, indent=2)}") # DEBUG
            content = None # Initialize content to None

            try:
                if self.provider == 'openai':
                    # Instruct OpenAI to return JSON
                    response = self.client.chat.completions.create(
                        messages=messages,
                        model=self.model,
                        max_tokens=400, # Increased slightly for potentially complex JSON
                        temperature=0.1, # Lower temperature for more deterministic JSON
                        response_format={"type": "json_object"} # Request JSON mode
                    )
                    content = response.choices[0].message.content.strip()
                    print(f"Raw OpenAI JSON response for {purpose}: {content}")

                elif self.provider == 'gemini':
                    # Adapt messages for Gemini (similar to generate_final_response)
                    system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
                    history_openai_format = [msg for msg in messages if msg['role'] != 'system']
                    # Ensure history_openai_format is not empty before popping
                    user_message_content = history_openai_format.pop()['content'] if history_openai_format else ""

                    temp_history_manager = HistoryManager() # Consider making adaptation static/util
                    gemini_formatted_history = temp_history_manager.adapt_history_for_gemini(history_openai_format)

                    # Combine system prompts and user message, explicitly asking for JSON
                    prompt_parts = [
                        f"System Instructions:\n{' '.join(system_prompts)}\n\nUser Request:\n{user_message_content}\n\n"
                        f"IMPORTANT: Respond ONLY with a valid JSON object based on the request. Do not include any other text or explanations."
                    ]

                    generation_config = genai.types.GenerationConfig(
                        # Ensure Gemini knows we want JSON - response_mime_type might work
                        response_mime_type="application/json", # Explicitly request JSON if supported
                        max_output_tokens=400, # Increased slightly
                        temperature=0.1, # Lower temperature for JSON
                    )

                    chat_session = self.client.start_chat(history=gemini_formatted_history)
                    response = chat_session.send_message(
                        prompt_parts,
                        generation_config=generation_config,
                        # stream=False # Ensure we get the full response at once
                    )
                    content = response.text.strip()
                    print(f"Raw Gemini JSON response for {purpose}: {content}")
                else:
                    print(f"Unsupported provider '{self.provider}' for JSON generation.")
                    return {"error": f"Unsupported provider '{self.provider}'"}

                # --- JSON Parsing (common for both providers) ---
                if not content:
                    print(f"Warning: Received empty content from {self.provider} for {purpose} (Attempt {attempt + 1}).")
                    # Treat empty content as a retryable error for JSON calls
                    raise json.JSONDecodeError("Received empty content", "", 0)

                # Clean potential markdown code block fences before parsing
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip() # Clean again after removing fences

                # Attempt to parse the cleaned content
                parsed_json = json.loads(content)
                return parsed_json # Success! Return the parsed JSON

            # --- Exception Handling within the loop ---
            except (OpenAIRateLimitError, google_exceptions.ResourceExhausted) as e:
                print(f"Rate limit error encountered for {purpose} (Attempt {attempt + 1}/{MAX_LLM_API_RETRIES}): {e}")
                if attempt < MAX_LLM_API_RETRIES - 1:
                    print(f"Waiting {LLM_RETRY_DELAY_SECONDS} seconds before retrying...")
                    await asyncio.sleep(LLM_RETRY_DELAY_SECONDS)
                    continue # Go to the next attempt
                else:
                    print(f"Max retries reached for rate limit error.")
                    return {"error": f"Rate limit exceeded after {MAX_LLM_API_RETRIES} attempts."}
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON response for {purpose} (Attempt {attempt + 1}/{MAX_LLM_API_RETRIES}): {e}\nRaw content: '{content}'")
                if attempt < MAX_LLM_API_RETRIES - 1:
                    print(f"Retrying JSON call...")
                    await asyncio.sleep(2) # Shorter delay for JSON errors
                    continue # Go to the next attempt
                else:
                    print(f"Max retries reached for JSON decoding error.")
                    return {"error": f"Failed to decode JSON after {MAX_LLM_API_RETRIES} attempts. Last content: '{content}'"}
            except Exception as e:
                logging.exception(f"Unexpected error calling LLM API ({purpose} - Attempt {attempt + 1}): {e}") # Log full traceback
                # Break on other unexpected errors immediately
                return {"error": f"Unexpected API error: {e}"}

        # Should only be reached if all retries failed for some reason (e.g., loop logic error)
        print(f"Failed to get valid JSON response for {purpose} after {MAX_LLM_API_RETRIES} attempts.")
        return {"error": f"Failed to get JSON response after {MAX_LLM_API_RETRIES} attempts."}

    # --- Tool Interaction Methods ---

    async def get_next_action(
        self,
        messages: List[Dict],
        allowed_tools: Optional[List[str]] = None,
        context_type: Optional[str] = None,
        force_tool_options: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Prompts the LLM to decide the next action: use a tool or respond directly.
        Can be forced to consider only specific tools.

        Args:
            messages: The current conversation history in OpenAI format.
            allowed_tools: List of tool names allowed in the *overall* context. If None, all tools are allowed.
            context_type: Optional string identifying the context (e.g., 'chatbox', 'discord').
            force_tool_options: Optional list of tool names. If provided, the LLM MUST choose one of these or null.

        Returns:
            A dictionary like {"action_type": "tool_choice", "tool_name": "tool_name_here" or None},
            or an error dictionary if all retries fail.
        """
        # Determine the actual tools the LLM can choose from in this specific call
        if force_tool_options is not None:
            # Filter forced options against tools actually available/allowed in the context
            all_available_context_tools = set(get_tool_names(allowed_tools=allowed_tools))
            valid_forced_options = [tool for tool in force_tool_options if tool in all_available_context_tools]
            if not valid_forced_options:
                print(f"Warning: Forced tool options {force_tool_options} are not available/allowed in this context. Skipping tool check.")
                return {"action_type": "tool_choice", "tool_name": None}
            choosable_tool_names = valid_forced_options
            tool_list_prompt = get_tool_list_for_prompt(allowed_tools=choosable_tool_names) # Prompt only shows forced tools
            prompt_instruction = f"You MUST choose one of the tools listed below or null:"
        else:
            # Standard case: choose from all allowed tools in the context
            choosable_tool_names = get_tool_names(allowed_tools=allowed_tools)
            if not choosable_tool_names:
                print("No tools allowed or available in this context. Skipping tool check.")
                return {"action_type": "tool_choice", "tool_name": None}
            tool_list_prompt = get_tool_list_for_prompt(allowed_tools=choosable_tool_names)
            prompt_instruction = "Decide if you need to use one of the available tools *from the list below* to fulfill the request."

        # --- Build the System Prompt ---
        system_prompt_lines = [
            "You are an AI assistant deciding the next step.",
            "Analyze the conversation history.",
            prompt_instruction,
            f"{tool_list_prompt}"
        ]

        # Add context-specific encouragement for saving, ONLY if 'save_memory' is a forced option
        if context_type == 'chatbox' and force_tool_options and 'save_memory' in force_tool_options:
            system_prompt_lines.append(
                "IMPORTANT (ChatBox Context - Final Save Check): Review the entire conversation. If you learned any new, specific, and potentially useful facts (e.g., user preferences, project details, key information) that haven't been saved yet, you SHOULD use the 'save_memory' tool now."
            )

        # Add JSON formatting instructions
        system_prompt_lines.extend([
            "Respond ONLY with a JSON object containing the key 'tool_name'.",
            f"The value must be the name of one of the tools listed above ({', '.join(choosable_tool_names)}) or null.",
            f"Example for using a tool: {{\"tool_name\": \"{choosable_tool_names[0] if choosable_tool_names else 'example_tool'}\"}}",
            "Example for not using a tool: {\"tool_name\": null}"
        ])

        system_prompt = "\n".join(system_prompt_lines)
        # print(f"--- Tool Selection Prompt ---\n{system_prompt}\n--------------------------") # DEBUG

        # Prepare messages for the LLM
        request_messages = [msg for msg in messages] # Create a copy
        # Insert the system prompt for tool selection
        # Find the first user message and insert before it, or append if none?
        # Let's just prepend it for simplicity for now.
        request_messages.insert(0, {"role": "system", "content": system_prompt})

        json_response = await self._call_llm_for_json(request_messages, "Tool Selection")

        if json_response and isinstance(json_response, dict) and "tool_name" in json_response:
            tool_name = json_response["tool_name"]
            # Check for None (JSON null), the string "null", or a valid tool name from the choosable list
            if tool_name is None or tool_name == "null" or tool_name in choosable_tool_names:
                 # If the tool name is the string "null", treat it as None (no tool)
                 actual_tool_name = None if tool_name == "null" else tool_name
                 # print(f"LLM decided action: {actual_tool_name}") # DEBUG
                 return {"action_type": "tool_choice", "tool_name": actual_tool_name}
            else:
                 print(f"Error: LLM chose an invalid tool name: {tool_name}")
                 # Fallback: Default to no tool if the name is invalid
                 return {"action_type": "tool_choice", "tool_name": None}
        else:
            print(f"Error: Failed to get valid tool selection JSON. Response: {json_response}")
            # Fallback: Assume no tool needed if JSON is invalid/missing or contains an error
            if not json_response or "error" in json_response:
                 error_msg = json_response.get("error", "Unknown JSON error") if json_response else "No JSON response"
                 print(f"Error in tool selection JSON: {error_msg}. Assuming no tool needed.")
                 return {"action_type": "tool_choice", "tool_name": None, "error": error_msg}
            # Proceed with valid JSON
            tool_name = json_response.get("tool_name")
            # Check for None (JSON null), the string "null", or a valid tool name from the choosable list
            if tool_name is None or tool_name == "null" or tool_name in choosable_tool_names:
                 actual_tool_name = None if tool_name == "null" else tool_name
                 return {"action_type": "tool_choice", "tool_name": actual_tool_name}
            else:
                 print(f"Error: LLM chose an invalid tool name: {tool_name}")
                 # Fallback: Default to no tool if the name is invalid
                 return {"action_type": "tool_choice", "tool_name": None, "error": f"Invalid tool name '{tool_name}' chosen."}


    async def get_tool_arguments(self, tool: ToolDefinition, messages: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        Prompts the LLM to provide arguments for the chosen tool, handling retries.

        Args:
            tool: The ToolDefinition object for the chosen tool.
            messages: The current conversation history in OpenAI format.

        Returns:
            A dictionary like {"action_type": "tool_arguments", "arguments": {...}},
            or an error dictionary if all retries fail.
            The arguments dictionary should match the tool's json_schema.
        """
        # --- Check if the tool requires arguments ---
        # If the schema defines no properties and no required fields, assume no arguments needed.
        if not tool.json_schema.get("properties") and not tool.json_schema.get("required"):
            print(f"Tool '{tool.name}' requires no arguments. Returning empty dict.")
            return {"action_type": "tool_arguments", "arguments": {}}

        # --- If arguments are needed, prompt the LLM ---
        system_prompt = (
            f"You have decided to use the '{tool.name}' tool.\n"
            f"Tool Description: {tool.description}\n"
            f"Instructions: {tool.instruction}\n"
            f"Based on the conversation history and the user's request, provide the necessary arguments for this tool.\n"
            f"Respond ONLY with a valid JSON object containing the arguments, matching this structure: {json.dumps(tool.json_schema)}"
        )

        request_messages = [msg for msg in messages] # Create a copy
        request_messages.insert(0, {"role": "system", "content": system_prompt})

        json_response = await self._call_llm_for_json(request_messages, f"Argument Generation for {tool.name}")

        if json_response and isinstance(json_response, dict):
            # TODO: Add JSON schema validation here using jsonschema library if needed
            if not json_response or "error" in json_response:
                 error_msg = json_response.get("error", "Unknown JSON error") if json_response else "No JSON response"
                 print(f"Error getting arguments JSON for tool {tool.name}: {error_msg}")
                 return {"action_type": "tool_arguments", "arguments": {}, "error": error_msg} # Return empty args and error
            else:
                 print(f"Received arguments for {tool.name}: {json_response}")
                 return {"action_type": "tool_arguments", "arguments": json_response}


    # --- Final Response Generation ---
    async def generate_final_response(self, messages: List[Dict], personality_prompt: str) -> Optional[str]:
        """
        Generates the final conversational response after tool use (or if no tool was needed).

        Args:
            messages: The complete list of messages (including history, tool calls/results,
                      and the final user message) in OpenAI format.
            personality_prompt: The system prompt defining the chatbot's personality.

        Returns:
            The generated message string, or an error string if all retries fail.
        """
        # Ensure personality prompt is included, followed by the full history
        final_messages = [{"role": "system", "content": personality_prompt}]
        # Add the rest of the conversation history, preserving all roles including 'system' for tool results
        final_messages.extend(messages) # Pass the full history

        # --- Call the appropriate provider ---
        # --- Call the appropriate provider ---
        # Add retry logic here
        for attempt in range(MAX_LLM_API_RETRIES): # Line 356
            print(f"--- Attempt {attempt + 1}/{MAX_LLM_API_RETRIES} for Final {self.provider.capitalize()} Response ---")
            try: # Indented this block
                if self.provider == 'openai':
                    return await self._generate_openai_response(final_messages)
                elif self.provider == 'gemini':
                    return await self._generate_gemini_response(final_messages)
                else:
                    print(f"Unsupported provider '{self.provider}' for final response generation.")
                    return f"Error: Unsupported provider '{self.provider}'."
            except (OpenAIRateLimitError, google_exceptions.ResourceExhausted) as e: # Indented this block
                print(f"Rate limit error during final response generation (Attempt {attempt + 1}): {e}")
                if attempt < MAX_LLM_API_RETRIES - 1:
                    print(f"Waiting {LLM_RETRY_DELAY_SECONDS} seconds before retrying...")
                    await asyncio.sleep(LLM_RETRY_DELAY_SECONDS)
                    continue
                else:
                    return f"Error: Rate limit exceeded after {MAX_LLM_API_RETRIES} attempts during final response generation."
            except Exception as e: # Indented this block
                 logging.exception(f"Unexpected error during final response generation (Attempt {attempt + 1}): {e}")
                 # Don't retry on unexpected errors
                 return f"Error: Unexpected error during final response generation: {e}"
        # Fallback if loop finishes without returning
        return f"Error: Failed to generate final response after {MAX_LLM_API_RETRIES} attempts." # Indented this line


    async def _generate_openai_response(self, messages: List[Dict]) -> str:
        """Handles the actual OpenAI API call for message generation. Assumes retry logic is handled by caller."""
        # Note: No try/except here, handled by the calling loop in generate_final_response
        print(f"--- Calling OpenAI API for Final Response ---")
        # print(f"Messages sent for final response:\n{json.dumps(messages, indent=2)}") # DEBUG
        response = self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                max_tokens=450, # Keep original max_tokens for final response
                temperature=random.uniform(0.2, 0.8), # Keep original temperature range
                # No JSON format needed here
            )
        message = response.choices[0].message.content.strip()
        print(f"Final OpenAI Response received.")
        return message


    def _generate_gemini_response(self, messages: List[Dict]) -> str:
        """Handles the actual Gemini API call for message generation. Assumes retry logic is handled by caller."""
        # Note: No try/except here, handled by the calling loop in generate_final_response
        print(f"--- Calling Gemini API for Final Response ---")
        # Adapt system prompts and history for Gemini
        system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
        history_openai_format = [msg for msg in messages if msg['role'] != 'system']

        if not history_openai_format:
             # Should not happen if called correctly, but handle defensively
             print("Warning: No user/model messages found for Gemini final response.")
             final_user_content = "Please respond." # Placeholder
             gemini_history_to_pass = []
        else:
            # Assume last is user/tool result to prompt response
            # Check if the last message has 'content' before popping
            final_user_content = history_openai_format.pop()['content'] if history_openai_format and 'content' in history_openai_format[-1] else "Please respond based on history."
            temp_history_manager = HistoryManager()
            gemini_history_to_pass = temp_history_manager.adapt_history_for_gemini(history_openai_format)

        prompt_parts = [
            f"System Instructions:\n{' '.join(system_prompts)}\n\n"
            f"User Request/Context:\n{final_user_content}\n\n"
            f"IMPORTANT: Generate your final response based *only* on the information provided in the System Instructions and the preceding conversation history (including any Tool results shown). Synthesize the information accurately."
        ]

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=1000,
            temperature=random.uniform(0.2, 0.7),
        )

        chat_session = self.client.start_chat(history=gemini_history_to_pass)
        response = chat_session.send_message(
            prompt_parts,
            generation_config=generation_config,
        )
        # print(f"--- Raw Gemini Final Response Text ---\n{response.text}\n----------------------------------------") # DEBUG
        if response.text:
            message = response.text.strip()
            print(f"Final Gemini Response received.")
            return message
        else:
            # If response.text is empty, check for blocking/safety feedback
            feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else "Unknown reason"
            block_reason = feedback.block_reason if hasattr(feedback, 'block_reason') else "N/A"
            safety_ratings = feedback.safety_ratings if hasattr(feedback, 'safety_ratings') else "N/A"
            print(f"Gemini final response issue: Block Reason: {block_reason}, Safety Ratings: {safety_ratings}")
            # Raise an exception that the outer loop can catch if needed, or return error string
            # For simplicity, return an error string here. The outer loop will handle it.
            return f"Error: Gemini final response was empty or blocked. Reason: {block_reason}"
