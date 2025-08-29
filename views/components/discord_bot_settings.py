#:kivy 2.0.0
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ObjectProperty
from kivy.lang import Builder

# Import LLMSelector if it's used directly in the .kv, or pass properties if it's instantiated there
# from ..llm_selector import LLMSelector # Assuming LLMSelector is in views/components/

Builder.load_file('views/components/discord_bot_settings.kv')

class DiscordBotSettings(BoxLayout):
    """
    A component to group Discord bot settings inputs and save button.
    """
    # --- Discord Specific Settings ---
    discord_token = StringProperty("")
    guild_id = StringProperty("")
    channel_id = StringProperty("")
    master_discord_id = StringProperty("")
    lily_discord_id = StringProperty("")

    # --- Callback for saving settings ---
    save_settings_callback = ObjectProperty(None) # Will be root.save_all_discord_settings

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation and other layout properties are typically set in the .kv file
        # self.orientation = 'vertical' # Example, if not set in KV
