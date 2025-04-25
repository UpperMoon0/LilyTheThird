from kivy.uix.boxlayout import BoxLayout
from kivy.properties import BooleanProperty
from kivy.lang import Builder
from kivy.event import EventDispatcher

# Load the corresponding kv file
Builder.load_file('views/components/chatbox_settings.kv')

class ChatboxSettings(BoxLayout, EventDispatcher):
    """
    Component containing TTS checkbox and Clear History button.
    Dispatches an 'on_clear_history' event when the button is pressed.
    """
    tts_enabled = BooleanProperty(False)

    # Register the event dispatcher
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_clear_history')

    def on_clear_history(self, *args):
        """
        Default handler for the on_clear_history event.
        This method is called when the event is dispatched.
        You bind to this event from the parent widget (e.g., ChatTab).
        """
        pass # Implementation is handled by the widget using this component
