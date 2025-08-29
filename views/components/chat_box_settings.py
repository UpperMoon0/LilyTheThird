from kivy.uix.boxlayout import BoxLayout
from kivy.properties import BooleanProperty, ListProperty, StringProperty, NumericProperty
from kivy.event import EventDispatcher
from kivy.lang import Builder
from kivy.clock import Clock # Added import
from settings_manager import load_chat_settings, save_chat_settings, CHAT_TOOL_USE_ENABLED # Import settings

# Load the KV file after the class definition
Builder.load_file('views/components/chat_box_settings.kv')

class ChatBoxSettings(BoxLayout, EventDispatcher):
    """
    Component containing TTS settings, tool use checkbox, and Clear History button.
    Dispatches events: 'on_clear_history', 'on_tts_model_changed_event'.
    """
    tts_enabled = BooleanProperty(False)
    tool_use_enabled = BooleanProperty(True) # New property for tool use
    tts_models = ListProperty(["edge", "zonos"]) # Available TTS models
    selected_tts_model = StringProperty("edge") # Default selected TTS model
    selected_tts_speaker = NumericProperty(1) # ADDED TTS speaker ID property

    # Component properties

    # Register the event dispatcher
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_clear_history')
        self.register_event_type('on_tts_model_changed_event') # Register new event for TTS model
        self.register_event_type('on_tts_speaker_changed_event') # ADDED event for TTS speaker
        self.load_settings() # Load settings on initialization

    def load_settings(self):
        """Loads settings from SettingsManager."""
        settings = load_chat_settings()
        self.tool_use_enabled = settings.get(CHAT_TOOL_USE_ENABLED, True)
        # Other settings can be loaded here if needed, e.g., tts_enabled
        self.tts_enabled = settings.get('tts_provider_enabled', False)
        self.selected_tts_model = settings.get('selected_tts_model', "edge")
        self.selected_tts_speaker = settings.get('selected_tts_speaker', 1)


    def on_clear_history(self, *args):
        """
        Default handler for the on_clear_history event.
        """
        pass # Implementation is handled by the widget using this component

    # Event handlers

    def on_tts_model_changed_event(self, model_name):
        """
        Handler for the 'on_tts_model_changed_event' dispatched from KV.
        """
        print(f"DEBUG: ChatBoxSettings: Event 'on_tts_model_changed_event' dispatched with value: {model_name}")
        # This event will be bound by the parent (ChatTab)
        pass

    def on_tts_speaker_changed_event(self, speaker_id): # ADDED event handler stub
        """
        Handler for the 'on_tts_speaker_changed_event' dispatched from this class.
        """
        print(f"DEBUG: ChatBoxSettings: Event 'on_tts_speaker_changed_event' dispatched with value: {speaker_id}")
        # This event will be bound by the parent (ChatTab)
        pass

    # --- Property Observers for Debugging (Kivy's on_<property_name>) ---
    def on_selected_tts_model(self, instance, value): # Kivy property observer
        """Called by Kivy when self.selected_tts_model KivyProperty changes."""
        print(f"DEBUG: ChatBoxSettings: own selected_tts_model (property observer) changed to: {value}")
        # You can add logic here if the ChatBoxSettings itself needs to react directly
        # to changes in selected_tts_model, beyond just dispatching an event.
        self.dispatch('on_tts_model_changed_event', value) # Dispatch event when property changes

    def on_selected_tts_speaker(self, instance, value): # ADDED Kivy property observer
        """Called by Kivy when self.selected_tts_speaker KivyProperty changes."""
        print(f"DEBUG: ChatBoxSettings: own selected_tts_speaker (property observer) changed to: {value}")
        self.dispatch('on_tts_speaker_changed_event', value) # Dispatch event




    def on_tool_use_enabled(self, instance, value):
        """Called by Kivy when self.tool_use_enabled KivyProperty changes."""
        print(f"DEBUG: ChatBoxSettings: tool_use_enabled changed to: {value} (type: {type(value)})")
        print(f"DEBUG: ChatBoxSettings: CHAT_TOOL_USE_ENABLED constant = '{CHAT_TOOL_USE_ENABLED}'")
        
        settings = load_chat_settings()
        print(f"DEBUG: ChatBoxSettings: Settings before update: {settings}")
        
        settings[CHAT_TOOL_USE_ENABLED] = value
        print(f"DEBUG: ChatBoxSettings: Settings after update: {settings}")
        
        save_chat_settings(settings)
        print(f"DEBUG: ChatBoxSettings: Settings saved successfully")
        
        # Dispatch an event if other parts of the app need to react immediately
        # self.dispatch('on_tool_use_setting_changed', value)
