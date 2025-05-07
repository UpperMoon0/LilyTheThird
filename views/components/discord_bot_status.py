from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty
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

    # Register the event that will be dispatched when the button is pressed
    __events__ = ('on_toggle_bot_pressed',)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Properties are bound in the kv file.

    def on_toggle_bot_pressed(self, *args):
        """
        Default handler for the 'on_toggle_bot_pressed' event.
        This method is required by Kivy when an event is registered.
        The actual logic will be handled by the parent widget (DiscordTab)
        that binds to this event.
        """
        # print("DiscordBotStatus: on_toggle_bot_pressed event dispatched")
        pass
