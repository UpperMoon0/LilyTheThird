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
    plugin_developer = "YourName" # Replace with your name/alias
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

        try:
            await self.vts.connect()
            print("VTS Connected to WebSocket")

            # --- Authentication Process ---
            # Assume request_authenticate returns True/False or raises error
            authenticated = False
            try:
                print("Checking VTS Authentication...")
                authenticated = await self.vts.request_authenticate()
                print(f"VTS Authentication Status: {authenticated}")

            except Exception as auth_err:
                # Handle potential errors during the initial auth check itself
                # (e.g., if the library raises an error instead of returning False)
                print(f"Error during initial VTS authentication check: {auth_err}")
                self.status_text = f"Auth Check Error: {auth_err}"
                # Proceed to token request as authentication failed

            if not authenticated:
                # If not authenticated, try requesting a token.
                self.status_text = "Authenticating... (Check VTube Studio for prompt)"
                try:
                    print("Requesting VTS Authentication Token...")
                    # Assume request_authenticate_token doesn't return a useful value directly
                    await self.vts.request_authenticate_token()
                    print("VTS Token Requested. User needs to approve in VTube Studio.")
                    self.status_text = "Authentication Required. Please approve in VTube Studio and click Connect again."

                except Exception as token_err:
                    # Handle errors during token request (e.g., API disabled, VTS closed)
                    print(f"Error requesting VTS token: {token_err}")
                    self.status_text = f"Error requesting token: {token_err}"
                    # Still ensure connection is closed and state is reset
                    if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                        await self.vts.close()

                # Regardless of token request success/failure, authentication failed for *this* attempt.
                # User needs to approve and click connect *again*.
                self.is_connected = False
                self.button_text = "Connect"
                print("VTS Authentication Failed for this attempt.")
                # Ensure connection is closed if it wasn't already by an error handler
                if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
                    await self.vts.close()

            # This part only runs if the initial check returned authenticated = True
            else: # authenticated is True
                 self.is_connected = True
                 self.status_text = f"Connected to VTube Studio on {self.vts_host}:{self.vts_port}"
                 self.button_text = "Disconnect"
                 print("VTS Authentication Successful")

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
             # Re-enable button only if it exists in ids
             if hasattr(self.ids, 'connect_button'):
                 self.ids.connect_button.disabled = False


    async def _disconnect_vts(self):
        """Asynchronously disconnect from VTube Studio."""
        self.status_text = "Disconnecting..."
        # Disable button immediately if it exists
        if hasattr(self.ids, 'connect_button'):
            self.ids.connect_button.disabled = True

        # Check vts object exists and has ws attribute before checking connection
        if self.vts and hasattr(self.vts, 'ws') and self.vts.ws.connected:
            try:
                await self.vts.close()
                print("VTS Disconnected")
            except Exception as e:
                print(f"Error during VTS disconnection: {e}")

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
            self.status_text = "Disconnecting..." # Update status immediately
            # Run the async disconnection function
            Clock.schedule_once(lambda dt: asyncio.create_task(self._disconnect_vts()))

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
