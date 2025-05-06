from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty, ObjectProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.utils import get_color_from_hex
from kivy.lang import Builder

# Import the LLM configuration mixin
from .llm_config_mixin import LLMConfigMixin
# Import settings manager functions
from settings_manager import load_discord_settings, save_discord_settings 

# Load the kv file for this widget
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
    # settings_prefix = 'discord_' # REMOVED - Keys will match DEFAULT_DISCORD_SETTINGS

    # --- Animation Properties ---
    idle_color_1 = ListProperty(get_color_from_hex("#C90000")) # Red
    idle_color_2 = ListProperty(get_color_from_hex("#C4A000")) # Yellow
    running_color_1 = ListProperty(get_color_from_hex("#00FF4C")) # Green
    running_color_2 = ListProperty(get_color_from_hex("#00C4BA")) # Turquoise
    anim = None # Holds the current animation

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set the load and save functions for the LLMConfigMixin
        self.load_function = load_discord_settings
        self.save_function = save_discord_settings

        # Load non-LLM settings first
        self._load_discord_settings() # Loads guild_id, channel_id
        # LLM settings are loaded in _post_init after the widget is built using the mixin's _load_llm_settings
        
        # Bind LLM property changes AFTER loading initial settings
        self.bind(selected_provider=self.on_selected_provider_changed_discord)
        self.bind(selected_model=self.on_selected_model_changed_discord)
        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)

    def _load_discord_settings(self):
        """Load Discord-specific settings (guild_id, channel_id)."""
        if not self.load_function:
            print("DiscordTab: Error - load_function not set. Cannot load Discord-specific settings.")
            return
        settings = self.load_function()
        print(f"DiscordTab: Loading Discord-specific settings using {self.load_function.__name__}: {settings}")
        self.guild_id = settings.get('guild_id', '') # Matches DEFAULT_DISCORD_SETTINGS
        self.channel_id = settings.get('channel_id', '') # Matches DEFAULT_DISCORD_SETTINGS

    # _load_initial_settings is replaced by _load_discord_settings and the mixin's methods

    # --- LLMConfigMixin Required Methods ---
    def _get_provider_setting_key(self) -> str:
        """Return the key used in settings for the selected provider."""
        return 'selected_provider' # Matches DEFAULT_DISCORD_SETTINGS

    def _get_model_setting_key(self) -> str:
        """Return the key used in settings for the selected model."""
        return 'selected_model' # Matches DEFAULT_DISCORD_SETTINGS

    def _post_init(self, dt):
        """Called after the widget is fully initialized."""
        # Initialize the LLM part (loads settings and populates models)
        # This will use self.load_function (load_discord_settings)
        self._load_llm_settings() 
        self.update_models(initial_load=True)
        # Start the initial animation
        self.update_status_animation()

    def _save_discord_specific_settings(self):
        """Helper method to save only the Discord-specific settings (guild_id, channel_id)."""
        if not self.load_function or not self.save_function:
            print("DiscordTab: Error - load_function or save_function not set. Cannot save Discord-specific settings.")
            return

        settings = self.load_function() # Load existing discord settings

        settings['guild_id'] = self.guild_id
        settings['channel_id'] = self.channel_id

        self.save_function(settings) # Save updated discord settings
        print(f"DiscordTab: Discord-specific settings (guild, channel) saved using {self.save_function.__name__}.")

    # update_models, set_update_flag are inherited from LLMConfigMixin.
    # We define specific callbacks below instead of relying on the mixin's defaults.

    # --- Callbacks for LLM settings ---
    def on_selected_provider_changed_discord(self, instance, value):
        """Callback when provider changes. Updates models, then schedules save."""
        print(f"DiscordTab: Provider changed to {value}")
        # 1. Update models and set the default selected_model for the new provider
        self.update_models() # This now sets self.selected_model correctly

        # 2. Schedule save AFTER update_models finishes and clears its flag
        Clock.schedule_once(self._save_llm_settings_after_provider_change, 0.1) # Small delay

    def _save_llm_settings_after_provider_change(self, dt):
        """Helper function scheduled after provider change to save LLM settings."""
        print(f"DiscordTab: Saving LLM settings after provider change.")
        # Ensure the flag isn't somehow still set
        if self._updating_models:
            print("DiscordTab: Warning - _updating_models still true during scheduled save. Retrying later.")
            Clock.schedule_once(self._save_llm_settings_after_provider_change, 0.2)
            return
        self._save_llm_settings() # Save the new provider and the default model

    def on_selected_model_changed_discord(self, instance, value):
        """Callback when model changes (user interaction or default set). Saves LLM settings."""
        # LLMConfigMixin.on_selected_model_changed handles the _updating_models check.
        # We just need to ensure _save_llm_settings is called if the model is valid.
        if value and hasattr(self, 'llm_models') and value in self.llm_models:
            print(f"DiscordTab: Model changed to: {value}. Saving LLM settings.")
            self._save_llm_settings() # This is from LLMConfigMixin, uses self.save_function
        elif not value:
             print(f"DiscordTab: Model selection cleared or invalid by user.")


    # --- Callbacks for saving Discord-specific settings ---
    def on_guild_id(self, instance, value):
        """Callback when Guild ID changes."""
        print(f"DiscordTab: Guild ID changed to {value}")
        self._save_discord_specific_settings()

    def on_channel_id(self, instance, value):
        """Callback when Channel ID changes."""
        print(f"DiscordTab: Channel ID changed to {value}")
        self._save_discord_specific_settings()

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
        # Ensure the widget exists before starting the animation
        if self.status_circle:
            self.anim.start(self.status_circle)
        else:
            print("DiscordTab: Warning - status_circle widget not found yet for animation.")


    def send_message(self):
        """Send a message to the running bot (via IPC/Queue)."""
        if not self.is_bot_running or not self.message_text:
            print("Cannot send message: Bot not running or message empty.")
            return

        msg = self.message_text
        print(f"Sending message to bot: {msg} (Simulated)")
        # Add actual IPC/Queue logic here to send the message
        self.message_text = "" # Clear input field
