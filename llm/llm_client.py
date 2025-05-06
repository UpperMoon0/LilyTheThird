import random
import json
from itertools import cycle
from pathlib import Path
import logging 
from tools.tools import ToolDefinition, get_tool_list_for_prompt, get_tool_names
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # For Gemini exceptions
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from openai import OpenAI, RateLimitError as OpenAIRateLimitError # For OpenAI exceptions
from typing import List, Dict, Optional, Any

# Assuming history manager is in the same directory or adjust import path
from .history_manager import HistoryManager

# Constants
API_KEYS_FILE = Path("llm_api_keys.json")
API_KEYS_TEMPLATE_FILE = Path("llm_api_keys.json.template")

class LLMClient:
    """
    Handles communication with the underlying LLM provider (OpenAI or Gemini),
    managing multiple API keys with round-robin selection.
    """

    def __init__(self, provider: str, model_name: Optional[str] = None):
        """
        Initializes the LLM client based on the provider.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use.
        """
        self.provider = provider.lower() # Ensure lowercase provider name
        self.model = model_name
        self.client = None
        self.api_keys: Dict[str, List[str]] = {}
        self.key_iterators: Dict[str, cycle] = {} # Store iterators for round-robin

        self._load_api_keys_from_json()
        self._initialize_client()

    def _load_api_keys_from_json(self):
        """Loads API keys from llm_api_keys.json."""
        if not API_KEYS_FILE.exists():
            raise FileNotFoundError(
                f"API keys file not found: {API_KEYS_FILE}. "
                f"Please create it by copying and filling in {API_KEYS_TEMPLATE_FILE}."
            )
        try:
            with open(API_KEYS_FILE, 'r') as f:
                loaded_keys = json.load(f)

            # Validate and store keys, ensuring they are lists of strings
            for provider, keys in loaded_keys.items():
                provider_lower = provider.lower()
                if isinstance(keys, list) and all(isinstance(k, str) for k in keys):
                    if keys: # Only store if there are keys
                        self.api_keys[provider_lower] = keys
                        self.key_iterators[provider_lower] = cycle(keys) # Create iterator
                        print(f"Loaded {len(keys)} API key(s) for provider: {provider_lower}")
                    else:
                        print(f"Warning: No API keys found for provider '{provider_lower}' in {API_KEYS_FILE}.")
                else:
                    print(f"Warning: Invalid format for keys of provider '{provider_lower}' in {API_KEYS_FILE}. Expected a list of strings.")

        except json.JSONDecodeError:
            raise ValueError(f"Error decoding JSON from {API_KEYS_FILE}.")
        except Exception as e:
            raise RuntimeError(f"Failed to load API keys from {API_KEYS_FILE}: {e}")

    def _get_next_api_key(self) -> Optional[str]:
        """Gets the next API key for the current provider using round-robin."""
        if self.provider not in self.key_iterators:
            print(f"Error: No API keys loaded or available for provider: {self.provider}")
            return None # Or raise an error? Returning None might be handled better by caller.

        key = next(self.key_iterators[self.provider])
        # print(f"Using {self.provider} API key ending with: ...{key[-4:]}") # Debug: Don't log full key
        return key

    def _initialize_client(self):
        """Initializes the appropriate client. If no API keys are available for the provider,
        self.client remains None and a warning is logged."""

        # Check if keys were successfully loaded and an iterator was created for this provider
        if self.provider not in self.key_iterators:
            print(f"Warning: No API keys were successfully loaded for provider '{self.provider}'. Client will not be initialized.")
            self.client = None
            # Attempt to set a default model name for informational purposes, even if client is not active
            if not self.model:
                if self.provider == 'openai': self.model = "gpt-4o-mini"
                elif self.provider == 'gemini': self.model = "gemini-1.5-flash"
            
            # Log information about the uninitialized provider
            model_info = f"model: {self.model}" if self.model else "model: not specified"
            print(f"Info: Provider '{self.provider}' ({model_info}) is configured but client cannot be initialized due to missing/invalid API keys.")
            return # Exit early, self.client is None

        # If we are here, key_iterators[self.provider] exists, meaning keys are available.
        initial_api_key = self._get_next_api_key() # This should now reliably return a key.
        if not initial_api_key: # Should not happen if key_iterators check passed, but as a safeguard
            print(f"Error: Could not retrieve an API key for provider '{self.provider}' despite key iterator existing. Client will not be initialized.")
            self.client = None
            return

        # Determine default model if not already set (self.model might have been set by __init__ or above)
        if not self.model:
            if self.provider == 'openai':
                self.model = "gpt-4o-mini"
            elif self.provider == 'gemini':
                self.model = "gemini-1.5-flash"
            
            if self.model: # Print warning only if a default was applied here
                 print(f"Warning: No model name provided during LLMClient instantiation, using default for {self.provider}: {self.model}")
            elif self.provider not in ['openai', 'gemini']: # If provider is unknown and model is still None
                 print(f"Error: Model name must be provided for unknown provider: {self.provider}. Client initialization will likely fail.")
                 # self.client will remain None or fail in the try-except block below.

        # Initialize the client with the first key
        try:
            if self.provider == 'openai':
                if not self.model:
                    print(f"Error: OpenAI model name is missing. Cannot initialize client for provider '{self.provider}'.")
                    self.client = None; return
                self.client = OpenAI(api_key=initial_api_key)
            elif self.provider == 'gemini':
                if not self.model:
                    print(f"Error: Gemini model name is missing. Cannot initialize client for provider '{self.provider}'.")
                    self.client = None; return
                genai.configure(api_key=initial_api_key)
                self.client = genai.GenerativeModel(self.model)
            else:
                print(f"Error: Unsupported LLM provider '{self.provider}' encountered during client initialization. Client set to None.")
                self.client = None
                return
            print(f"LLM Client initialized for provider: {self.provider}, model: {self.model}")
        except Exception as e:
            model_name_for_log = self.model if self.model else "unknown"
            print(f"Error: Failed to initialize LLM client for {self.provider} (model: {model_name_for_log}) with the first key: {e}. Client set to None.")
            self.client = None


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
            A dictionary parsed from the JSON response, or an error dictionary if the single attempt fails.
        """
        print(f"--- Attempting {purpose} JSON call (Provider: {self.provider}) ---")

        # Check if client could not be initialized due to no keys at all for this provider
        if self.provider not in self.api_keys or not self.api_keys[self.provider]:
            model_name_for_log = self.model if self.model else "N/A"
            error_msg = f"No API keys loaded for provider '{self.provider}' (model: {model_name_for_log}). Cannot make {purpose} call."
            print(f"Error: {error_msg}")
            return {"error": error_msg}

        num_available_keys = len(self.api_keys.get(self.provider, []))
        last_exception_details = None # To store details of the last relevant exception

        for attempt in range(num_available_keys):
            api_key = self._get_next_api_key()
            if not api_key:
                # This should ideally not happen if num_available_keys > 0 and iterators are correctly managed
                print(f"Error: Failed to retrieve an API key for {self.provider} on attempt {attempt + 1}/{num_available_keys}.")
                # If it does, it's safer to stop and report an issue with key retrieval.
                return {"error": f"Internal error: Failed to retrieve API key for {self.provider}."}

            print(f"Attempt {attempt + 1}/{num_available_keys} for {purpose} using key ending ...{api_key[-4:]}")
            content = None # Reset content for each attempt

            try:
                if self.provider == 'openai':
                    # Initialize client with the current key for this attempt
                    current_client = OpenAI(api_key=api_key)
                    response = current_client.chat.completions.create(
                        messages=messages,
                            model=self.model,
                            max_tokens=400,
                            temperature=0.1,
                            response_format={"type": "json_object"}
                        )
                    # TODO: There are two identical OpenAI calls here. Was this intentional? Assuming the second one is the one to keep for now.
                    # If both are needed, the first response is overwritten.
                    response = current_client.chat.completions.create( 
                        messages=messages,
                            model=self.model,
                            max_tokens=400,
                            temperature=0.1,
                            response_format={"type": "json_object"}
                        )
                    content = response.choices[0].message.content.strip()
                    # print(f"Raw OpenAI JSON response for {purpose}: {content}") # Less verbose logging

                elif self.provider == 'gemini':
                    # Re-configure genai globally for this attempt
                    genai.configure(api_key=api_key)
                    # Re-fetch the model instance using the explicit model_name parameter
                    current_client = genai.GenerativeModel(model_name=self.model) # Explicitly use model_name

                    # Adapt messages
                    system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
                    history_openai_format = [msg for msg in messages if msg['role'] != 'system']
                    user_message_content = history_openai_format.pop()['content'] if history_openai_format else ""

                    temp_history_manager = HistoryManager()
                    gemini_formatted_history = temp_history_manager.adapt_history_for_gemini(history_openai_format)

                    # Combine prompts
                    prompt_parts = [
                        f"System Instructions:\n{' '.join(system_prompts)}\n\nUser Request:\n{user_message_content}\n\n"
                        f"IMPORTANT: Respond ONLY with a valid JSON object based on the request. Do not include any other text or explanations."
                    ]

                    safety_settings_config = [
                        {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                        {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
                        {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                        {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
                    ]
                    generation_config = genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        max_output_tokens=400,
                        temperature=0.1,
                        safety_settings=safety_settings_config
                    )

                    # Use the potentially reconfigured client instance
                    chat_session = current_client.start_chat(history=gemini_formatted_history)
                    response = chat_session.send_message(
                        prompt_parts,
                        generation_config=generation_config,
                    )
                    content = response.text.strip()
                    # print(f"Raw Gemini JSON response for {purpose}: {content}") # Less verbose logging
                else: # This else corresponds to the if/elif for provider
                    print(f"Unsupported provider '{self.provider}' for JSON generation.")
                    # This error should not be retried with other keys, as it's a config issue.
                    return {"error": f"Unsupported provider '{self.provider}'"}

                # --- JSON Parsing (common for both providers, executed if API call was successful for the provider) ---
                if not content: # This check is now inside the try, after a successful API call
                    print(f"Warning: Received empty content from {self.provider} for {purpose} with key ...{api_key[-4:]}.")
                    # Treat empty content as an error, potentially retrying with a new key as it might be a transient LLM issue
                    raise json.JSONDecodeError("Received empty content", "", 0) # This will be caught by the JSONDecodeError handler below

                content = content.strip() # Clean again

                # Attempt to parse the cleaned content
                # This try-except is nested because a JSONDecodeError here is different from an API error
                try:
                    parsed_json = json.loads(content)
                    print(f"Successfully parsed JSON for {purpose} on attempt {attempt + 1}")
                    return parsed_json # Success! Return the parsed JSON
                except json.JSONDecodeError as e_json_parse: # Specific variable for this exception
                    print(f"Error decoding JSON response for {purpose} on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_json_parse}\nRaw content: '{content}'")
                    last_exception_details = {"error": f"Failed to decode JSON. Content: '{content}'", "key_info": api_key[-4:]}
                    # If JSON decoding fails, it might be a malformed response from the LLM.
                    # We'll let it retry with the next key if available.
                    if attempt < num_available_keys - 1:
                        print("Retrying with next key due to JSON decode error.")
                        continue 
                    else: # Last attempt also failed to decode
                        return last_exception_details

            # --- Exception Handling for the current API call attempt ---
            except (OpenAIRateLimitError, google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e_api:
                error_type = "Rate limit" if isinstance(e_api, (OpenAIRateLimitError, google_exceptions.ResourceExhausted)) else "Permission/API Key"
                print(f"{error_type} error on attempt {attempt + 1}/{num_available_keys} for {purpose} with key ending ...{api_key[-4:]}: {e_api}")
                last_exception_details = {"error": f"{error_type} error: {e_api}", "key_info": api_key[-4:]}
                if attempt < num_available_keys - 1:
                    print("Retrying with next key...")
                    continue # Go to the next iteration of the loop (next key for API call)
                else: # This was the last key for an API error
                    print(f"All {num_available_keys} API key(s) failed for {purpose}. Last API error: {error_type}")
                    return last_exception_details
            except json.JSONDecodeError as e_json_outer: # Handles JSONDecodeError from empty content before parsing
                print(f"JSON decoding error (likely empty content from API) on attempt {attempt + 1} for {purpose} with key ...{api_key[-4:]}: {e_json_outer}\nRaw content was: '{content}'")
                last_exception_details = {"error": f"Failed to decode JSON (empty content from API?). Content: '{content}'", "key_info": api_key[-4:]}
                if attempt < num_available_keys - 1:
                    print("Retrying with next key due to empty/unanalyzable API response.")
                    continue
                else: # Last attempt also resulted in content that couldn't be parsed (or was empty)
                    return last_exception_details
            except Exception as e_general:
                logging.exception(f"Unexpected error calling LLM API ({purpose}) on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_general}")
                # For truly unexpected errors, stop and return immediately.
                return {"error": f"Unexpected API error: {e_general}", "key_info": api_key[-4:]}

        # If loop finishes, it means all keys failed with retriable errors (API or JSON parsing related)
        print(f"All {num_available_keys} API key(s) exhausted for {purpose}.")
        return last_exception_details if last_exception_details else {"error": f"All API keys failed for {self.provider} during {purpose} after exhausting all attempts."}

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
        required_args = tool.json_schema.get("required", [])
        properties = tool.json_schema.get("properties", {})
        arg_descriptions = [f"- '{prop}': {details.get('description', 'No description')}" for prop, details in properties.items() if prop in required_args]
        # Try to extract the example from the tool's instruction string
        example_json_str = "{}" # Default empty JSON
        if "Example: " in tool.instruction:
            try:
                example_json_str = tool.instruction.split("Example: ")[-1]
            except Exception:
                pass # Keep default if split fails

        system_prompt = (
            f"You MUST use the tool '{tool.name}'.\n"
            f"Tool Description: {tool.description}\n"
            f"Based ONLY on the preceding conversation history, determine the values for the following required arguments:\n" +
            "\n".join(arg_descriptions) + "\n\n" +
            f"Respond ONLY with a single, valid JSON object containing these keys and their determined values. Your entire response must be the JSON object, starting with {{ and ending with }}.\n"
            f"Example JSON format (values depend on context): {example_json_str}"
        )
        # print(f"--- Argument Generation Prompt for {tool.name} ---\n{system_prompt}\n--------------------------") # DEBUG

        request_messages = [msg for msg in messages] # Create a copy
        # Prepend the system prompt for argument generation
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
            The generated message string, or an error string if the single attempt fails.
        """
        # Ensure personality prompt is included, followed by the full history
        final_messages = [{"role": "system", "content": personality_prompt}]
        final_messages.extend(messages)

        if self.provider not in self.api_keys or not self.api_keys[self.provider]:
            model_name_for_log = self.model if self.model else "N/A"
            error_msg = f"No API keys loaded for provider '{self.provider}' (model: {model_name_for_log}). Cannot generate final response."
            print(f"Error: {error_msg}")
            return error_msg # Return the error message string

        num_available_keys = len(self.api_keys.get(self.provider, []))
        last_error_message = f"Error: All {num_available_keys} API key(s) failed for {self.provider} during final response generation."

        print(f"--- Attempting Final {self.provider.capitalize()} Response ({num_available_keys} key(s) available) ---")

        for attempt in range(num_available_keys):
            api_key = self._get_next_api_key()
            if not api_key:
                print(f"Error: Failed to retrieve an API key for {self.provider} on attempt {attempt + 1}/{num_available_keys} for final response.")
                # This indicates an internal issue, update last_error_message
                last_error_message = f"Error: Internal error retrieving API key for {self.provider}."
                break # Stop if key retrieval fails

            print(f"Attempt {attempt + 1}/{num_available_keys} for Final Response using key ending ...{api_key[-4:]}")

            try:
                if self.provider == 'openai':
                    response_text = await self._generate_openai_response(final_messages, api_key)
                    return response_text # Success
                elif self.provider == 'gemini':
                    response_text = await self._generate_gemini_response(final_messages, api_key)
                    return response_text # Success
                else:
                    # This should ideally be caught earlier or by a more general mechanism if providers are dynamic
                    unsupported_provider_msg = f"Error: Unsupported provider '{self.provider}' for final response generation."
                    print(unsupported_provider_msg)
                    return unsupported_provider_msg # Not a retriable error with other keys

            except (OpenAIRateLimitError, google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
                error_type = "Rate limit" if isinstance(e, (OpenAIRateLimitError, google_exceptions.ResourceExhausted)) else "Permission/API Key"
                current_error_msg = f"{error_type} error on attempt {attempt + 1} with key ...{api_key[-4:]}: {e}"
                print(current_error_msg)
                last_error_message = f"Error: {current_error_msg}" # Store as the latest error encountered
                if attempt < num_available_keys - 1:
                    print("Retrying with next key for final response...")
                    continue # Try next key
                else: # Last key also failed with a retriable error
                    print(f"All {num_available_keys} API key(s) failed for final response. Last error: {error_type}")
                    return last_error_message
            except Exception as e:
                # For any other unexpected exception during the helper call
                unexpected_error_msg = f"Unexpected error during final response generation on attempt {attempt + 1} with key ...{api_key[-4:]}: {e}"
                logging.exception(unexpected_error_msg)
                return f"Error: {unexpected_error_msg}" # Stop on unexpected errors

        # If loop completes, all keys were tried and failed with retriable errors
        return last_error_message

    async def _generate_openai_response(self, messages: List[Dict], api_key: str) -> str:
        """Handles the actual OpenAI API call for message generation, using the provided key."""
        # Note: No try/except here, handled by the calling loop
        # print(f"--- Calling OpenAI API for Final Response (Key: ...{api_key[-4:]}) ---")
        current_client = OpenAI(api_key=api_key) # Initialize with the specific key for this attempt
        response = current_client.chat.completions.create(
                messages=messages,
                model=self.model,
                max_tokens=450,
                temperature=random.uniform(0.2, 0.8),
            )
        message = response.choices[0].message.content.strip()
        print(f"Final OpenAI Response received (using key ...{api_key[-4:]}).")
        return message


    async def _generate_gemini_response(self, messages: List[Dict], api_key: str) -> str:
        """Handles the actual Gemini API call for message generation, using the provided key."""
        # Note: No try/except here, handled by the calling loop
        # print(f"--- Calling Gemini API for Final Response (Key: ...{api_key[-4:]}) ---")
        # Re-configure genai globally for this attempt
        genai.configure(api_key=api_key)
        # Re-fetch the model instance using the explicit model_name parameter
        current_client = genai.GenerativeModel(model_name=self.model) # Explicitly use model_name

        # Adapt messages
        system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
        history_openai_format = [msg for msg in messages if msg['role'] != 'system']

        if not history_openai_format:
            print("Warning: No user/model messages found for Gemini final response.")
            final_user_content = "Please respond."
            gemini_history_to_pass = []
        else:
            final_user_content = history_openai_format.pop()['content'] if history_openai_format and 'content' in history_openai_format[-1] else "Please respond based on history."
            temp_history_manager = HistoryManager()
            gemini_history_to_pass = temp_history_manager.adapt_history_for_gemini(history_openai_format)

        prompt_parts = [
            f"System Instructions:\n{' '.join(system_prompts)}\n\n"
            f"User Request/Context:\n{final_user_content}\n\n"
            f"IMPORTANT: Generate your final response based *only* on the information provided in the System Instructions and the preceding conversation history (including any Tool results shown). Synthesize the information accurately."
        ]

        safety_settings_config = [
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=1000,
            temperature=random.uniform(0.2, 0.7),
            safety_settings=safety_settings_config
        )

        # Use the reconfigured client instance
        chat_session = current_client.start_chat(history=gemini_history_to_pass)
        response = chat_session.send_message(
            prompt_parts,
            generation_config=generation_config,
        )

        if response.text:
            message = response.text.strip()
            print(f"Final Gemini Response received (using key ...{api_key[-4:]}).")
            return message
        else:
            # Handle potential blocking or empty response
            feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else "Unknown reason"
            block_reason = feedback.block_reason if hasattr(feedback, 'block_reason') else "N/A"
            safety_ratings = feedback.safety_ratings if hasattr(feedback, 'safety_ratings') else "N/A"
            print(f"Gemini final response issue (using key ...{api_key[-4:]}): Block Reason: {block_reason}, Safety Ratings: {safety_ratings}")
            # Raise an exception to be caught by the retry loop
            raise google_exceptions.PermissionDenied(f"Gemini response blocked or empty. Reason: {block_reason}")
