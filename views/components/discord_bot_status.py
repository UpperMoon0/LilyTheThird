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

    def update_status(self, is_online: bool, status_text: str, color_hex: str, is_connecting: bool = False):
        """
        Updates the visual status of the bot.
        If is_connecting is True, the color circle will pulsate.
        """
        self.status_text = status_text
        self.toggle_button_text = "Stop Bot" if is_online else "Start Bot"
        self.message_section_visible = is_online

        color_circle_widget = self.ids.get('status_display_layout', {}).children[1] # Assuming ColorCircle is the second child
        if not hasattr(color_circle_widget, 'set_color_hex'): # Check if it's the ColorCircle
            # Fallback or error handling if the widget structure is not as expected
            # This might happen if ids are not correctly assigned or kv structure changes
            for child in self.ids.get('status_display_layout', {}).children:
                if hasattr(child, 'set_color_hex'): # Find the ColorCircle
                    color_circle_widget = child
                    break
            else: # If no ColorCircle found
                print("Error: ColorCircle widget not found in discord_bot_status.kv")
                self.status_circle_color = get_color_from_hex(color_hex) # Fallback to old method
                return

        if is_connecting:
            color_circle_widget.set_color_hex(color_hex) # Set base color for animation
            color_circle_widget.start_pulsing_animation()
        else:
            color_circle_widget.stop_animation() # Stop animation if it was running
            color_circle_widget.set_color_hex(color_hex) # Set static color
        # self.status_circle_color = get_color_from_hex(color_hex) # Keep this for direct binding if needed elsewhere

    def on_toggle_bot_pressed(self, *args):
        """
        Default handler for the 'on_toggle_bot_pressed' event.
        """
        # print("DiscordBotStatus: on_toggle_bot_pressed event dispatched")
        pass

    def on_send_message_pressed(self, *args):
        """
        Default handler for the 'on_send_message_pressed' event.
        """
        # print("DiscordBotStatus: on_send_message_pressed event dispatched")
        pass
