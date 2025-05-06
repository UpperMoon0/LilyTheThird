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
    discord_token = StringProperty("")
    guild_id = StringProperty("")
    channel_id = StringProperty("")
    master_discord_id = StringProperty("")
    lily_discord_id = StringProperty("")
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
        self._load_discord_settings() # Loads guild_id, channel_id, discord_token, etc.
        # LLM settings are loaded in _post_init after the widget is built using the mixin's _load_llm_settings
        
        # Bind LLM property changes AFTER loading initial settings
        self.bind(selected_provider=self.on_selected_provider_changed_discord)
        self.bind(selected_model=self.on_selected_model_changed_discord)
        
        # Bind Discord-specific property changes
        self.bind(discord_token=self.on_discord_token_changed)
        self.bind(guild_id=self.on_guild_id_changed) # Renamed for consistency
        self.bind(channel_id=self.on_channel_id_changed) # Renamed for consistency
        self.bind(master_discord_id=self.on_master_discord_id_changed)
        self.bind(lily_discord_id=self.on_lily_discord_id_changed)

        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)

    def _load_discord_settings(self):
        """Load Discord-specific settings."""
        if not self.load_function:
            print("DiscordTab: Error - load_function not set. Cannot load Discord-specific settings.")
            return
        settings = self.load_function()
        print(f"DiscordTab: Loading Discord-specific settings using {self.load_function.__name__}: {settings}")
        self.discord_token = settings.get('discord_token', '')
        self.guild_id = settings.get('guild_id', '')
        self.channel_id = settings.get('channel_id', '')
        self.master_discord_id = settings.get('master_discord_id', '')
        self.lily_discord_id = settings.get('lily_discord_id', '')

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

    def save_all_discord_settings(self):
        """Saves all Discord tab settings (specific and LLM)."""
        if not self.load_function or not self.save_function:
            print("DiscordTab: Error - load_function or save_function not set. Cannot save settings.")
            return

        settings = self.load_function() # Load existing settings to preserve other values

        # Update Discord-specific settings
        settings['discord_token'] = self.discord_token
        settings['guild_id'] = self.guild_id
        settings['channel_id'] = self.channel_id
        settings['master_discord_id'] = self.master_discord_id
        settings['lily_discord_id'] = self.lily_discord_id
        
        # Update LLM settings (already handled by _save_llm_settings, but good to be explicit if combining)
        settings[self._get_provider_setting_key()] = self.selected_provider
        settings[self._get_model_setting_key()] = self.selected_model
        # Add other LLM settings if they are managed directly here and not by the mixin's save

        self.save_function(settings)
        print(f"DiscordTab: All Discord settings saved using {self.save_function.__name__}.")

    # update_models, set_update_flag are inherited from LLMConfigMixin.
    # We define specific callbacks below.

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
        if not self._updating_models and value and hasattr(self, 'llm_models') and value in self.llm_models:
            print(f"DiscordTab: Model changed to: {value}. Saving LLM settings.")
            self._save_llm_settings()
        elif not value and not self._updating_models:
             print(f"DiscordTab: Model selection cleared or invalid by user. Saving.")
             self._save_llm_settings() # Save even if cleared by user


    # --- Callbacks for saving Discord-specific settings (now trigger save_all_discord_settings) ---
    def on_discord_token_changed(self, instance, value):
        print(f"DiscordTab: Discord Token changed. Length: {len(value)}")
        # No immediate save, will be saved by button click
        
    def on_guild_id_changed(self, instance, value):
        print(f"DiscordTab: Guild ID changed to {value}")
        # No immediate save, will be saved by button click

    def on_channel_id_changed(self, instance, value):
        print(f"DiscordTab: Channel ID changed to {value}")
        # No immediate save, will be saved by button click

    def on_master_discord_id_changed(self, instance, value):
        print(f"DiscordTab: Master Discord ID changed to {value}")
        # No immediate save, will be saved by button click
        
    def on_lily_discord_id_changed(self, instance, value):
        print(f"DiscordTab: Lily Discord ID changed to {value}")
        # No immediate save, will be saved by button click

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
