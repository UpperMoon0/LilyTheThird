from kivy.properties import ListProperty, StringProperty, BooleanProperty, ObjectProperty
from kivy.clock import Clock
# Import model lists from config
from config.models import OPENAI_MODELS, GEMINI_MODELS
# Import settings manager functions
# from settings_manager import load_settings, save_settings # No longer directly used by mixin


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
            print(f"{self.__class__.__name__}: Skipping save during model update.")
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
        try: # Use try/finally to ensure flag is cleared
            print(f"{self.__class__.__name__}: Updating models for provider: {self.selected_provider}")
            saved_model = None
            if initial_load:
                if not self.load_function:
                    print(f"{self.__class__.__name__}: Warning - load_function not set during initial_load. Cannot load saved model.")
                else:
                    settings = self.load_function() # Load again to get the saved model for this provider
                    provider_key = self._get_provider_setting_key()
                    model_key = self._get_model_setting_key()
                    if settings.get(provider_key) == self.selected_provider:
                        saved_model = settings.get(model_key)
                        print(f"{self.__class__.__name__}: Found saved model for initial load: {saved_model}")

            # Determine models based on provider
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
                print(f"{self.__class__.__name__}: Saved model '{saved_model}' not valid for provider '{self.selected_provider}'. Using default '{default_model}'.")
            else:
                 print(f"{self.__class__.__name__}: No saved model found for provider '{self.selected_provider}'. Using default '{default_model}'.")

            # Explicitly set the selected_model property *after* list is populated
            print(f"{self.__class__.__name__}: Setting selected_model to '{model_to_select}'") # ADDED LOG
            self.selected_model = model_to_select

            print(f"{self.__class__.__name__}: Models updated. Provider: {self.selected_provider}, Models: {self.llm_models}, Final Selected: {self.selected_model}")

        finally:
            # Clear the flag *after* the current event cycle using Clock.schedule_once
            print(f"{self.__class__.__name__}: Scheduling _updating_models = False") # ADDED LOG
            Clock.schedule_once(lambda dt: self.set_update_flag(False), 0)

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
