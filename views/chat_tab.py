import asyncio
import threading
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ObjectProperty 
from kivy.clock import Clock
from kivy.lang import Builder

# Import settings manager functions
from settings_manager import load_chat_settings, save_chat_settings # UPDATED
# Import the ChatBoxLLM
from llm.chatbox_llm import ChatBoxLLM
# Import the LLM Config Mixin
from views.llm_config_mixin import LLMConfigMixin
from tts import generate_speech_from_provider # Import the TTS function

# Load the KV string for ChatTab
Builder.load_file('views/chat_tab.kv')

# Define colors for markup
USER_COLOR_HEX = "FFFFFF" # White
LLM_COLOR_HEX = "FFFFFF"  # White
SYSTEM_COLOR_HEX = "00FF00" # Green (Lime)

# Inherit from BoxLayout and the Mixin
class ChatTab(BoxLayout, LLMConfigMixin):
    """
    Kivy equivalent of the ChatTab QWidget, using LLMConfigMixin and ChatBox component.
    """
    # --- Properties specific to ChatTab (excluding those moved to ChatBox) ---
    # prompt_text = StringProperty("") # MOVED to ChatBox
    # response_text = StringProperty("") # MOVED to ChatBox
    tts_enabled = BooleanProperty(False) # Renamed from tts_provider_enabled for consistency
    selected_tts_model = StringProperty("edge") # Added TTS model property
    # is_recording = BooleanProperty(False) # MOVED to ChatBox (state managed here, UI in ChatBox)
    # record_button_icon = StringProperty("assets/mic_idle.png") # MOVED to ChatBox
    temperature = NumericProperty(0.7) # Default temperature
    selected_tts_speaker = NumericProperty(1) # ADDED TTS speaker ID property

    # Flag to indicate if the backend LLM is ready
    backend_initialized = BooleanProperty(False)
    initialization_status = StringProperty("Initializing backend...") # Status message

    # Object properties to hold references to widgets if needed
    # prompt_input = ObjectProperty(None) # MOVED to ChatBox
    send_button = ObjectProperty(None) # Keep if separate send button exists
    chat_box = ObjectProperty(None) # Reference to ChatBox instance
    actions_list = ObjectProperty(None) # ADDED reference to ActionsList instance
    action_details = ObjectProperty(None) # ADDED reference to ActionDetails instance
    llm_instance: ChatBoxLLM = None # To hold the LLM instance
    selected_action_data = ObjectProperty(None, allownone=True) # ADDED property for selected action

    # Internal state for recording (if needed beyond UI)
    _is_currently_recording = BooleanProperty(False)

    # --- LLMConfigMixin Implementation ---
    def _get_provider_setting_key(self) -> str:
        return 'selected_provider' # Key used in settings for ChatTab provider

    def _get_model_setting_key(self) -> str:
        return 'selected_model' # Key used in settings for ChatTab model

    # --- Initialization ---
    def __init__(self, **kwargs):
        # Explicitly load KV string *before* super init
        # Builder.load_string(CHAT_TAB_KV) # Moved outside class definition
        super().__init__(**kwargs)
        
        # Set the load and save functions for the LLMConfigMixin
        self.load_function = load_chat_settings
        self.save_function = save_chat_settings
        
        # Load general settings first
        self._load_chat_settings() # Loads non-LLM chat settings
        # Load LLM specific settings using the mixin method (which now uses self.load_function)
        self.initialize_llm_config() # New call to mixin method
        
        # Bindings
        self.bind(selected_provider=self._handle_selected_provider_change) # Bind to mixin's handler
        self.bind(selected_model=self._handle_selected_model_change)     # Bind to mixin's handler

        Clock.schedule_once(self._post_init)

    def _load_chat_settings(self):
        """Load settings specific to ChatTab (excluding LLM provider/model)."""
        # This method now specifically loads non-LLM settings for the chat tab.
        # LLM provider/model are handled by _load_llm_settings via the mixin.
        settings = self.load_function() # Uses load_chat_settings
        print(f"ChatTab: Loading non-LLM settings using {self.load_function.__name__}: {settings}")
        # Use .get() with defaults
        self.tts_enabled = settings.get('tts_provider_enabled', False) # Key from DEFAULT_CHAT_SETTINGS
        self.selected_tts_model = settings.get('selected_tts_model', 'edge') # Load selected TTS model
        self.selected_tts_speaker = settings.get('selected_tts_speaker', 1) # Load selected TTS speaker ID
        self.temperature = settings.get('temperature', 0.7) # Key from DEFAULT_CHAT_SETTINGS

    def _post_init(self, dt):
        """Tasks to run after widgets are loaded."""
        # Link chat_box property FIRST
        self.chat_box = self.ids.get('chat_box')
        if not self.chat_box:
             print("ChatTab FATAL Error: Could not find ChatBox with id 'chat_box'. Check chattab.kv naming and structure.")
             return # Stop initialization
        # Link actions_list property
        self.actions_list = self.ids.get('actions_list')
        if not self.actions_list:
             print("ChatTab FATAL Error: Could not find ActionsList with id 'actions_list'. Check chattab.kv naming and structure.")
             # Decide if this is fatal or just a warning
             # return # Stop initialization if fatal
        # Link action_details property
        self.action_details = self.ids.get('action_details')
        if not self.action_details:
             print("ChatTab FATAL Error: Could not find ActionDetails with id 'action_details'. Check chattab.kv naming and structure.")
             # Decide if this is fatal or just a warning
             # return # Stop initialization if fatal

        # Now that chat_box is linked, bind the backend_initialized property change
        self.bind(backend_initialized=self._update_chat_box_initialization)
        # Also, immediately update the chat_box's state if backend is already initialized (unlikely here, but safe)
        self._update_chat_box_initialization(self, self.backend_initialized)


        # Initial population of models
        self.update_models(initial_load=True)

        # Add initial status message *after* linking chat_box
        # No need to schedule this separately now, as chat_box is confirmed linked
        self.add_message("System", self.initialization_status, scroll=False)

        # Start backend initialization in a separate thread
        threading.Thread(target=self._initialize_backend_thread, daemon=True).start()

    # update_models and set_update_flag are now inherited from LLMConfigMixin

    # --- Callbacks for saving settings ---
    # These methods now handle ChatTab specific actions (like updating LLM instance)
    # and call the appropriate mixin methods for saving LLM config or chat-specific settings.

    # Note: The actual binding happens in __init__ to these specific methods.
    # def on_selected_provider_changed_chat(self, instance, value): # MOVED to LLMConfigMixin as _handle_selected_provider_change
    #     """Callback when provider changes. Updates models, then schedules save and LLM update."""
    #     print(f"DEBUG: ChatTab: own on_selected_provider_changed_chat. New provider: {value}")
    #     print(f"DEBUG: ChatTab: BEFORE update_models: self.llm_models={self.llm_models}, self.selected_model='{self.selected_model}', self.selected_provider='{self.selected_provider}'")
        
    #     # 1. Update models and set the default selected_model for the new provider
    #     self.update_models() # This updates self.llm_models and self.selected_model on ChatTab
        
    #     print(f"DEBUG: ChatTab: AFTER update_models: self.llm_models={self.llm_models}, self.selected_model='{self.selected_model}', self.selected_provider='{self.selected_provider}'")

    #     # Check ChatBoxSettings properties directly via ids
    #     if hasattr(self, 'ids') and 'chat_controls' in self.ids:
    #         chat_settings_widget = self.ids.chat_controls
    #         print(f"DEBUG: ChatTab: Accessing chat_controls.llm_models: {chat_settings_widget.llm_models}")
    #         print(f"DEBUG: ChatTab: Accessing chat_controls.selected_model: '{chat_settings_widget.selected_model}'")
    #         print(f"DEBUG: ChatTab: Accessing chat_controls.selected_provider: '{chat_settings_widget.selected_provider}'")
    #     else:
    #         print("DEBUG: ChatTab: chat_controls (ChatBoxSettings instance) not found in self.ids.")

    #     # 2. Schedule save and update AFTER update_models finishes and clears its flag
    #     Clock.schedule_once(self._save_and_update_llm_after_provider_change, 0.1) # Small delay

    # def _save_and_update_llm_after_provider_change(self, dt): # Partially MOVED to mixin's _save_settings_and_notify_provider_change
    #     """Helper function scheduled after provider change to save and update."""
    #     # Save LLM settings (handled by mixin)
    #     self._save_llm_settings()

    #     # Specific ChatTab action: Trigger LLM instance update if ready
    #     if self.backend_initialized:
    #         self._start_llm_instance_update_thread()
    #     else:
    #         print("ChatTab: Provider changed, backend not ready. Settings saved.")

    # def on_selected_model_changed_chat(self, instance, value): # MOVED to LLMConfigMixin as _handle_selected_model_change
    #     """Callback when model changes (user interaction or default set). Saves and triggers LLM update."""
    #     print(f"DEBUG: ChatTab: own on_selected_model_changed_chat. New model: {value}, _updating_models: {self._updating_models}")
    #     if value and hasattr(self, 'llm_models') and value in self.llm_models:
    #         print(f"DEBUG: ChatTab: User selected model: {value}. Saving and updating LLM.")
    #         self._save_llm_settings() # Save LLM settings (handled by mixin)
            
    #         # Check ChatBoxSettings properties directly via ids
    #         if hasattr(self, 'ids') and 'chat_controls' in self.ids:
    #             chat_settings_widget = self.ids.chat_controls
    #             print(f"DEBUG: ChatTab: (model change) Accessing chat_controls.selected_model: '{chat_settings_widget.selected_model}'")
    #         else:
    #             print("DEBUG: ChatTab: (model change) chat_controls (ChatBoxSettings instance) not found in self.ids.")

    #         # Specific ChatTab action: Trigger LLM instance update if ready
    #         if self.backend_initialized:
    #             self._start_llm_instance_update_thread()
    #         else:
    #             print("ChatTab: Model changed by user, backend not ready. Settings saved.")
    #     elif not value:
    #          print(f"ChatTab: Model selection cleared or invalid by user.")

    # --- LLMConfigMixin Hooks Implementation ---
    def on_llm_provider_updated(self):
        """Called by LLMConfigMixin after provider is updated and saved."""
        super().on_llm_provider_updated() # Call super if it does anything in the future
        print("ChatTab: LLM Provider has been updated. Triggering LLM instance update.")
        if self.backend_initialized:
            self._start_llm_instance_update_thread()
        else:
            print("ChatTab: Provider updated, but backend not ready. Settings saved.")

    def on_llm_model_updated(self):
        """Called by LLMConfigMixin after model is updated and saved."""
        super().on_llm_model_updated()
        print("ChatTab: LLM Model has been updated. Triggering LLM instance update.")
        if self.backend_initialized:
            self._start_llm_instance_update_thread()
        else:
            print("ChatTab: Model updated, but backend not ready. Settings saved.")

    # --- Existing ChatTab specific methods ---
    def on_tts_enabled(self, instance, value):
        """Callback when TTS checkbox changes."""
        print(f"ChatTab: TTS Enabled changed to: {value}")
        self._save_chat_settings() # Save only chat-specific settings
        # Add logic if needed when TTS state changes (e.g., load/unload TTS engine)

    def on_temperature(self, instance, value):
        """Callback when temperature slider changes."""
        print(f"ChatTab: Temperature changed to: {value:.2f}")
        self._save_chat_settings() # Save only chat-specific settings

    def on_selected_tts_model(self, instance, value):
        """Callback when TTS model changes."""
        print(f"ChatTab: Selected TTS Model changed to: {value}")
        self._save_chat_settings() # Save chat-specific settings

    def on_selected_tts_speaker(self, instance, value): # ADDED Kivy property observer
        """Called when selected_tts_speaker changes."""
        self._save_chat_settings()

    def _save_chat_settings(self):
        """Helper method to save only the ChatTab specific settings (TTS, temperature)."""
        if not self.load_function or not self.save_function:
            print("ChatTab: Error - load_function or save_function not set. Cannot save chat-specific settings.")
            return

        settings = self.load_function() # Load existing chat settings first
        settings['tts_provider_enabled'] = self.tts_enabled
        settings['selected_tts_model'] = self.selected_tts_model # Save selected TTS model
        settings['selected_tts_speaker'] = self.selected_tts_speaker # Save selected TTS speaker ID
        settings['temperature'] = self.temperature
        self.save_function(settings) # Save updated chat settings
        print(f"ChatTab: Chat-specific settings (TTS, temp, tts_model) saved using {self.save_function.__name__}.")

    # _save_llm_settings is inherited from LLMConfigMixin and will use self.save_function

    # --- Action Handling ---
    def on_action_selected(self, instance, action_data):
        """Handles the 'on_action_selected' event from ActionsList."""
        print(f"ChatTab: Received selected action data: {action_data.get('tool_name')}")
        self.selected_action_data = action_data

    # --- Backend Initialization and Update (Remains largely the same) ---
    def _initialize_backend_thread(self):
        """Runs LLM initialization in a background thread."""
        print("ChatTab: Backend initialization thread started.")
        instance = None
        error_message = None
        try:
            # This is the blocking call
            instance = ChatBoxLLM(provider=self.selected_provider, model_name=self.selected_model)
            print("ChatTab: Backend ChatBoxLLM instance created successfully in thread.")
        except Exception as e:
            print(f"ChatTab: Error initializing backend LLM instance in thread: {e}")
            error_message = f"Error initializing backend: {e}"
            instance = None

        # Schedule the final update on the main Kivy thread
        Clock.schedule_once(lambda dt: self._finish_backend_initialization(instance, error_message))

    def _finish_backend_initialization(self, instance, error_message):
        """Called on the main thread to update UI after backend init."""
        print("ChatTab: Finishing backend initialization on main thread.")
        status_message = ""
        if instance:
            self.llm_instance = instance
            # Set the flag. The binding added in _post_init will trigger _update_chat_box_initialization
            self.backend_initialized = True
            status_message = "Backend initialized successfully."
            print("ChatTab: Backend marked as initialized.")

            # --- Model Mismatch Check ---
            if self.llm_instance and self.selected_model != self.llm_instance.model: # Use .model instead of .model_name
                print(f"ChatTab: Model mismatch after init ({self.selected_model} vs {self.llm_instance.model}). Triggering update.")
                self._start_llm_instance_update_thread()
            # --- END ADDED CHECK ---

        else:
            self.llm_instance = None
            self.backend_initialized = False # Set the flag. Binding will trigger update.
            status_message = error_message or "Backend initialization failed."
            print(f"ChatTab: Backend initialization failed: {status_message}")

        # Update the system message using add_message
        # Replace the initial "Initializing..." message
        self.add_message("System", status_message, replace_last=True) # This should now work as chat_box is linked

    def _update_chat_box_initialization(self, instance, value):
        """Callback when backend_initialized changes to update the ChatBox."""
        # This should only be called after _post_init successfully linked chat_box and added the binding
        if self.chat_box:
            self.chat_box.backend_initialized = value
            print(f"ChatTab: Updated chat_box.backend_initialized to {value}")
        else:
            # This case should ideally not happen now
            print("ChatTab CRITICAL Warning: _update_chat_box_initialization called but self.chat_box is None!")

    def _start_llm_instance_update_thread(self):
        """Starts a background thread to update the LLM instance without freezing the UI."""
        if not self.backend_initialized: # Should ideally be checked before calling
             print("ChatTab: Backend not initialized, skipping LLM instance update trigger.")
             return

        if not self.selected_provider or not self.selected_model:
            print("ChatTab: Cannot update LLM instance, provider or model not selected.")
            self.add_message("System", "Error: Cannot switch LLM. Provider or model missing.")
            return

        # Show updating status via add_message
        print(f"ChatTab: _start_llm_instance_update_thread: Using provider='{self.selected_provider}', model='{self.selected_model}'")
        self.add_message("System", f"Switching LLM to {self.selected_provider} - {self.selected_model}...", replace_last=True) # Replace previous status

        # Start the update in a background thread
        print(f"ChatTab: Starting LLM update thread (Old Instance ID: {id(self.llm_instance) if self.llm_instance else None})") # Log ID before thread start
        threading.Thread(target=self._run_llm_update_in_thread, daemon=True).start()

    def _run_llm_update_in_thread(self):
        """Runs the potentially blocking LLM update in a background thread."""
        print(f"ChatTab: LLM update thread running for {self.selected_provider} - {self.selected_model}")
        new_instance = None
        error_message = None
        try:
            # Close existing instance *before* creating the new one in the thread
            # Ensure thread safety if close() has side effects, but usually okay.
            if self.llm_instance and hasattr(self.llm_instance, 'close'):
                print("ChatTab: Closing previous LLM instance in update thread...")
                self.llm_instance.close()
                print("ChatTab: Previous LLM instance closed in update thread.")

            # Create the new instance (potentially blocking)
            new_instance = ChatBoxLLM(provider=self.selected_provider, model_name=self.selected_model)

        except Exception as e:
            error_message = f"Error updating LLM: {e}"
            new_instance = None # Ensure instance is None on error

        # Schedule the final update on the main Kivy thread
        Clock.schedule_once(lambda dt: self._finish_llm_instance_update(new_instance, error_message))

    def _finish_llm_instance_update(self, new_instance, error_message):
        """Called on the main thread to finalize the LLM instance update."""
        print("ChatTab: Finishing LLM instance update on main thread.")
        update_status = ""
        if new_instance:
            self.llm_instance = new_instance
            # Keep backend_initialized as True, just update the instance
            update_status = f"LLM switched to {self.selected_provider} - {self.selected_model}"
            print(f"ChatTab: {update_status}")
        else:
            # Update failed, keep the old instance? Or set to None?
            # Setting to None and marking backend as uninitialized might be safer.
            self.llm_instance = None
            self.backend_initialized = False # Mark as failed if update fails
            update_status = error_message or "LLM update failed."
            print(f"ChatTab: LLM update failed: {update_status}")

        # Update the system message via add_message, replacing the "Switching..." message
        self.add_message("System", update_status, replace_last=True)
        print(f"ChatTab: Finished LLM instance update. Current Instance ID: {id(self.llm_instance) if self.llm_instance else None}")

    # --- Chat Interaction Methods ---

    def toggle_recording(self):
        """Handles the on_toggle_recording event from ChatBox."""
        self._is_currently_recording = not self._is_currently_recording
        if self._is_currently_recording:
            print("ChatTab: Recording started (Simulated)")
            # Add actual voice recording logic here
            # Example: Start recording -> on result -> self.send_prompt(result); self.toggle_recording()
        else:
            print("ChatTab: Recording stopped (Simulated)")
            # Add logic to process recorded audio if needed

        # Update the ChatBox UI state
        if self.chat_box:
            self.chat_box.set_recording_state(self._is_currently_recording)

    def send_prompt(self, prompt: str):
        """Handles the on_send_prompt event from ChatBox."""
        # Check if backend is ready before sending
        if not self.backend_initialized or not self.llm_instance:
            print("ChatTab: Send attempt failed - Backend not initialized or LLM instance missing.")
            self.add_message("System", "Error: Backend not ready. Please wait or check logs.")
            return

        if not prompt: # Should not happen if ChatBox validates, but check anyway
            return

        print(f"ChatTab: Received prompt from ChatBox: {prompt}")
        self.add_message("You", prompt) # Add user message to ChatBox display
        # Input is cleared within ChatBox._dispatch_send_prompt

        # Add a "Thinking..." message to ChatBox display
        self.add_message("Lily", "Thinking...")

        # Run the async LLM call in a separate thread
        thread = threading.Thread(target=self._run_async_in_thread, args=(prompt,), daemon=True)
        thread.start()

    def _run_async_in_thread(self, prompt: str):
        """Helper function to run the async LLM call in a separate thread."""
        try:
            # Run the async function using asyncio.run() in this new thread
            asyncio.run(self._get_llm_response_async(prompt))
        except Exception as e:
            print(f"ChatTab: Error running async task in thread: {e}")
            # Schedule error display back on the main thread
            error_message = f"An error occurred in async task: {e}"
            # Ensure receive_response is robust enough to handle errors even if thinking message wasn't added
            # Pass an empty list for tools in case of error
            Clock.schedule_once(lambda dt: self.receive_response(error_message, [])) # Pass empty list

    async def _get_llm_response_async(self, prompt: str):
        """Async function to get response and successful tool details from LLM and schedule UI update."""
        try:
            # Ensure the LLM instance is up-to-date (optional, could rely on callbacks)
            # self._update_llm_instance() # Might be redundant if callbacks work reliably

            print(f"ChatTab: Calling LLM instance get_response for: '{prompt[:50]}...'")
            # The get_response method now returns (response, successful_tool_details_list)
            response, successful_tool_details_list = await self.llm_instance.get_response(prompt)
            print(f"ChatTab: Received response and tool details: {successful_tool_details_list} from LLM instance.")

            # Schedule the UI update back on the main Kivy thread, passing both response and the list of dictionaries
            Clock.schedule_once(lambda dt: self.receive_response(response, successful_tool_details_list))

        except Exception as e:
            print(f"ChatTab: Error during LLM interaction: {e}")
            error_message = f"An error occurred: {e}"
            # Schedule the error message display back on the main Kivy thread, pass empty list for tools
            Clock.schedule_once(lambda dt: self.receive_response(error_message, [])) # Pass empty list

    def receive_response(self, response: str, successful_tool_details_list: list):
        """Handle receiving the final response and successful tool details, update ChatBox and ActionsList UI."""
        print(f"ChatTab: Updating ChatBox UI with response: {response[:100]}...")
        print(f"ChatTab: Received successful tool details: {successful_tool_details_list}")

        # Replace the "Thinking..." message with the actual response in ChatBox
        self.add_message("Lily", response, replace_last=True)

        # Update the ActionsList with the detailed dictionaries
        if self.actions_list and successful_tool_details_list:
            print(f"ChatTab: Adding successful tool details to ActionsList...")
            for tool_details in successful_tool_details_list:
                # Pass the entire dictionary to add_action
                self.actions_list.add_action(tool_details)
        elif not self.actions_list:
            print("ChatTab Warning: actions_list widget not found, cannot add tool calls.")
        
        if self.tts_enabled and response: # Ensure there is a response to speak
            print(f"ChatTab: TTS Enabled. Requesting speech for: {response[:50]}...")
            # Run the async TTS generation in a separate thread
            threading.Thread(target=self._run_tts_async, args=(response,), daemon=True).start()

    def _run_tts_async(self, text_to_speak: str):
        """Helper to run the async TTS function in a new event loop in a separate thread."""
        try:
            asyncio.run(generate_speech_from_provider(text_to_speak, speaker=int(self.selected_tts_speaker), model=self.selected_tts_model))
        except Exception as e:
            print(f"ChatTab: Error running TTS in thread: {e}")

    def add_message(self, sender_type, text, scroll: bool = True, replace_last: bool = False):
        """Adds a message to the ChatBox display."""
        # Check if chat_box is linked. It should be after _post_init runs.
        if self.chat_box:
            self.chat_box.add_message(sender_type, text, scroll=scroll, replace_last=replace_last)
        else:
            # This indicates _post_init hasn't run or failed to link
            print(f"ChatTab Error: chat_box not available in add_message. Message '{text}' lost.")
            # Avoid trying to link here, rely on _post_init

    def clear_chat_history(self): 
        """Clears the chat history display in ChatBox and LLM internal history."""
        print("ChatTab: Clearing chat history.")
        if self.chat_box:
            self.chat_box.clear_history() # Clears display and adds system message

        # Clear the ActionsList as well
        if self.actions_list:
            self.actions_list.clear_actions()
            print("ChatTab: Cleared ActionsList.")

        # Optionally, clear the LLM's internal history if applicable
        if self.llm_instance and hasattr(self.llm_instance, 'clear_history'):
            print("ChatTab: Clearing LLM internal history.")
            self.llm_instance.clear_history()
