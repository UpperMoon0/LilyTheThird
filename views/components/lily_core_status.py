from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder
from kivy.clock import Clock

Builder.load_file('views/components/lily_core_status.kv')

class LilyCoreStatus(BoxLayout):
    """
    A component to display the connection status to Lily Core.
    """
    status_text = StringProperty("Connecting to Lily Core...")
    is_connected = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)