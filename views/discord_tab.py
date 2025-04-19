import os
import time
from multiprocessing import Process, Queue

from PyQt5.QtCore import (
    Qt,
    QPropertyAnimation,
    Qt
)
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QWidget, QComboBox) # Added QComboBox
from dotenv import load_dotenv

# Import models from central config
from config.models import OPENAI_MODELS, GEMINI_MODELS
# Import settings manager
from settings_manager import load_settings, save_settings
from processes.discord_process import run_discord_bot
from views.components.color_circle import ColorCircle

class DiscordTab(QWidget):
    def __init__(self):
        super().__init__()
        self._initializing = True # Flag to prevent signals during setup
        self.settings = load_settings() # Load settings first

        load_dotenv()  # Load environment variables from .env file

        self.bot_process = None
        self.is_bot_running = False
        self.ipc_queue = None  # Will hold the multiprocessing.Queue for IPC

        # --- UI Setup (Apply loaded settings) ---

        # LLM Provider Selector for Discord Bot
        self.discord_provider_label = QLabel("Bot LLM Provider:", self)
        self.discord_provider_selector = QComboBox(self)
        self.discord_provider_selector.addItems(["OpenAI", "Gemini"])
        # Set loaded provider *before* connecting signals
        provider_key = 'discord_selected_provider'
        default_provider = 'OpenAI' # Default if not found
        provider_index = self.discord_provider_selector.findText(self.settings.get(provider_key, default_provider))
        if provider_index != -1:
            self.discord_provider_selector.setCurrentIndex(provider_index)
        # Connect signal LATER

        # LLM Model Selector for Discord Bot
        self.discord_model_label = QLabel("Bot LLM Model:", self)
        self.discord_model_selector = QComboBox(self)
        # Populate models based on the *loaded* provider first
        self._update_discord_model_selector(set_from_settings=True)
        # Connect signal LATER

        # Replace QLabel status circle with ColorCircle
        self.status_circle = ColorCircle(self)

        # Create animations
        self.idle_animation = QPropertyAnimation(self.status_circle, b"color")
        self.idle_animation.setDuration(1500)
        self.idle_animation.setLoopCount(-1)  # Infinite loop
        self.setup_idle_animation()

        self.running_animation = QPropertyAnimation(self.status_circle, b"color")
        self.running_animation.setDuration(1500)
        self.running_animation.setLoopCount(-1)
        self.setup_running_animation()

        # Start the idle animation when the app starts
        self.idle_animation.start()

        self.toggle_bot_button = QPushButton("Start Bot", self)
        self.toggle_bot_button.clicked.connect(self.on_toggle_bot_clicked)
        self.toggle_bot_button.setStyleSheet("width: 200px; height: 40px;")

        self.status_label = QLabel("Not Running", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("text-align: center;")

        # Load guild_id and channel_id from .env and set in the input fields
        self.guild_id_input = QLineEdit(self)
        self.guild_id_input.setPlaceholderText("Enter Guild ID")
        self.guild_id_input.setText(os.getenv("DISCORD_GUILD_ID"))
        self.guild_id_input.setStyleSheet("width: 300px; height: 30px;")

        self.channel_id_input = QLineEdit(self)
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setText(os.getenv("DISCORD_CHANNEL_ID"))
        self.channel_id_input.setStyleSheet("width: 300px; height: 30px;")

        # Show message input and send button for IPC messaging
        self.message_input = QLineEdit(self)
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setVisible(False)
        self.message_input.setStyleSheet("width: 300px; height: 30px;")

        self.send_message_button = QPushButton("Send Message", self)
        self.send_message_button.clicked.connect(self.on_send_message_clicked)
        self.send_message_button.setVisible(False)
        self.send_message_button.setStyleSheet("width: 200px; height: 40px;")

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.save_button.setStyleSheet("width: 200px; height: 40px;")

        # --- Layouts ---

        # Status layout with button and status label
        status_layout = QVBoxLayout()
        status_layout.setAlignment(Qt.AlignCenter)

        status_circle_layout = QHBoxLayout()
        status_circle_layout.addStretch()
        status_circle_layout.addWidget(self.status_circle)
        status_circle_layout.addStretch()
        status_layout.addLayout(status_circle_layout)

        toggle_button_layout = QHBoxLayout()
        toggle_button_layout.addStretch()
        toggle_button_layout.addWidget(self.toggle_bot_button)
        toggle_button_layout.addStretch()
        status_layout.addLayout(toggle_button_layout)

        status_label_layout = QHBoxLayout()
        status_label_layout.addStretch()
        status_label_layout.addWidget(self.status_label)
        status_label_layout.addStretch()
        status_layout.addLayout(status_label_layout)

        # Input layout
        input_layout = QVBoxLayout()
        input_layout.setAlignment(Qt.AlignCenter)

        guild_id_layout = QHBoxLayout()
        guild_id_layout.addStretch()
        guild_id_layout.addWidget(self.guild_id_input)
        guild_id_layout.addStretch()
        input_layout.addLayout(guild_id_layout)

        channel_id_layout = QHBoxLayout()
        channel_id_layout.addStretch()
        channel_id_layout.addWidget(self.channel_id_input)
        channel_id_layout.addStretch()
        input_layout.addLayout(channel_id_layout)

        # Add LLM selectors to input layout
        discord_provider_layout = QHBoxLayout()
        discord_provider_layout.addStretch()
        discord_provider_layout.addWidget(self.discord_provider_label)
        discord_provider_layout.addWidget(self.discord_provider_selector)
        discord_provider_layout.addStretch()
        input_layout.addLayout(discord_provider_layout)

        discord_model_layout = QHBoxLayout()
        discord_model_layout.addStretch()
        discord_model_layout.addWidget(self.discord_model_label)
        discord_model_layout.addWidget(self.discord_model_selector)
        discord_model_layout.addStretch()
        input_layout.addLayout(discord_model_layout)

        save_button_layout = QHBoxLayout()
        save_button_layout.addStretch()
        save_button_layout.addWidget(self.save_button)
        save_button_layout.addStretch()
        input_layout.addLayout(save_button_layout)

        message_input_layout = QHBoxLayout()
        message_input_layout.addStretch()
        message_input_layout.addWidget(self.message_input)
        message_input_layout.addStretch()
        input_layout.addLayout(message_input_layout)

        send_button_layout = QHBoxLayout()
        send_button_layout.addStretch()
        send_button_layout.addWidget(self.send_message_button)
        send_button_layout.addStretch()
        input_layout.addLayout(send_button_layout)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.addLayout(status_layout)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

        # NOW connect the signals that should trigger saving settings
        self.discord_provider_selector.currentIndexChanged.connect(self.on_discord_provider_changed)
        self.discord_model_selector.currentIndexChanged.connect(self.on_discord_model_changed)

        self._initializing = False # Setup complete

    def _save_discord_settings(self):
        """Gathers current discord settings and saves them."""
        if self._initializing: # Don't save during initial setup
            return

        current_settings = {
            'discord_selected_provider': self.discord_provider_selector.currentText(),
            'discord_selected_model': self.discord_model_selector.currentText()
        }
        # Update the in-memory settings object as well
        self.settings.update(current_settings)
        save_settings(self.settings)
        print("Discord LLM settings saved.") # Add confirmation

    def _update_discord_model_selector(self, set_from_settings=False):
        """Populates the Discord model selector based on the selected provider."""
        selected_provider = self.discord_provider_selector.currentText().lower()
        # Block signals during modification to prevent premature triggers
        self.discord_model_selector.blockSignals(True)
        self.discord_model_selector.clear() # Clear existing items

        model_list = []
        if selected_provider == 'openai':
            model_list = OPENAI_MODELS
        elif selected_provider == 'gemini':
            model_list = GEMINI_MODELS

        if model_list:
            self.discord_model_selector.addItems(model_list)
            if set_from_settings:
                # Try to set the loaded model
                model_key = 'discord_selected_model'
                loaded_model = self.settings.get(model_key)
                model_index = self.discord_model_selector.findText(loaded_model)
                if model_index != -1:
                    self.discord_model_selector.setCurrentIndex(model_index)
                elif model_list: # Fallback to first if loaded model not found
                    self.discord_model_selector.setCurrentIndex(0)
            elif model_list: # Default to first if not setting from saved
                self.discord_model_selector.setCurrentIndex(0)

        self.discord_model_selector.blockSignals(False) # Unblock signals
        # Save settings if the model was changed *not* during initial load
        if not set_from_settings:
             self._save_discord_settings()


    def on_discord_provider_changed(self):
        """Handles the change in the Discord LLM provider selection."""
        if self._initializing:
            return
        print("Discord LLM Provider selection changed.")
        self._update_discord_model_selector() # Update models (saves settings inside if not initializing)
        # No need to re-initialize LLM here, settings are saved automatically.

    def on_discord_model_changed(self):
        """Handles the change in the Discord LLM model selection."""
        if self._initializing:
            return
        print("Discord LLM Model selection changed.")
        # Save settings if the model text is valid
        if self.discord_model_selector.currentText():
            self._save_discord_settings()


    def setup_idle_animation(self):
        # Create keyframes for smoother animation
        self.idle_animation.setKeyValueAt(0, QColor(201, 0, 0))    # Red
        self.idle_animation.setKeyValueAt(0.5, QColor(196, 160, 0))  # Yellow
        self.idle_animation.setKeyValueAt(1, QColor(201, 0, 0))      # Back to red

    def setup_running_animation(self):
        # Create keyframes for smoother animation
        self.running_animation.setKeyValueAt(0, QColor(0, 255, 76))      # Green
        self.running_animation.setKeyValueAt(0.5, QColor(0, 196, 186))     # Turquoise
        self.running_animation.setKeyValueAt(1, QColor(0, 255, 76))      # Back to green

    def update_status(self, status):
        self.status_label.setText(status)
        # Stop both animations first
        self.idle_animation.stop()
        self.running_animation.stop()
        if status == "Running":
            self.running_animation.start()
        else:
            self.idle_animation.start()

    def on_toggle_bot_clicked(self):
        if not self.is_bot_running:
            self.update_status("Starting")
            self.toggle_bot_button.setEnabled(False)
            # Get selected LLM config
            selected_provider = self.discord_provider_selector.currentText().lower()
            selected_model = self.discord_model_selector.currentText()

            if not selected_model:
                 print("Error: No model selected for Discord bot.")
                 self.update_status("Error: No model selected")
                 self.toggle_bot_button.setEnabled(True) # Re-enable button
                 return

            # Create config dictionary using the keys expected by DiscordBot
            discord_config = {
                'discord_llm_provider': selected_provider, # Use 'discord_llm_provider'
                'discord_llm_model': selected_model,       # Use 'discord_llm_model'
                'guild_id': self.guild_id_input.text(),
                'channel_id': self.channel_id_input.text()
            }

            # Create a new IPC queue for communication
            self.ipc_queue = Queue()
            # Start the Discord bot in a new process, passing the config and queue
            self.bot_process = Process(target=run_discord_bot, args=(self.ipc_queue, discord_config))
            self.bot_process.start()
            # For simplicity, assume the bot is ready soon.
            self.is_bot_running = True
            self.on_bot_ready()
        else:
            self.update_status("Stopping")
            self.toggle_bot_button.setEnabled(False)

            if self.bot_process is not None:
                # Send shutdown command through IPC
                if self.ipc_queue:
                    self.ipc_queue.put({"command": "shutdown"})

                    # Wait briefly for graceful shutdown (max 5 seconds)
                    timeout = 5.0
                    start_time = time.time()
                    while self.bot_process.is_alive() and time.time() - start_time < timeout:
                        time.sleep(0.1)

                # If bot is still running after timeout, terminate it
                if self.bot_process.is_alive():
                    self.bot_process.terminate()
                    self.bot_process.join()

                self.bot_process = None

            self.is_bot_running = False
            self.ipc_queue = None  # Clear IPC queue reference
            self.on_bot_stopped()

    def on_bot_ready(self):
        self.update_status("Running")
        self.toggle_bot_button.setText("Stop Bot")
        self.toggle_bot_button.setEnabled(True)
        # Show message input and send button for IPC messaging:
        self.message_input.setVisible(True)
        self.send_message_button.setVisible(True)

    def on_bot_stopped(self):
        self.update_status("Not Running")
        self.toggle_bot_button.setText("Start Bot")
        self.toggle_bot_button.setEnabled(True)
        self.message_input.setVisible(False)
        self.send_message_button.setVisible(False)

    def on_send_message_clicked(self):
        if self.ipc_queue:
            msg_text = self.message_input.text().strip()
            if msg_text:
                try:
                    channel_id = int(self.channel_id_input.text())
                except ValueError:
                    print("Invalid Channel ID entered.")
                    return
                message = {"channel_id": channel_id, "content": msg_text}
                self.ipc_queue.put(message)
                print("Sent message via IPC:", message)
                self.message_input.clear()
        else:
            print("IPC channel is not available.")

    def on_save_clicked(self):
        guild_id_text = self.guild_id_input.text()
        channel_id_text = self.channel_id_input.text()
        # --- Save Guild ID and Channel ID to .env ---
        # Note: This saves to the *current* environment variables,
        # but doesn't persist them in the .env file itself unless we write to it.
        # For simplicity, we'll just update os.environ for the current session.
        # LLM settings are saved automatically via signals now.
        guild_id_updated = False
        channel_id_updated = False

        if guild_id_text:
            try:
                int(guild_id_text)
                os.environ["DISCORD_GUILD_ID"] = guild_id_text # Update env var
                print(f"Guild ID updated in environment: {guild_id_text}")
                guild_id_updated = True
            except ValueError:
                print("Invalid Guild ID entered.")

        if channel_id_text:
            try:
                int(channel_id_text)
                os.environ["DISCORD_CHANNEL_ID"] = channel_id_text # Update env var
                print(f"Channel ID updated in environment: {channel_id_text}")
                channel_id_updated = True
            except ValueError:
                print("Invalid Channel ID entered.")

        if guild_id_updated or channel_id_updated:
            print("Guild/Channel IDs updated for this session. LLM settings are saved automatically.")
            # TODO: Consider writing to .env file here if persistence is needed across restarts.
        else:
            print("No valid Guild/Channel ID changes detected.")


    def setup_hook(self):
        pass
