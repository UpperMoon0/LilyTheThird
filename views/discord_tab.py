import threading
import queue
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.utils import get_color_from_hex
from kivy.lang import Builder

# Import the LLM configuration mixin
from .llm_config_mixin import LLMConfigMixin
# Import settings manager functions
from settings_manager import load_discord_settings, save_discord_settings 

# Import the function to run the bot in a separate process
from processes.discord_process import run_discord_bot

# Load the kv file for this widget
Builder.load_file('views/discord_tab.kv')

class DiscordTab(BoxLayout, LLMConfigMixin): # Inherit from the mixin
    """
    Kivy equivalent of the DiscordTab QWidget, now using LLMConfigMixin.
    Manages the Discord bot process and IPC.
    """
    # --- State Properties ---
    is_bot_running = BooleanProperty(False)
    _bot_thread = None # Renamed from _bot_process
    _ipc_queue = None
    status_text = StringProperty("Not Running")
    toggle_button_text = StringProperty("Start Bot")
    discord_status_circle_color = ListProperty(get_color_from_hex("#808080")) # Default gray for the new component
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
        Clock.schedule_interval(self._check_ipc_queue, 0.1) # Check IPC queue periodically

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
        if self.is_bot_running: # If bot is running, stop it
            self._stop_bot_process()
        else: # If bot is not running, start it
            self._start_bot_process()

    def _start_bot_process(self):
        """Starts the Discord bot in a separate thread.""" # Changed comment
        if self._bot_thread and self._bot_thread.is_alive():
            print("DiscordTab: Bot thread is already running.") # Changed comment
            return

        if not self.discord_token:
            print("DiscordTab: Discord Token is not set. Cannot start bot.")
            self.status_text = "Error: Token Missing"
            # Optionally, show a popup or notification to the user
            return

        self._ipc_queue = queue.Queue()
        
        discord_config = {
            'discord_token': self.discord_token, # Already available as property
            'guild_id': self.guild_id,
            'channel_id': self.channel_id,
            'master_discord_id': self.master_discord_id, # Added
            'lily_discord_id': self.lily_discord_id, # Added
            'discord_llm_provider': self.selected_provider, # From LLMConfigMixin
            'discord_llm_model': self.selected_model,       # From LLMConfigMixin
        }
        print(f"DiscordTab: Starting bot with config: {discord_config}")

        try:
            self._bot_thread = threading.Thread(
                target=run_discord_bot,
                args=(self._ipc_queue, discord_config)
            )
            self._bot_thread.daemon = True # Ensure thread exits when main app exits
            self._bot_thread.start()
            
            self.status_text = "Starting..."
            self.toggle_button_text = "Stop Bot"
            # self.is_bot_running will be set to True by _check_ipc_queue on 'ready'
            # self.message_section_visible = True # Enable when bot is confirmed ready
            print("DiscordTab: Bot thread started.") # Changed comment
        except Exception as e:
            print(f"DiscordTab: Failed to start bot thread: {e}") # Changed comment
            self.status_text = "Error Starting"
            self.is_bot_running = False # Ensure state is correct
            self._reset_bot_state()

        self.update_status_animation()


    def _stop_bot_process(self):
        """Stops the Discord bot thread gracefully.""" # Changed comment
        if self._bot_thread and self._bot_thread.is_alive() and self._ipc_queue:
            print("DiscordTab: Sending shutdown command to bot thread...") # Changed comment
            try:
                self._ipc_queue.put({'command': 'shutdown'})
                self.status_text = "Stopping..."
                # The actual stopping and state reset will be handled by _check_ipc_queue
                # when it receives the 'stopped' status or if the thread ends.
            except Exception as e:
                print(f"DiscordTab: Error sending shutdown to IPC queue: {e}")
                # Force stop if IPC fails
                self._terminate_bot_process() # Changed to _terminate_bot_thread if you rename it
        else:
            print("DiscordTab: Bot thread not running or IPC queue not available.") # Changed comment
            self._reset_bot_state() # Ensure UI is reset if something is inconsistent

        self.update_status_animation()

    def _terminate_bot_process(self): # Consider renaming to _terminate_bot_thread for clarity
        """Attempts to signal the bot thread to stop and resets state.""" # Changed comment
        if self._bot_thread and self._bot_thread.is_alive():
            print("DiscordTab: Signaling bot thread to stop.") # Changed comment
            # Threads cannot be forcefully terminated like processes.
            # We rely on the bot_instance.stop_bot() and the daemon=True nature.
            # If the bot doesn't stop gracefully, it might hang until app exit.
            # If your bot has a specific stop mechanism that can be triggered via IPC, use that.
            if self._ipc_queue:
                try:
                    self._ipc_queue.put({'command': 'shutdown'}) # Try again if not done in _stop_bot_process
                except Exception as e:
                    print(f"DiscordTab: Error sending shutdown to IPC during terminate: {e}")
            print("DiscordTab: Note - Threads cannot be forcefully terminated. Relying on graceful shutdown.")
        self._reset_bot_state()

    def _reset_bot_state(self):
        """Resets UI and internal state related to the bot."""
        self.is_bot_running = False
        self.status_text = "Not Running"
        self.toggle_button_text = "Start Bot"
        self.message_section_visible = False
        self._bot_thread = None
        self._ipc_queue = None
        self.update_status_animation()
        print("DiscordTab: Bot state reset.")

    def _check_ipc_queue(self, dt):
        """Periodically checks the IPC queue for messages from the bot thread.""" # Changed comment
        if not self._ipc_queue:
            # If bot thread died unexpectedly, reset state
            if self._bot_thread and not self._bot_thread.is_alive() and self.is_bot_running:
                print("DiscordTab: Bot thread seems to have died unexpectedly.") # Changed comment
                self._reset_bot_state()
            return

        try:
            while not self._ipc_queue.empty():
                message = self._ipc_queue.get_nowait()
                print(f"DiscordTab: Received IPC message: {message}")
                if isinstance(message, dict):
                    status = message.get('status')
                    if status == 'ready':
                        self.is_bot_running = True
                        self.status_text = f"Running as {message.get('user', 'Bot')}"
                        self.toggle_button_text = "Stop Bot"
                        self.message_section_visible = True
                        print("DiscordTab: Bot is ready.")
                    elif status == 'stopped':
                        print("DiscordTab: Bot reported stopped.")
                        self._reset_bot_state()
                        if self._bot_process: # Ensure process is joined
                            self._bot_process.join(timeout=1)
                            self._bot_process = None
                    elif status == 'error':
                        error_msg = message.get('message', 'Unknown error')
                        print(f"DiscordTab: Bot reported an error: {error_msg}")
                        self.status_text = f"Error: {error_msg}"
                        # Optionally, stop the bot or attempt restart depending on error
                        self._terminate_bot_process() # For now, just stop on error
                # Handle other types of messages if needed
        except queue.Empty:
            pass # No message, normal
        except Exception as e:
            print(f"DiscordTab: Error checking IPC queue: {e}")

        # Check if process is still alive if we think it should be
        if self.is_bot_running and self._bot_process and not self._bot_process.is_alive():
            print("DiscordTab: Bot process no longer alive but UI thinks it's running. Resetting.")
            self._reset_bot_state()
        
        self.update_status_animation() # Keep animation in sync

    def update_status_animation(self):
        """Update the animation of the status circle based on bot state."""
        if self.anim:
            # The animation is now on the property, not a widget directly from here.
            # Kivy's animation system handles properties well.
            # We need to cancel it from the property itself if that's how it was started.
            # However, Animation targets an object and a property name.
            # If we start anim on `self` for property `discord_status_circle_color`,
            # then we cancel from `self`.
            Animation.cancel_all(self, 'discord_status_circle_color')

        if self.is_bot_running:
            color1 = self.running_color_1
            color2 = self.running_color_2
        else:
            color1 = self.idle_color_1
            color2 = self.idle_color_2

        # Create a pulsating animation on the property
        self.anim = Animation(discord_status_circle_color=color2, duration=0.75) + \
                    Animation(discord_status_circle_color=color1, duration=0.75)
        self.anim.repeat = True
        self.anim.start(self) # Start animation on self, targeting the property


    def send_message(self):
        """Send a message to the running bot (via IPC/Queue)."""
        if not self.is_bot_running or not self.message_text or not self._ipc_queue:
            print("DiscordTab: Cannot send message. Bot not running, message empty, or IPC queue unavailable.")
            return
        
        if not self.channel_id:
            print("DiscordTab: Cannot send message. Channel ID not set in UI.")
            # Optionally, show a user notification
            return

        msg_data = {
            'command': 'send_message', # Or just rely on content presence
            'channel_id': self.channel_id, # Use channel_id from UI settings
            'content': self.message_text
        }
        try:
            self._ipc_queue.put(msg_data)
            print(f"DiscordTab: Sent message to IPC queue: {msg_data}")
            self.message_text = "" # Clear input field
        except Exception as e:
            print(f"DiscordTab: Error sending message to IPC queue: {e}")

    def on_stop(self):
        """Ensure bot process is stopped when the application/widget is stopped."""
        print("DiscordTab: on_stop called, ensuring bot process is terminated.")
        self._stop_bot_process()
        if self._bot_process and self._bot_process.is_alive():
            self._terminate_bot_process() # Force terminate if graceful stop failed
