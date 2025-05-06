from kivy.uix.boxlayout import BoxLayout # Changed from ModalView
from kivy.properties import ObjectProperty, DictProperty, BooleanProperty, ListProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.event import EventDispatcher # Added for dispatching events

Builder.load_file('views/components/animation_editor_panel.kv')

class AnimationEditorPanel(BoxLayout, EventDispatcher): # Changed base class, added EventDispatcher
    """
    Inline panel for adding or editing VTube Studio animations.
    Dispatches 'on_save_animation' and 'on_cancel_edit' events.
    """
    # Register custom events
    __events__ = ('on_save_animation', 'on_cancel_edit', 'on_copy_names', 'on_set_from_clipboard')

    # --- Widget References (from KV) ---
    editor_title = ObjectProperty(None)
    animation_name_input = ObjectProperty(None)
    param_list_widget = ObjectProperty(None) # Reference to the VTSParamList inside

    # --- Data Properties ---
    # These will be set by the parent (VTubeTab)
    animation_data = DictProperty(None, allownone=True) # Data being edited or None for new
    is_edit_mode = BooleanProperty(False)
    available_vts_params = ListProperty([]) # Current params from VTube Studio

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Link widgets after kv is loaded (important!)
        Clock.schedule_once(self._link_widgets)

    def _link_widgets(self, dt):
        """Ensure internal widget references are linked via ids."""
        # Use ids directly now as this is part of the main layout
        self.editor_title = self.ids.get('editor_title')
        self.animation_name_input = self.ids.get('editor_animation_name_input')
        self.param_list_widget = self.ids.get('editor_param_list')
        if not all([self.editor_title, self.animation_name_input, self.param_list_widget]):
            print("Warning: Not all editor widgets linked in AnimationEditorPanel.")
            # Try again slightly later? Or rely on direct access via self.ids in methods
            # Clock.schedule_once(self._link_widgets, 0.1)


    def populate_editor(self, available_params: list, data: dict = None):
        """
        Populates the editor fields based on mode (add/edit).
        Called by the parent widget (VTubeTab).

        Args:
            available_params: List of current parameter dicts from VTube Studio.
            data: Animation data dictionary for editing, or None for adding.
        """
        print(f"Populating editor. Edit mode: {data is not None}. Data: {data}")
        self.available_vts_params = available_params
        self.animation_data = data if data else {} # Ensure it's a dict
        self.is_edit_mode = data is not None

        # Schedule the internal population method for the next frame.
        # This ensures Kivy has processed the panel's internal KV rules
        # after it becomes visible/enabled in the parent.
        Clock.schedule_once(self._populate_fields_internal, 0)


    def _populate_fields_internal(self, dt): # Added dt argument back
        """Internal method to populate fields after widgets are assumed ready."""
        # Use the references set by _link_widgets
        editor_title = self.editor_title
        animation_name_input = self.animation_name_input
        param_list_widget = self.param_list_widget # Use the attribute set in _link_widgets

        # Check if the references were successfully linked earlier
        if not self.param_list_widget:
             print("Error: self.param_list_widget is None in _populate_fields_internal. Linking failed or happened too late.")
             # Optionally, try linking again, though this might indicate a deeper issue
             # self._link_widgets(0) # Be cautious with recursive calls or infinite loops
             # param_list_widget = self.param_list_widget # Re-check after trying to link again
             # if not param_list_widget:
             #    return # Still failed
             return # Cannot proceed if linking failed

        if not self.animation_name_input:
             print("Error: self.animation_name_input is None in _populate_fields_internal.")
             return

        if not self.editor_title:
             print("Error: self.editor_title is None in _populate_fields_internal.")

        if not animation_name_input:
             print("Error: editor_animation_name_input not found in AnimationEditorPanel.")
             return

        if not editor_title:
             print("Error: editor_title not found in AnimationEditorPanel.")
             return

        # Set title and name input
        editor_title.text = "Edit Animation" if self.is_edit_mode else "Add New Animation"
        animation_name_input.text = self.animation_data.get('name', '') if self.is_edit_mode else ''

        # --- Parameter List Population ---
        params_to_display = []
        # Get saved values if editing, default to empty dict if adding
        saved_param_values = self.animation_data.get('parameters', {})

        # Ensure saved_param_values is a dict, handle potential list format from older saves?
        if isinstance(saved_param_values, list):
            print("Warning: Converting old list-based parameter format to dict.")
            saved_param_values = {p.get('id'): p.get('value') for p in saved_param_values if 'id' in p}


        for vts_param in self.available_vts_params:
            param_name = vts_param.get('name')
            if not param_name:
                continue

            display_param = vts_param.copy()

            # Override the 'value' with the saved value if it exists
            if param_name in saved_param_values:
                # Ensure value type is correct (float)
                try:
                    display_param['value'] = float(saved_param_values[param_name])
                except (ValueError, TypeError):
                    print(f"Warning: Invalid saved value for {param_name}, using default.")
                    # Keep the default value from vts_param if conversion fails
            # else: use the default value from available_vts_params

            params_to_display.append(display_param)

        # Update the VTSParamList component
        param_list_widget.set_parameters(params_to_display)
        print(f"Editor populated with {len(params_to_display)} parameters.")

    def _show_popup(self, title, message):
        """Helper to show a simple popup message."""
        # Consider making this a method on the App or a utility class
        popup = Popup(title=title,
                      content=Label(text=message, halign='center', valign='middle'),
                      size_hint=(0.6, 0.3),
                      auto_dismiss=True)
        popup.open()

    def trigger_copy_names(self):
        """Dispatches the 'on_copy_names' event."""
        print("AnimationEditorPanel: Dispatching on_copy_names")
        self.dispatch('on_copy_names')

    def trigger_set_from_clipboard(self):
        """Dispatches the 'on_set_from_clipboard' event."""
        print("AnimationEditorPanel: Dispatching on_set_from_clipboard")
        self.dispatch('on_set_from_clipboard')

    def trigger_save(self):
        """Validates input and dispatches the 'on_save_animation' event with current data."""
        animation_name_input = self.ids.get('editor_animation_name_input')
        param_list_widget = self.ids.get('editor_param_list')

        if not animation_name_input or not param_list_widget:
            print("Error: Cannot save, editor widgets not found.")
            self._show_popup("Error", "Internal error: Editor widgets missing.")
            return

        anim_name = animation_name_input.text.strip()
        if not anim_name:
            print("Error: Animation name cannot be empty.")
            self._show_popup("Validation Error", "Animation name cannot be empty.")
            # TODO: Add visual feedback (e.g., red border)
            return

        # Get current parameter values from the VTSParamList widget
        current_params = param_list_widget.get_current_parameter_values()

        # Construct the data to save (parent will handle actual file writing)
        save_data = {
            "name": anim_name,
            "parameters": current_params
            # Include original filename if editing, so parent knows which file to update
        }
        if self.is_edit_mode and '_filename' in self.animation_data:
            save_data['_filename'] = self.animation_data['_filename']

        print(f"AnimationEditorPanel: Dispatching on_save_animation with data: {save_data}")
        self.dispatch('on_save_animation', save_data)

    def trigger_cancel(self):
        """Dispatches the 'on_cancel_edit' event."""
        print("AnimationEditorPanel: Dispatching on_cancel_edit")
        self.dispatch('on_cancel_edit')

    # --- Event stubs (needed for dispatch) ---
    def on_save_animation(self, animation_data):
        pass # Parent (VTubeTab) will bind to this

    def on_cancel_edit(self):
        pass # Parent (VTubeTab) will bind to this

    def on_copy_names(self):
        pass # Parent (VTubeTab) will bind to this

    def on_set_from_clipboard(self):
        pass # Parent (VTubeTab) will bind to this

    # --- Methods previously in Modal, now potentially moved to VTubeTab or kept here if purely UI ---
    # get_animations_dir - Should be handled by VTubeTab as it manages file paths
    # copy_param_names_to_clipboard - Logic moved to VTubeTab, triggered by on_copy_names event
    # set_animation_from_clipboard - Logic moved to VTubeTab, triggered by on_set_from_clipboard event
