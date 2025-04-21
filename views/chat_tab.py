from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.clock import Clock
import os

# Load the corresponding kv file
Builder.load_file('views/chat_tab.kv')

class ChatTab(BoxLayout):
    """
    Kivy equivalent of the ChatTab QWidget.
    """
    prompt_text = StringProperty("")
    response_text = StringProperty("") # For displaying chat history
    llm_providers = ListProperty(["OpenAI", "Gemini"]) # Example providers
    llm_models = ListProperty([]) # Models will depend on the selected provider
    selected_provider = StringProperty("OpenAI") # Default provider
    selected_model = StringProperty("")
    tts_enabled = BooleanProperty(False)
    is_recording = BooleanProperty(False)
    record_button_icon = StringProperty("assets/mic_idle.png") # Path to icon

    # Object properties to hold references to widgets if needed (optional)
    # prompt_input = ObjectProperty(None)
    # response_box_layout = ObjectProperty(None) # Reference to the layout inside ScrollView

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Orientation is set in the kv file
        Clock.schedule_once(self._post_init) # Schedule updates after widgets are loaded

    def _post_init(self, dt):
        # Initial population of models based on default provider
        self.update_models()
        # Add some initial placeholder text to the response box
        self.add_message("System", "Chat initialized. Enter your prompt below.")

    def update_models(self, *args):
        """Update the list of models based on the selected provider."""
        # Placeholder logic: Replace with actual model fetching
        if self.selected_provider == "OpenAI":
            self.llm_models = ["gpt-4", "gpt-3.5-turbo"]
            self.selected_model = "gpt-4" if "gpt-4" in self.llm_models else ""
        elif self.selected_provider == "Gemini":
            self.llm_models = ["gemini-pro", "gemini-1.5-flash"]
            self.selected_model = "gemini-pro" if "gemini-pro" in self.llm_models else ""
        else:
            self.llm_models = []
            self.selected_model = ""
        print(f"Provider changed to: {self.selected_provider}, Models: {self.llm_models}")

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
        """Send the prompt text to the LLM."""
        prompt = self.prompt_text
        if not prompt:
            return

        print(f"Sending prompt: {prompt}")
        self.add_message("You", prompt)
        self.prompt_text = "" # Clear input field

        # --- Placeholder for LLM interaction ---
        # Simulate receiving a response
        Clock.schedule_once(lambda dt: self.receive_response(f"This is a simulated response to '{prompt}'."), 1)
        # --- End Placeholder ---

    def receive_response(self, response):
        """Handle receiving a response from the LLM."""
        print(f"Received response: {response}")
        self.add_message("Lily", response)

        if self.tts_enabled:
            print(f"TTS Enabled: Speaking response (Simulated)")
            # Add actual TTS logic here

    def add_message(self, sender, message):
        """Append a message to the response box."""
        # Simple append for now. For better performance with long histories,
        # consider using RecycleView or managing the label's text more carefully.
        self.response_text += f"[b]{sender}:[/b] {message}\n\n" # Use Kivy markup

    def clear_history(self):
        """Clear the chat history."""
        self.response_text = ""
        self.add_message("System", "Chat history cleared.")
        print("Chat history cleared")

    def on_tts_enabled(self, instance, value):
        """Callback when TTS checkbox changes."""
        print(f"TTS Enabled changed to: {value}")
        # Add logic if needed when TTS state changes (e.g., load/unload TTS engine)
