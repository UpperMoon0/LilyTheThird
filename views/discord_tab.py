from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.utils import get_color_from_hex

# Import the LLM configuration mixin
from .llm_config_mixin import LLMConfigMixin
# Import settings manager functions (only needed for non-LLM settings now)
from settings_manager import load_settings, save_settings

# Import the custom ColorCircle component (assuming it's used elsewhere or will be)

# Load the corresponding kv file
Builder.load_file('views/discord_tab.kv')

class DiscordTab(BoxLayout, LLMConfigMixin): # Inherit from the mixin
    """
    Kivy equivalent of the DiscordTab QWidget, now using LLMConfigMixin.
    """
    # --- State Properties ---
    is_bot_running = BooleanProperty(False)
    status_text = StringProperty("Not Running")
    toggle_button_text = StringProperty("Start Bot")
    message_section_visible = BooleanProperty(False) # Controls visibility of message input/button

    # --- Config Properties (Specific to Discord) ---
    guild_id = StringProperty("")
    channel_id = StringProperty("")
    # LLM properties (llm_providers, llm_models, selected_provider, selected_model)
    # are now inherited from LLMConfigMixin.

    # --- Message Properties ---
    message_text = StringProperty("")

    # --- Widget References (Optional, if needed for direct access) ---
    status_circle = ObjectProperty(None) # Reference to the ColorCircle widget
    # _updating_models flag is now handled by LLMConfigMixin.
    settings_prefix = 'discord_' # Prefix for LLM settings keys

    # --- Animation Properties ---
    idle_color_1 = ListProperty(get_color_from_hex("#C90000")) # Red
    idle_color_2 = ListProperty(get_color_from_hex("#C4A000")) # Yellow
    running_color_1 = ListProperty(get_color_from_hex("#00FF4C")) # Green
    running_color_2 = ListProperty(get_color_from_hex("#00C4BA")) # Turquoise
    anim = None # Holds the current animation

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Load non-LLM settings first
        self._load_discord_settings()
        # LLM settings are loaded in _post_init after the widget is built
        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)

    def _load_discord_settings(self):
        """Load Discord-specific settings."""
        settings = load_settings()
        print("DiscordTab: Loading Discord-specific settings:", settings)
        self.guild_id = settings.get(f'{self.settings_prefix}guild_id', '')
        self.channel_id = settings.get(f'{self.settings_prefix}channel_id', '')

    # _load_initial_settings is replaced by _load_discord_settings and the mixin's methods

    # --- LLMConfigMixin Required Methods ---
    def _get_provider_setting_key(self) -> str:
        """Return the key used in settings for the selected provider."""
        return f'{self.settings_prefix}selected_provider'

    def _get_model_setting_key(self) -> str:
        """Return the key used in settings for the selected model."""
        return f'{self.settings_prefix}selected_model'

    def _post_init(self, dt):
        """Called after the widget is fully initialized."""
        # Initialize the LLM part (loads settings and populates models)
        self._load_llm_settings()
        self.update_models(initial_load=True)
        # Start the initial animation
        self.update_status_animation()

    def _save_current_settings(self):
        """Helper method to save the current state (both Discord and LLM)."""
        settings = load_settings() # Load existing settings

        # Save Discord-specific settings
        settings[f'{self.settings_prefix}guild_id'] = self.guild_id
        settings[f'{self.settings_prefix}channel_id'] = self.channel_id

        # Save the combined settings (Discord specific)
        save_settings(settings)
        # Save LLM settings using the mixin's method (which handles loading/saving internally)
        self._save_llm_settings()
        print("DiscordTab: Settings saved.")

    # update_models, set_update_flag, on_selected_provider, and on_selected_model
    # are now handled by LLMConfigMixin.

    # --- Callbacks for saving Discord-specific settings ---
    def on_guild_id(self, instance, value):
        """Callback when Guild ID changes."""
        print(f"DiscordTab: Guild ID changed to {value}")
        self._save_current_settings() # Saves both Discord and LLM settings

    def on_channel_id(self, instance, value):
        """Callback when Channel ID changes."""
        print(f"DiscordTab: Channel ID changed to {value}")
        self._save_current_settings() # Saves both Discord and LLM settings

    # --- Bot Control ---
    def toggle_bot(self):
        """Start or stop the Discord bot process."""
        self.is_bot_running = not self.is_bot_running
        if self.is_bot_running:
            self.status_text = "Running"
            self.toggle_button_text = "Stop Bot"
            self.message_section_visible = True
            print("Starting Discord Bot (Simulated)")
            # Add actual bot starting logic here (e.g., start subprocess)
        else:
            self.status_text = "Not Running"
            self.toggle_button_text = "Start Bot"
            self.message_section_visible = False
            print("Stopping Discord Bot (Simulated)")
            # Add actual bot stopping logic here (e.g., terminate subprocess)

        # Update the status circle animation
        self.update_status_animation()

    def update_status_animation(self):
        """Update the animation of the status circle based on bot state."""
        if self.anim:
            self.anim.cancel_all(self.status_circle) # Cancel previous animation

        if self.is_bot_running:
            color1 = self.running_color_1
            color2 = self.running_color_2
        else:
            color1 = self.idle_color_1
            color2 = self.idle_color_2

        # Create a pulsating animation
        self.anim = Animation(circle_color=color2, duration=0.75) + \
                    Animation(circle_color=color1, duration=0.75)
        self.anim.repeat = True
        self.anim.start(self.status_circle)

    def send_message(self):
        """Send a message to the running bot (via IPC/Queue)."""
        if not self.is_bot_running or not self.message_text:
            print("Cannot send message: Bot not running or message empty.")
            return

        msg = self.message_text
        print(f"Sending message to bot: {msg} (Simulated)")
        # Add actual IPC/Queue logic here to send the message
        self.message_text = "" # Clear input field
