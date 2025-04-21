from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder

# Load the corresponding kv file
Builder.load_file('views/vtube_tab.kv')

class VTubeTab(BoxLayout):
    """
    Kivy equivalent of the VTubeTab QWidget.
    Uses a BoxLayout to arrange widgets vertically.
    """
    status_text = StringProperty("Not Connected")
    is_connected = BooleanProperty(False)
    button_text = StringProperty("Connect")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is set in the kv file

    def toggle_connection(self):
        """
        Placeholder for the connection logic.
        Updates button text and status label based on connection state.
        """
        if self.is_connected:
            # Simulate disconnection
            self.status_text = "Disconnecting..."
            # In a real app, call disconnect logic here
            self.is_connected = False
            self.button_text = "Connect"
            self.status_text = "Not Connected"
            print("VTube Disconnected (Simulated)")
        else:
            # Simulate connection
            self.status_text = "Connecting..."
            # In a real app, call connect logic here
            self.is_connected = True
            self.button_text = "Disconnect"
            self.status_text = "Connected"
            print("VTube Connected (Simulated)")
