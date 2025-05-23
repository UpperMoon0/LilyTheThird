import random
import json
from itertools import cycle
from pathlib import Path
import logging
import os # Added for APPDATA
import datetime # Added for timestamps
from tools.tools import ToolDefinition, get_tool_list_for_prompt, get_tool_names
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
from typing import List, Dict, Optional, Any
import shutil

import google.generativeai as genai
import random
import json # Ensure json is imported for _load_api_keys_from_json
import shutil # Ensure shutil is imported for copying template file
import logging # Ensure logging is imported

# Assuming history manager is in the same directory or adjust import path
from .history_manager import HistoryManager

# Constants
# Go up one level from the current file's directory (llm/) to reach the project root
PROJECT_ROOT = Path(__file__).parent.parent
API_KEYS_FILE = PROJECT_ROOT / "llm_api_keys.json"
API_KEYS_TEMPLATE_FILE = PROJECT_ROOT / "llm_api_keys.json.template"

# --- Helper functions to fetch models ---
def get_openai_models(api_key: str) -> List[str]:
    """Fetches available models from OpenAI."""
    try:
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        # Filter for GPT models and sort by creation date or name if needed
        # For now, returning all model IDs that seem like primary models
        return sorted([model.id for model in models if "gpt" in model.id and "instruct" not in model.id and "vision" not in model.id])
    except Exception as e:
        print(f"Error fetching OpenAI models: {e}")
        return []

