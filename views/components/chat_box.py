from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, NumericProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.utils import get_color_from_hex

Builder.load_file('views/components/chat_box.kv')

# Define colors for markup (can be centralized later)
USER_COLOR_HEX = "FFFFFF" # White
LLM_COLOR_HEX = "FFFFFF"  # White
SYSTEM_COLOR_HEX = "00FF00" # Green (Lime)

class ChatBox(BoxLayout):
    """
    A reusable component for chat input and display.
    Handles UI elements and dispatches events for actions.
    """
    # --- Properties for UI Binding ---
    prompt_text = StringProperty("")
    response_text = StringProperty("")
    is_recording = BooleanProperty(False)
    record_button_icon = StringProperty("assets/mic_idle.png") # Path to icon
    backend_initialized = BooleanProperty(False) # Controlled by parent

    # --- Internal Widget References (Optional, if needed) ---
    prompt_input = ObjectProperty(None)
    response_scroll = ObjectProperty(None)
    response_label = ObjectProperty(None)

    # --- Event Registration ---
    # Called when the user presses Enter in the TextInput or clicks a send button (if added)
    # The event handler in the parent should expect the prompt text as an argument.
    def register_event_type(self, event_type):
        super().register_event_type(event_type)

    __events__ = ('on_send_prompt', 'on_toggle_recording')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure IDs are available after kv loading
        Clock.schedule_once(self._link_widget_refs)

    def _link_widget_refs(self, dt):
        """Link object properties to actual widgets using IDs."""
        self.prompt_input = self.ids.get('prompt_input')
        self.response_scroll = self.ids.get('response_scroll')
        self.response_label = self.ids.get('response_label')

    # --- Internal Methods to Dispatch Events ---
    def _dispatch_send_prompt(self):
        """Called by TextInput's on_text_validate."""
        prompt = self.prompt_input.text if self.prompt_input else ""
        if prompt:
            self.dispatch('on_send_prompt', prompt) # Dispatch event with prompt text
            self.prompt_input.text = "" # Clear input after dispatching

    def _dispatch_toggle_recording(self):
        """Called by Record Button's on_press."""
        self.dispatch('on_toggle_recording') # Dispatch event

    # --- Methods Called by Parent (ChatTab) ---
    def set_recording_state(self, is_recording: bool):
        """Updates the recording state and button icon."""
        self.is_recording = is_recording
        self.record_button_icon = "assets/mic_on.png" if is_recording else "assets/mic_idle.png"

    def add_message(self, sender_type, text, scroll: bool = True, replace_last: bool = False):
        """Adds a formatted message to the response display."""
        sender_prefix = ""
        color_hex = LLM_COLOR_HEX # Default to LLM color

        # Handle replacement logic if needed (e.g., for status updates)
        current_text = self.response_text
        if replace_last:
            lines = current_text.split('\n\n')
            if lines:
                # Simple replacement: just remove the last line/block
                if len(lines) > 1:
                    current_text = "\n\n".join(lines[:-1]) + "\n\n"
                else:
                    current_text = "" # Clear if it was the only message

        if sender_type == 'You':
            sender_prefix = "[b]You:[/b] "
            color_hex = USER_COLOR_HEX
        elif sender_type == 'Lily':
            sender_prefix = "[b]Lily:[/b] "
            color_hex = LLM_COLOR_HEX
        elif sender_type == 'System':
            sender_prefix = "[b]System:[/b] "
            color_hex = SYSTEM_COLOR_HEX
        else: # Default case or unknown sender
             sender_prefix = f"[b]{sender_type}:[/b] "

        # Escape markup characters within the actual text
        escaped_text = text.replace('[', '&bl;').replace(']', '&br;')

        # Append formatted message
        new_message = f"[color={color_hex}]{sender_prefix}{escaped_text}[/color]"

        if current_text and not current_text.endswith("\n\n"):
             current_text += "\n\n" # Ensure separation if needed

        self.response_text = current_text + new_message

        # Only schedule scrolling if requested
        if scroll:
            Clock.schedule_once(self._scroll_to_bottom, 0)

    def clear_history(self):
        """Clears the chat history display."""
        self.response_text = ""
        # Add system message indicating clearance, without triggering scroll check
        self.add_message("System", "Chat history cleared.", scroll=False)
        # Explicitly set scroll position to the top after clearing
        if self.response_scroll:
            self.response_scroll.scroll_y = 1 # 1 means top

    def _scroll_to_bottom(self, dt):
        """Scrolls the response ScrollView to the bottom."""
        if self.response_scroll and self.response_label:
            # Only scroll if the label's height is greater than the scrollview's visible height
            if self.response_label.height > self.response_scroll.height:
                self.response_scroll.scroll_y = 0 # Scroll to bottom

    # --- Event Handlers (Defaults) ---
    def on_send_prompt(self, prompt_text):
        """Default handler for the send prompt event."""
        # print(f"ChatBox: on_send_prompt dispatched with: {prompt_text}")
        pass # Parent (ChatTab) should handle this

    def on_toggle_recording(self):
        """Default handler for the toggle recording event."""
        # print("ChatBox: on_toggle_recording dispatched")
        pass # Parent (ChatTab) should handle this
