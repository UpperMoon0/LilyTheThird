from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ColorProperty, BooleanProperty, ObjectProperty

class DiscordBotStatus(BoxLayout):
    parent_toggle_bot_callback = ObjectProperty(None)
    toggle_button_text = StringProperty("Start Bot")
    status_text = StringProperty("Not Running")
    bot_status = BooleanProperty(False) # False for Not Running (red), True for Running (green)
    status_circle_color = ColorProperty([1, 0, 0, 1]) # Default to red

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(bot_status=self.update_status_visuals)
        self.update_status_visuals() # Initial update

    def update_status_visuals(self, *args):
        if self.bot_status:
            self.status_text = "Running"
            self.toggle_button_text = "Stop Bot"
            self.ids.status_circle.color = [0, 1, 0, 1] # Green
        else:
            self.status_text = "Not Running"
            self.toggle_button_text = "Start Bot"
            self.ids.status_circle.color = [1, 0, 0, 1] # Red

    def toggle_bot(self):
        if self.parent_toggle_bot_callback:
            self.parent_toggle_bot_callback()
        else:
            print("DiscordBotStatus: parent_toggle_bot_callback not set")
