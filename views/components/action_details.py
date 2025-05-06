from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ObjectProperty
from kivy.lang import Builder
import json
from datetime import datetime

# Load the KV file for this component
Builder.load_file('views/components/action_details.kv')

class ActionDetails(BoxLayout):
    """
    A widget to display the details of a selected action (tool call).
    """
    action_data = ObjectProperty(None, allownone=True)

    # Properties to bind to labels in KV
    action_name = StringProperty("No action selected")
    action_time = StringProperty("")
    action_params = StringProperty("")
    action_result = StringProperty("") # Added property for result

    def on_action_data(self, instance, value):
        """
        Update the display properties when the action_data changes.
        """
        if value:
            self.action_name = value.get("tool_name", "N/A")

            timestamp = value.get("timestamp")
            if timestamp:
                # Assuming timestamp is already a datetime object or compatible string
                try:
                    # If it's a string, parse it (adjust format if needed)
                    if isinstance(timestamp, str):
                        dt_object = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) # Handle Z timezone
                    else: # Assume it's already a datetime object
                        dt_object = timestamp
                    self.action_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    self.action_time = str(timestamp) # Fallback
            else:
                self.action_time = "N/A"

            params = value.get("arguments", {})
            # Pretty print the JSON parameters
            try:
                self.action_params = json.dumps(params, indent=2)
            except TypeError:
                self.action_params = str(params) # Fallback if not JSON serializable

            result = value.get("result", "No result recorded") # Get the result
            # Pretty print if it looks like JSON, otherwise just display as string
            if isinstance(result, (dict, list)):
                 try:
                    self.action_result = json.dumps(result, indent=2)
                 except TypeError:
                    self.action_result = str(result)
            else:
                self.action_result = str(result)

        else:
            # Reset to default values if no action is selected
            self.action_name = "No action selected"
            self.action_time = ""
            self.action_params = ""
            self.action_result = ""
