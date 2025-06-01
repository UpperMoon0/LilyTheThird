import random
import json
from itertools import cycle
from pathlib import Path
import logging
import os 
import datetime 
from tools.tools import ToolDefinition # get_tool_list_for_prompt, get_tool_names removed
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from openai import OpenAI, RateLimitError as OpenAIRateLimitError
from typing import List, Dict, Optional, Any
import shutil

# Added for Gemini Function Calling
from google.generativeai.types import FunctionDeclaration, Tool as GeminiTool
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
        self.model_list_cache: Dict[str, List[str]] = {} # Cache for model lists

        self._setup_request_logger() # Added logger setup
        self._load_api_keys_from_json()
        # self._initialize_client() # Deferred to ensure_initialized

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
                    models = []
                    if "openai" in self.model_list_cache:
                        models = self.model_list_cache["openai"]
                        # print("Using cached OpenAI models.") # Optional: for debugging
                    else:
                        fetched_models = get_openai_models(initial_api_key)
                        if fetched_models: # Cache only if successful and models list is not empty
                            self.model_list_cache["openai"] = fetched_models
                            models = fetched_models
                        elif "openai" in self.model_list_cache: # Use stale cache if fetch fails but cache exists
                            models = self.model_list_cache["openai"]


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
                    models = []
                    if "gemini" in self.model_list_cache:
                        models = self.model_list_cache["gemini"]
                        # print("Using cached Gemini models.") # Optional: for debugging
                    else:
                        fetched_models = get_gemini_models(initial_api_key) # Pass key to get_gemini_models
                        if fetched_models: # Cache only if successful and models list is not empty
                            self.model_list_cache["gemini"] = fetched_models
                            models = fetched_models
                        elif "gemini" in self.model_list_cache: # Use stale cache if fetch fails but cache exists
                            models = self.model_list_cache["gemini"]
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
                
                # Configure safety settings to disable all content filtering (uncensored mode)
                safety_settings = {
                    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                }
                
                self.client = genai.GenerativeModel(
                    self.model,
                    safety_settings=safety_settings
                ) # Store model instance as client with disabled safety settings
                print(f"Gemini client (GenerativeModel) initialized with model {self.model}, UNCENSORED mode (all safety filters disabled), and key ending ...{initial_api_key[-4:]}")
            else:
                print(f"Error: Unknown provider '{self.provider}'. Client not initialized.")
                self.client = None
        except Exception as e:
            print(f"Error initializing LLM client for {self.provider} with key ...{initial_api_key[-4:]}: {e}")
            self.client = None # Ensure client is None if initialization fails
            # Attempt to cycle to the next key if this one failed at initialization
            # This is complex as _initialize_client is called once.
            # Better to let subsequent calls fail and retry with next key.

    def ensure_initialized(self):
        """Ensures the client is initialized. Calls _initialize_client if not already done."""
        if self.client is None:
            self._initialize_client()

    def get_model_name(self) -> str:
        """Returns the name of the model being used."""
        self.ensure_initialized()
        if self.model:
            return self.model
        return "Error: Model not set (client initialization failed or pending)"

    # --- Core LLM Call for JSON ---
    async def _call_llm_for_json(self, messages: List[Dict], purpose: str) -> Optional[Dict]:
        """
        Internal helper to call the LLM and expect a JSON response, with retries for rate limits and JSON errors.
        This method is primarily used by OpenAI or when Gemini is not using its native function calling.

        Args:
            messages: The list of messages for the prompt.
            purpose: A string describing the purpose (e.g., "Tool Selection", "Argument Generation") for logging.

        Returns:
            A dictionary parsed from the JSON response, or an error dictionary if the single attempt fails.
        """
        self.ensure_initialized()
        if self.client is None:
            error_msg = f"LLMClient for {self.provider} not initialized. Cannot make {purpose} call."
            print(f"Error in _call_llm_for_json: {error_msg}")
            self._log_request_data("llm_json_request_failure_not_initialized", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

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
                    
                    # Configure safety settings to disable all content filtering (uncensored mode)
                    safety_settings = {
                        genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                        genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    }
                    
                    # Re-fetch the model instance using the explicit model_name parameter
                    current_client = genai.GenerativeModel(
                        model_name=self.model,
                        safety_settings=safety_settings
                    ) # Explicitly use model_name with disabled safety settings

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

    async def _get_gemini_function_call(
        self,
        messages: List[Dict],
        gemini_tool_config: Optional[GeminiTool],
        purpose: str
    ) -> Optional[Dict[str, Any]]:
        """
        Calls Gemini with a tool configuration and attempts to get a function call.
        Handles retries with different API keys for rate limits and other specified errors.
        """
        self.ensure_initialized()
        if self.client is None: # Gemini client is the model instance after genai.configure
            error_msg = f"LLMClient for {self.provider} (Gemini) not initialized. Cannot make {purpose} call."
            print(f"Error in _get_gemini_function_call: {error_msg}")
            self._log_request_data("gemini_function_call_request_failure_not_initialized", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        self._log_request_data("gemini_function_call_request", {"purpose": purpose, "request_messages_count": len(messages), "tool_config_present": gemini_tool_config is not None})
        print(f"--- Attempting Gemini {purpose} with function calling ---")

        if self.provider != 'gemini':
            error_msg = "Attempted to call _get_gemini_function_call with non-Gemini provider."
            print(f"Error: {error_msg}")
            self._log_request_data("gemini_function_call_error", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        if "gemini" not in self.api_keys or not self.api_keys["gemini"]:
            model_name_for_log = self.model if self.model else "N/A"
            error_msg = f"No API keys loaded for provider 'gemini' (model: {model_name_for_log}). Cannot make {purpose} call."
            print(f"Error: {error_msg}")
            self._log_request_data("gemini_function_call_error", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        num_available_keys = len(self.api_keys.get("gemini", []))
        last_exception_details = None

        for attempt in range(num_available_keys):
            api_key = self._get_next_api_key() # This should fetch a Gemini key
            if not api_key:
                error_payload = {"error": "Internal error: Failed to retrieve API key for Gemini."}
                self._log_request_data("gemini_function_call_attempt_failure", {"purpose": purpose, "details": error_payload, "attempt": attempt + 1})
                return error_payload

            print(f"Attempt {attempt + 1}/{num_available_keys} for Gemini {purpose} using key ending ...{api_key[-4:]}")

            try:
                # Re-configure genai globally for this attempt
                genai.configure(api_key=api_key)

                system_instruction_text = None
                conversation_messages = []

                if messages and messages[0]["role"] == "system":
                    system_instruction_text = messages[0]["content"]
                    conversation_messages = messages[1:]
                else:
                    # This case should ideally not happen if get_next_action always prepends a system prompt
                    print("Warning: No system prompt found at the start of messages for _get_gemini_function_call.")
                    conversation_messages = messages
                
                # Configure safety settings to disable all content filtering (uncensored mode)
                safety_settings = {
                    genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                    genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                }
                
                # Initialize the model instance with system_instruction and disabled safety settings
                current_client = genai.GenerativeModel(
                    model_name=self.model,
                    system_instruction=system_instruction_text,
                    safety_settings=safety_settings
                )

                # Convert remaining OpenAI message format to Gemini's content format
                gemini_formatted_contents = []
                for msg in conversation_messages:
                    role = "user" if msg["role"] == "user" else "model" # Gemini uses 'user' and 'model'
                    # Ensure content is a string, as Gemini parts expect text.
                    content_text = msg.get("content", "")
                    if not isinstance(content_text, str): # Handle cases where content might be non-string (e.g. from tool_results)
                        content_text = str(content_text)
                    gemini_formatted_contents.append({"role": role, "parts": [genai.protos.Part(text=content_text)]})

                generation_config = genai.types.GenerationConfig(
                    # response_mime_type="application/json", # Not needed when using 'tools' for function calling
                    max_output_tokens=1024, # Increased for potentially complex tool args
                    temperature=0.1 # Keep low for predictable tool use
                )
                
                print(f"Sending to Gemini with tools: {gemini_tool_config is not None}. System instruction: {'Present' if system_instruction_text else 'Absent'}")
                response = current_client.generate_content(
                    contents=gemini_formatted_contents, # Use the adapted conversation messages
                    tools=[gemini_tool_config] if gemini_tool_config else None,
                    generation_config=generation_config
                )
                if not response.candidates or not response.candidates[0].content:
                    print(f"Warning: Received empty or incomplete response from Gemini for {purpose} with key ...{api_key[-4:]}.")
                    # Consider this a potentially retriable issue.
                    raise google_exceptions.GoogleAPIError("Empty or incomplete response from Gemini.")

                # Check if there are any parts at all - if not, it might still be a valid empty response
                if not response.candidates[0].content.parts:
                    print(f"Warning: Gemini response has no parts for {purpose} with key ...{api_key[-4:]}.")
                    # Log the response for debugging
                    self._log_request_data("gemini_function_call_debug_no_parts", {
                        "purpose": purpose, "key_info": api_key[-4:], 
                        "response_structure": str(response), "attempt": attempt + 1
                    })
                    raise google_exceptions.GoogleAPIError("Gemini response has no content parts.")


                # Check for function call in response
                called_function_name = None
                called_function_args = {}
                text_response_parts = []

                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        called_function_name = part.function_call.name
                        called_function_args = dict(part.function_call.args)
                        self._log_request_data("gemini_function_call_success", {
                            "purpose": purpose, "key_info": api_key[-4:], 
                            "function_name": called_function_name, 
                            "function_args": called_function_args, "attempt": attempt + 1
                        })
                        print(f"Gemini called function: {called_function_name} with args: {called_function_args}")
                        return {"name": called_function_name, "args": called_function_args}
                    if hasattr(part, 'text'):
                        text_response_parts.append(part.text)
                
                # If no function call was made, but there's text
                if text_response_parts:
                    full_text_response = "".join(text_response_parts)
                    self._log_request_data("gemini_function_call_no_call_text_response", {
                        "purpose": purpose, "key_info": api_key[-4:], 
                        "text_response": full_text_response, "attempt": attempt + 1
                    })
                    print(f"Gemini responded with text (no function call): {full_text_response[:100]}...")
                    return {"text_response": full_text_response} # LLM decided to respond with text

                # If no function call and no text, it's an unusual empty response.
                print(f"Gemini response had no function call and no text for {purpose} on attempt {attempt + 1}.")
                # This could be treated as an error to retry.
                raise google_exceptions.GoogleAPIError("Gemini response had no function call and no text.")


            except (google_exceptions.ResourceExhausted, google_exceptions.PermissionDenied, google_exceptions.Aborted, google_exceptions.DeadlineExceeded, google_exceptions.ServiceUnavailable, google_exceptions.InternalServerError, google_exceptions.Unknown, google_exceptions.GoogleAPIError) as e_api:
                error_type = "Rate limit/Resource" if isinstance(e_api, (google_exceptions.ResourceExhausted, google_exceptions.ServiceUnavailable)) else \
                             "Permission/API Key" if isinstance(e_api, google_exceptions.PermissionDenied) else \
                             "API Error" # General catch-all for other GoogleAPIError types
                
                print(f"Gemini {error_type} on attempt {attempt + 1}/{num_available_keys} for {purpose} with key ...{api_key[-4:]}: {e_api}")
                last_exception_details = {"error": f"Gemini {error_type}: {e_api}", "key_info": api_key[-4:]}
                self._log_request_data("gemini_function_call_attempt_failure_api", {"purpose": purpose, "key_info": api_key[-4:], "error_type": error_type, "error_details": str(e_api), "attempt": attempt + 1})
                
                if attempt < num_available_keys - 1:
                    print("Retrying with next key...")
                    continue
                else:
                    print(f"All {num_available_keys} Gemini API key(s) failed for {purpose}. Last API error: {error_type}")
                    return last_exception_details
            except Exception as e_general:
                logging.exception(f"Unexpected error calling Gemini API for {purpose} on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_general}")
                error_payload = {"error": f"Unexpected API error: {e_general}", "key_info": api_key[-4:]}
                self._log_request_data("gemini_function_call_attempt_failure_unexpected", {"purpose": purpose, "key_info": api_key[-4:], "error_details": str(e_general), "attempt": attempt + 1})
                # For a truly unexpected error, we might not want to retry with other keys,
                # as it could be a code issue rather than a key issue.
                return error_payload # Return immediately for unexpected errors.

        # If loop finishes, it means all keys failed with retriable API errors
        print(f"All {num_available_keys} Gemini API key(s) exhausted for {purpose}.")
        final_error_payload = last_exception_details if last_exception_details else {"error": f"All API keys failed for Gemini during {purpose} after exhausting all attempts."}
        self._log_request_data("gemini_function_call_final_failure_all_keys", {"purpose": purpose, "details": final_error_payload})
        return final_error_payload

    async def _call_openai_with_tools(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]], # OpenAI tool format
        tool_choice: Optional[Any], # OpenAI tool_choice format
        purpose: str
    ) -> Any: # Returns the OpenAI SDK response object or an error dict
        """
        Calls OpenAI with a tool configuration and attempts to get a function call or text response.
        Handles retries with different API keys for rate limits and other specified errors.
        """
        self.ensure_initialized()
        if self.client is None: # OpenAI client
            error_msg = f"LLMClient for {self.provider} (OpenAI) not initialized. Cannot make {purpose} call."
            print(f"Error in _call_openai_with_tools: {error_msg}")
            self._log_request_data("openai_tool_call_request_failure_not_initialized", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        self._log_request_data("openai_tool_call_request", {"purpose": purpose, "request_messages_count": len(messages), "tools_present": tools is not None})
        print(f"--- Attempting OpenAI {purpose} with tools ---")

        if self.provider != 'openai':
            error_msg = "Attempted to call _call_openai_with_tools with non-OpenAI provider."
            print(f"Error: {error_msg}")
            self._log_request_data("openai_tool_call_error_provider", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        if "openai" not in self.api_keys or not self.api_keys["openai"]:
            model_name_for_log = self.model if self.model else "N/A"
            error_msg = f"No API keys loaded for provider 'openai' (model: {model_name_for_log}). Cannot make {purpose} call."
            print(f"Error: {error_msg}")
            self._log_request_data("openai_tool_call_error_no_keys", {"purpose": purpose, "error": error_msg})
            return {"error": error_msg}

        num_available_keys = len(self.api_keys.get("openai", []))
        last_exception_details = None

        for attempt in range(num_available_keys):
            api_key = self._get_next_api_key() # This should fetch an OpenAI key
            if not api_key:
                error_payload = {"error": "Internal error: Failed to retrieve API key for OpenAI."}
                self._log_request_data("openai_tool_call_attempt_failure_key_retrieval", {"purpose": purpose, "details": error_payload, "attempt": attempt + 1})
                return error_payload

            print(f"Attempt {attempt + 1}/{num_available_keys} for OpenAI {purpose} using key ending ...{api_key[-4:]}")

            try:
                current_client = OpenAI(api_key=api_key)
                response = await current_client.chat.completions.create( # Use await for async
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice=tool_choice if tool_choice else "auto", # "auto" is default, can be more specific
                    temperature=0.1, # Low temperature for predictable tool use
                    max_tokens=1024  # Sufficient for tool arguments and some text
                )
                self._log_request_data("openai_tool_call_api_success_raw", {"purpose": purpose, "key_info": api_key[-4:], "attempt": attempt + 1})
                return response # Return the full response object

            except OpenAIRateLimitError as e_rate_limit:
                print(f"OpenAI Rate limit error on attempt {attempt + 1}/{num_available_keys} for {purpose} with key ...{api_key[-4:]}: {e_rate_limit}")
                last_exception_details = {"error": f"OpenAI Rate limit error: {e_rate_limit}", "key_info": api_key[-4:]}
                self._log_request_data("openai_tool_call_attempt_failure_rate_limit", {"purpose": purpose, "key_info": api_key[-4:], "error_details": str(e_rate_limit), "attempt": attempt + 1})
                if attempt < num_available_keys - 1:
                    print("Retrying with next key...")
                    continue
                else:
                    print(f"All {num_available_keys} OpenAI API key(s) failed for {purpose} due to rate limits.")
                    return last_exception_details
            except Exception as e_general: # Catch other OpenAI client errors or general errors
                logging.exception(f"Unexpected error calling OpenAI API for {purpose} on attempt {attempt + 1} with key ...{api_key[-4:]}: {e_general}")
                error_payload = {"error": f"Unexpected API error: {e_general}", "key_info": api_key[-4:]}
                self._log_request_data("openai_tool_call_attempt_failure_unexpected", {"purpose": purpose, "key_info": api_key[-4:], "error_details": str(e_general), "attempt": attempt + 1})
                # For truly unexpected errors, decide if retry is appropriate or return immediately.
                # For now, let's assume most other errors are not key-specific and return.
                return error_payload

        # If loop finishes, it means all keys failed with retriable errors (e.g. rate limits)
        print(f"All {num_available_keys} OpenAI API key(s) exhausted for {purpose}.")
        final_error_payload = last_exception_details if last_exception_details else {"error": f"All API keys failed for OpenAI during {purpose} after exhausting all attempts."}
        self._log_request_data("openai_tool_call_final_failure_all_keys", {"purpose": purpose, "details": final_error_payload})
        return final_error_payload

    async def get_next_action(
        self,
        messages: List[Dict[str, Any]],
        allowed_tools: Optional[List[Dict[str, Any]]] = None,
        context_type: Optional[str] = None,
        force_tool_options: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        OPTIMIZED action decision with smart early returns and reduced verbosity.
        """
        # Quick early return for no tools
        if not allowed_tools:
            return {"action_type": "text_response", "text": ""}

        # Efficiently determine choosable tools
        if force_tool_options:
            available_names = {tool_data["name"] for tool_data in allowed_tools}
            valid_forced_names = [name for name in force_tool_options if name in available_names]
            
            if not valid_forced_names:
                return {"action_type": "text_response", "text": ""}
            
            final_choosable_tool_definitions = [
                tool_data for tool_data in allowed_tools if tool_data["name"] in valid_forced_names
            ]
        else:
            final_choosable_tool_definitions = allowed_tools
        
        if not final_choosable_tool_definitions:
            return {"action_type": "text_response", "text": ""}

        choosable_names_for_prompt = [td["name"] for td in final_choosable_tool_definitions]

        # --- Provider-Specific Logic for Tool Choice & Argument Generation ---

        if self.provider == 'gemini':
            gemini_function_declarations = []
            if final_choosable_tool_definitions:
                for tool_data in final_choosable_tool_definitions:
                    name = tool_data["name"]
                    description = tool_data["description"]
                    # parameters_schema is already a JSON schema dict
                    parameters_schema = tool_data.get("parameters", {"type": "object", "properties": {}}) # Default if missing, though prompt implies it's there

                    # Clean schema for Gemini (remove 'title' at root and in properties)
                    clean_schema = {k: v for k, v in parameters_schema.items() if k != 'title'}
                    if 'properties' in clean_schema and isinstance(clean_schema['properties'], dict):
                        cleaned_props = {}
                        for prop_name, prop_schema in clean_schema['properties'].items():
                            if isinstance(prop_schema, dict):
                                cleaned_props[prop_name] = {k: v for k, v in prop_schema.items() if k != 'title'}
                            else:
                                cleaned_props[prop_name] = prop_schema # Preserve non-dict property schemas
                        clean_schema['properties'] = cleaned_props
                    
                    gemini_function_declarations.append(
                        FunctionDeclaration(
                            name=name,
                            description=description,
                            parameters=clean_schema if clean_schema else {"type": "object", "properties": {}} # Ensure valid schema
                        )
                    )

            gemini_tool_config = GeminiTool(function_declarations=gemini_function_declarations) if gemini_function_declarations else None
            
            system_prompt_lines = [
                "You are an AI assistant. Analyze the conversation and decide if using one of your available functions (tools) is the best way to respond.",
                "If a function is appropriate, call it with the necessary arguments. Otherwise, respond directly to the user."
            ]
            if force_tool_options and choosable_names_for_prompt: # Only add if there are tools to suggest
                system_prompt_lines.append(f"You are strongly encouraged to use one of the following tools if relevant: {', '.join(choosable_names_for_prompt)}.")
            
            if context_type == 'chatbox' and force_tool_options and 'save_memory' in force_tool_options:
                 system_prompt_lines.append(
                    "IMPORTANT (ChatBox Context - Final Save Check): Review the entire conversation. If you learned any new, specific, and potentially useful facts (e.g., user preferences, project details, key information) that haven't been saved yet, you SHOULD use the 'save_memory' tool now."
                )

            system_prompt = "\\n".join(system_prompt_lines)
            
            request_messages = [{"role": "system", "content": system_prompt}] + messages

            gemini_response = await self._get_gemini_function_call(
                messages=request_messages,
                gemini_tool_config=gemini_tool_config,
                purpose="Gemini Action Decision"
            )

            if gemini_response and "error" not in gemini_response:
                if "name" in gemini_response:
                    return {
                        "action_type": "tool_call",
                        "tool_name": gemini_response["name"],
                        "tool_args": gemini_response["args"]
                    }
                elif "text_response" in gemini_response:
                    return {"action_type": "text_response", "text": gemini_response["text_response"]}
                else:
                    return {"action_type": "error", "error": "Invalid response from _get_gemini_function_call"}
            else:
                error_detail = gemini_response.get("error", "Unknown error from Gemini function call") if isinstance(gemini_response, dict) else "Unknown error structure from Gemini"
                return {"action_type": "error", "error": error_detail}

        elif self.provider == 'openai':
            openai_tools_definitions = []
            if final_choosable_tool_definitions:
                for tool_data in final_choosable_tool_definitions:
                    name = tool_data["name"]
                    description = tool_data["description"]
                    # parameters_schema is already a JSON schema dict
                    parameters_schema = tool_data.get("parameters", {"type": "object", "properties": {}})

                    # OpenAI schema doesn't like 'title' at the top level of parameters,
                    # but it's fine within properties. Remove if present at top.
                    # Create a copy to modify
                    final_params_schema = dict(parameters_schema)
                    if 'title' in final_params_schema:
                        del final_params_schema['title']
                    
                    openai_tools_definitions.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": description,
                            "parameters": final_params_schema if final_params_schema else {"type": "object", "properties": {}},
                        }
                    })
            
            system_prompt_lines = [
                "You are an AI assistant. Analyze the conversation and decide if using one of your available functions (tools) is the best way to respond.",
                "If a function is appropriate, call it with the necessary arguments. Otherwise, respond directly to the user."
            ]
            if force_tool_options and choosable_names_for_prompt: # Only add if there are tools to suggest
                system_prompt_lines.append(f"You are strongly encouraged to use one of the following tools if relevant: {', '.join(choosable_names_for_prompt)}.")
            
            if context_type == 'chatbox' and force_tool_options and 'save_memory' in force_tool_options:
                 system_prompt_lines.append(
                    "IMPORTANT (ChatBox Context - Final Save Check): Review the entire conversation. If you learned any new, specific, and potentially useful facts (e.g., user preferences, project details, key information) that haven't been saved yet, you SHOULD use the 'save_memory' tool now."
                )
            system_prompt = "\\n".join(system_prompt_lines)
            request_messages = [{"role": "system", "content": system_prompt}] + messages

            tool_choice_openai = "auto"
            # Use choosable_names_for_prompt for checking if the forced tool is valid in the current context
            if force_tool_options and len(force_tool_options) == 1 and force_tool_options[0] in choosable_names_for_prompt:
                tool_choice_openai = {"type": "function", "function": {"name": force_tool_options[0]}}
            elif force_tool_options:
                pass # "auto" with strong prompt is the best for multiple preferred tools


            openai_response_obj = await self._call_openai_with_tools(
                messages=request_messages,
                tools=openai_tools_definitions if openai_tools_definitions else None,
                tool_choice=tool_choice_openai,
                purpose="OpenAI Action Decision"
            )

            if isinstance(openai_response_obj, dict) and "error" in openai_response_obj:
                # Error from _call_openai_with_tools
                return {"action_type": "error", "error": openai_response_obj["error"]}
            
            if openai_response_obj and hasattr(openai_response_obj, 'choices') and openai_response_obj.choices:
                choice = openai_response_obj.choices[0]
                response_message = choice.message

                if response_message.tool_calls:
                    # For now, assume one tool call, as per typical agentic flows.
                    # OpenAI can technically return multiple in one go.
                    tool_call = response_message.tool_calls[0]
                    if tool_call.type == "function":
                        tool_name = tool_call.function.name
                        tool_args_str = tool_call.function.arguments
                        try:
                            tool_args = json.loads(tool_args_str)
                            self._log_request_data("openai_tool_call_success_parsed", {"tool_name": tool_name, "tool_args": tool_args})
                            return {"action_type": "tool_call", "tool_name": tool_name, "tool_args": tool_args}
                        except json.JSONDecodeError as e:
                            error_msg = f"Failed to parse tool arguments JSON from OpenAI: {tool_args_str}. Error: {e}"
                            print(f"Error: {error_msg}")
                            self._log_request_data("openai_tool_call_parse_failure", {"tool_name": tool_name, "raw_args": tool_args_str, "error": str(e)})
                            return {"action_type": "error", "error": error_msg}
                elif response_message.content:
                    self._log_request_data("openai_tool_call_text_response", {"text_response": response_message.content})
                    return {"action_type": "text_response", "text": response_message.content}
                else: # No tool call and no text content, could be due to finish_reason (e.g. length, content_filter)
                    finish_reason = choice.finish_reason
                    error_msg = f"OpenAI responded with no tool_call and no text content. Finish reason: {finish_reason}"
                    print(f"Warning: {error_msg}")
                    self._log_request_data("openai_tool_call_empty_response", {"finish_reason": finish_reason, "response_message": str(response_message)})
                    # Decide if this should be an error or a specific type of text response
                    return {"action_type": "text_response", "text": f"(AI decided no action or text response. Finish reason: {finish_reason})"}

            else: # Should not happen if _call_openai_with_tools returns valid response or error dict
                error_msg = "Invalid or unexpected response from _call_openai_with_tools."
                print(f"Error: {error_msg}")
                self._log_request_data("openai_tool_call_invalid_response_obj", {"response_obj": str(openai_response_obj)})
                return {"action_type": "error", "error": error_msg}

        else:
            return {"action_type": "error", "error": f"Unsupported provider: {self.provider}"}

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
        
        # Generate schema from Pydantic model
        schema = tool.argument_schema.model_json_schema() if tool.argument_schema else {}

        if not schema.get("properties") and not schema.get("required"):
            print(f"Tool '{tool.name}' requires no arguments. Returning empty dict.")
            return {"action_type": "tool_arguments", "arguments": {}}        # --- If arguments are needed, prompt the LLM ---
        required_args = schema.get("required", [])
        properties = schema.get("properties", {})
        arg_descriptions = [f"- '{prop}': {details.get('description', 'No description')}" for prop, details in properties.items() if prop in required_args]
        # Default empty JSON for example
        example_json_str = "{}"

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


    def _should_skip_final_response(self, messages: List[Dict]) -> bool:
        """Smart detection of when final response generation can be skipped."""
        if len(messages) < 2:
            return False
            
        # Check if last message is a recent assistant response
        last_msg = messages[-1]
        if (last_msg.get('role') == 'assistant' and
            len(last_msg.get('content', '')) > 10 and
            not last_msg.get('content', '').startswith('(')):  # Skip internal messages
            return True
            
        # Check if second-to-last is assistant response after tool use
        if len(messages) >= 2:
            second_last = messages[-2]
            if (second_last.get('role') == 'assistant' and
                len(second_last.get('content', '')) > 20):
                return True
                
        return False
    
    def _extract_recent_assistant_response(self, messages: List[Dict]) -> str:
        """Extract the most recent assistant response to reuse."""
        for msg in reversed(messages):
            if (msg.get('role') == 'assistant' and
                len(msg.get('content', '')) > 10 and
                not msg.get('content', '').startswith('(')):
                return msg.get('content', '')
        return ""

    # --- Final Response Generation ---
    async def generate_final_response(self, messages: List[Dict], personality_prompt: str) -> Optional[str]:
        """
        OPTIMIZED final response generation with smart skipping logic.
        """
        # Smart detection: Skip final response if recent assistant message exists
        if self._should_skip_final_response(messages):
            return self._extract_recent_assistant_response(messages)
            
        self.ensure_initialized()
        if self.client is None:
            error_msg = f"LLMClient for {self.provider} not initialized. Cannot generate final response."
            return error_msg

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
            # Configure safety settings to disable all content filtering (uncensored mode)
            safety_settings = {
                genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            }
            
            model_instance = genai.GenerativeModel(
                model_name=self.model, # Use model_name parameter
                system_instruction=system_instruction_text,
                safety_settings=safety_settings
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
