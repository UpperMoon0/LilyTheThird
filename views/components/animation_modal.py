import os
import json
from kivy.uix.modalview import ModalView
from kivy.properties import ObjectProperty, DictProperty, BooleanProperty, ListProperty, StringProperty
from kivy.lang import Builder
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.popup import Popup # For showing simple messages
from kivy.uix.label import Label # For popup content


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

    def _show_popup(self, title, message):
        """Helper to show a simple popup message."""
        popup = Popup(title=title,
                      content=Label(text=message, halign='center', valign='middle'),
                      size_hint=(0.6, 0.3),
                      auto_dismiss=True)
        popup.open()

    def copy_param_names_to_clipboard(self):
        """Copies the names of all available parameters to the clipboard as a JSON list."""
        if not self.param_list_widget:
            self.param_list_widget = self.ids.get('param_list_in_modal')
        if not self.param_list_widget:
            print("Error: Cannot copy names, param_list_widget not found.")
            self._show_popup("Error", "Could not find parameter list widget.")
            return

        # Get all parameter names from the underlying full list
        all_params_data = self.param_list_widget._all_parameters
        param_names = [p.get('name') for p in all_params_data if p.get('name')]

        if not param_names:
            print("No parameter names found to copy.")
            self._show_popup("Info", "No parameter names available to copy.")
            return

        try:
            json_string = json.dumps(param_names, indent=4) # Pretty print JSON
            Clipboard.copy(json_string)
            print(f"Copied {len(param_names)} parameter names to clipboard.")
            self._show_popup("Success", f"Copied {len(param_names)} parameter names\nto clipboard as JSON.")
        except Exception as e:
            print(f"Error converting parameter names to JSON or copying: {e}")
            self._show_popup("Error", f"Failed to copy names:\n{e}")

    def set_animation_from_clipboard(self):
        """Sets the animation name and parameter values from JSON data in the clipboard."""
        if not self.param_list_widget:
            self.param_list_widget = self.ids.get('param_list_in_modal')
        if not self.animation_name_input:
            self.animation_name_input = self.ids.get('animation_name_input')

        if not self.param_list_widget or not self.animation_name_input:
            print("Error: Cannot set from clipboard, modal widgets not linked.")
            self._show_popup("Error", "Modal widgets not properly linked.")
            return

        clipboard_content = Clipboard.paste()
        if not clipboard_content:
            print("Clipboard is empty.")
            self._show_popup("Info", "Clipboard is empty.")
            return

        try:
            data = json.loads(clipboard_content)
        except json.JSONDecodeError:
            print("Error: Clipboard content is not valid JSON.")
            self._show_popup("Error", "Clipboard content is not valid JSON.")
            return
        except Exception as e:
            print(f"Error reading clipboard JSON: {e}")
            self._show_popup("Error", f"Error reading clipboard:\n{e}")
            return

        # Validate data structure
        if not isinstance(data, dict):
            print("Error: Clipboard JSON is not a dictionary.")
            self._show_popup("Error", "Clipboard JSON is not a dictionary\n(expected format: {'name': '...', 'parameters': {...}}).")
            return
        if 'name' not in data or not isinstance(data.get('name'), str):
            print("Error: Clipboard JSON missing 'name' string.")
            self._show_popup("Error", "Clipboard JSON missing 'name' string.")
            return
        if 'parameters' not in data or not isinstance(data.get('parameters'), dict):
            print("Error: Clipboard JSON missing 'parameters' dictionary.")
            self._show_popup("Error", "Clipboard JSON missing 'parameters' dictionary.")
            return

        # --- Apply data ---
        new_anim_name = data['name']
        clipboard_params = data['parameters']

        # Update animation name input
        self.animation_name_input.text = new_anim_name

        # Update parameter values in the list
        # Get the current full list structure (including min/max etc.)
        current_full_params = self.param_list_widget._all_parameters
        updated_params_list = []

        params_updated_count = 0
        params_not_found_count = 0

        for param_struct in current_full_params:
            param_name = param_struct.get('name')
            if not param_name:
                updated_params_list.append(param_struct) # Keep params without names as is
                continue

            new_param_struct = param_struct.copy() # Work on a copy

            if param_name in clipboard_params:
                new_value = clipboard_params[param_name]
                # Basic validation: ensure value is numeric
                if isinstance(new_value, (int, float)):
                    # Clamp value within min/max bounds
                    min_val = new_param_struct.get('min', 0)
                    max_val = new_param_struct.get('max', 1)
                    clamped_value = max(min_val, min(new_value, max_val))
                    new_param_struct['value'] = clamped_value
                    params_updated_count += 1
                else:
                    print(f"Warning: Invalid value type for parameter '{param_name}' in clipboard JSON (expected number, got {type(new_value)}). Keeping original value.")
            else:
                 params_not_found_count += 1
                 # Keep original value if not found in clipboard

            updated_params_list.append(new_param_struct)

        # Update the VTSParamList with the modified list
        # This will automatically update the cache and the visual display
        self.param_list_widget.set_parameters(updated_params_list)

        print(f"Set animation from clipboard: Name='{new_anim_name}', {params_updated_count} parameters updated.")
        if params_not_found_count > 0:
            print(f"Warning: {params_not_found_count} parameters from the list were not found in the clipboard JSON.")
            self._show_popup("Success (with warnings)",
                             f"Set animation: '{new_anim_name}'\n"
                             f"{params_updated_count} parameters updated.\n"
                             f"{params_not_found_count} parameters not found in clipboard data.")
        else:
            self._show_popup("Success",
                             f"Set animation: '{new_anim_name}'\n"
                             f"{params_updated_count} parameters updated.")


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
