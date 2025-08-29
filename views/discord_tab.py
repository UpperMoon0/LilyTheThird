import threading
import queue
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.utils import get_color_from_hex
from kivy.lang import Builder

# Import settings manager functions
from settings_manager import load_discord_settings, save_discord_settings

# Import the function to run the bot in a separate process
from processes.discord_process import run_discord_bot

# Load the kv file for this widget
Builder.load_file('views/discord_tab.kv')

class DiscordTab(BoxLayout):
    """
    Kivy equivalent of the DiscordTab QWidget.
    Manages the Discord bot process and IPC with simplified settings (LLM removed).
    """
    # --- State Properties ---
    is_bot_running = BooleanProperty(False)
    _bot_thread = None
    _ipc_queue = None
    status_text = StringProperty("Not Running")
    toggle_button_text = StringProperty("Start Bot")
    discord_status_circle_color = ListProperty(get_color_from_hex("#808080"))

    # --- Config Properties (Specific to Discord) ---
    discord_token = StringProperty("")
    guild_id = StringProperty("")
    channel_id = StringProperty("")  # This is now the "Listening channel ID"
    master_discord_id = StringProperty("")
    lily_discord_id = StringProperty("")
    manual_send_channel_id_prop = StringProperty("")

    # LLM functionality removed

    # --- Message Properties ---
    message_text = StringProperty("")

    # --- Animation Properties ---
    idle_color_1 = ListProperty(get_color_from_hex("#C90000"))  # Red
    idle_color_2 = ListProperty(get_color_from_hex("#C4A000"))  # Yellow
    running_color_1 = ListProperty(get_color_from_hex("#00FF4C"))  # Green
    running_color_2 = ListProperty(get_color_from_hex("#00C4BA"))  # Turquoise
    anim = None  # Holds the current animation

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set the load and save functions for settings
        self.load_function = load_discord_settings
        self.save_function = save_discord_settings

        # Load non-LLM settings first
        self._load_discord_settings()

        # Bind property changes
        self.bind(discord_token=self.on_discord_token_changed)
        self.bind(guild_id=self.on_guild_id_changed)
        self.bind(channel_id=self.on_channel_id_changed)
        self.bind(master_discord_id=self.on_master_discord_id_changed)
        self.bind(lily_discord_id=self.on_lily_discord_id_changed)
        self.bind(manual_send_channel_id_prop=self.on_manual_send_channel_id_changed)

        Clock.schedule_once(self._post_init)
        Clock.schedule_interval(self._check_ipc_queue, 0.1)  # Check IPC queue periodically

    def _bind_discord_bot_status_events(self):
        """Binds events from the DiscordBotStatus component."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.bind(on_toggle_bot_pressed=self.toggle_bot)
            discord_bot_status_widget.bind(on_send_message_pressed=self.on_send_message_button_pressed)
        else:
            print("DiscordTab: Error - Could not find DiscordBotStatus widget to bind events.")

    def _load_discord_settings(self):
        """Load Discord-specific settings including LLM settings."""
        if not self.load_function:
            print("DiscordTab: Error - load_function not set. Cannot load settings.")
            return

        settings = self.load_function()
        print(f"DiscordTab: Loading settings using {self.load_function.__name__}")

        # Load Discord-specific settings
        self.discord_token = settings.get('discord_token', '')
        self.guild_id = settings.get('guild_id', '')
        self.channel_id = settings.get('channel_id', '')  # Listening channel ID
        self.master_discord_id = settings.get('master_discord_id', '')
        self.lily_discord_id = settings.get('lily_discord_id', '')
        self.manual_send_channel_id_prop = settings.get('manual_send_channel_id', '')

        # LLM settings removed

    def save_all_discord_settings(self):
        """Saves all Discord tab settings."""
        if not self.load_function or not self.save_function:
            print("DiscordTab: Error - load_function or save_function not set. Cannot save settings.")
            return

        settings = self.load_function()  # Load existing settings to preserve other values

        # Update Discord-specific settings
        settings['discord_token'] = self.discord_token
        settings['guild_id'] = self.guild_id
        settings['channel_id'] = self.channel_id  # Listening channel ID
        settings['master_discord_id'] = self.master_discord_id
        settings['lily_discord_id'] = self.lily_discord_id
        settings['manual_send_channel_id'] = self.manual_send_channel_id_prop

        # LLM settings removed

        self.save_function(settings)
        print(f"DiscordTab: All settings saved using {self.save_function.__name__}.")

    # --- Discord Property Change Handlers ---
    def on_discord_token_changed(self, instance, value):
        print(f"DiscordTab: Discord Token changed. Length: {len(value)}")

    def on_guild_id_changed(self, instance, value):
        print(f"DiscordTab: Guild ID changed to {value}")

    def on_channel_id_changed(self, instance, value):
        print(f"DiscordTab: Channel ID changed to {value}")

    def on_master_discord_id_changed(self, instance, value):
        print(f"DiscordTab: Master Discord ID changed to {value}")

    def on_lily_discord_id_changed(self, instance, value):
        print(f"DiscordTab: Lily Discord ID changed to {value}")

    def on_manual_send_channel_id_changed(self, instance, value):
        print(f"DiscordTab: Manual Send Channel ID changed to {value}")

    def _post_init(self, dt):
        """Called after the widget is fully initialized."""
        # Bind events from the child component
        self._bind_discord_bot_status_events()
        # Start the initial animation
        self.update_status_animation()
        # Set initial state for message section in DiscordBotStatus
        self._update_discord_bot_status_widget_properties()

    # --- Bot Control ---
    def toggle_bot(self, instance=None):
        """Start or stop the Discord bot process."""
        if self.is_bot_running:
            self._stop_bot_process()
        else:
            self._start_bot_process()

    def _start_bot_process(self):
        """Starts the Discord bot in a separate thread."""
        if self._bot_thread and self._bot_thread.is_alive():
            print("DiscordTab: Bot thread is already running.")
            return

        if not self.discord_token:
            print("DiscordTab: Discord Token is not set. Cannot start bot.")
            self.status_text = "Error: Token Missing"
            return

        self._ipc_queue = queue.Queue()

        discord_config = {
            'discord_token': self.discord_token,
            'guild_id': self.guild_id,
            'channel_id': self.channel_id,
            'master_discord_id': self.master_discord_id,
            'lily_discord_id': self.lily_discord_id,
        }
        print(f"DiscordTab: Starting bot with config: {discord_config}")

        try:
            self._bot_thread = threading.Thread(
                target=run_discord_bot,
                args=(self._ipc_queue, discord_config)
            )
            self._bot_thread.daemon = True  # Ensure thread exits when main app exits
            self._bot_thread.start()

            self.status_text = "Starting..."
            self.toggle_button_text = "Stop Bot"
            print("DiscordTab: Bot thread started.")
        except Exception as e:
            print(f"DiscordTab: Failed to start bot thread: {e}")
            self.status_text = "Error Starting"
            self.is_bot_running = False
            self._reset_bot_state()

        self.update_status_animation()
        self._update_discord_bot_status_widget_properties()

    def _stop_bot_process(self):
        """Stops the Discord bot thread gracefully."""
        if self._bot_thread and self._bot_thread.is_alive() and self._ipc_queue:
            print("DiscordTab: Sending shutdown command to bot thread...")
            try:
                self._ipc_queue.put({'command': 'shutdown'})
                self.status_text = "Stopping..."
            except Exception as e:
                print(f"DiscordTab: Error sending shutdown to IPC queue: {e}")
                self._terminate_bot_process()
        else:
            print("DiscordTab: Bot thread not running or IPC queue not available.")
            self._reset_bot_state()

        self.update_status_animation()

    def _terminate_bot_process(self):
        """Attempts to signal the bot thread to stop and resets state."""
        if self._bot_thread and self._bot_thread.is_alive():
            print("DiscordTab: Signaling bot thread to stop.")
            if self._ipc_queue:
                try:
                    self._ipc_queue.put({'command': 'shutdown'})
                except Exception as e:
                    print(f"DiscordTab: Error sending shutdown to IPC during terminate: {e}")
            print("DiscordTab: Note - Threads cannot be forcefully terminated. Relying on graceful shutdown.")
        self._reset_bot_state()

    def _reset_bot_state(self):
        """Resets UI and internal state related to the bot."""
        self.is_bot_running = False
        self.status_text = "Not Running"
        self.toggle_button_text = "Start Bot"
        self._bot_thread = None
        self._ipc_queue = None
        self.update_status_animation()
        self._update_discord_bot_status_widget_properties()
        print("DiscordTab: Bot state reset.")

    def _update_discord_bot_status_widget_properties(self):
        """Updates properties of the DiscordBotStatus widget."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if discord_bot_status_widget:
            discord_bot_status_widget.status_text = self.status_text
            discord_bot_status_widget.toggle_button_text = self.toggle_button_text
            discord_bot_status_widget.message_section_visible = self.is_bot_running
            discord_bot_status_widget.manual_send_channel_id = self.manual_send_channel_id_prop
        else:
            pass

    def _check_ipc_queue(self, dt):
        """Periodically checks the IPC queue for messages from the bot thread."""
        if not self._ipc_queue:
            if self.is_bot_running and self._bot_thread and not self._bot_thread.is_alive():
                print("DiscordTab: Bot thread died unexpectedly.")
                self._reset_bot_state()
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
                        self.update_status_animation()
                        self._update_discord_bot_status_widget_properties()
                        message_handled_that_affects_running_state = True
                        print("DiscordTab: Bot is ready.")
                    elif status == 'stopped':
                        print("DiscordTab: Bot reported stopped.")
                        self._reset_bot_state()
                        message_handled_that_affects_running_state = True
                    elif status == 'error':
                        error_msg = message.get('message', 'Unknown error')
                        print(f"DiscordTab: Bot reported an error: {error_msg}")
                        self.status_text = f"Error: {error_msg}"
                        self._terminate_bot_process()
                        message_handled_that_affects_running_state = True
        except queue.Empty:
            pass  # No message, normal
        except Exception as e:
            print(f"DiscordTab: Error checking IPC queue: {e}")

        # Check if bot thread died unexpectedly
        if not message_handled_that_affects_running_state and \
           self.is_bot_running and \
           self._bot_thread and \
           not self._bot_thread.is_alive():
            print("DiscordTab: Bot thread died unexpectedly.")
            self._reset_bot_state()

    def update_status_animation(self):
        """Update the animation of the status circle based on bot state."""
        if self.anim:
            Animation.cancel_all(self, 'discord_status_circle_color')

        if self.is_bot_running:
            color1 = self.running_color_1
            color2 = self.running_color_2
        else:
            color1 = self.idle_color_1
            color2 = self.idle_color_2

        self.anim = Animation(discord_status_circle_color=color2, duration=0.75) + \
                    Animation(discord_status_circle_color=color1, duration=0.75)
        self.anim.repeat = True
        self.anim.start(self)

    def on_send_message_button_pressed(self, instance):
        """Handles the on_send_message_pressed event from DiscordBotStatus."""
        discord_bot_status_widget = self.ids.get('discord_bot_status_id')
        if not discord_bot_status_widget:
            print("DiscordTab: Error - DiscordBotStatus widget not found.")
            return

        message_to_send = discord_bot_status_widget.message_text
        manual_channel_id_to_use = discord_bot_status_widget.manual_send_channel_id

        if not self.is_bot_running or not message_to_send or not self._ipc_queue:
            print(f"DiscordTab: Cannot send message. Bot running: {self.is_bot_running}")
            return

        if not manual_channel_id_to_use:
            print("DiscordTab: Manual channel ID not set.")
            return

        msg_data = {
            'command': 'send_message',
            'channel_id': manual_channel_id_to_use,
            'content': message_to_send
        }
        try:
            self._ipc_queue.put(msg_data)
            print(f"DiscordTab: Sent message to IPC queue: {msg_data}")
            discord_bot_status_widget.message_text = ""  # Clear input field
        except Exception as e:
            print(f"DiscordTab: Error sending message to IPC queue: {e}")

    def on_stop(self):
        """Ensure bot process is stopped when the application exits."""
        print("DiscordTab: Stopping bot process...")
        self._stop_bot_process()
        if self._bot_thread and self._bot_thread.is_alive():
            self._terminate_bot_process()