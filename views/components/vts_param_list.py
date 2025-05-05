# views/components/vts_param_list.py
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ListProperty, StringProperty, NumericProperty, ObjectProperty, DictProperty
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.slider import Slider

# KV file is now loaded centrally in main.py
# Builder.load_file('views/components/vtsparamlist.kv')

class VTSParamListItem(BoxLayout):
    """Widget representing a single VTS parameter with name, value, min, max."""
    param_name = StringProperty('')
    param_value = NumericProperty(0)
    param_min = NumericProperty(0)
    param_max = NumericProperty(1)
    vts_param_ref = ObjectProperty(None, allownone=True) # Original data reference
    parent_list = ObjectProperty(None) # Reference to the VTSParamList containing this item

    def on_slider_value(self, slider_instance, value):
        """Callback when the slider value changes."""
        # Update the internal value (bound visually)
        self.param_value = value
        # Update the cache in the parent list
        if self.parent_list:
            self.parent_list.update_param_cache(self.param_name, value)
        # Optional: print statement for debugging
        # print(f"Slider changed for {self.param_name}: {value}")


class VTSParamList(BoxLayout):
    """
    A widget to display a list of VTube Studio parameters.
    """
    parameters = ListProperty([]) # List of currently displayed parameter dictionaries/objects
    _all_parameters = ListProperty([]) # Store the full list for filtering logic
    _parameter_values_cache = DictProperty({}) # Stores current values for ALL params

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
                vts_param_ref=param_data, # Pass the original dict/object if needed
                parent_list=self # Pass reference to self
            )
            params_container.add_widget(item)

    def set_parameters(self, params_data: list):
        """Sets the full list of parameters, initializes cache, and updates the display."""
        self._all_parameters = params_data
        # Initialize the cache with values from the input data
        self._parameter_values_cache = {
            p.get('name'): p.get('value', 0) for p in params_data if p.get('name')
        }
        # Initial filter (show all or based on current search text if any)
        search_text = self.ids.search_input.text if 'search_input' in self.ids else ''
        self.filter_params(search_text) # This will trigger update_parameters_display

    def clear_parameters(self):
        """Clears all parameters from the list and cache."""
        self._all_parameters = []
        self.parameters = [] # Clear the displayed list as well
        self._parameter_values_cache = {} # Clear the cache

    def update_param_cache(self, param_name: str, value: float):
        """Updates the value for a specific parameter in the cache."""
        if param_name in self._parameter_values_cache:
            self._parameter_values_cache[param_name] = value
        else:
            # This case might happen if parameters are added dynamically without full reset
            # For now, let's just add it, but ideally set_parameters handles initialization
            print(f"Warning: Parameter '{param_name}' not found in cache, adding.")
            self._parameter_values_cache[param_name] = value

    def get_current_parameter_values(self) -> dict:
        """
        Retrieves the current values of ALL parameters managed by this list
        from the internal cache.

        Returns:
            A dictionary mapping parameter names to their current values.
        """
        # Return a copy of the cache to prevent external modification
        return self._parameter_values_cache.copy()

    def filter_params(self, search_text: str):
        """Filters the displayed parameters based on the search text."""
        if not self._all_parameters:
            return # No parameters to filter

        search_text = search_text.lower().strip()
        if not search_text:
            # If search is empty, show all parameters
            self.parameters = self._all_parameters[:] # Use a copy
        else:
            # Filter based on name containing the search text (case-insensitive)
            filtered_list = [
                param for param in self._all_parameters
                if search_text in param.get('name', '').lower()
            ]
            self.parameters = filtered_list
