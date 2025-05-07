from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.lang import Builder
from kivy.utils import get_color_from_hex # For default color

Builder.load_file('views/components/discord_bot_status.kv')

class DiscordBotStatus(BoxLayout):
    """
    A component to display Discord bot status, including a status circle,
    a start/stop button, and a status text label.
    """
    status_circle_color = ListProperty(get_color_from_hex("#808080")) # Default to gray
    toggle_button_text = StringProperty("Start Bot")
    status_text = StringProperty("Bot is Offline")
    message_text = StringProperty("")
    manual_send_channel_id = StringProperty("") # New property for the manual send channel ID
    message_section_visible = BooleanProperty(False) # Default to hidden

    # Register the events that will be dispatched
    __events__ = ('on_toggle_bot_pressed', 'on_send_message_pressed')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Properties are bound in the kv file.

    def on_toggle_bot_pressed(self, *args):
        """
        Default handler for the 'on_toggle_bot_pressed' event.
        """
        print("DiscordBotStatus: on_toggle_bot_pressed event dispatched from component")
        pass

    def on_send_message_pressed(self, *args):
        """
        Default handler for the 'on_send_message_pressed' event.
        """
        # print("DiscordBotStatus: on_send_message_pressed event dispatched")
        pass
