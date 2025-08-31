from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder

Builder.load_file('views/components/service_status.kv')

class ServiceStatus(BoxLayout):
    """
    A component to display the status of a service.
    """
    service_name = StringProperty("Service")
    status_text = StringProperty("Unknown")
    is_healthy = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
    def update_status(self, name, status, healthy):
        """Update the service status display."""
        self.service_name = name
        self.status_text = status
        self.is_healthy = healthy