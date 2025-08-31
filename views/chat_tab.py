import asyncio
import threading
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ObjectProperty
from kivy.clock import Clock
from kivy.lang import Builder

# Import settings manager functions
from settings_manager import load_chat_settings, save_chat_settings
# Lily Core integration
from llm.lily_core_client import LilyCoreChatOrchestrator
from tts import generate_speech_from_lily_core  # Use new Lily-Core WebSocket TTS function
import os

# Import the new status component
from views.components.lily_core_status import LilyCoreStatus

# Load the KV string for ChatTab
Builder.load_file('views/chat_tab.kv')

# Define colors for markup
USER_COLOR_HEX = "FFFFFF"  # White
LLM_COLOR_HEX = "FFFFFF"   # White
SYSTEM_COLOR_HEX = "00FF00"  # Green (Lime)

class ChatTab(BoxLayout):
    """
    Kivy equivalent of the ChatTab QWidget, integrated with Lily Core.
    """

    # TTS Properties
    tts_enabled = BooleanProperty(False)
    selected_tts_model = StringProperty("edge")
    selected_tts_speaker = NumericProperty(1)

    # Lily Core tool use setting
    tool_use_enabled_for_llm = BooleanProperty(False)

    # Backend state
    backend_initialized = BooleanProperty(False)
    initialization_status = StringProperty("Connecting to Lily Core...")

    # UI references
    send_button = ObjectProperty(None)
    chat_box = ObjectProperty(None)
    actions_list = ObjectProperty(None)
    action_details = ObjectProperty(None)
    selected_action_data = ObjectProperty(None, allownone=True)
    llm_instance = None  # Lily Core orchestrator instance

    # Internal state
    _is_currently_recording = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set the load and save functions for settings
        self.load_function = load_chat_settings
        self.save_function = save_chat_settings

        # Load settings
        self._load_chat_settings()

        # Bind property changes
        self.bind(tts_enabled=self._on_tts_enabled)
        self.bind(selected_tts_model=self._on_tts_model_changed)
        self.bind(selected_tts_speaker=self._on_tts_speaker_changed)
        self.bind(tool_use_enabled_for_llm=self._on_tool_use_changed)

        Clock.schedule_once(self._post_init)

    def _load_chat_settings(self):
        """Load chat-specific settings."""
        settings = self.load_function()
        print(f"ChatTab: Loading settings: {settings}")

        from settings_manager import CHAT_TOOL_USE_ENABLED
        self.tts_enabled = settings.get('tts_provider_enabled', False)
        self.selected_tts_model = settings.get('selected_tts_model', 'edge')
        self.selected_tts_speaker = settings.get('selected_tts_speaker', 1)
        self.tool_use_enabled_for_llm = settings.get(CHAT_TOOL_USE_ENABLED, False)

        print(f"ChatTab: TTS enabled: {self.tts_enabled}, Tool use: {self.tool_use_enabled_for_llm}")

    def _save_chat_settings(self):
        """Save chat-specific settings."""
        settings = self.load_function()
        settings['tts_provider_enabled'] = self.tts_enabled
        settings['selected_tts_model'] = self.selected_tts_model
        settings['selected_tts_speaker'] = self.selected_tts_speaker

        from settings_manager import CHAT_TOOL_USE_ENABLED
        settings[CHAT_TOOL_USE_ENABLED] = self.tool_use_enabled_for_llm

        self.save_function(settings)
        print("ChatTab: Settings saved")

    # Property change handlers
    def _on_tts_enabled(self, instance, value):
        print(f"ChatTab: TTS enabled changed to: {value}")
        self._save_chat_settings()

    def _on_tts_model_changed(self, instance, value):
        print(f"ChatTab: TTS model changed to: {value}")
        self._save_chat_settings()

    def _on_tts_speaker_changed(self, instance, value):
        print(f"ChatTab: TTS speaker changed to: {value}")
        self._save_chat_settings()

    def _on_tool_use_changed(self, instance, value):
        print(f"ChatTab: Tool use enabled changed to: {value}")
        self._save_chat_settings()
        if self.backend_initialized:
            print("ChatTab: Restarting Lily Core...")
            threading.Thread(target=self._reinitialize_orchestrator, daemon=True).start()

    def _post_init(self, dt):
        """Initialize UI components after KV is loaded."""
        print("ChatTab: Post-initialization...")

        # Connect UI components
        self.chat_box = self.ids.get('chat_box')
        self.actions_list = self.ids.get('actions_list')
        self.action_details = self.ids.get('action_details')

        # Check if components were found
        if not self.chat_box:
            print("ChatTab: ERROR - Could not find chat_box!")
            return

        # Bind to backend initialization
        self.bind(backend_initialized=self._update_chat_box_initialization)

        # Bind to UI settings changes
        settings_widget = self.ids.get('chat_controls')
        if settings_widget:
            settings_widget.bind(tool_use_enabled=self._handle_settings_tool_use_change)

        # Add initial status message
        self.add_message("System", self.initialization_status, scroll=False)

                # Start Lily Core connection in background
        threading.Thread(target=self._connect_to_lily_core, daemon=True).start()

        # Initialize TTS WebSocket client
        threading.Thread(target=self._initialize_tts_websocket, daemon=True).start()


    def _connect_to_lily_core(self):
        """Connect to Lily Core in background thread."""
        instance = None
        error_message = None

        try:
            print("ChatTab: Connecting to Lily Core")

            # Create Lily Core orchestrator
            instance = LilyCoreChatOrchestrator()

            # Initialize the connection (this is async, so we need to use asyncio)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(instance.initialize())
                print("ChatTab: ✅ Successfully connected to Lily Core!")
            finally:
                loop.close()

        except Exception as e:
            print(f"ChatTab: Failed to connect to Lily Core: {e}")
            error_message = f"Cannot connect to Lily Core: {str(e)}"
            instance = None

        # Schedule UI update on main thread
        Clock.schedule_once(lambda dt: self._finish_lily_core_connection(instance, error_message))

    def _reinitialize_orchestrator(self):
        """Reinitialize orchestrator with new settings."""
        print("ChatTab: Reinitializing Lily Core orchestrator...")

        try:
            # Create new orchestrator
            new_instance = LilyCoreChatOrchestrator()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(new_instance.initialize())
                print("ChatTab: ✅ Orchestrator reinitialized!")
            except Exception as e:
                print(f"ChatTab: Failed to reinitialize: {e}")
                new_instance = None
            finally:
                loop.close()

        except Exception as e:
            print(f"ChatTab: Reinitialization error: {e}")
            new_instance = None

        # Update on main thread
        Clock.schedule_once(lambda dt: self._finish_orchestrator_reinit(new_instance))

    def _finish_lily_core_connection(self, instance, error_message):
        """Complete Lily Core connection on main thread."""
        print("ChatTab: Finishing Lily Core connection...")

        if instance:
            self.llm_instance = instance
            self.backend_initialized = True
            status_message = "Connected to Lily Core successfully"
            print("ChatTab: Lily Core connection established!")
        else:
            self.llm_instance = None
            self.backend_initialized = False
            status_message = error_message or "Failed to connect to Lily Core"
            print(f"ChatTab: Lily Core connection failed: {status_message}")

        # Update initialization status property (this will update the status component)
        self.initialization_status = status_message

        # Update status message in chat
        self.add_message("System", status_message, replace_last=True)

    def _initialize_tts_websocket(self):
        """Initialize TTS WebSocket connection to Lily-Core."""
        try:
            from tts import get_lily_core_tts_client
            client = get_lily_core_tts_client()

            # Create event loop and initialize connection
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Connect to Lily-Core
                if loop.run_until_complete(client._connect()):
                    print("ChatTab: ✅ TTS WebSocket connected to Lily-Core")

                    # Start message handling loop
                    message_thread = threading.Thread(target=self._run_tts_message_loop, daemon=True)
                    message_thread.start()

                    # Send initial settings
                    settings = self.load_function()
                    if settings.get('tts_provider_enabled', False):
                        loop.run_until_complete(client.update_settings(
                            speaker=int(settings.get('selected_tts_speaker', 1)),
                            model=settings.get('selected_tts_model', 'edge')
                        ))

                else:
                    print("ChatTab: ❌ Failed to connect TTS WebSocket to Lily-Core")
            finally:
                loop.close()

        except Exception as e:
            print(f"ChatTab: TTS WebSocket initialization error: {e}")

    def _run_tts_message_loop(self):
        """Run the TTS WebSocket message handling loop."""
        try:
            from tts import get_lily_core_tts_client
            client = get_lily_core_tts_client()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(client.start_message_loop())
            finally:
                loop.close()

        except Exception as e:
            print(f"ChatTab: TTS message loop error: {e}")

    def _finish_orchestrator_reinit(self, new_instance):
        """Complete orchestrator reinitialization."""
        if new_instance:
            self.llm_instance = new_instance
            print("ChatTab: Orchestrator updated successfully")
        else:
            print("ChatTab: Orchestrator update failed")

    def _update_chat_box_initialization(self, instance, value):
        """Update chat box when backend initialization changes."""
        if self.chat_box:
            self.chat_box.backend_initialized = value
            print(f"ChatTab: Updated chat box initialization state: {value}")

    def _handle_settings_tool_use_change(self, instance, value):
        """Handle tool use setting changes from UI."""
        print(f"ChatTab: UI tool use setting changed to: {value}")
        self.tool_use_enabled_for_llm = value

    # Chat interaction methods
    def toggle_recording(self):
        """Handle recording toggle from UI."""
        self._is_currently_recording = not self._is_currently_recording
        if self.chat_box:
            self.chat_box.set_recording_state(self._is_currently_recording)
        print(f"ChatTab: Recording state changed to: {self._is_currently_recording}")

    def send_prompt(self, prompt: str):
        """Handle message send from UI."""
        if not prompt:
            return

        # Check if backend is ready
        if not self.backend_initialized or not self.llm_instance:
            print("ChatTab: Cannot send message - Lily Core not connected")
            self.add_message("System", "Not connected to Lily Core. Please wait or check console.")
            return

        print(f"ChatTab: Sending prompt: {prompt}")
        self.add_message("You", prompt)
        self.add_message("Lily", "Thinking...")

        # Send message in background thread
        thread = threading.Thread(target=self._send_message_async, args=(prompt,), daemon=True)
        thread.start()

    def _send_message_async(self, prompt: str):
        """Send message asynchronously."""
        try:
            # Get response from Lily Core
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response, tools = loop.run_until_complete(self.llm_instance.get_response(prompt))
            finally:
                loop.close()

            print(f"ChatTab: Received response: {response[:100]}...")
            print(f"ChatTab: Received tools: {tools}")

            # Update UI on main thread
            Clock.schedule_once(lambda dt: self._handle_response(response, tools))

        except Exception as e:
            print(f"ChatTab: Error sending message: {e}")
            error_msg = f"Error: {str(e)}"
            Clock.schedule_once(lambda dt: self._handle_response(error_msg, []))

    def _handle_response(self, response, tools):
        """Handle response on main thread."""
        # Replace "Thinking..." with actual response
        self.add_message("Lily", response, replace_last=True)

        # Add tool actions if any
        if self.actions_list and tools:
            for tool in tools:
                if hasattr(tool, 'model_dump'):
                    action_data = tool.model_dump()
                elif isinstance(tool, dict):
                    action_data = tool
                else:
                    continue
                self.actions_list.add_action(action_data)

        # Trigger TTS if enabled
        if self.tts_enabled and response:
            threading.Thread(
                target=self._run_tts_async,
                args=(response,),
                daemon=True
            ).start()

    def _run_tts_async(self, text_to_speak: str):
        """Run TTS in background thread."""
        try:
            success = asyncio.run(generate_speech_from_lily_core(
                text_to_speak,
                speaker=int(self.selected_tts_speaker),
                model=self.selected_tts_model
            ))
            if success:
                print(f"ChatTab: TTS request sent successfully for: {text_to_speak[:50]}...")
            else:
                print(f"ChatTab: TTS request failed for: {text_to_speak[:50]}...")
        except Exception as e:
            print(f"ChatTab: TTS error: {e}")

    def on_action_selected(self, instance, action_data):
        """Handle action selection from UI."""
        print(f"ChatTab: Action selected: {action_data}")
        self.selected_action_data = action_data

    def add_message(self, sender_type, text, scroll=True, replace_last=False):
        """Add message to chat display."""
        if self.chat_box:
            self.chat_box.add_message(sender_type, text, scroll=scroll, replace_last=replace_last)
        else:
            print(f"ChatTab: Chat box not available for message: {text}")

    def clear_chat_history(self):
        """Clear chat history."""
        print("ChatTab: Clearing chat history")
        if self.chat_box:
            self.chat_box.clear_history()
        if self.actions_list:
            self.actions_list.clear_actions()
        if self.llm_instance and hasattr(self.llm_instance, 'clear_history'):
            self.llm_instance.clear_history()

        # Add system message
        self.add_message("System", "Chat history cleared")