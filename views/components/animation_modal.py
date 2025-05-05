import os
import json
from kivy.uix.modalview import ModalView
from kivy.properties import ObjectProperty, DictProperty, BooleanProperty, ListProperty, StringProperty
from kivy.lang import Builder
from kivy.app import App
from kivy.clock import Clock

# Load KV file for this component (assuming it exists)
# Builder.load_file('views/components/animationmodal.kv') # Will load later or via main kv

class AnimationModal(ModalView):
    """
    Modal dialog for adding or editing VTube Studio animations.
    """
    animation_name_input = ObjectProperty(None)
    param_list_widget = ObjectProperty(None) # Reference to the VTSParamList inside the modal

    # Data properties
    animation_data = DictProperty(None, allownone=True) # Data being edited or None for new
    is_edit_mode = BooleanProperty(False)
    available_vts_params = ListProperty([]) # Current params from VTube Studio

    # Callback property for when saved
    on_save_callback = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure IDs are available after kv loading if kv is loaded here
        # Clock.schedule_once(self._link_widget_refs)

    # Link widgets if needed (can also be done via ids in kv)
    # def _link_widget_refs(self, dt):
    #     self.animation_name_input = self.ids.get('animation_name_input')
    #     self.param_list_widget = self.ids.get('param_list_in_modal')

    def open_modal(self, available_params: list, data: dict = None, save_callback=None):
        """
        Opens the modal, populating fields based on mode (add/edit).

        Args:
            available_params: List of current parameter dicts from VTube Studio.
            data: Animation data dictionary for editing, or None for adding.
            save_callback: Function to call after successfully saving.
        """
        self.available_vts_params = available_params
        self.animation_data = data
        self.is_edit_mode = data is not None
        self.on_save_callback = save_callback

        # Ensure widgets are linked before accessing them
        # Use Clock.schedule_once to allow Kivy time to process IDs if needed
        Clock.schedule_once(self._populate_fields, 0)

        self.open()

    def _populate_fields(self, dt):
        """Populates the input fields and parameter list."""
        if not self.param_list_widget:
             print("Error: param_list_widget not found in AnimationModal.")
             # Try finding it via ids as a fallback
             self.param_list_widget = self.ids.get('param_list_in_modal')
             if not self.param_list_widget:
                 print("Error: Still cannot find param_list_in_modal by ID.")
                 return # Cannot proceed without the param list

        if not self.animation_name_input:
             print("Error: animation_name_input not found in AnimationModal.")
             self.animation_name_input = self.ids.get('animation_name_input')
             if not self.animation_name_input:
                 print("Error: Still cannot find animation_name_input by ID.")
                 return

        # Set title and name input
        self.ids.modal_title.text = "Edit Animation" if self.is_edit_mode else "Add New Animation"
        self.animation_name_input.text = self.animation_data.get('name', '') if self.is_edit_mode else ''

        # --- Parameter List Population ---
        # Start with all available VTS parameters
        params_to_display = []
        saved_param_values = self.animation_data.get('parameters', {}) if self.is_edit_mode else {}

        for vts_param in self.available_vts_params:
            param_name = vts_param.get('name')
            if not param_name:
                continue

            # Create a copy to avoid modifying the original list
            display_param = vts_param.copy()

            # Override the 'value' with the saved value if it exists in the animation data
            if param_name in saved_param_values:
                display_param['value'] = saved_param_values[param_name]
            # else: use the default value from available_vts_params

            params_to_display.append(display_param)

        # Update the VTSParamList component within the modal
        self.param_list_widget.set_parameters(params_to_display)


    def get_animations_dir(self):
        """Gets the path to the animations directory (consistent with VTSAnimationList)."""
        app_data_root = os.getenv('APPDATA')
        if not app_data_root:
             print("Error: Could not determine APPDATA directory.")
             return None
        animations_path = os.path.join(app_data_root, 'NsTut', 'LilyTheThird', 'vtube', 'animations')
        # Ensure the directory exists
        os.makedirs(animations_path, exist_ok=True)
        return animations_path

    def save_animation(self):
        """Saves the current animation data to a JSON file."""
        if not self.param_list_widget or not self.animation_name_input:
            print("Error: Cannot save, modal widgets not linked.")
            return

        anim_name = self.animation_name_input.text.strip()
        if not anim_name:
            print("Error: Animation name cannot be empty.")
            # TODO: Show feedback to the user (e.g., change border color)
            return

        # Get current parameter values from the VTSParamList widget
        current_params = self.param_list_widget.get_current_parameter_values()

        # Construct the data to save
        save_data = {
            "name": anim_name,
            "parameters": current_params
            # Add any other relevant metadata if needed
        }

        # Determine filename
        # Use existing filename if editing, otherwise create from name
        if self.is_edit_mode and '_filename' in self.animation_data:
            filename_base = self.animation_data['_filename']
        else:
            # Basic sanitization for filename (replace spaces, remove invalid chars)
            filename_base = "".join(c for c in anim_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
            filename_base = filename_base.replace(' ', '_')
            if not filename_base: # Handle cases where name is only invalid chars
                filename_base = "unnamed_animation"

        filename = f"{filename_base}.json"
        animations_dir = self.get_animations_dir()
        if not animations_dir:
            print("Error: Cannot determine animations directory.")
            return

        filepath = os.path.join(animations_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4)
            print(f"Animation saved successfully to: {filepath}")

            # Trigger callback if provided
            if self.on_save_callback:
                self.on_save_callback()

            self.dismiss() # Close the modal

        except Exception as e:
            print(f"Error saving animation file {filepath}: {e}")
            # TODO: Show error message to the user

    def cancel(self):
        """Closes the modal without saving."""
        self.dismiss()
