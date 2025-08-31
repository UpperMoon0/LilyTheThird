from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder
from kivy.clock import Clock

Builder.load_file('views/components/tts_provider_status.kv')

class TTSProviderStatus(BoxLayout):
    """
    A component to display the connection status to TTS Provider.
    """
    status_text = StringProperty("Connecting to TTS Provider...")
    is_connected = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)