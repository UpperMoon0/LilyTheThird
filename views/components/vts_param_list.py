# views/components/vts_param_list.py
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ListProperty, StringProperty, NumericProperty, ObjectProperty
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.slider import Slider

# Load the corresponding kv file
Builder.load_file('views/components/vtsparamlist.kv')

class VTSParamListItem(BoxLayout):
    """Widget representing a single VTS parameter with name, value, min, max."""
    param_name = StringProperty('')
    param_value = NumericProperty(0)
    param_min = NumericProperty(0)
    param_max = NumericProperty(1)
    # Add a reference to the VTSParam object if needed for callbacks
    vts_param_ref = ObjectProperty(None, allownone=True)

    def on_slider_value(self, slider_instance, value):
        """Callback when the slider value changes."""
        # Update the internal value (optional, could be bound directly)
        self.param_value = value
        # Optionally, notify the parent or trigger an update back to VTube Studio
        # if self.vts_param_ref and hasattr(self.vts_param_ref, 'update_parameter'):
        #     self.vts_param_ref.update_parameter(self.param_name, value)
        print(f"Slider changed for {self.param_name}: {value}")


class VTSParamList(BoxLayout):
    """
    A widget to display a list of VTube Studio parameters.
    """
    parameters = ListProperty([]) # List of parameter dictionaries/objects

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(parameters=self.update_parameters_display)

    def update_parameters_display(self, instance, param_list):
        """
        Clears and repopulates the parameter list display.
        Expects param_list to be a list of dictionaries, e.g.:
        [{'name': 'Param1', 'value': 0.5, 'min': 0, 'max': 1}, ...]
        """
        params_container = self.ids.params_container
        params_container.clear_widgets()
        # Set height dynamically based on number of items (adjust item height as needed)
        item_height = dp(50) # Approximate height for each param item
        params_container.height = len(param_list) * item_height

        for param_data in param_list:
            item = VTSParamListItem(
                param_name=param_data.get('name', 'N/A'),
                param_value=param_data.get('value', 0),
                param_min=param_data.get('min', 0),
                param_max=param_data.get('max', 1),
                vts_param_ref=param_data # Pass the original dict/object if needed
            )
            params_container.add_widget(item)

    def set_parameters(self, params_data: list):
        """Sets the list of parameters to display."""
        self.parameters = params_data

    def clear_parameters(self):
        """Clears all parameters from the list."""
        self.parameters = []
