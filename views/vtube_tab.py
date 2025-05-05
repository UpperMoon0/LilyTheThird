import asyncio
import asyncio
import os # Added for file operations
import uuid # Import uuid for request IDs
import pyvts
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty, DictProperty
from kivy.lang import Builder
from kivy.clock import Clock
from views.components.rgb_strip import RGBStrip
from views.components.vts_animation_list import VTSAnimationList
from views.components.vts_param_list import VTSParamList # Import param list for editor

# Load the corresponding kv file automatically by Kivy convention (vtubetab.kv)

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
    is_editing = BooleanProperty(False) # True when adding or editing an animation
    editing_animation_data = DictProperty(None, allownone=True) # Data being edited

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize vts instance
        self.vts = pyvts.vts(
            pluginname=self.plugin_name,
            pluginauthor=self.plugin_developer,
            host=self.vts_host,
            port=self.vts_port
        )
        # No modal instantiation needed
        # Ensure editor is initially cleared
        Clock.schedule_once(lambda dt: self.cancel_edit()) # Clear editor on startup

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

    # Removed on_available_parameters method - parameter list is now in the modal

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

    # --- Integrated Editor Panel Logic ---

    def _populate_editor(self, animation_data=None):
        """Populates the editor panel fields."""
        editor_name_input = self.ids.get('editor_animation_name_input')
        editor_param_list = self.ids.get('editor_param_list')
        editor_title = self.ids.get('editor_title_label')

        if not editor_name_input or not editor_param_list or not editor_title:
            print("Error: Editor widgets not found in VTubeTab ids.")
            return

        if animation_data: # Editing existing animation
            self.editing_animation_data = animation_data
            editor_title.text = f"Editing: {animation_data.get('name', 'Unnamed')}"
            editor_name_input.text = animation_data.get('name', '')
            saved_param_values = animation_data.get('parameters', {})

            # Convert list format (old?) to dict format
            saved_param_values_dict = {}
            if isinstance(saved_param_values, list):
                print("Warning: Converting old list-based parameter format to dictionary.")
                for item in saved_param_values:
                    if isinstance(item, dict) and 'id' in item and 'value' in item:
                        saved_param_values_dict[item['id']] = item['value']
                # If conversion failed or list was empty, keep it as an empty dict
            elif isinstance(saved_param_values, dict):
                saved_param_values_dict = saved_param_values
            else:
                 # Handle unexpected type if necessary, default to empty dict
                 print(f"Warning: Unexpected type for saved_param_values: {type(saved_param_values)}. Using empty dict.")

        else: # Adding new animation or clearing
            self.editing_animation_data = None # Ensure it's cleared for 'add' mode
            editor_title.text = "Add New Animation"
            editor_name_input.text = ""
            saved_param_values_dict = {} # Use the same dict variable name for consistency

        # Populate parameter list
        params_to_display = []
        for vts_param in self.available_parameters:
            param_name = vts_param.get('name')
            if not param_name: continue
            display_param = vts_param.copy()
            # Override value if it exists in the animation being edited, else use VTS default
            # Use the potentially converted dictionary here
            display_param['value'] = saved_param_values_dict.get(param_name, vts_param.get('value', 0))
            params_to_display.append(display_param)

        editor_param_list.set_parameters(params_to_display)
        self.is_editing = True # Enable save/cancel buttons

    def handle_add_new_animation_button(self):
        """Prepares the editor panel for adding a new animation."""
        if not self.is_connected or not self.available_parameters:
            print("Cannot add animation: Connect to VTS and ensure parameters are loaded.")
            # TODO: Show user feedback
            return
        print("VTubeTab: Preparing editor for new animation.")
        self._populate_editor(animation_data=None) # Populate with defaults

    def handle_edit_animation_selection(self, animation_data):
        """Populates the editor panel with the selected animation's data."""
        if not self.is_connected or not self.available_parameters:
            print("Cannot edit animation: Connect to VTS and ensure parameters are loaded.")
            return
        anim_name = animation_data.get("name", "Unnamed")
        print(f"VTubeTab: Loading '{anim_name}' into editor.")
        self._populate_editor(animation_data=animation_data)

    def save_edited_animation(self):
        """Saves the animation currently in the editor panel."""
        editor_name_input = self.ids.get('editor_animation_name_input')
        editor_param_list = self.ids.get('editor_param_list')

        if not editor_name_input or not editor_param_list:
            print("Error: Cannot save, editor widgets not found.")
            return

        anim_name = editor_name_input.text.strip()
        if not anim_name:
            print("Error: Animation name cannot be empty.")
            # TODO: Show feedback (e.g., red border on input)
            return

        current_params = editor_param_list.get_current_parameter_values()
        save_data = {"name": anim_name, "parameters": current_params}

        # Determine filename
        if self.editing_animation_data and '_filename' in self.editing_animation_data:
            filename_base = self.editing_animation_data['_filename'] # Reuse existing base name
        else: # New animation
            filename_base = "".join(c for c in anim_name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(' ', '_')
            if not filename_base: filename_base = "unnamed_animation"

        filename = f"{filename_base}.json"
        animations_dir = self.get_animations_dir() # Use helper to get dir path
        if not animations_dir: return # Error handled in helper

        filepath = os.path.join(animations_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4)
            print(f"Animation saved successfully to: {filepath}")

            # Refresh the animation list in Column A
            anim_list_widget = self.ids.get('vts_animation_list_widget')
            if anim_list_widget:
                anim_list_widget.load_animations()

            self.cancel_edit() # Clear the editor panel

        except Exception as e:
            print(f"Error saving animation file {filepath}: {e}")
            # TODO: Show error message to the user

    def cancel_edit(self):
        """Clears the editor panel and resets its state."""
        editor_name_input = self.ids.get('editor_animation_name_input')
        editor_param_list = self.ids.get('editor_param_list')
        editor_title = self.ids.get('editor_title_label')

        if editor_name_input: editor_name_input.text = ""
        if editor_param_list: editor_param_list.clear_parameters()
        if editor_title: editor_title.text = "Animation Editor"

        self.is_editing = False
        self.editing_animation_data = None
        print("VTubeTab: Editor cleared.")

    def get_animations_dir(self):
        """Gets the path to the animations directory (consistent with VTSAnimationList)."""
        # Duplicated from modal logic for now, could be refactored into a utility
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

    # --- Placeholder for Delete ---
    def handle_delete_animation(self, animation_data):
        """Placeholder triggered by VTSAnimationList's 'Delete' button."""
        # TODO: Implement confirmation dialog and file deletion logic
        anim_name = animation_data.get("name", "Unnamed")
        print(f"VTubeTab: Delete Animation requested for '{anim_name}'.")
        # Example: Show confirmation, then if confirmed:
        # filename_base = animation_data.get('_filename')
        # if filename_base:
        #     animations_dir = self.get_animations_dir()
        #     filepath = os.path.join(animations_dir, f"{filename_base}.json")
        #     try:
        #         os.remove(filepath)
        #         print(f"Deleted animation file: {filepath}")
        #         # Refresh list
        #         anim_list_widget = self.ids.get('vts_animation_list_widget')
        #         if anim_list_widget: anim_list_widget.load_animations()
        #         self.cancel_edit() # Clear editor if the deleted item was being edited
        #     except OSError as e:
        #         print(f"Error deleting file {filepath}: {e}")
