from kivy.properties import ListProperty, StringProperty, BooleanProperty, ObjectProperty
from kivy.clock import Clock
# Import settings manager functions
# from settings_manager import load_settings, save_settings # No longer directly used by mixin

# Import the new model fetching functions
from llm.llm_client import get_openai_models, get_gemini_models
from llm.llm_client import API_KEYS_FILE # To access API keys
import json # For loading API keys

# Apply the combined metaclass to the mixin
# Note: We don't inherit ABC directly anymore, the metaclass handles abstract checks
class LLMConfigMixin:
    """
    A mixin class (using a combined metaclass) to handle common LLM provider/model selection logic
    and settings persistence for Kivy widgets.
    It requires load_function and save_function to be set by the consuming class.
    """
    llm_providers = ListProperty(["OpenAI", "Gemini"])
    llm_models = ListProperty([])
    selected_provider = StringProperty("OpenAI") # Default provider, might be overridden by load
    selected_model = StringProperty("")
    _updating_models = BooleanProperty(False) # Flag to prevent saving during updates

    # Functions to be provided by the consuming class
    load_function = ObjectProperty(None)
    save_function = ObjectProperty(None)

    def _get_provider_setting_key(self) -> str:
        """Return the key used in settings for the selected provider."""
        raise NotImplementedError("Subclasses must implement this method")

    def _get_model_setting_key(self) -> str:
        """Return the key used in settings for the selected model."""
        raise NotImplementedError("Subclasses must implement this method")

    def _load_llm_settings(self):
        """Load LLM related settings using the specific keys and the provided load_function."""
        if not self.load_function:
            print(f"{self.__class__.__name__}: Error - load_function not set. Cannot load LLM settings.")
            return

        settings = self.load_function()
        provider_key = self._get_provider_setting_key()
        # model_key = self._get_model_setting_key() # Model is set during update_models

        print(f"{self.__class__.__name__}: Loading LLM settings (Provider key: {provider_key}) using {self.load_function.__name__}")
        # Use .get() with defaults to handle potentially missing keys gracefully
        self.selected_provider = settings.get(provider_key, self.selected_provider) # Use current value as default if key missing
        # self.selected_model = settings.get(model_key, '') # Model set in update_models

    def _save_llm_settings(self):
        """Save LLM related settings using the specific keys and the provided save_function."""
        if self._updating_models:
            print(f"{self.__class__.__name__}: Skipping save because _updating_models is True.") # MODIFIED LOG
            return
        
        if not self.load_function or not self.save_function:
            print(f"{self.__class__.__name__}: Error - load_function or save_function not set. Cannot save LLM settings.")
            return

        settings = self.load_function() # Load existing settings first using the specific loader
        provider_key = self._get_provider_setting_key()
        model_key = self._get_model_setting_key()

        settings[provider_key] = self.selected_provider
        settings[model_key] = self.selected_model
        self.save_function(settings) # Save using the specific saver
        print(f"{self.__class__.__name__}: LLM settings saved (Keys: {provider_key}, {model_key}) using {self.save_function.__name__}.")

    def update_models(self, *args, initial_load=False):
        """Update the list of models based on the selected provider."""
        self._updating_models = True # Set flag immediately
        try:
            print(f"{self.__class__.__name__}: Updating models for provider: {self.selected_provider}. Initial load: {initial_load}")
            saved_model = "" # Initialize to empty
            if initial_load and self.load_function:
                settings = self.load_function()
                model_key = self._get_model_setting_key()
                saved_model = settings.get(model_key, "")
                print(f"{self.__class__.__name__}: Loaded saved model '{saved_model}' during initial load.")

            current_api_keys = {}
            if API_KEYS_FILE.exists():
                with open(API_KEYS_FILE, 'r') as f:
                    try:
                        current_api_keys = json.load(f)
                    except json.JSONDecodeError as e:
                        print(f"ERROR: Failed to decode JSON from API keys file: {API_KEYS_FILE}")
                        print(f"Error details: {e}")
                        # current_api_keys remains {}, subsequent logic should handle this gracefully.
            else:
                print(f"INFO: API keys file not found at {API_KEYS_FILE}. Proceeding without API keys from file.")

            api_key_for_provider = None
            if self.selected_provider.lower() in current_api_keys and current_api_keys[self.selected_provider.lower()]:
                api_key_for_provider = current_api_keys[self.selected_provider.lower()][0] # Use the first key

            fetched_models = []
            if api_key_for_provider:
                if self.selected_provider == "OpenAI":
                    fetched_models = get_openai_models(api_key_for_provider)
                elif self.selected_provider == "Gemini":
                    fetched_models = get_gemini_models(api_key_for_provider)
            else:
                print(f"{self.__class__.__name__}: No API key found for {self.selected_provider}. Cannot fetch models.")

            if fetched_models:
                self.llm_models = fetched_models
                default_model = self.llm_models[0] if self.llm_models else ""
            else:
                # Fallback to predefined models if API call fails or no key
                print(f"{self.__class__.__name__}: Falling back to predefined models for {self.selected_provider}.")
                from config.models import OPENAI_MODELS, GEMINI_MODELS # Local import for fallback
                if self.selected_provider == "OpenAI":
                    self.llm_models = OPENAI_MODELS[:]
                    default_model = self.llm_models[0] if self.llm_models else ""
                elif self.selected_provider == "Gemini":
                    self.llm_models = GEMINI_MODELS[:]
                    default_model = self.llm_models[0] if self.llm_models else ""
                else:
                    self.llm_models = []
                    default_model = ""

            # Determine the model to select
            model_to_select = default_model # Start with the default
            if saved_model and saved_model in self.llm_models:
                model_to_select = saved_model # Use saved model if valid
                print(f"{self.__class__.__name__}: Applying saved model '{saved_model}' for provider '{self.selected_provider}'.")
            elif saved_model:
                print(f"{self.__class__.__name__}: Saved model '{saved_model}' not in new list for {self.selected_provider}. Using default: '{default_model}'.")

            if self.selected_model != model_to_select:
                self.selected_model = model_to_select
            elif not self.selected_model and model_to_select: # If current is empty but we have a default
                self.selected_model = model_to_select
            
            print(f"{self.__class__.__name__}: Models updated. Selected model: {self.selected_model}. Models list: {self.llm_models}")

        finally:
            # Schedule the flag to be reset slightly later
            Clock.schedule_once(lambda dt: self.set_update_flag(False), 0.1) # Adjusted delay if necessary

    def set_update_flag(self, value):
        """Helper function to set the flag, used with Clock.schedule_once."""
        self._updating_models = value
        print(f"{self.__class__.__name__}: _updating_models actually set to {value} via Clock") # MODIFIED LOG

    # --- Default Callbacks ---
    # Subclasses can override these or connect them if needed.
    # The actual saving logic is now centralized in _save_llm_settings.
    def on_selected_provider_changed(self, instance, value):
        """Callback when provider changes. Updates models and saves."""
        print(f"{self.__class__.__name__}: Provider changed to {value}")
        self.update_models() # This will eventually trigger save via on_selected_model if model changes
        # We save immediately here as well in case the model list is the same
        # and on_selected_model doesn't trigger.
        self._save_llm_settings()

    def on_selected_model_changed(self, instance, value):
        """Callback when model changes. Saves settings."""
        if not self._updating_models:
            if value and hasattr(self, 'llm_models') and value in self.llm_models:
                print(f"{self.__class__.__name__}: User selected model: {value}")
                self._save_llm_settings()
            elif not value:
                 print(f"{self.__class__.__name__}: Model selection cleared or invalid by user.")
        else:
            print(f"{self.__class__.__name__}: on_selected_model skipped save during update_models for value: {value}")
