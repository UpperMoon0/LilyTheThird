import threading
import queue
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty # ListProperty and Animation removed
from kivy.clock import Clock
# from kivy.animation import Animation # No longer needed here
from kivy.utils import get_color_from_hex # Still used for color constants
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
    _bot_thread = None
    _ipc_queue = None
    status_text = StringProperty("Not Running") # Used by DiscordBotStatus.status_text
    toggle_button_text = StringProperty("Start Bot") # Used by DiscordBotStatus.toggle_button_text
    # discord_status_circle_color is REMOVED. DiscordBotStatus handles its own circle.
    # message_section_visible is REMOVED. DiscordBotStatus handles its own visibility.

    # --- Color Constants for Bot Status ---
    COLOR_OFFLINE = "#808080"  # Gray
    COLOR_CONNECTING = "#FFA500" # Orange
    COLOR_ONLINE = "#00FF00"   # Green
    COLOR_ERROR = "#FF0000"    # Red
    COLOR_STOPPING = "#FFFF00" # Yellow

    # --- Config Properties (Specific to Discord) ---
    discord_token = StringProperty("")
    guild_id = StringProperty("")
    channel_id = StringProperty("") # This is now the "Listening channel ID"
    master_discord_id = StringProperty("")
    lily_discord_id = StringProperty("")
    manual_send_channel_id_prop = StringProperty("") # New property for the manual send channel ID in DiscordTab
    # LLM properties (llm_providers, llm_models, selected_provider, selected_model)
    # are now inherited from LLMConfigMixin.

    # --- Message Properties (message_text is now in DiscordBotStatus) ---
    # message_text = StringProperty("") # Moved to DiscordBotStatus

    # _updating_models flag is now handled by LLMConfigMixin.

    # --- Animation Properties ---
    # idle_color_1, idle_color_2, running_color_1, running_color_2, anim are REMOVED.

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
        self.bind(channel_id=self.on_channel_id_changed) # This is for the "Listening channel ID"
        self.bind(master_discord_id=self.on_master_discord_id_changed)
        self.bind(lily_discord_id=self.on_lily_discord_id_changed)
        self.bind(manual_send_channel_id_prop=self.on_manual_send_channel_id_changed)

        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)
        Clock.schedule_interval(self._check_ipc_queue, 0.1)

    def _bind_discord_bot_status_events(self):
        """Binds events from the DiscordBotStatus component."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.bind(on_toggle_bot_pressed=self.toggle_bot)
            discord_bot_status_widget.bind(on_send_message_pressed=self.on_send_message_button_pressed)
            # Bind manual_send_channel_id from child to parent's property for saving
            discord_bot_status_widget.bind(manual_send_channel_id=self._update_manual_send_channel_id_prop)
        else:
            print("DiscordTab: Error - Could not find DiscordBotStatus widget to bind events.")

    def _update_manual_send_channel_id_prop(self, instance, value):
        """Updates the parent's property when the child's input changes."""
        self.manual_send_channel_id_prop = value

    def _load_discord_settings(self):
        """Load Discord-specific settings."""
        if not self.load_function:
            print("DiscordTab: Error - load_function not set. Cannot load Discord-specific settings.")
            return
        settings = self.load_function()
        print(f"DiscordTab: Loading Discord-specific settings using {self.load_function.__name__}: {settings}")
        self.discord_token = settings.get('discord_token', '')
        self.guild_id = settings.get('guild_id', '')
        self.channel_id = settings.get('channel_id', '') # Listening channel ID
        self.master_discord_id = settings.get('master_discord_id', '')
        self.lily_discord_id = settings.get('lily_discord_id', '')
        self.manual_send_channel_id_prop = settings.get('manual_send_channel_id', '') # Load new setting

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
        self._load_llm_settings()
        self.update_models(initial_load=True)
        self._bind_discord_bot_status_events()
        # Set initial state for DiscordBotStatus component
        self._update_child_status_component(
            is_online=self.is_bot_running,
            status_text="Not Running", # Initial text
            color_hex=self.COLOR_OFFLINE,
            is_connecting=False
        )
        # Ensure manual_send_channel_id is synced to child
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.manual_send_channel_id = self.manual_send_channel_id_prop


    def save_all_discord_settings(self):
        """Saves all Discord tab settings (specific and LLM)."""
        if not self.load_function or not self.save_function:
            print("DiscordTab: Error - load_function or save_function not set. Cannot save settings.")
            return

        settings = self.load_function() # Load existing settings to preserve other values

        # Update Discord-specific settings
        settings['discord_token'] = self.discord_token
        settings['guild_id'] = self.guild_id
        settings['channel_id'] = self.channel_id # Listening channel ID
        settings['master_discord_id'] = self.master_discord_id
        settings['lily_discord_id'] = self.lily_discord_id
        settings['manual_send_channel_id'] = self.manual_send_channel_id_prop # Save new setting
        
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

    def on_manual_send_channel_id_changed(self, instance, value):
        print(f"DiscordTab: Manual Send Channel ID changed to {value}")
        # No immediate save, will be saved by button click
        # self.manual_send_channel_id_prop is updated by _update_manual_send_channel_id_prop


    # --- Bot Control ---
    def toggle_bot(self, instance=None):
        """Start or stop the Discord bot process."""
        # instance argument is not used but needs to be accepted when called by event
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
            
            self.status_text = "Starting..." # This will be passed to child
            self.toggle_button_text = "Stop Bot" # This will be passed to child
            self._update_child_status_component(
                is_online=False, # Not yet online
                status_text="Starting...",
                color_hex=self.COLOR_CONNECTING,
                is_connecting=True
            )
            print("DiscordTab: Bot thread started.")
        except Exception as e:
            print(f"DiscordTab: Failed to start bot thread: {e}")
            self._update_child_status_component(
                is_online=False,
                status_text="Error Starting",
                color_hex=self.COLOR_ERROR,
                is_connecting=False
            )
            self.is_bot_running = False # Ensure state is correct
            self._reset_bot_state_ui_only() # Resets UI elements

    def _stop_bot_process(self):
        """Stops the Discord bot thread gracefully."""
        if self._bot_thread and self._bot_thread.is_alive() and self._ipc_queue:
            print("DiscordTab: Sending shutdown command to bot thread...")
            try:
                self._ipc_queue.put({'command': 'shutdown'})
                self._update_child_status_component(
                    is_online=self.is_bot_running, # Could still be true until 'stopped' received
                    status_text="Stopping...",
                    color_hex=self.COLOR_STOPPING, # Use a distinct "stopping" color
                    is_connecting=True # Pulsate while stopping
                )
            except Exception as e:
                print(f"DiscordTab: Error sending shutdown to IPC queue: {e}")
                self._terminate_bot_thread() # Force stop if IPC fails
        else:
            print("DiscordTab: Bot thread not running or IPC queue not available.")
            self._reset_bot_state_full()

    def _terminate_bot_thread(self):
        """Attempts to signal the bot thread to stop and resets state."""
        if self._bot_thread and self._bot_thread.is_alive():
            print("DiscordTab: Signaling bot thread to stop (terminate).")
            if self._ipc_queue:
                try:
                    self._ipc_queue.put({'command': 'shutdown'})
                except Exception as e:
                    print(f"DiscordTab: Error sending shutdown to IPC during terminate: {e}")
            print("DiscordTab: Note - Threads cannot be forcefully terminated. Relying on graceful shutdown.")
        self._reset_bot_state_full()

    def _reset_bot_state_full(self):
        """Resets UI and internal state related to the bot (thread, queue)."""
        self.is_bot_running = False
        self._bot_thread = None
        self._ipc_queue = None
        self._reset_bot_state_ui_only()
        print("DiscordTab: Bot state fully reset.")

    def _reset_bot_state_ui_only(self):
        """Resets only the UI elements to 'Not Running' state."""
        self.status_text = "Not Running" # For child component
        self.toggle_button_text = "Start Bot" # For child component
        self._update_child_status_component(
            is_online=False,
            status_text="Not Running",
            color_hex=self.COLOR_OFFLINE,
            is_connecting=False
        )
        print("DiscordTab: Bot UI state reset to offline.")

    def _update_child_status_component(self, is_online: bool, status_text: str, color_hex: str, is_connecting: bool = False):
        """Safely updates the DiscordBotStatus child component."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            # Update parent's properties that are bound to child's display
            self.status_text = status_text
            self.toggle_button_text = "Stop Bot" if is_online else "Start Bot"
            # Call the child's update method
            discord_bot_status_widget.update_status(is_online, status_text, color_hex, is_connecting)
            discord_bot_status_widget.manual_send_channel_id = self.manual_send_channel_id_prop
        else:
            print("DiscordTab: Error - DiscordBotStatus widget not found during update.")


    def _check_ipc_queue(self, dt):
        """Periodically checks the IPC queue for messages from the bot thread."""
        if not self._ipc_queue:
            if self.is_bot_running and self._bot_thread and not self._bot_thread.is_alive():
                print("DiscordTab: Bot thread died (no IPC queue, was running). Resetting.")
                self._reset_bot_state_full()
            elif self.is_bot_running and not self._bot_thread:
                print("DiscordTab: Bot thread object lost (no IPC queue, was running). Resetting.")
                self._reset_bot_state_full()
            return

        message_handled_that_affects_running_state = False
        try:
            while not self._ipc_queue.empty():
                message = self._ipc_queue.get_nowait()
                print(f"DiscordTab: Received IPC message: {message}")
                if isinstance(message, dict):
                    status = message.get('status')
                    if status == 'ready':
                        self.is_bot_running = True
                        bot_user_name = message.get('user', 'Bot')
                        self._update_child_status_component(
                            is_online=True,
                            status_text=f"Running as {bot_user_name}",
                            color_hex=self.COLOR_ONLINE,
                            is_connecting=False
                        )
                        message_handled_that_affects_running_state = True
                        print(f"DiscordTab: Bot is ready as {bot_user_name}.")
                    elif status == 'stopped':
                        print("DiscordTab: Bot reported stopped.")
                        self._reset_bot_state_full()
                        message_handled_that_affects_running_state = True
                    elif status == 'error':
                        error_msg = message.get('message', 'Unknown error')
                        print(f"DiscordTab: Bot reported an error: {error_msg}")
                        self._update_child_status_component(
                            is_online=False, # Or current self.is_bot_running if error doesn't mean full stop
                            status_text=f"Error: {error_msg}",
                            color_hex=self.COLOR_ERROR,
                            is_connecting=False
                        )
                        # Decide if error means full stop or just a notification
                        # For now, let's assume it might not be a full stop unless thread dies.
                        # If it's a critical error, the bot thread might terminate, caught below.
                        # self._terminate_bot_thread() # If error always means stop
                        message_handled_that_affects_running_state = True # Error is a state
                # Handle other types of messages if needed
        except queue.Empty:
            pass
        except Exception as e:
            print(f"DiscordTab: Error checking IPC queue: {e}")

        if not message_handled_that_affects_running_state and \
           self.is_bot_running and \
           self._bot_thread and \
           not self._bot_thread.is_alive():
            print("DiscordTab: Bot thread no longer alive (post-queue check), but UI thought it was running. Resetting.")
            self._reset_bot_state_full() # This will update UI to offline

    # update_status_animation is REMOVED.

    def on_send_message_button_pressed(self, instance):
        """Handles the on_send_message_pressed event from DiscordBotStatus."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if not discord_bot_status_widget:
            print("DiscordTab: Error - DiscordBotStatus widget not found for sending message.")
            return

        message_to_send = discord_bot_status_widget.message_text
        manual_channel_id_to_use = discord_bot_status_widget.manual_send_channel_id

        if not self.is_bot_running or not message_to_send or not self._ipc_queue:
            print(f"DiscordTab: Cannot send message. Bot running: {self.is_bot_running}, Message: '{message_to_send}', IPC Queue: {bool(self._ipc_queue)}")
            return

        if not manual_channel_id_to_use: # Check the new manual channel ID field
            print("DiscordTab: Cannot send message. 'Channel ID to send' is not set in UI.")
            # Optionally, show a user notification
            return

        msg_data = {
            'command': 'send_message',
            'channel_id': manual_channel_id_to_use, # Use the new channel ID from the input field
            'content': message_to_send
        }
        try:
            self._ipc_queue.put(msg_data)
            print(f"DiscordTab: Sent message to IPC queue: {msg_data}")
            discord_bot_status_widget.message_text = "" # Clear input field in the child component
        except Exception as e:
            print(f"DiscordTab: Error sending message to IPC queue: {e}")


    def on_stop(self):
        """Ensure bot process is stopped when the application/widget is stopped."""
        print("DiscordTab: on_stop called, ensuring bot thread is terminated.")
        self._stop_bot_process()
        if self._bot_thread and self._bot_thread.is_alive():
            self._terminate_bot_thread()
