import asyncio
import asyncio
import os # Added for file operations
import uuid # Import uuid for request IDs
import pyvts
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty # Added ListProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.label import Label # Added for displaying parameters
from views.components.rgb_strip import RGBStrip # Import the strip

# Load the corresponding kv file automatically by Kivy convention (vtubetab.kv)
# Builder.load_file('views/vtube_tab.kv') # REMOVED - Rely on automatic loading

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is set in the kv file
        # Initialize vts instance
        self.vts = pyvts.vts(
            pluginname=self.plugin_name,
            pluginauthor=self.plugin_developer,
            host=self.vts_host,
            port=self.vts_port
        )

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

    def on_available_parameters(self, instance, value):
        """Kivy property observer, schedules UI update when parameters are fetched."""
        # Schedule the UI update for the next frame to ensure stability
        Clock.schedule_once(self._update_parameter_ui)

    def _update_parameter_ui(self, dt=None):
        """Updates the parameter list UI based on the available_parameters property."""
        print("Updating parameter list UI (scheduled)...")
        param_list_layout = self.ids.get('param_list_layout')
        if not param_list_layout:
            print("Error: param_list_layout not found in ids during scheduled update.")
            return

        param_list_layout.clear_widgets()
        value = self.available_parameters # Use the current value of the property

        # Set height dynamically based on number of items
        # Adjust multiplier as needed for label height/padding
        param_list_layout.height = len(value) * 30 # Example: 30 pixels per label

        if not value:
            param_list_layout.add_widget(Label(text="No parameters found or error fetching.", size_hint_y=None, height=30))
        else:
            for param_data in value:
                param_name = param_data.get('name', 'Unknown Parameter')
                # You could add more info like min/max here if needed
                label_text = f"{param_name}"
                param_label = Label(text=label_text, size_hint_y=None, height=30)
                param_list_layout.add_widget(param_label)
        print("Parameter list UI update complete (scheduled).")


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

    def set_wink_smile_expression(self):
        """Sets the VTube Studio model parameters for a 'Wink Smile' expression."""
        print("Scheduling 'Wink Smile' expression parameter set...")
        param_values = [
            {"id": "EyeOpenLeft", "value": 0.0},
            {"id": "EyeOpenRight", "value": 1.0},
            {"id": "MouthSmile", "value": 0.8},
            {"id": "MouthOpen", "value": 0.1},
            {"id": "TongueOut", "value": 0.2}
            # Add other parameters to reset if needed, e.g., FaceAngry: 0.0
        ]
        # Schedule the async task to run
        Clock.schedule_once(lambda dt: asyncio.create_task(self.set_parameter_values(param_values)))
