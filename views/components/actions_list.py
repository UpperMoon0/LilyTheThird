from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button # Changed from Label
from kivy.uix.scrollview import ScrollView
from kivy.properties import ListProperty, NumericProperty, ObjectProperty, DictProperty # Added DictProperty
from kivy.metrics import dp
from kivy.lang import Builder
from kivy.event import EventDispatcher # Needed for event registration

# Load the corresponding kv file
Builder.load_file('views/components/actions_list.kv')

# Custom Button class to hold action data
class ActionListItemButton(Button):
    action_data = DictProperty(None)

class ActionsList(BoxLayout, EventDispatcher): # Inherit from EventDispatcher
    """
    A widget to display a list of successfully executed actions (tool calls).
    Dispatches 'on_action_selected' event when an action is clicked.
    """
    actions = ListProperty([]) # Now stores list of action dictionaries
    item_height = NumericProperty(dp(40)) # Increased height for buttons

    # Register the event
    __events__ = ('on_action_selected',)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(actions=self.update_actions_display)

    def update_actions_display(self, instance, actions_list):
        """
        Clears and repopulates the actions list display with buttons.
        """
        actions_container = self.ids.actions_container
        actions_container.clear_widgets()
        # Set height dynamically based on number of items and item_height
        actions_container.height = len(actions_list) * self.item_height
        for action_data in actions_list:
            action_name = action_data.get("tool_name", "Unknown Action") # Get name from dict
            # Use the custom button class
            item_button = ActionListItemButton(
                text=action_name,
                size_hint_y=None,
                height=self.item_height,
                halign='left',
                valign='middle',
                # Store the full data on the button itself for easy retrieval
                action_data=action_data
            )
            # Adjust text alignment padding if needed (Button text_size works differently)
            item_button.bind(on_press=self._dispatch_action_selected)
            actions_container.add_widget(item_button)

    def _dispatch_action_selected(self, button_instance):
        """Called when an action button is pressed."""
        action_data = getattr(button_instance, 'action_data', None)
        if action_data:
            print(f"ActionsList: Action selected: {action_data.get('tool_name')}")
            # Dispatch the event with the full action data dictionary
            self.dispatch('on_action_selected', action_data)
        else:
            print("ActionsList Warning: Clicked button missing action_data.")

    def on_action_selected(self, *args):
        """Default handler for the 'on_action_selected' event.
        Kivy requires this method to exist in the class that dispatches the event.
        The actual handling is done by the parent widget (ChatTab) or KV bindings.
        """
        pass # Does nothing by default

    def add_action(self, action_data: dict):
        """
        Adds a new action dictionary to the list.
        Expects a dictionary like:
        {'tool_name': '...', 'arguments': {...}, 'timestamp': ..., 'result': ...}
        """
        if isinstance(action_data, dict) and "tool_name" in action_data:
            self.actions.append(action_data)
            print(f"ActionsList: Added action data for '{action_data['tool_name']}'")
        else:
            print(f"ActionsList Error: Invalid action_data format: {action_data}")


    def clear_actions(self):
        """
        Clears all actions from the list.
        """
        self.actions = []
