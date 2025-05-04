import asyncio
import pyvts
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
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
            # Re-initialize vts instance if it was set to None after a disconnect
            if self.vts is None:
                print("Re-initializing pyvts instance for connection...")
                self.vts = pyvts.vts(
                    pluginname=self.plugin_name,
                    pluginauthor=self.plugin_developer,
                    host=self.vts_host,
                    port=self.vts_port
                )

            # Always attempt connection/reconnection. Assume pyvts handles the state.
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
            else:
                # Authentication failed or didn't return True - Token likely missing or invalid, request a new one
                print("VTS Authentication Failed or indeterminate. Requesting new token...")
                self.status_text = "Authenticating... (Check VTube Studio for prompt)"
                try:
                    await self.vts.request_authenticate_token()
                    print("VTS Token Requested. Waiting for user approval...")
                    self.status_text = "Authenticating... (Check VTube Studio for prompt)"

                    # --- Start Polling for Authentication ---
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
                        # Close connection if authentication ultimately failed
                        if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                            await self.vts.close()
                            print("VTS connection closed due to authentication timeout.")
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

        # Only set vts to None if close was attempted and successful
        if closed_successfully:
             self.vts = None
             print("VTS instance set to None.")

        # Reset state after attempting close
        self.is_connected = False
        self.button_text = "Connect"
        self.status_text = "Not Connected"
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
            # --- Modified Disconnect Behavior ---
            # When connected, clicking "Disconnect" will only reset the UI state.
            # It will NOT actually close the websocket connection to avoid duplicate plugin issues.
            # User must restart the app to fully disconnect the plugin from VTS.
            print("Disconnect button clicked: Resetting UI state only. Connection remains active.")
            self.is_connected = False
            self.button_text = "Connect"
            self.status_text = "Not Connected (UI Reset)"
            # Re-enable button as we are simulating disconnection
            if hasattr(self.ids, 'connect_button'):
                self.ids.connect_button.disabled = False
            # DO NOT call Clock.schedule_once(lambda dt: asyncio.create_task(self._disconnect_vts()))

    # --- Example VTS Interaction (Optional) ---
    # You can add methods here to interact with VTS once connected
    # For example, triggering a hotkey:
    # async def trigger_hotkey(self, hotkey_id):
    #     if self.is_connected and self.vts:
    #         try:
    #             response = await self.vts.request(self.vts.requestTriggerHotkey(hotkeyID=hotkey_id))
    #             print(f"Hotkey {hotkey_id} triggered: {response}")
    #             # Handle response if needed
    #         except Exception as e:
    #             print(f"Error triggering hotkey {hotkey_id}: {e}")
    #     else:
    #         print("Cannot trigger hotkey: Not connected to VTube Studio.")

    # def trigger_example_hotkey(self):
    #      # Example: Call this from a button press in the kv file
    #      # Replace "YourHotkeyID" with an actual hotkey ID from VTS
    #      Clock.schedule_once(lambda dt: asyncio.create_task(self.trigger_hotkey("YourHotkeyID")))
