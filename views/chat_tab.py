import asyncio
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
# Remove ListProperty if only used for llm lists now in mixin
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, NumericProperty
from kivy.lang import Builder
from kivy.clock import Clock

# Import settings manager functions
from settings_manager import load_settings, save_settings
# Import the ChatBoxLLM
from llm.chatbox_llm import ChatBoxLLM
# Import the LLM Config Mixin
from views.llm_config_mixin import LLMConfigMixin

# Load the corresponding kv file
Builder.load_file('views/chat_tab.kv')

# Inherit from BoxLayout and the Mixin
class ChatTab(BoxLayout, LLMConfigMixin):
    """
    Kivy equivalent of the ChatTab QWidget, using LLMConfigMixin.
    """
    # --- Properties specific to ChatTab ---
    prompt_text = StringProperty("")
    response_text = StringProperty("") # For displaying chat history
    # llm_providers, llm_models, selected_provider, selected_model, _updating_models are now in LLMConfigMixin
    tts_enabled = BooleanProperty(False) # Renamed from tts_provider_enabled for consistency
    is_recording = BooleanProperty(False)
    record_button_icon = StringProperty("assets/mic_idle.png") # Path to icon
    temperature = NumericProperty(0.7) # Default temperature

    # Flag to indicate if the backend LLM is ready
    backend_initialized = BooleanProperty(False)
    initialization_status = StringProperty("Initializing backend...") # Status message

    # Object properties to hold references to widgets if needed (optional)
    prompt_input = ObjectProperty(None)
    send_button = ObjectProperty(None)
    llm_instance: ChatBoxLLM = None # To hold the LLM instance

    # --- LLMConfigMixin Implementation ---
    def _get_provider_setting_key(self) -> str:
        return 'selected_provider' # Key used in settings for ChatTab provider

    def _get_model_setting_key(self) -> str:
        return 'selected_model' # Key used in settings for ChatTab model

    # --- Initialization ---
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # Calls __init__ of BoxLayout and LLMConfigMixin
        # Load general settings first
        self._load_chat_settings()
        # Load LLM specific settings using the mixin method
        self._load_llm_settings()
        # Bind mixin callbacks AFTER loading initial settings
        # Use specific names to avoid potential conflicts if mixin methods were directly bound
        self.bind(selected_provider=self.on_selected_provider_changed_chat)
        self.bind(selected_model=self.on_selected_model_changed_chat)
        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init) # Schedule updates after widgets are loaded

    def _load_chat_settings(self):
        """Load settings specific to ChatTab (excluding LLM provider/model)."""
        settings = load_settings()
        print("ChatTab: Loading non-LLM settings:", settings)
        # Use .get() with defaults
        self.tts_enabled = settings.get('tts_provider_enabled', False) # Match key in settings
        self.temperature = settings.get('temperature', 0.7) # Load temperature

    def _post_init(self, dt):
        """Tasks to run after widgets are loaded."""
        # Initial population of models based on the loaded provider (from mixin)
        self.update_models(initial_load=True) # Pass flag to load saved model (uses mixin's update_models)
        # Add initial status message
        self.add_message("System", self.initialization_status)
        # Start backend initialization in a separate thread
        threading.Thread(target=self._initialize_backend_thread, daemon=True).start()

    # update_models and set_update_flag are now inherited from LLMConfigMixin

    # --- Callbacks for saving settings ---
    # These methods now handle ChatTab specific actions (like updating LLM instance)
    # and call the appropriate mixin methods for saving LLM config or chat-specific settings.

    # Note: The actual binding happens in __init__ to these specific methods.
    def on_selected_provider_changed_chat(self, instance, value):
        """Callback when provider changes. Updates models, saves, and triggers LLM update."""
        print(f"ChatTab: Provider changed to {value}")
        self.update_models() # Update model list (handled by mixin)
        self._save_llm_settings() # Save LLM settings (handled by mixin)
        # Specific ChatTab action: Trigger LLM instance update if ready
        if self.backend_initialized:
            self._start_llm_instance_update_thread()
        else:
            print("ChatTab: Provider changed, backend not ready. Settings saved.")

    def on_selected_model_changed_chat(self, instance, value):
        """Callback when model changes. Saves and triggers LLM update."""
        if not self._updating_models: # Check mixin flag
            if value and hasattr(self, 'llm_models') and value in self.llm_models:
                print(f"ChatTab: User selected model: {value}")
                self._save_llm_settings() # Save LLM settings (handled by mixin)
                # Specific ChatTab action: Trigger LLM instance update if ready
                if self.backend_initialized:
                    self._start_llm_instance_update_thread()
                else:
                    print("ChatTab: Model changed, backend not ready. Settings saved.")
            elif not value:
                 print(f"ChatTab: Model selection cleared or invalid by user.")
        else:
            print(f"ChatTab: on_selected_model skipped save during update_models for value: {value}")

    def on_tts_enabled(self, instance, value):
        """Callback when TTS checkbox changes."""
        print(f"ChatTab: TTS Enabled changed to: {value}")
        self._save_chat_settings() # Save only chat-specific settings
        # Add logic if needed when TTS state changes (e.g., load/unload TTS engine)

    def on_temperature(self, instance, value):
        """Callback when temperature slider changes."""
        print(f"ChatTab: Temperature changed to: {value:.2f}")
        self._save_chat_settings() # Save only chat-specific settings

    def _save_chat_settings(self):
        """Helper method to save only the ChatTab specific settings."""
        settings = load_settings() # Load existing settings first
        settings['tts_provider_enabled'] = self.tts_enabled # Match key in settings
        settings['temperature'] = self.temperature # Save temperature
        save_settings(settings)
        print("ChatTab: Chat-specific settings saved.")

    # _save_llm_settings is inherited from LLMConfigMixin

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
        if instance:
            self.llm_instance = instance
            self.backend_initialized = True
            self.initialization_status = "Backend initialized successfully."
            print("ChatTab: Backend marked as initialized.")
            # Update UI elements (enable prompt, etc.) - handled by binding in kv
        else:
            self.llm_instance = None
            self.backend_initialized = False # Keep it false on error
            self.initialization_status = error_message or "Backend initialization failed."
            print(f"ChatTab: Backend initialization failed: {self.initialization_status}")

        # Update the system message
        self.add_message("System", self.initialization_status)

    def _start_llm_instance_update_thread(self):
        """Starts a background thread to update the LLM instance without freezing the UI."""
        if not self.backend_initialized: # Should ideally be checked before calling
             print("ChatTab: Backend not initialized, skipping LLM instance update trigger.")
             return

        if not self.selected_provider or not self.selected_model:
            print("ChatTab: Cannot update LLM instance, provider or model not selected.")
            self.add_message("System", "Error: Cannot switch LLM. Provider or model missing.")
            return

        # Show updating status
        self.add_message("System", f"Switching LLM to {self.selected_provider} - {self.selected_model}...")
        # Disable input while updating? (Optional, depends on desired UX)
        # self.ids.prompt_input.disabled = True

        # Start the update in a background thread
        threading.Thread(target=self._run_llm_update_in_thread, daemon=True).start()

    def _run_llm_update_in_thread(self):
        """Runs the potentially blocking LLM update in a background thread."""
        print(f"ChatTab: LLM update thread started for {self.selected_provider} - {self.selected_model}")
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
            print("ChatTab: New LLM instance created successfully in update thread.")

        except Exception as e:
            print(f"ChatTab: Error updating LLM instance in thread: {e}")
            error_message = f"Error updating LLM: {e}"
            new_instance = None # Ensure instance is None on error

        # Schedule the final update on the main Kivy thread
        Clock.schedule_once(lambda dt: self._finish_llm_instance_update(new_instance, error_message))

    def _finish_llm_instance_update(self, new_instance, error_message):
        """Called on the main thread to finalize the LLM instance update."""
        print("ChatTab: Finishing LLM instance update on main thread.")
        # Re-enable input (if disabled earlier)
        # self.ids.prompt_input.disabled = False

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
            self.initialization_status = error_message or "LLM update failed."
            update_status = self.initialization_status # Use the error message
            print(f"ChatTab: LLM update failed: {update_status}")

        # Update the system message
        self.add_message("System", update_status)


    def toggle_recording(self):
        """Toggle voice recording state."""
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.record_button_icon = "assets/mic_on.png"
            print("Recording started (Simulated)")
            # Add actual voice recording logic here
            # Example: Start recording -> on result -> self.prompt_text = result; self.toggle_recording()
        else:
            self.record_button_icon = "assets/mic_idle.png"
            print("Recording stopped (Simulated)")
            # Add logic to process recorded audio if needed

    def send_prompt(self):
        """Handles sending the prompt and initiating the async LLM call."""
        # Check if backend is ready before sending
        if not self.backend_initialized or not self.llm_instance:
            print("ChatTab: Send attempt failed - Backend not initialized or LLM instance missing.")
            self.add_message("System", "Error: Backend not ready. Please wait or check logs.")
            return

        prompt = self.ids.prompt_input.text
        if not prompt:
            return # Don't send empty prompts

        print(f"ChatTab: Sending prompt: {prompt}")
        self.add_message("You", prompt)
        self.ids.prompt_input.text = "" # Clear input

        # Add a "Thinking..." message
        self.add_message("Lily", "Thinking...")

        # Run the async LLM call in a separate thread (existing fix)
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
            Clock.schedule_once(lambda dt: self.receive_response(error_message))

    async def _get_llm_response_async(self, prompt: str):
        """Async function to get response from LLM and schedule UI update."""
        try:
            # Ensure the LLM instance is up-to-date (optional, could rely on callbacks)
            # self._update_llm_instance() # Might be redundant if callbacks work reliably

            print(f"ChatTab: Calling LLM instance get_response for: '{prompt[:50]}...'")
            # The get_response method in ChatBoxLLM handles the full process
            response, _ = await self.llm_instance.get_response(prompt) # Ignore the second element (None)
            print(f"ChatTab: Received response from LLM instance.")

            # Schedule the UI update back on the main Kivy thread
            Clock.schedule_once(lambda dt: self.receive_response(response))

        except Exception as e:
            print(f"ChatTab: Error during LLM interaction: {e}")
            error_message = f"An error occurred: {e}"
            # Schedule the error message display back on the main Kivy thread
            Clock.schedule_once(lambda dt: self.receive_response(error_message))

    def receive_response(self, response: str):
        """Handle receiving the final response and update UI."""
        print(f"ChatTab: Updating UI with response: {response[:100]}...")

        # Remove the "Thinking..." message before adding the actual response
        # This requires modifying how messages are stored or displayed.
        # Simple approach: Replace the last line if it's "Thinking..."
        lines = self.response_text.strip().split('\n\n')
        if lines and lines[-1].startswith("[b]Lily:[/b] Thinking..."):
            lines.pop() # Remove the last "Thinking..." message
            self.response_text = "\n\n".join(lines) + "\n\n" # Rebuild text, add trailing newlines

        self.add_message("Lily", response) # Add the actual response

        if self.tts_enabled:
            print(f"ChatTab: TTS Enabled: Speaking response (Simulated)")
            # Add actual TTS logic here (ensure it runs on the main thread or is thread-safe)

    def add_message(self, sender, message):
        """Append a message to the response box."""
        # Ensure the ScrollView scrolls to the bottom after adding text
        response_label = self.ids.response_label # Assuming id: response_label for the Label
        response_scroll = self.ids.response_scroll # Assuming id: response_scroll for the ScrollView

        # Append text
        response_label.text += f"[b]{sender}:[/b] {message}\n\n" # Use Kivy markup

        # Schedule scroll to bottom *after* the text update has been processed by Kivy layout
        Clock.schedule_once(lambda dt: setattr(response_scroll, 'scroll_y', 0), 0.1)


    def clear_history(self):
        """Clear the chat history."""
        self.response_text = ""
        self.add_message("System", "Chat history cleared.")
        print("Chat history cleared")
