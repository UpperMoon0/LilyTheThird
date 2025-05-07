#:kivy 2.0.0
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, ObjectProperty, BooleanProperty
from kivy.lang import Builder

# Import LLMSelector if it's used directly in the .kv, or pass properties if it's instantiated there
# from ..llm_selector import LLMSelector # Assuming LLMSelector is in views/components/

Builder.load_file('views/components/discord_bot_settings.kv')

class DiscordBotSettings(BoxLayout):
    """
    A component to group Discord bot settings inputs, LLM selection, and save button.
    """
    # --- Discord Specific Settings ---
    discord_token = StringProperty("")
    guild_id = StringProperty("")
    channel_id = StringProperty("")
    master_discord_id = StringProperty("")
    lily_discord_id = StringProperty("")

    # --- LLM Settings (passed from parent) ---
    selected_provider = StringProperty("")
    selected_model = StringProperty("")
    llm_providers = ListProperty([])
    llm_models = ListProperty([])

    # --- Callback for saving settings ---
    save_settings_callback = ObjectProperty(None) # Will be root.save_all_discord_settings

    # --- Properties for LLMSelector (if needed to pass through) ---
    # These are bound in the kv file directly to the LLMSelector instance
    # provider_label_text = StringProperty("Discord LLM Provider:") # Example, can be set in kv
    # model_label_text = StringProperty("Discord LLM Model:")    # Example, can be set in kv

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation and other layout properties are typically set in the .kv file
        # self.orientation = 'vertical' # Example, if not set in KV

    def trigger_save_settings(self):
        """Calls the provided callback to save all settings."""
        if self.save_settings_callback:
            self.save_settings_callback()
        else:
            print("DiscordBotSettings: Error - save_settings_callback not set.")