def get_gemini_models(api_key: str) -> List[str]:
    """Fetches available models from Gemini."""
    try:
        # Ensure genai is configured before listing models if this function can be called standalone
        # However, API key is passed, so direct usage is fine.
        genai.configure(api_key=api_key) 
        models = genai.list_models()
        # Filter for models that support 'generateContent'
        return sorted([m.name for m in models if 'generateContent' in m.supported_generation_methods and "gemini" in m.name]) # Added "gemini" in m.name filter
    except Exception as e:
        print(f"Error fetching Gemini models: {e}")
        return []

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

        self._setup_request_logger() # Added logger setup
        self._load_api_keys_from_json()
        self._initialize_client()

    def _setup_request_logger(self):
        """Sets up the logger for LLM requests."""
        try:
            appdata_dir_path = os.getenv('APPDATA')
            if not appdata_dir_path:
                # Fallback if APPDATA is not set (e.g., non-Windows or specific configurations)
                home_dir = Path.home()
                if os.name == 'nt': # Windows specific fallback
                    appdata_dir_path = home_dir / 'AppData' / 'Roaming'
                elif os.name == 'posix': # Linux/macOS style
                    xdg_config_home = os.getenv('XDG_CONFIG_HOME')
                    appdata_dir_path = Path(xdg_config_home) if xdg_config_home else home_dir / '.config'
                else: # Generic fallback
                    appdata_dir_path = home_dir / '.app_support'
            
            log_dir = Path(appdata_dir_path) / "NsTut" / "LilyTheThird" / "llm"
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file_path = log_dir / "llm_requests.log"

            self.request_logger = logging.getLogger('LLMRequestLogger')
            self.request_logger.setLevel(logging.INFO)
            
            # Prevent adding multiple handlers if LLMClient is instantiated multiple times
            if not self.request_logger.handlers:
                fh = logging.FileHandler(self.log_file_path, encoding='utf-8')
                formatter = logging.Formatter('%(asctime)s - %(message)s')
                fh.setFormatter(formatter)
                self.request_logger.addHandler(fh)
            
            print(f"LLMClient request logger initialized. Logging to: {self.log_file_path}")

        except Exception as e:
            print(f"Error setting up LLM request logger: {e}")
            self.request_logger = None # Ensure it's None if setup fails
            self.log_file_path = None

    def _log_request_data(self, log_type: str, data: Dict):
        """Helper method to log structured request data."""
        if self.request_logger:
            try:
                log_entry = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "log_type": log_type,
                    "provider": self.provider,
                    "model": self.model,
                    **data
                }
                self.request_logger.info(json.dumps(log_entry, ensure_ascii=False, indent=2)) # Added indent=2
            except Exception as e:
                # Avoid crashing the main application due to logging errors
                print(f"Error writing to LLM request log: {e}")

    def _load_api_keys_from_json(self):
        """Loads API keys from llm_api_keys.json."""
        if not API_KEYS_FILE.exists():
            print(f"Warning: API keys file not found at {API_KEYS_FILE}. Creating from template.")
            try:
                shutil.copy(API_KEYS_TEMPLATE_FILE, API_KEYS_FILE)
                print(f"Successfully created {API_KEYS_FILE}. Please edit it with your API keys.")
                self.api_keys = {} # No keys loaded yet
            except Exception as e:
                print(f"Error: Could not create API keys file from template: {e}")
                self.api_keys = {}
            return

        try:
            with open(API_KEYS_FILE, 'r') as f:
                self.api_keys = json.load(f)
            # Initialize iterators for providers that have keys
            for provider, keys in self.api_keys.items():
                if keys and isinstance(keys, list) and all(isinstance(key, str) for key in keys):
                    self.key_iterators[provider.lower()] = cycle(keys) # Ensure provider key is lowercase
                else:
                    print(f"Warning: Invalid or empty API key list for provider '{provider}' in {API_KEYS_FILE}.")
                    if provider.lower() in self.key_iterators: # Remove if previously valid
                        del self.key_iterators[provider.lower()]


        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {API_KEYS_FILE}. Please ensure it's valid JSON.")
            self.api_keys = {}
        except Exception as e:
            print(f"Error loading API keys: {e}")
            self.api_keys = {}

    def _get_next_api_key(self) -> Optional[str]:
        """Gets the next API key for the current provider using round-robin."""
        provider_lower = self.provider.lower() # Use lowercase provider consistently
        if provider_lower not in self.key_iterators:
            print(f"Warning: No API key iterator found for provider '{self.provider}'. Keys might be missing or invalid.")
            return None

        try:
            key = next(self.key_iterators[provider_lower])
            # print(f"Using {self.provider} API key ending with: ...{key[-4:]}") # Debug: Don't log full key
            return key
        except StopIteration: # Should not happen with cycle, but as a safeguard
            print(f"Warning: API key iterator exhausted unexpectedly for provider '{self.provider}'.")
            return None


    def _initialize_client(self):
        """Initializes the appropriate client. If no API keys are available for the provider,
        self.client remains None and a warning is logged."""
        provider_lower = self.provider.lower() # Use lowercase provider consistently

        # Check if keys were successfully loaded and an iterator was created for this provider
        if provider_lower not in self.key_iterators:
            print(f"Warning: No API keys available or loaded for provider '{self.provider}'. Client cannot be initialized.")
            self.client = None # Explicitly set to None
            return

        initial_api_key = self._get_next_api_key()
        if not initial_api_key:
            print(f"Warning: Failed to get an initial API key for provider '{self.provider}'. Client cannot be initialized.")
            self.client = None # Explicitly set to None
            return

        # Determine default model if not already set (self.model might have been set by __init__ or above)
        if not self.model:
            if provider_lower == "openai":
                # Fetch models and pick the first one as default, or a fallback
                # This requires an API call, ensure it's handled if key is invalid
                try:
                    models = get_openai_models(initial_api_key)
                    if models:
                        self.model = models[0] # Or a preferred default like "gpt-3.5-turbo"
                        print(f"Default OpenAI model set to: {self.model}")
                    else:
                        print(f"Warning: Could not fetch OpenAI models. Using fallback 'gpt-3.5-turbo'.")
                        self.model = "gpt-3.5-turbo" # Fallback
                except Exception as e:
                    print(f"Error fetching OpenAI models for default: {e}. Using fallback 'gpt-3.5-turbo'.")
                    self.model = "gpt-3.5-turbo"
            elif provider_lower == "gemini":
                try:
                    # Configure genai temporarily for model listing if needed, or rely on a default
                    # genai.configure(api_key=initial_api_key) # Might be needed if get_gemini_models doesn't configure
                    models = get_gemini_models(initial_api_key) # Pass key to get_gemini_models
                    if models:
                        # Prefer "gemini-1.5-flash-latest" or "gemini-pro" if available
                        preferred_models = ["gemini-1.5-flash-latest", "gemini-pro", "gemini-1.0-pro"]
                        for pref_model in preferred_models:
                            if any(m.endswith(pref_model) for m in models): # Gemini models often have 'models/' prefix
                                self.model = [m for m in models if m.endswith(pref_model)][0]
                                break
                        if not self.model and models: # If preferred not found, take first available
                           self.model = models[0]
                        print(f"Default Gemini model set to: {self.model}")
                    else:
                        print(f"Warning: Could not fetch Gemini models. Using fallback 'gemini-pro'.")
                        self.model = "gemini-pro" # Fallback
                except Exception as e:
                    print(f"Error fetching Gemini models for default: {e}. Using fallback 'gemini-pro'.")
                    self.model = "gemini-pro"
            else:
                print(f"Warning: Unknown provider '{self.provider}' for setting default model.")


        # Initialize the client with the first key
        try:
            if provider_lower == "openai":
                self.client = OpenAI(api_key=initial_api_key)
                print(f"OpenAI client initialized with model {self.model} and key ending ...{initial_api_key[-4:]}")
            elif provider_lower == "gemini":
                # For Gemini, client is typically the model instance.
                # Configuration is global or per-model.
                genai.configure(api_key=initial_api_key)
                self.client = genai.GenerativeModel(self.model) # Store model instance as client
                print(f"Gemini client (GenerativeModel) initialized with model {self.model} and key ending ...{initial_api_key[-4:]}")
            else:
                print(f"Error: Unknown provider '{self.provider}'. Client not initialized.")
                self.client = None
        except Exception as e:
            print(f"Error initializing LLM client for {self.provider} with key ...{initial_api_key[-4:]}: {e}")
            self.client = None # Ensure client is None if initialization fails
            # Attempt to cycle to the next key if this one failed at initialization
            # This is complex as _initialize_client is called once.
            # Better to let subsequent calls fail and retry with next key.

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
        self._log_request_data("llm_json_request", {"purpose": purpose, "request_messages": messages})

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
                # Log this specific failure before returning
                error_payload = {"error": f"Internal error: Failed to retrieve API key for {self.provider}."}
                self._log_request_data("llm_json_attempt_failure", {"purpose": purpose, "details": error_payload, "attempt": attempt + 1})
                return error_payload

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
                    content = response.choices[0].message.content.strip() # Restored content assignment
                    if content:
                        self._log_request_data("llm_json_response_raw", {"purpose": purpose, "key_info": api_key[-4:], "raw_response": content, "attempt": attempt + 1})

                elif self.provider == 'gemini':
                    # Re-configure genai globally for this attempt
                    genai.configure(api_key=api_key)
                    
                    # Re-fetch the model instance using the explicit model_name parameter
                    current_client = genai.GenerativeModel(
                        model_name=self.model
                    ) # Explicitly use model_name

                    # Adapt messages
                    system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
                    history_openai_format = [msg for msg in messages if msg['role'] != 'system']
                    user_message_content = history_openai_format.pop()['content'] if history_openai_format else ""

                    temp_history_manager = HistoryManager()
                    gemini_formatted_history = temp_history_manager.adapt_history_for_gemini(history_openai_format)

                    # Combine prompts
                    prompt_parts = [
                        f"System Instructions:\\n{' '.join(system_prompts)}\\n\\nUser Request:\\n{user_message_content}\\n\\n"
                        f"IMPORTANT: Respond ONLY with a valid JSON object based on the request. Do not include any other text or explanations."
                    ]

                    generation_config = genai.types.GenerationConfig(
                        response_mime_type="application/json",
                        max_output_tokens=400,
                        temperature=0.1
                    )

                    # Use the potentially reconfigured client instance
                    chat_session = current_client.start_chat(history=gemini_formatted_history)
                    response = chat_session.send_message(
                        prompt_parts,
                        generation_config=generation_config
                    )
                    content = response.text.strip()
                    if content:
                        self._log_request_data("llm_json_response_raw", {"purpose": purpose, "key_info": api_key[-4:], "raw_response": content, "attempt": attempt + 1})
                else: # This else corresponds to the if/elif for provider
                    print(f"Unsupported provider '{self.provider}' for JSON generation.")
                    # This error should not be retried with other keys, as it's a config issue.
                    error_payload = {"error": f"Unsupported provider '{self.provider}'"}
                    self._log_request_data("llm_json_attempt_failure", {"purpose": purpose, "details": error_payload, "attempt": attempt + 1})
                    return error_payload

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
                    self._log_request_data("llm_json_response_parsed", {"purpose": purpose, "key_info": api_key[-4:], "parsed_response": parsed_json, "attempt": attempt + 1})
                    return parsed_json # Success! Return the parsed JSON
                except json.JSONDecodeError as e_json_parse: # Specific variable for this exception
                    print(f"Error decoding JSON response for {purpose} on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_json_parse}\nRaw content: '{content}'")
                    last_exception_details = {"error": f"Failed to decode JSON. Content: '{content}'", "key_info": api_key[-4:]}
                    self._log_request_data("llm_json_attempt_failure_json_decode", {"purpose": purpose, "key_info": api_key[-4:], "error": str(e_json_parse), "raw_content_on_error": content, "attempt": attempt + 1})
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
                self._log_request_data("llm_json_attempt_failure_api", {"purpose": purpose, "key_info": api_key[-4:], "error_type": error_type, "error_details": str(e_api), "attempt": attempt + 1})
                if attempt < num_available_keys - 1:
                    print("Retrying with next key...")
                    continue # Go to the next iteration of the loop (next key for API call)
                else: # This was the last key for an API error
                    print(f"All {num_available_keys} API key(s) failed for {purpose}. Last API error: {error_type}")
                    return last_exception_details
            except json.JSONDecodeError as e_json_outer: # Handles JSONDecodeError from empty content before parsing
                print(f"JSON decoding error (likely empty content from API) on attempt {attempt + 1} for {purpose} with key ...{api_key[-4:]}: {e_json_outer}\nRaw content was: '{content}'")
                last_exception_details = {"error": f"Failed to decode JSON (empty content from API?). Content: '{content}'", "key_info": api_key[-4:]}
                self._log_request_data("llm_json_attempt_failure_json_decode_outer", {"purpose": purpose, "key_info": api_key[-4:], "error": str(e_json_outer), "raw_content_on_error": content, "attempt": attempt + 1})
                if attempt < num_available_keys - 1:
                    print("Retrying with next key due to empty/unanalyzable API response.")
                    continue
                else: # Last attempt also resulted in content that couldn't be parsed (or was empty)
                    return last_exception_details
            except Exception as e_general:
                logging.exception(f"Unexpected error calling LLM API ({purpose}) on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_general}")
                error_payload = {"error": f"Unexpected API error: {e_general}", "key_info": api_key[-4:]}
                self._log_request_data("llm_json_attempt_failure_unexpected", {"purpose": purpose, "key_info": api_key[-4:], "error_details": str(e_general), "attempt": attempt + 1})
                return error_payload

        # If loop finishes, it means all keys failed with retriable errors (API or JSON parsing related)
        print(f"All {num_available_keys} API key(s) exhausted for {purpose}.")
        final_error_payload = last_exception_details if last_exception_details else {"error": f"All API keys failed for {self.provider} during {purpose} after exhausting all attempts."}
        self._log_request_data("llm_json_final_failure_all_keys", {"purpose": purpose, "details": final_error_payload})
        return final_error_payload

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

        system_prompt = "\\n".join(system_prompt_lines)

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
            f"Respond ONLY with a single, valid JSON object containing these keys and their determined values. Your entire response must be the JSON object, starting with {{ and ending with }}.\\n"
            f"Example JSON format (values depend on context): {example_json_str}"
        )

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
        final_messages_for_llm = []
        # Check if the personality_prompt is already the first system message in 'messages'
        # to avoid duplication.
        if not (messages and messages[0].get("role") == "system" and messages[0].get("content") == personality_prompt):
            final_messages_for_llm.append({"role": "system", "content": personality_prompt})
        
        final_messages_for_llm.extend(messages)
        self._log_request_data("llm_final_request", {"request_messages": final_messages_for_llm})

        if self.provider not in self.api_keys or not self.api_keys[self.provider]:
            model_name_for_log = self.model if self.model else "N/A"
            error_msg = f"No API keys loaded for provider '{self.provider}' (model: {model_name_for_log}). Cannot generate final response."
            print(f"Error: {error_msg}")
            self._log_request_data("llm_final_failure_no_keys", {"details": error_msg})
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
                self._log_request_data("llm_final_failure_key_retrieval", {"details": last_error_message, "attempt": attempt + 1})
                break # Stop if key retrieval fails

            print(f"Attempt {attempt + 1}/{num_available_keys} for Final Response using key ending ...{api_key[-4:]}")

            try:
                response_text = None 
                if self.provider == 'openai':
                    response_text = await self._generate_openai_response(final_messages_for_llm, api_key)
                elif self.provider == 'gemini':
                    response_text = await self._generate_gemini_response(final_messages_for_llm, api_key)
                else:
                    unsupported_provider_msg = f"Error: Unsupported provider '{self.provider}' for final response generation."
                    print(unsupported_provider_msg)
                    self._log_request_data("llm_final_failure_unsupported_provider", {"details": unsupported_provider_msg, "attempt": attempt + 1})
                    return unsupported_provider_msg 

                self._log_request_data("llm_final_response_success", {"key_info": api_key[-4:], "response_text": response_text, "attempt": attempt + 1})
                return response_text # Success

            except (OpenAIRateLimitError, google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied) as e:
                error_type = "Rate limit" if isinstance(e, (OpenAIRateLimitError, google_exceptions.ResourceExhausted)) else "Permission/API Key"
                current_error_msg = f"{error_type} error on attempt {attempt + 1} with key ...{api_key[-4:]}: {e}"
                print(current_error_msg)
                last_error_message = f"Error: {current_error_msg}" # Store as the latest error encountered
                self._log_request_data("llm_final_attempt_failure_api", {"key_info": api_key[-4:], "error_type": error_type, "error_details": str(e), "attempt": attempt + 1})
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
                self._log_request_data("llm_final_attempt_failure_unexpected", {"key_info": api_key[-4:], "error_details": str(e), "attempt": attempt + 1})
                return f"Error: {unexpected_error_msg}" # Stop on unexpected errors

        # If loop completes, all keys were tried and failed with retriable errors
        self._log_request_data("llm_final_failure_all_keys", {"details": last_error_message})
        return last_error_message

    async def _generate_openai_response(self, messages: List[Dict], api_key: str) -> str:
        """Handles the actual OpenAI API call for message generation, using the provided key."""
        # Note: No try/except here, handled by the calling loop
        current_client = OpenAI(api_key=api_key) # Initialize with the specific key for this attempt
        response = await current_client.chat.completions.create( # Use await for async
                messages=messages,
                model=self.model,
                max_tokens=1000,
                temperature=random.uniform(0.4, 1.0), 
            )
        message = response.choices[0].message.content.strip()
        print(f"Final OpenAI Response received (using key ...{api_key[-4:]}).")
        return message


    async def _generate_gemini_response(self, messages: List[Dict], api_key: str) -> str:
        """Handles the actual Gemini API call for message generation, using the provided key."""
        genai.configure(api_key=api_key)

        system_instruction_text = None
        history_contents = []

        if messages and messages[0]["role"] == "system":
            system_instruction_text = messages[0]["content"]
            processed_messages = messages[1:]
        else:
            processed_messages = messages

        for msg in processed_messages:
            role = "user" if msg["role"] == "user" else "model"
            content_text = msg.get("content", "")
            if not isinstance(content_text, str):
                content_text = str(content_text)
            history_contents.append({"role": role, "parts": [{"text": content_text}]})

        try:
            model_instance = genai.GenerativeModel(
                model_name=self.model, # Use model_name parameter
                system_instruction=system_instruction_text
            )
            
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=1000,
                temperature=random.uniform(0.4, 1.0) 
            )

            response = await model_instance.generate_content_async(
                contents=history_contents,
                generation_config=generation_config
            )
            

            if not response.candidates:
                block_reason_info = ""
                if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason'):
                    block_reason_info = f" Prompt block reason: {response.prompt_feedback.block_reason}."
                return f"Error: No candidates returned from Gemini.{block_reason_info} (key ...{api_key[-4:]})"

            candidate = response.candidates[0]

            # FinishReason enums (integer values):
            # UNSPECIFIED = 0, STOP = 1, MAX_TOKENS = 2, SAFETY = 3, RECITATION = 4, OTHER = 5
            finish_reason = candidate.finish_reason

            if finish_reason == 1:  # STOP
                if candidate.content and candidate.content.parts:
                    message_text = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
                    print(f"Final Gemini Response received (key ...{api_key[-4:]}, finish_reason: STOP).")
                    return message_text.strip()
                else:
                    print(f"Warning: Gemini response finished with STOP but no content parts found (key ...{api_key[-4:]}).")
                    return "Error: Gemini response indicates successful completion (STOP) but no content was found."
            elif finish_reason == 2:  # MAX_TOKENS
                partial_text = ""
                if candidate.content and candidate.content.parts:
                    partial_text = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text')).strip()
                
                error_message = f"Error: Response truncated by Gemini due to maximum token limit (MAX_TOKENS). (key ...{api_key[-4:]})"
                if partial_text:
                    print(f"Warning: {error_message} Partial text available.")
                    return f"{error_message} Partial response: \"{partial_text}\""
                else:
                    print(f"Warning: {error_message} No partial text available.")
                    return error_message
            elif finish_reason == 3:  # SAFETY
                safety_ratings_str = str(getattr(candidate, 'safety_ratings', 'N/A'))
                error_message = f"Error: Gemini response blocked due to safety concerns (SAFETY). Ratings: {safety_ratings_str}. (key ...{api_key[-4:]})"
                print(f"Warning: {error_message}")
                return error_message
            elif finish_reason == 4:  # RECITATION
                error_message = f"Error: Gemini response blocked due to recitation policy (RECITATION). (key ...{api_key[-4:]})"
                print(f"Warning: {error_message}")
                return error_message
            else:  # UNSPECIFIED (0), OTHER (5), or any unknown
                if candidate.content and candidate.content.parts:
                    try:
                        message_text = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))
                        print(f"Final Gemini Response received (key ...{api_key[-4:]}, finish_reason: {finish_reason}). Text extracted.")
                        return message_text.strip()
                    except Exception as e_text_extract:
                        error_message = f"Error: Could not extract text from Gemini. Finish reason: {finish_reason}. Details: {e_text_extract}. (key ...{api_key[-4:]})"
                        print(f"Warning: {error_message}")
                        return error_message
                else:
                    error_message = f"Error: Gemini response generation failed or was incomplete. Finish reason: {finish_reason}, no content parts. (key ...{api_key[-4:]})"
                    print(f"Warning: {error_message}")
                    return error_message

        except google_exceptions.GoogleAPIError as e_google:
            # Re-raise Google API errors to be handled by the outer loop's specific exception handlers
            print(f"ERROR: GoogleAPIError in _generate_gemini_response (key ...{api_key[-4:]}): {type(e_google).__name__} - {e_google}")
            raise
        except Exception as e_general:
            err_msg = f"Error during Gemini API call or response processing (key ...{api_key[-4:]}): {type(e_general).__name__} - {e_general}"
            print(f"ERROR: {err_msg}")
            return err_msg
