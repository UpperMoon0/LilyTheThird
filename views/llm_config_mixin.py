from kivy.properties import ListProperty, StringProperty, BooleanProperty, ObjectProperty
from kivy.clock import Clock # Added Clock

from llm.llm_client import get_openai_models, get_gemini_models
from llm.llm_client import API_KEYS_FILE 
import json 

class LLMConfigMixin:
    """
    A mixin class (using a combined metaclass) to handle common LLM provider/model selection logic
    and settings persistence for Kivy widgets.
    It requires load_function and save_function to be set by the consuming class.
    """
    llm_providers = ListProperty(["OpenAI", "Gemini"])
    llm_models = ListProperty([])
    selected_provider = StringProperty("OpenAI")
    selected_model = StringProperty("")
    _updating_models = BooleanProperty(False) # Flag to prevent saving during updates

    # Functions to be provided by the consuming class
    load_function = ObjectProperty(None)
    save_function = ObjectProperty(None)

    # --- Initialization ---
    def initialize_llm_config(self):
        """
        Initializes LLM configuration by loading settings and populating models.
        Should be called by the consuming class after load_function is set.
        """
        if not self.load_function:
            print(f"{self.__class__.__name__}: Error - load_function not set. Cannot initialize LLM config.")
            return
        self._load_llm_settings()
        self.update_models(initial_load=True)

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

        print(f"{self.__class__.__name__}: Loading LLM settings (Provider key: {provider_key}) using {self.load_function.__name__}")
        self.selected_provider = settings.get(provider_key, self.selected_provider)

    def _save_llm_settings(self):
        """Save LLM related settings using the specific keys and the provided save_function."""
        if self._updating_models:
            print(f"{self.__class__.__name__}: Skipping save because _updating_models is True.")
            return
        
        if not self.load_function or not self.save_function:
            print(f"{self.__class__.__name__}: Error - load_function or save_function not set. Cannot save LLM settings.")
            return

        settings = self.load_function() 
        provider_key = self._get_provider_setting_key()
        model_key = self._get_model_setting_key()

        settings[provider_key] = self.selected_provider
        settings[model_key] = self.selected_model
        self.save_function(settings) 
        print(f"{self.__class__.__name__}: LLM settings saved (Keys: {provider_key}, {model_key}) using {self.save_function.__name__}.")

    def update_models(self, *args, initial_load=False):
        """Update the list of models based on the selected provider, with new logic."""
        self._updating_models = True
        try:
            print(f"{self.__class__.__name__}: Starting model update for provider: {self.selected_provider}. Initial load: {initial_load}")

            if not self.selected_provider:
                print(f"{self.__class__.__name__}: No provider selected or available. Cannot update models.")
                if not self.llm_providers: # If the main list is also empty
                    self.llm_models = []
                    self.selected_model = ""
                # If llm_providers has items, on_selected_provider_changed should handle picking one if selected_provider was cleared.
                return

            current_api_keys = {}
            if API_KEYS_FILE.exists():
                with open(API_KEYS_FILE, 'r') as f:
                    try:
                        current_api_keys = json.load(f)
                    except json.JSONDecodeError as e:
                        print(f"ERROR: Failed to decode JSON from API keys file: {API_KEYS_FILE}. Error: {e}")
            else:
                print(f"INFO: API keys file not found at {API_KEYS_FILE}.")

            api_key_for_provider = None
            provider_lower = self.selected_provider.lower()
            if provider_lower in current_api_keys and current_api_keys[provider_lower]:
                api_key_for_provider = current_api_keys[provider_lower][0]

            fetched_models = []
            if api_key_for_provider:
                print(f"{self.__class__.__name__}: API key found for {self.selected_provider}. Fetching models...")
                if self.selected_provider == "OpenAI":
                    fetched_models = get_openai_models(api_key_for_provider)
                elif self.selected_provider == "Gemini":
                    fetched_models = get_gemini_models(api_key_for_provider)
                
                if fetched_models:
                    print(f"{self.__class__.__name__}: Successfully fetched {len(fetched_models)} models for {self.selected_provider}.")
                else:
                    print(f"{self.__class__.__name__}: API call made for {self.selected_provider}, but no models were returned.")
            else:
                print(f"{self.__class__.__name__}: No API key found or configured for {self.selected_provider}. Cannot fetch models.")

            if fetched_models:
                self.llm_models = fetched_models
                
                saved_model_name = ""
                if self.load_function:
                    settings = self.load_function()
                    model_key = self._get_model_setting_key()
                    saved_model_name = settings.get(model_key, "")
                    if saved_model_name:
                        print(f"{self.__class__.__name__}: Loaded saved model name '{saved_model_name}' from settings for provider '{self.selected_provider}'.")

                model_to_select = ""
                if saved_model_name and saved_model_name in self.llm_models:
                    model_to_select = saved_model_name
                    print(f"{self.__class__.__name__}: Saved model '{saved_model_name}' is in the fetched list. Selecting it.")
                elif self.llm_models:
                    model_to_select = self.llm_models[0]
                    print(f"{self.__class__.__name__}: Saved model not applicable or not found. Selecting first model from fetched list: '{model_to_select}'.")
                
                self.selected_model = model_to_select
                if not model_to_select:
                    print(f"{self.__class__.__name__}: No models available to select for {self.selected_provider} after successful fetch (empty list).")

            else: # Fetch failed or returned no models
                print(f"{self.__class__.__name__}: Failed to fetch models or no models returned for provider '{self.selected_provider}'.")
                
                provider_to_remove = self.selected_provider
                # Ensure llm_providers is a mutable list for removal
                if not isinstance(self.llm_providers, list):
                    self.llm_providers = list(self.llm_providers)

                if provider_to_remove in self.llm_providers:
                    self.llm_providers.remove(provider_to_remove)
                    print(f"{self.__class__.__name__}: Removed provider '{provider_to_remove}'. Remaining providers: {self.llm_providers}")

                if self.llm_providers:
                    new_provider = self.llm_providers[0]
                    print(f"{self.__class__.__name__}: Attempting to switch to next available provider: '{new_provider}'.")
                    self.selected_provider = new_provider # This will trigger on_selected_provider_changed
                else:
                    print(f"{self.__class__.__name__}: No providers available after failure. Clearing models and selection.")
                    self.llm_models = []
                    self.selected_model = ""
                    # self.selected_provider will be the one that just failed, or empty if it was the last one.
                    # If it's empty, the UI should reflect no provider selected.

            print(f"{self.__class__.__name__}: Model update cycle finished. Provider: {self.selected_provider}, Model: {self.selected_model}, Models: {len(self.llm_models)}, Avail Providers: {self.llm_providers}")

        finally:
            Clock.schedule_once(lambda dt: self.set_update_flag(False), 0.1) 

    def set_update_flag(self, value):
        """Helper function to set the flag, used with Clock.schedule_once."""
        self._updating_models = value
        print(f"{self.__class__.__name__}: _updating_models actually set to {value} via Clock")

    # --- Internal Handlers for Property Changes ---
    def _handle_selected_provider_change(self, instance, value):
        """Handles changes to selected_provider."""
        if self._updating_models:
            return # Avoid loops or premature actions if models are already being updated

        print(f"{self.__class__.__name__}: Provider changed to {value}. Updating models and scheduling save.")
        self.update_models() # This updates self.llm_models and potentially self.selected_model

        # Schedule save and notification to allow property changes to settle
        Clock.schedule_once(self._save_settings_and_notify_provider_change, 0.1)

    def _save_settings_and_notify_provider_change(self, dt):
        """Saves LLM settings and calls the provider updated hook."""
        self._save_llm_settings()
        self.on_llm_provider_updated()

    def _handle_selected_model_change(self, instance, value):
        """Handles changes to selected_model."""
        if self._updating_models:
            return # Avoid loops or premature actions

        if value and hasattr(self, 'llm_models') and value in self.llm_models:
            print(f"{self.__class__.__name__}: Model changed to {value}. Saving settings and notifying.")
            self._save_llm_settings()
            self.on_llm_model_updated()
        elif not value and not self._updating_models: # Handle model being cleared by user
            print(f"{self.__class__.__name__}: Model selection cleared. Saving settings and notifying.")
            self._save_llm_settings() # Save the cleared state
            self.on_llm_model_updated() # Notify even if cleared

    # --- Overridable Hooks ---
    def on_llm_provider_updated(self):
        """
        Hook method called after the LLM provider has been updated and settings saved.
        Consuming classes can override this to perform specific actions.
        """
        print(f"{self.__class__.__name__}: LLM Provider updated hook called.")
        pass

    def on_llm_model_updated(self):
        """
        Hook method called after the LLM model has been updated and settings saved.
        Consuming classes can override this to perform specific actions.
        """
        print(f"{self.__class__.__name__}: LLM Model updated hook called.")
        pass

    # --- Default Callbacks ---
    def on_selected_provider_changed(self, instance, value):
        """Callback when provider changes. Updates models and saves."""
        self._handle_selected_provider_change(instance, value)

    def on_selected_model_changed(self, instance, value):
        """Callback when model changes. Saves settings."""
        self._handle_selected_model_change(instance, value)
