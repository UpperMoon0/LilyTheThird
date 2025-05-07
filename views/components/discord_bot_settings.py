from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, ObjectProperty

class DiscordBotSettings(BoxLayout):
    discord_token = StringProperty('')
    guild_id = StringProperty('')
    channel_id = StringProperty('')
    master_discord_id = StringProperty('')
    lily_discord_id = StringProperty('')

    # Properties for LLMSelector
    selected_provider = StringProperty('')
    selected_model = StringProperty('')
    llm_providers = ListProperty([])
    llm_models = ListProperty([])
    
    # To be connected to the main DiscordTab's method
    save_all_discord_settings_callback = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # If LLMSelector needs specific initialization or binding, it can be done here
        # For now, its properties are bound in KV

    def save_all_discord_settings(self):
        if self.save_all_discord_settings_callback:
            self.save_all_discord_settings_callback()
        else:
            print("DiscordBotSettings: save_all_discord_settings_callback not set")
