from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty, ObjectProperty, NumericProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.utils import get_color_from_hex
import os

# Import the custom ColorCircle component
from views.components.color_circle import ColorCircle

# Load the corresponding kv file
Builder.load_file('views/discord_tab.kv')

class DiscordTab(BoxLayout):
    """
    Kivy equivalent of the DiscordTab QWidget.
    """
    # --- State Properties ---
    is_bot_running = BooleanProperty(False)
    status_text = StringProperty("Not Running")
    toggle_button_text = StringProperty("Start Bot")
    message_section_visible = BooleanProperty(False) # Controls visibility of message input/button

    # --- Config Properties ---
    guild_id = StringProperty("")
    channel_id = StringProperty("")
    llm_providers = ListProperty(["OpenAI", "Gemini"]) # Example providers
    llm_models = ListProperty([]) # Models will depend on the selected provider
    selected_provider = StringProperty("OpenAI") # Default provider
    selected_model = StringProperty("")

    # --- Message Properties ---
    message_text = StringProperty("")

    # --- Widget References (Optional, if needed for direct access) ---
    status_circle = ObjectProperty(None) # Reference to the ColorCircle widget

    # --- Animation Properties ---
    idle_color_1 = ListProperty(get_color_from_hex("#C90000")) # Red
    idle_color_2 = ListProperty(get_color_from_hex("#C4A000")) # Yellow
    running_color_1 = ListProperty(get_color_from_hex("#00FF4C")) # Green
    running_color_2 = ListProperty(get_color_from_hex("#00C4BA")) # Turquoise
    anim = None # Holds the current animation

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init)

    def _post_init(self, dt):
        # Initial population of models based on default provider
        self.update_models()
        # Start the initial animation
        self.update_status_animation()
        # Load saved settings if available (placeholder)
        self.load_settings()

    def load_settings(self):
        # Placeholder: Load Guild ID, Channel ID, Provider, Model from a config file/storage
        print("Loading Discord settings (Simulated)")
        # Example: self.guild_id = loaded_guild_id
        # Example: self.channel_id = loaded_channel_id
        # Example: self.selected_provider = loaded_provider
        # Example: self.update_models() # Update models based on loaded provider
        # Example: self.selected_model = loaded_model

    def save_settings(self):
        """Save the current configuration."""
        # Placeholder: Save Guild ID, Channel ID, Provider, Model
        print(f"Saving Discord settings:")
        print(f"  Guild ID: {self.guild_id}")
        print(f"  Channel ID: {self.channel_id}")
        print(f"  Provider: {self.selected_provider}")
        print(f"  Model: {self.selected_model}")
        # Add actual saving logic here (e.g., to JSON file, settings manager)

    def update_models(self, *args):
        """Update the list of models based on the selected provider."""
        # Placeholder logic: Replace with actual model fetching
        if self.selected_provider == "OpenAI":
            self.llm_models = ["gpt-4-discord", "gpt-3.5-turbo-discord"]
            self.selected_model = "gpt-4-discord" if "gpt-4-discord" in self.llm_models else ""
        elif self.selected_provider == "Gemini":
            self.llm_models = ["gemini-pro-discord", "gemini-1.5-flash-discord"]
            self.selected_model = "gemini-pro-discord" if "gemini-pro-discord" in self.llm_models else ""
        else:
            self.llm_models = []
            self.selected_model = ""
        print(f"Discord Provider changed to: {self.selected_provider}, Models: {self.llm_models}")

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
