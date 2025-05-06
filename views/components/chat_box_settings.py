from kivy.uix.boxlayout import BoxLayout
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.event import EventDispatcher
from kivy.lang import Builder

# Load the KV file after the class definition
Builder.load_file('views/components/chat_box_settings.kv')

class ChatBoxSettings(BoxLayout, EventDispatcher):
    """
    Component containing TTS checkbox, Clear History button, and LLM Selector.
    Dispatches events: 'on_clear_history', 'on_selected_provider', 'on_selected_model'.
    """
    tts_enabled = BooleanProperty(False)

    # --- LLM Properties (Passed down from parent) ---
    llm_providers = ListProperty([])
    llm_models = ListProperty([])
    selected_provider = StringProperty("")
    selected_model = StringProperty("")

    # Register the event dispatcher
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_clear_history')
        # Register events to bubble up from LLMSelector
        self.register_event_type('on_selected_provider')
        self.register_event_type('on_selected_model')

    def on_clear_history(self, *args):
        """
        Default handler for the on_clear_history event.
        """
        pass # Implementation is handled by the widget using this component

    # --- Default handlers for LLM events (to allow bubbling) ---
    def on_selected_provider(self, *args):
        """
        Default handler for the on_selected_provider event.
        """
        pass # Bound in kv to bubble up

    def on_selected_model(self, *args):
        """
        Default handler for the on_selected_model event.
        """
        pass # Bound in kv to bubble up
