from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder
from kivy.clock import Clock

Builder.load_file('views/components/web_scout_status.kv')

class WebScoutStatus(BoxLayout):
    """
    A component to display the connection status to Web Scout.
    """
    status_text = StringProperty("Connecting to Web Scout...")
    is_connected = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)