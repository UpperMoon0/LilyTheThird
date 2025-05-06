import asyncio
import asyncio
import os
import uuid
import json # Added for save/load and clipboard
import pyvts
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty, DictProperty
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard # Added for clipboard functions
from kivy.uix.popup import Popup # Added for showing messages
from kivy.uix.label import Label # Added for popup content
from kivy.uix.button import Button # Added for confirmation popup buttons
from kivy.metrics import dp # Added to fix NameError
from kivy.lang import Builder # Added for loading kv files

Builder.load_file('views/vtube_tab.kv')

class VTubeTab(BoxLayout):
    """
    Kivy equivalent of the VTubeTab QWidget.
    Uses a BoxLayout to arrange widgets vertically.
    """
    status_text = StringProperty("Not Connected")
    is_connected = BooleanProperty(False)
    button_text = StringProperty("Connect")
    vts = ObjectProperty(None, allownone=True) # Store the pyvts instance
    available_parameters = ListProperty([]) # To store fetched parameters

    # Default VTS connection details (can be made configurable later)
    plugin_name = "LilyTheThird"
    plugin_developer = "NsTut" # Replace with your name/alias
    vts_host = "127.0.0.1"
    vts_port = 8001

    # --- Editor State Properties ---
    is_editing = BooleanProperty(False) # True when the inline editor panel is active
    editing_animation_data = DictProperty(None, allownone=True) # Data for the animation being edited/added

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize vts instance
        self.vts = pyvts.vts(
            pluginname=self.plugin_name,
            pluginauthor=self.plugin_developer,
            host=self.vts_host,
            port=self.vts_port
        )
        # No need to instantiate modal
        self.cancel_edit() # Ensure editor is initially hidden/disabled

    async def _connect_vts(self):
        """Asynchronously connect to VTube Studio."""
        self.status_text = "Connecting..."
        self.button_text = "Connecting..."
        self.ids.connect_button.disabled = True # Disable button during connection attempt
        connection_successful = False # Flag to track success for finally block

        try:
            # Always use the existing self.vts instance created in __init__
            if self.vts is None:
                 # This should ideally not happen if __init__ always runs first
                 print("ERROR: VTS instance is None. Cannot connect.")
                 self.status_text = "Error: VTS instance missing"
                 self.button_text = "Connect"
                 return # Exit if instance is missing

            # Always attempt connection/reconnection using the persistent instance.
            print("Attempting VTS connection/reconnection...")
            # Ensure connect is only called if not already connected by checking ws state
            if not (hasattr(self.vts, 'ws') and self.vts.ws.connected):
                 await self.vts.connect() # Use the existing or new instance
                 print("VTS Connected to WebSocket")
            else:
                 print("VTS WebSocket already connected, proceeding to auth check.")

            # --- Authentication Process ---
            print("Checking VTS Authentication...")
            authenticated = False # Default to not authenticated
            try:
                # Attempt authentication. Expect True on success.
                # Failure (no token) might return non-True or raise an exception (like KeyError).
                auth_result = await self.vts.request_authenticate()
                print(f"VTS Raw Authentication Result: {auth_result}")

                if auth_result is True:
                     authenticated = True # Explicit success, token likely valid

            except Exception as auth_err:
                # Assume ANY exception during request_authenticate means auth failed / token needed
                print(f"Exception during VTS authentication check (likely missing token): {auth_err}")
                authenticated = False # Ensure we proceed to token request

            # Proceed based on the determined authenticated status
            if authenticated:
                # Successfully authenticated (likely using existing token)
                self.is_connected = True
                self.status_text = f"Connected to VTube Studio on {self.vts_host}:{self.vts_port}"
                self.button_text = "Disconnect"
                print("VTS Authentication Successful")
                connection_successful = True # Mark as successful
                # --- Fetch parameters after successful authentication ---
                print("Authentication successful, fetching parameters...")
                asyncio.create_task(self._fetch_available_parameters())
                # --- End fetch parameters ---
            else:
                # Authentication failed or didn't return True - Token likely missing or invalid, request a new one
                print("VTS Authentication Failed or indeterminate. Requesting new token...")
                self.status_text = "Authenticating... (Check VTube Studio for prompt)"
                try:
                    print(">>> Calling request_authenticate_token() NOW...") # DEBUG PRINT
                    await self.vts.request_authenticate_token()
                    print(">>> Finished request_authenticate_token(). Pop-up should be visible in VTS.") # DEBUG PRINT
                    print("VTS Token Requested. Waiting for user approval...")
                    self.status_text = "Authenticating... (Check VTube Studio for prompt)"

                    # --- Start Polling for Authentication ---
                    print(">>> Starting polling loop NOW...") # DEBUG PRINT
                    auth_success = False
                    for attempt in range(30): # Try for 30 seconds
                        await asyncio.sleep(1) # Wait 1 second between checks
                        print(f"Checking VTS Authentication (Attempt {attempt + 1}/30)...")
                        try:
                            re_auth_result = await self.vts.request_authenticate()
                            print(f"VTS Re-Authentication Result: {re_auth_result}")
                            if re_auth_result is True:
                                print("VTS Authentication Successful after token approval.")
                                self.is_connected = True
                                self.status_text = f"Connected to VTube Studio on {self.vts_host}:{self.vts_port}"
                                self.button_text = "Disconnect"
                                connection_successful = True # Mark as successful
                                auth_success = True
                                # --- Fetch parameters after successful authentication ---
                                print("Authentication successful after token approval, fetching parameters...")
                                asyncio.create_task(self._fetch_available_parameters())
                                # --- End fetch parameters ---
                                break # Exit the loop on success
                            else:
                                # Update status but keep trying
                                self.status_text = f"Waiting for approval... ({attempt + 1}/30)"
                        except Exception as poll_err:
                            print(f"Error during authentication polling: {poll_err}")
                            # Optionally break or handle specific errors, for now just log and continue trying
                            self.status_text = f"Error checking auth: {poll_err}"
                            await asyncio.sleep(1) # Wait a bit longer after an error

                    if not auth_success:
                        print("VTS Authentication timed out after token request.")
                        self.status_text = "Authentication timed out. Please try connecting again."
                        self.is_connected = False
                        self.button_text = "Connect"

                        # --- Delete token file on timeout ---
                        token_file = "pyvts_token.txt"
                        if os.path.exists(token_file):
                            try:
                                os.remove(token_file)
                                print(f"Removed token file '{token_file}' due to authentication timeout.")
                            except OSError as e:
                                print(f"Error removing token file '{token_file}': {e}")
                        else:
                            print(f"Token file '{token_file}' not found, nothing to remove.")
                        # --- End delete token file ---

                        # --- Explicitly close connection FIRST ---
                        if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                            try:
                                print("Explicitly closing VTS connection before reset...")
                                await self.vts.close()
                                print("VTS connection closed.")
                            except Exception as close_err:
                                print(f"Error during explicit close before reset: {close_err}")
                        # --- End explicit close ---

                        # --- Reset VTS instance ---
                        print("Resetting VTS instance state...")
                        self.vts = None # Clear the old instance reference
                        # Re-initialize for the next attempt
                        self.vts = pyvts.vts(
                            pluginname=self.plugin_name,
                            pluginauthor=self.plugin_developer,
                            host=self.vts_host,
                            port=self.vts_port
                        )
                        print("VTS instance re-initialized.")
                        # --- End reset VTS instance ---

                    # --- End Polling ---

                except Exception as token_err:
                    # Handle errors during the initial token request itself
                    print(f"Error requesting VTS token: {token_err}")
                    self.status_text = f"Error requesting token: {token_err}"
                    self.is_connected = False
                    self.button_text = "Connect"
                    # Close connection if token request failed
                    if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                        await self.vts.close()
                        print("VTS connection closed due to token request error.")

        except ConnectionRefusedError:
            self.status_text = "Connection Refused. Is VTube Studio running and API enabled?"
            self.is_connected = False
            self.button_text = "Connect"
            print("VTS Connection Refused")
        # Removed the incorrect pyvts.AuthenticationTokenMissing handler
        except KeyError as ke:
             # Catch potential KeyErrors during response parsing (though .get should prevent most)
             self.status_text = f"Error parsing VTS response: {ke}"
             self.is_connected = False
             self.button_text = "Connect"
             print(f"VTS Response Parsing Error: {ke}")
             if self.vts and self.vts.ws.connected:
                 await self.vts.close()
        except Exception as e:
            self.status_text = f"Connection Error: {type(e).__name__}: {e}"
            self.is_connected = False
            self.button_text = "Connect"
            print(f"VTS Connection Error: {type(e).__name__}: {e}")
            # Ensure cleanup on unexpected errors only if vts object exists and is connected
            if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                 await self.vts.close()
        finally:
             # Re-enable button correctly based on outcome
             if hasattr(self.ids, 'connect_button'):
                 self.ids.connect_button.disabled = False


    async def _disconnect_vts(self):
        """Asynchronously disconnect from VTube Studio."""
        self.status_text = "Disconnecting..."
        # Disable button immediately if it exists
        if hasattr(self.ids, 'connect_button'):
            self.ids.connect_button.disabled = True

        vts_instance_to_close = self.vts # Keep ref
        closed_successfully = False
        # Use the existing self.vts instance
        if vts_instance_to_close and hasattr(vts_instance_to_close, 'ws') and vts_instance_to_close.ws.connected:
            try:
                print("Attempting to close VTS WebSocket...")
                await vts_instance_to_close.close()
                print("VTS WebSocket closed.")
                closed_successfully = True
                # Optional: Add delay back if needed, but let's test without first
                # await asyncio.sleep(0.5)
                # print("Post-disconnect delay complete.")
            except Exception as e:
                print(f"Error during VTS disconnection: {e}")
                 # Continue cleanup even if close fails

        # Reset state after attempting close
        self.is_connected = False
        self.button_text = "Connect"
        self.status_text = "Not Connected"
        self.available_parameters = [] # Clear parameters on disconnect
        # Re-enable button only if it exists in ids
        if hasattr(self.ids, 'connect_button'):
            self.ids.connect_button.disabled = False


    def toggle_connection(self):
        """
        Starts the async connection or disconnection process.
        Disables the button immediately to prevent multiple clicks.
        """
        # Disable button immediately if it exists
        if hasattr(self.ids, 'connect_button'):
             if self.ids.connect_button.disabled:
                 print("Connection/Disconnection already in progress.")
                 return # Prevent starting new task if already busy
             self.ids.connect_button.disabled = True # Disable button before starting task

        if not self.is_connected:
            self.status_text = "Connecting..." # Update status immediately
            self.button_text = "Connecting..."
            # Run the async connection function
            Clock.schedule_once(lambda dt: asyncio.create_task(self._connect_vts()))
        else:
            # Run the async disconnection function
            self.status_text = "Disconnecting..." # Update status immediately
            self.button_text = "Disconnecting..."
            Clock.schedule_once(lambda dt: asyncio.create_task(self._disconnect_vts()))

    # --- VTS Interaction Methods ---
    async def trigger_hotkey(self, hotkey_id: str):
        """Asynchronously triggers a VTube Studio hotkey by its ID."""
        if not self.is_connected or not self.vts:
            print(f"Cannot trigger hotkey '{hotkey_id}': Not connected to VTube Studio.")
            # Optionally provide user feedback here (e.g., update a status label)
            return

        print(f"Attempting to trigger hotkey: {hotkey_id}")
        try:
            # Construct the request payload using the pyvts helper
            hotkey_request = self.vts.requestTriggerHotkey(hotkeyID=hotkey_id)
            # Send the request
            response = await self.vts.request(hotkey_request)
            print(f"Hotkey '{hotkey_id}' trigger response: {response}")
            # You might want to check the response for success/failure if needed
            # Example: Check if response indicates an error
            if response and response.get('data', {}).get('errorID'):
                 error_msg = response.get('data', {}).get('message', 'Unknown VTS Error')
                 print(f"Error triggering hotkey '{hotkey_id}': {error_msg}")
                 # Update UI to show error
            else:
                 print(f"Hotkey '{hotkey_id}' triggered successfully (based on response).")
                 # Update UI to show success (optional)

        except Exception as e:
            print(f"Exception while triggering hotkey '{hotkey_id}': {e}")
            # Update UI to show error

    # --- Parameter Fetching and Control Methods ---

    async def _fetch_available_parameters(self):
        """Fetches the list of available input parameters from VTube Studio."""
        if not self.is_connected or not self.vts:
            print("Cannot fetch parameters: Not connected.")
            return

        print("Attempting to fetch available parameters...")
        try:
            request_id = str(uuid.uuid4())
            payload = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": request_id,
                "messageType": "InputParameterListRequest"
                # No data field needed for this request type
            }
            print(f"Sending InputParameterListRequest payload: {payload}")
            response = await self.vts.request(payload)
            print(f"InputParameterListRequest response: {response}")

            # Corrected the messageType check based on VTS response log
            if response and response.get("messageType") == "InputParameterListResponse":
                default_params = response.get("data", {}).get("defaultParameters", [])
                custom_params = response.get("data", {}).get("customParameters", [])
                # Combine default and custom parameters (or handle them separately)
                # Storing the whole dict for potential future use (min/max values)
                all_params = default_params + custom_params
                self.available_parameters = all_params
                print(f"Fetched {len(all_params)} parameters.")
                # print(f"Available parameters: {self.available_parameters}") # Optional: very verbose
            elif response and response.get('data', {}).get('errorID'):
                error_msg = response.get('data', {}).get('message', 'Unknown VTS Error')
                print(f"Error fetching parameters: {error_msg}")
                self.available_parameters = [] # Clear on error
            elif response and response.get("messageType") == "APIError":
                 error_msg = response.get('data', {}).get('message', 'Unknown VTS API Error')
                 print(f"API Error fetching parameters: {error_msg}")
                 self.available_parameters = [] # Clear on error
            else:
                print("Unknown response format when fetching parameters.")
                self.available_parameters = [] # Clear on unknown error

        except Exception as e:
            print(f"Exception while fetching parameters: {e}")
            self.available_parameters = [] # Clear on exception
        finally:
            # Ensure editor state is consistent with connection status
            if not self.is_connected:
                self.cancel_edit() # Hide editor if connection fails/drops
            # Re-enable button correctly based on outcome (moved from original finally)
            if hasattr(self.ids, 'connect_button'):
                self.ids.connect_button.disabled = False


    async def set_parameter_values(self, param_values: list[dict]):
        """
        Asynchronously sets multiple VTube Studio parameter values.
        param_values: A list of dictionaries, e.g.,
                      [{ "id": "ParamName1", "value": 0.8 },
                       { "id": "ParamName2", "value": -0.5 }]
        """
        if not self.is_connected or not self.vts:
            print("Cannot set parameters: Not connected to VTube Studio.")
            return

        print(f"Attempting to set parameters via generic request: {param_values}")
        try:
            # Construct the full request payload manually for InjectParameterDataRequest
            request_id = str(uuid.uuid4()) # Generate a unique ID
            payload = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": request_id,
                "messageType": "InjectParameterDataRequest",
                "data": {
                    # "faceFound": False, # Optional, defaults likely okay
                    "mode": "set", # Use "set" to directly set values
                    "parameterValues": param_values # Pass the list directly
                }
            }

            print(f"Sending InjectParameterDataRequest payload: {payload}")
            # Use the generic request method
            response = await self.vts.request(payload)
            print(f"InjectParameterDataRequest response: {response}")

            # Check response for errors (structure might vary slightly)
            if response and response.get('data', {}).get('errorID'):
                 error_msg = response.get('data', {}).get('message', 'Unknown VTS Error')
                 print(f"Error setting parameters via InjectParameterDataRequest: {error_msg}")
                 # Optionally update UI or raise an exception
            elif response and response.get("messageType") == "APIError":
                 # Handle APIError messageType if it occurs
                 error_msg = response.get('data', {}).get('message', 'Unknown VTS API Error')
                 print(f"API Error setting parameters: {error_msg}")
            else:
                 print("Parameters set successfully via InjectParameterDataRequest (based on response).")

        except Exception as e:
            print(f"Exception while setting parameters via generic request: {e}")
            # Optionally update UI

    def trigger_vts_animation(self, animation_data: dict):
        """
        Triggered by the VTSAnimationList component when an animation button is pressed.
        Sets the parameter values defined in the animation data.
        Handles 'parameters' being either a dict {name: value} or a list [{'id': name, 'value': value}].
        """
        params_data = animation_data.get("parameters") # Get the parameters data
        anim_name = animation_data.get("name", "Unnamed")

        if not params_data:
            print(f"Animation '{anim_name}' has no parameters defined.")
            return

        param_values_list = []
        if isinstance(params_data, dict):
            # Convert dict {name: value} to list of dicts [{"id": name, "value": value}]
            print(f"Converting parameters dict to list for animation '{anim_name}'")
            param_values_list = [{"id": name, "value": val} for name, val in params_data.items()]
        elif isinstance(params_data, list):
            # Assume it's already in the correct list format [{"id": name, "value": value}]
            # Basic validation could be added here if needed
            print(f"Using parameters list directly for animation '{anim_name}'")
            param_values_list = params_data
        else:
            print(f"Error: Unexpected type for 'parameters' in animation '{anim_name}': {type(params_data)}")
            return # Don't proceed if the format is wrong

        if not param_values_list:
             print(f"Animation '{anim_name}' resulted in empty parameter list after processing.")
             return

        print(f"Scheduling '{anim_name}' animation parameter set...")
        Clock.schedule_once(lambda dt: asyncio.create_task(self.set_parameter_values(param_values_list)))

    # --- Inline Editor Interaction Logic ---

    def _refresh_animation_list(self):
        """Refreshes the VTSAnimationList widget."""
        print("VTubeTab: Refreshing animation list.")
        anim_list_widget = self.ids.get('vts_animation_list_widget')
        if anim_list_widget:
            anim_list_widget.load_animations()
        else:
            print("Error: Cannot refresh list, vts_animation_list_widget not found.")

    def handle_add_new_animation_button(self):
        """Shows and prepares the inline editor panel for adding a new animation."""
        if not self.is_connected or not self.available_parameters:
            self._show_popup("Error", "Connect to VTS and load parameters first.")
            print("Cannot add animation: Connect to VTS and ensure parameters are loaded.")
            return

        editor_panel = self.ids.get('editor_panel')
        if not editor_panel:
            print("Error: editor_panel not found in VTubeTab ids.")
            return

        print("VTubeTab: Activating editor panel for new animation.")
        self.editing_animation_data = {} # Clear any previous edit data
        self.is_editing = True # This will make the panel visible via KV binding
        # Populate the panel with available params and no existing data
        editor_panel.populate_editor(self.available_parameters, None)

    def handle_edit_animation_selection(self, animation_data):
        """Shows and prepares the inline editor panel with the selected animation's data."""
        if not self.is_connected or not self.available_parameters:
            self._show_popup("Error", "Connect to VTS and load parameters first.")
            print("Cannot edit animation: Connect to VTS and ensure parameters are loaded.")
            return

        editor_panel = self.ids.get('editor_panel')
        if not editor_panel:
            print("Error: editor_panel not found in VTubeTab ids.")
            return

        anim_name = animation_data.get("name", "Unnamed")
        print(f"VTubeTab: Activating editor panel to edit '{anim_name}'.")
        self.editing_animation_data = animation_data # Store data being edited
        self.is_editing = True # Make panel visible
        # Populate the panel with available params and the selected data
        editor_panel.populate_editor(self.available_parameters, animation_data)

    def save_edited_animation(self, save_data):
        """
        Handles the 'on_save_animation' event from the AnimationEditorPanel.
        Saves the animation data to a JSON file.
        """
        anim_name = save_data.get("name")
        current_params = save_data.get("parameters")
        original_filename_base = save_data.get("_filename") # Present if editing

        if not anim_name or current_params is None:
            print("Error: Invalid data received from editor panel for saving.")
            self._show_popup("Save Error", "Invalid data received from editor.")
            return

        # Determine filename
        if original_filename_base: # Editing existing
            filename_base = original_filename_base
        else: # Adding new
            # Basic sanitization for filename
            filename_base = "".join(c for c in anim_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
            filename_base = filename_base.replace(' ', '_')
            if not filename_base:
                filename_base = "unnamed_animation"

        filename = f"{filename_base}.json"
        animations_dir = self.get_animations_dir()
        if not animations_dir:
            print("Error: Cannot determine animations directory for saving.")
            self._show_popup("Save Error", "Could not determine animations directory.")
            return

        filepath = os.path.join(animations_dir, filename)

        # Data structure to save (ensure parameters are dict, not list)
        data_to_write = {
            "name": anim_name,
            "parameters": current_params # Already a dict {name: value} from VTSParamList
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_write, f, indent=4)
            print(f"Animation saved successfully to: {filepath}")
            self._show_popup("Success", f"Animation '{anim_name}' saved.")

            self._refresh_animation_list() # Update the list on the left
            self.cancel_edit() # Hide the editor panel

        except Exception as e:
            print(f"Error saving animation file {filepath}: {e}")
            self._show_popup("Save Error", f"Error saving file:\n{e}")

    def cancel_edit(self):
        """Handles the 'on_cancel_edit' event. Hides the editor panel."""
        print("VTubeTab: Cancelling edit.")
        self.is_editing = False
        self.editing_animation_data = None

    def copy_param_names_to_clipboard(self):
        """Handles 'on_copy_names'. Copies parameter names to clipboard."""
        editor_panel = self.ids.get('editor_panel')
        if not editor_panel or not editor_panel.ids.get('editor_param_list'):
            print("Error: Cannot copy names, editor panel or param list not found.")
            self._show_popup("Error", "Could not find parameter list widget.")
            return

        param_list_widget = editor_panel.ids.editor_param_list
        all_params_data = param_list_widget._all_parameters # Access internal list
        param_names = [p.get('name') for p in all_params_data if p.get('name')]

        if not param_names:
            print("No parameter names found to copy.")
            self._show_popup("Info", "No parameter names available to copy.")
            return

        try:
            json_string = json.dumps(param_names, indent=4)
            Clipboard.copy(json_string)
            print(f"Copied {len(param_names)} parameter names to clipboard.")
            self._show_popup("Success", f"Copied {len(param_names)} parameter names\nto clipboard as JSON.")
        except Exception as e:
            print(f"Error converting parameter names to JSON or copying: {e}")
            self._show_popup("Error", f"Failed to copy names:\n{e}")

    def set_animation_from_clipboard(self):
        """Handles 'on_set_from_clipboard'. Sets editor values from clipboard JSON."""
        editor_panel = self.ids.get('editor_panel')
        if not editor_panel:
             print("Error: Cannot set from clipboard, editor panel not found.")
             self._show_popup("Error", "Editor panel not found.")
             return

        # Get references to widgets inside the editor panel
        animation_name_input = editor_panel.ids.get('editor_animation_name_input')
        param_list_widget = editor_panel.ids.get('editor_param_list')

        if not param_list_widget or not animation_name_input:
            print("Error: Cannot set from clipboard, editor widgets not linked.")
            self._show_popup("Error", "Editor widgets not properly linked.")
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
        if not isinstance(data, dict) or \
           'name' not in data or not isinstance(data.get('name'), str) or \
           'parameters' not in data or not isinstance(data.get('parameters'), dict):
            print("Error: Clipboard JSON has incorrect structure.")
            self._show_popup("Error", "Clipboard JSON format incorrect.\nExpected: {'name': '...', 'parameters': {...}}")
            return

        # --- Apply data ---
        new_anim_name = data['name']
        clipboard_params = data['parameters'] # Should be {name: value}

        # Update animation name input
        animation_name_input.text = new_anim_name

        # Update parameter values in the list
        current_full_params = param_list_widget._all_parameters # Get full structure
        updated_params_list = []
        params_updated_count = 0
        params_not_found_count = 0

        for param_struct in current_full_params:
            param_name = param_struct.get('name')
            new_param_struct = param_struct.copy() # Work on a copy

            if param_name and param_name in clipboard_params:
                new_value = clipboard_params[param_name]
                if isinstance(new_value, (int, float)):
                    min_val = new_param_struct.get('min', 0)
                    max_val = new_param_struct.get('max', 1)
                    clamped_value = max(min_val, min(float(new_value), max_val)) # Ensure float
                    new_param_struct['value'] = clamped_value
                    params_updated_count += 1
                else:
                    print(f"Warning: Invalid value type for '{param_name}' in clipboard.")
            elif param_name:
                 params_not_found_count += 1

            updated_params_list.append(new_param_struct)

        # Update the VTSParamList with the modified list
        param_list_widget.set_parameters(updated_params_list)

        print(f"Set animation from clipboard: Name='{new_anim_name}', {params_updated_count} parameters updated.")
        msg = f"Set animation: '{new_anim_name}'\n{params_updated_count} parameters updated."
        if params_not_found_count > 0:
            msg += f"\n({params_not_found_count} parameters not found in clipboard data.)"
            self._show_popup("Success (with warnings)", msg)
        else:
            self._show_popup("Success", msg)


    # --- Helper Functions ---
    def _show_popup(self, title, message):
        """Helper to show a simple popup message."""
        popup = Popup(title=title,
                      content=Label(text=message, halign='center', valign='middle'),
                      size_hint=(0.6, 0.3),
                      auto_dismiss=True)
        popup.open()

    def get_animations_dir(self):
        """Gets the path to the animations directory."""
        app_data_root = os.getenv('APPDATA')
        if not app_data_root:
             print("Error: Could not determine APPDATA directory.")
             return None
        animations_path = os.path.join(app_data_root, 'NsTut', 'LilyTheThird', 'vtube', 'animations')
        os.makedirs(animations_path, exist_ok=True) # Ensure it exists
        return animations_path

    # --- Animation List Filtering ---
    def filter_animations(self, search_text: str):
        """Filters the displayed animations in the VTSAnimationList."""
        anim_list_widget = self.ids.get('vts_animation_list_widget')
        if anim_list_widget:
            anim_list_widget.filter_display(search_text)
        else:
            print("Error: Cannot filter, vts_animation_list_widget not found.")

    def handle_delete_animation(self, animation_data):
        """Handles the 'on_delete_animation' event from VTSAnimationList."""
        anim_name = animation_data.get("name", "Unnamed")
        filename_base = animation_data.get('_filename')

        if not filename_base:
            print(f"Error: Cannot delete animation '{anim_name}', missing filename information.")
            self._show_popup("Delete Error", f"Could not determine the file for '{anim_name}'.")
            return

        # --- Confirmation Dialog ---
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        content.add_widget(Label(text=f"Are you sure you want to delete\nthe animation '{anim_name}'?\nThis cannot be undone.", halign='center'))
        buttons = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))

        confirm_button = Button(text="Delete")
        cancel_button = Button(text="Cancel")
        buttons.add_widget(confirm_button)
        buttons.add_widget(cancel_button)
        content.add_widget(buttons)

        popup = Popup(title="Confirm Deletion",
                      content=content,
                      size_hint=(0.7, 0.4),
                      auto_dismiss=False) # Prevent dismissing by clicking outside

        def _confirm_delete(instance):
            popup.dismiss()
            self._perform_delete(animation_data)

        def _cancel_delete(instance):
            popup.dismiss()
            print(f"Deletion cancelled for '{anim_name}'.")

        confirm_button.bind(on_press=_confirm_delete)
        cancel_button.bind(on_press=_cancel_delete)

        popup.open()

    def _perform_delete(self, animation_data):
        """Actually performs the file deletion after confirmation."""
        anim_name = animation_data.get("name", "Unnamed")
        filename_base = animation_data.get('_filename')
        # Double-check filename_base just in case
        if not filename_base:
            print(f"Error: Filename base missing during confirmed delete for '{anim_name}'.")
            self._show_popup("Internal Error", "Filename missing during delete.")
            return

        animations_dir = self.get_animations_dir()
        if not animations_dir:
            print(f"Error: Cannot determine animations directory for deleting '{anim_name}'.")
            self._show_popup("Delete Error", "Could not determine animations directory.")
            return

        filepath = os.path.join(animations_dir, f"{filename_base}.json")

        try:
            os.remove(filepath)
            print(f"Successfully deleted animation file: {filepath}")
            self._show_popup("Success", f"Animation '{anim_name}' deleted.")

            # Refresh the animation list
            self._refresh_animation_list()

            # If the deleted animation was being edited, close the editor
            if self.is_editing and self.editing_animation_data and \
               self.editing_animation_data.get('_filename') == filename_base:
                self.cancel_edit()

        except FileNotFoundError:
            print(f"Error deleting file: {filepath} not found.")
            self._show_popup("Delete Error", f"File not found:\n{filename_base}.json")
            # Refresh list anyway, in case it was already gone
            self._refresh_animation_list()
        except OSError as e:
            print(f"Error deleting file {filepath}: {e}")
            self._show_popup("Delete Error", f"Error deleting file:\n{e}")
        except Exception as e:
            print(f"Unexpected error during deletion of {filepath}: {e}")
            self._show_popup("Delete Error", f"An unexpected error occurred:\n{e}")
