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
    # message_section_visible is now in DiscordBotStatus

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
        self.bind(channel_id=self.on_channel_id_changed) # This is for the "Listening channel ID"
        self.bind(master_discord_id=self.on_master_discord_id_changed)
        self.bind(lily_discord_id=self.on_lily_discord_id_changed)
        self.bind(manual_send_channel_id_prop=self.on_manual_send_channel_id_changed)

        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)
        Clock.schedule_interval(self._check_ipc_queue, 0.1) # Check IPC queue periodically

    def _bind_discord_bot_status_events(self):
        """Binds events from the DiscordBotStatus component."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id') # Assuming you add an id in kv
        if discord_bot_status_widget:
            discord_bot_status_widget.bind(on_toggle_bot_pressed=self.toggle_bot)
            discord_bot_status_widget.bind(on_send_message_pressed=self.on_send_message_button_pressed)
            # Bind message_text and message_section_visible if DiscordTab needs to react to them
            # For now, DiscordTab will set them on the component.
        else:
            print("DiscordTab: Error - Could not find DiscordBotStatus widget to bind events.")


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
        # This will use self.load_function (load_discord_settings)
        self._load_llm_settings()
        self.update_models(initial_load=True)
        # Bind events from the child component
        self._bind_discord_bot_status_events()
        # Start the initial animation
        self.update_status_animation()
        # Set initial state for message section in DiscordBotStatus
        self._update_discord_bot_status_widget_properties()


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
        # Update the child component if it's already created
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.manual_send_channel_id = value


    # --- Bot Control ---
    def toggle_bot(self, instance=None): # Added instance=None to accept the argument from event dispatch
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
            
            self.status_text = "Starting..."
            self.toggle_button_text = "Stop Bot"
            # self.is_bot_running will be set to True by _check_ipc_queue on 'ready'
            # self._update_discord_bot_status_widget_properties() # Update child component
            print("DiscordTab: Bot thread started.") # Changed comment
        except Exception as e:
            print(f"DiscordTab: Failed to start bot thread: {e}") # Changed comment
            self.status_text = "Error Starting"
            self.is_bot_running = False # Ensure state is correct
            self._reset_bot_state() # This will also update the child component

        self.update_status_animation() # This updates parent's circle, child's circle is bound in KV
        self._update_discord_bot_status_widget_properties()


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
            print("DiscordTab: Signaling bot thread to stop.") 
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
        # self.message_section_visible = False # Handled by child
        self._bot_thread = None
        self._ipc_queue = None
        self.update_status_animation() # Updates parent's circle
        self._update_discord_bot_status_widget_properties() # Update child component
        print("DiscordTab: Bot state reset.")

    def _update_discord_bot_status_widget_properties(self):
        """Updates properties of the DiscordBotStatus widget based on DiscordTab's state."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.status_text = self.status_text
            discord_bot_status_widget.toggle_button_text = self.toggle_button_text
            # discord_bot_status_widget.status_circle_color = self.discord_status_circle_color # Now bound directly in KV
            discord_bot_status_widget.message_section_visible = self.is_bot_running # Show if bot is running
            discord_bot_status_widget.manual_send_channel_id = self.manual_send_channel_id_prop # Update child
        else:
            pass


    def _check_ipc_queue(self, dt):
        """Periodically checks the IPC queue for messages from the bot thread.""" # Changed comment
        if not self._ipc_queue:
            if self.is_bot_running and self._bot_thread and not self._bot_thread.is_alive():
                print("DiscordTab: Bot thread died (no IPC queue, was running). Resetting.")
                self._reset_bot_state() # Calls update_status_animation
            elif self.is_bot_running and not self._bot_thread: # Bot was running, but thread object lost
                print("DiscordTab: Bot thread object lost (no IPC queue, was running). Resetting.")
                self._reset_bot_state() # Calls update_status_animation
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
                        self.status_text = f"Running as {message.get('user', 'Bot')}"
                        self.toggle_button_text = "Stop Bot"
                        # self.message_section_visible = True # Handled by child via _update_discord_bot_status_widget_properties
                        self.update_status_animation() # Update parent's circle
                        self._update_discord_bot_status_widget_properties() # Update child component
                        message_handled_that_affects_running_state = True
                        print("DiscordTab: Bot is ready.")
                    elif status == 'stopped':
                        print("DiscordTab: Bot reported stopped.")
                        self._reset_bot_state() # Calls update_status_animation and _update_discord_bot_status_widget_properties
                        message_handled_that_affects_running_state = True
                    elif status == 'error':
                        error_msg = message.get('message', 'Unknown error')
                        print(f"DiscordTab: Bot reported an error: {error_msg}")
                        self.status_text = f"Error: {error_msg}"
                        self._terminate_bot_process() # Calls _reset_bot_state
                        message_handled_that_affects_running_state = True
                # Handle other types of messages if needed
        except queue.Empty:
            pass # No message, normal
        except Exception as e:
            print(f"DiscordTab: Error checking IPC queue: {e}")

        # If no message was processed that explicitly set the running state (like 'ready' or 'stopped'),
        # then check if the bot thread died unexpectedly while we thought it was running.
        if not message_handled_that_affects_running_state and \
           self.is_bot_running and \
           self._bot_thread and \
           not self._bot_thread.is_alive():
            print("DiscordTab: Bot thread no longer alive (post-queue check), but UI thinks it's running. Resetting.")
            self._reset_bot_state()

    def update_status_animation(self):
        """Update the animation of the status circle based on bot state."""
        if self.anim:
            # Cancel any existing animation on this property for this widget
            Animation.cancel_all(self, 'discord_status_circle_color')
            # It's good practice to also nullify self.anim if you're about to create a new one
            # or if the state means no animation should run (though here we always start one).

        if self.is_bot_running:
            color1 = self.running_color_1
            color2 = self.running_color_2
            # print(f"DiscordTab: Animating RUNNING between {color1} and {color2}")
        else:
            color1 = self.idle_color_1
            color2 = self.idle_color_2
            # print(f"DiscordTab: Animating IDLE between {color1} and {color2}")

        # Create a new pulsating animation on the discord_status_circle_color property of self (DiscordTab)
        self.anim = Animation(discord_status_circle_color=color2, duration=0.75) + \
                    Animation(discord_status_circle_color=color1, duration=0.75)
        self.anim.repeat = True
        self.anim.start(self) # Start the animation on 'self' (the DiscordTab instance)

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
        print("DiscordTab: on_stop called, ensuring bot process is terminated.")
        self._stop_bot_process()
        if self._bot_thread and self._bot_thread.is_alive(): # Changed to _bot_thread
            self._terminate_bot_process() # Force terminate if graceful stop failed
