import asyncio
import os
import threading
import speech_recognition as sr

from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QMetaObject, Q_ARG, QSize
from PyQt5.QtGui import QFont, QRegion, QPixmap, QIcon
from PyQt5.QtWidgets import (QLineEdit, QTextEdit, QVBoxLayout, QWidget,
                             QCheckBox, QPushButton, QLabel, QHBoxLayout, QComboBox)
from actions import action_handler
from llm.chatbox_llm import ChatBoxLLM
from tts import generate_speech_from_provider
from kg import kg_handler
from config.models import OPENAI_MODELS, GEMINI_MODELS
# Import settings manager
from settings_manager import load_settings, save_settings


def clear_output_folder():
    # Remove old audio files from the outputs folder
    output_folder = "outputs"
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            if filename.startswith("audio"):
                file_path = os.path.join(output_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted {file_path}")
                except Exception as e:
                    pass

class ChatTab(QWidget):
    # Signal to update the chat with user input and assistant response
    updateResponse = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._initializing = True # Flag to prevent signals during setup
        self.settings = load_settings() # Load settings first

        # --- UI Setup (largely the same, but apply loaded settings) ---

        # LLM Provider Selector
        self.provider_label = QLabel("Select LLM Provider:", self)
        self.provider_selector = QComboBox(self)
        self.provider_selector.addItems(["OpenAI", "Gemini"])
        # Set loaded provider *before* connecting signals
        provider_index = self.provider_selector.findText(self.settings.get('selected_provider', 'OpenAI'))
        if provider_index != -1:
            self.provider_selector.setCurrentIndex(provider_index)
        # Connect signal LATER

        # LLM Model Selector
        self.model_label = QLabel("Select Model:", self)
        self.model_selector = QComboBox(self)
        # Populate models based on the *loaded* provider first
        self._update_model_selector(set_from_settings=True)
        # Connect signal LATER

        # Avatar setup
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(300, 300)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        avatar_pixmap = QPixmap("assets/avatar.png")
        avatar_pixmap = avatar_pixmap.scaled(self.avatar_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.avatar_label.setPixmap(avatar_pixmap)
        mask_region = QRegion(0, 0, self.avatar_label.width(), self.avatar_label.height(), QRegion.Ellipse)
        self.avatar_label.setMask(mask_region)
        avatar_layout = QHBoxLayout()
        avatar_layout.setAlignment(Qt.AlignCenter)
        avatar_layout.addWidget(self.avatar_label)

        # Prompt input field and voice record button setup
        self.prompt_input = QLineEdit(self)
        font = QFont("Arial", 14)
        self.prompt_input.setFont(font)

        self.record_button = QPushButton(self)
        self.record_button.setStyleSheet("width: 100px; height: 30px;")
        self.record_button.setIcon(QIcon("assets/mic_idle.png"))
        self.record_button.setIconSize(QSize(30, 30))
        self.record_button.clicked.connect(self.record_voice)

        # Layout for text input and record button
        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(self.record_button)

        # Create response box and other controls
        self.response_box = QTextEdit(self)
        self.response_box.setReadOnly(True)
        self.tts_provider_enabled = QCheckBox("Enable TTS (TTS-Provider)", self)
        self.tts_provider_enabled.setChecked(self.settings.get('tts_provider_enabled', False))
        # Connect signal LATER

        self.clear_history_button = QPushButton("Clear History", self)

        # Knowledge Graph Memory checkbox and status display
        self.enable_kg_memory_checkbox = QCheckBox("Enable Knowledge Graph Memory", self)
        self.enable_kg_memory_checkbox.setChecked(self.settings.get('enable_kg_memory', False))
        # Connect signal LATER

        self.kg_status_label = QLabel(self)
        if not kg_handler.knowledge_graph_loaded:
            self.enable_kg_memory_checkbox.setEnabled(False)
            self.kg_status_label.setText("Knowledge graph has to be enabled to use this feature")
        else:
            self.enable_kg_memory_checkbox.setEnabled(True)
            self.kg_status_label.setText("Knowledge graph loaded")

        # Main layout for the ChatTab
        layout = QVBoxLayout()
        layout.addLayout(avatar_layout)
        layout.addLayout(prompt_layout)
        layout.addWidget(self.response_box)
        layout.addWidget(self.tts_provider_enabled)
        layout.addWidget(self.enable_kg_memory_checkbox)
        layout.addWidget(self.kg_status_label)
        provider_layout = QHBoxLayout()
        provider_layout.addWidget(self.provider_label)
        provider_layout.addWidget(self.provider_selector)
        model_layout = QHBoxLayout()
        model_layout.addWidget(self.model_label)
        model_layout.addWidget(self.model_selector)
        layout.addLayout(provider_layout)
        layout.addLayout(model_layout)
        layout.addWidget(self.clear_history_button)
        self.setLayout(layout)

        # Connect other signals
        self.prompt_input.returnPressed.connect(self.get_response)
        self.clear_history_button.clicked.connect(self.clear_history)
        self.updateResponse.connect(self.on_update_response)

        # Initialize LLM based on loaded settings
        self._initialize_llm()

        # NOW connect the signals that should trigger saving settings
        self.provider_selector.currentIndexChanged.connect(self.on_provider_changed)
        self.model_selector.currentIndexChanged.connect(self.on_model_changed)
        self.tts_provider_enabled.stateChanged.connect(self._save_current_settings)
        self.enable_kg_memory_checkbox.stateChanged.connect(self._save_current_settings)

        self._initializing = False  # Setup complete
        clear_output_folder()

    def _save_current_settings(self):
        """Gathers current settings and saves them."""
        if self._initializing: # Don't save during initial setup
            return

        current_settings = {
            'tts_provider_enabled': self.tts_provider_enabled.isChecked(),
            'enable_kg_memory': self.enable_kg_memory_checkbox.isChecked(),
            'selected_provider': self.provider_selector.currentText(),
            'selected_model': self.model_selector.currentText()
        }
        # Update the in-memory settings object as well
        self.settings.update(current_settings)
        save_settings(self.settings)

    def _update_model_selector(self, set_from_settings=False):
        """Populates the model selector based on the selected provider."""
        selected_provider = self.provider_selector.currentText().lower()
        # Block signals during modification to prevent premature triggers
        self.model_selector.blockSignals(True)
        self.model_selector.clear() # Clear existing items

        model_list = []
        if selected_provider == 'openai':
            model_list = OPENAI_MODELS
        elif selected_provider == 'gemini':
            model_list = GEMINI_MODELS

        if model_list:
            self.model_selector.addItems(model_list)
            if set_from_settings:
                # Try to set the loaded model
                loaded_model = self.settings.get('selected_model')
                model_index = self.model_selector.findText(loaded_model)
                if model_index != -1:
                    self.model_selector.setCurrentIndex(model_index)
                elif model_list: # Fallback to first if loaded model not found
                    self.model_selector.setCurrentIndex(0)
            elif model_list: # Default to first if not setting from saved
                self.model_selector.setCurrentIndex(0)

        self.model_selector.blockSignals(False) # Unblock signals
        # Save settings if the model was changed *not* during initial load
        if not set_from_settings:
             self._save_current_settings()

    def _initialize_llm(self):
        """Initializes or re-initializes the ChatBoxLLM based on the selected provider and model."""
        selected_provider = self.provider_selector.currentText().lower()
        selected_model = self.model_selector.currentText()

        if not selected_model:
             print("--- Initialize LLM: No model selected, skipping. ---")
             self.chatBoxLLM = None
             return

        # Prevent re-initialization if settings haven't changed (unless initializing)
        if not self._initializing and hasattr(self, 'chatBoxLLM') and self.chatBoxLLM and \
           self.chatBoxLLM.provider == selected_provider and \
           self.chatBoxLLM.model == selected_model:
            print(f"--- Initialize LLM: Settings unchanged ({selected_provider}/{selected_model}), skipping. ---")
            return

        print(f"--- Initializing LLM: Provider={selected_provider}, Model={selected_model} ---")
        try:
            self.chatBoxLLM = ChatBoxLLM(provider=selected_provider, model_name=selected_model)
            # Clear history only if not initializing (avoids clearing on startup)
            if not self._initializing:
                self.clear_history(notify=False)
                self.response_box.append(f"Switched LLM to: {selected_provider.capitalize()} - {selected_model}")
        except ValueError as e:
            print(f"--- Error initializing LLM: {e} ---")
            if hasattr(self, 'response_box'):
                 self.response_box.append(f'<span style="color: red;">Error: Could not initialize {selected_provider.capitalize()} ({selected_model}). Check API key/config.</span>')
            self.chatBoxLLM = None
        # Save settings after successful initialization or change
        self._save_current_settings()

    def on_provider_changed(self):
        """Handles the change in the provider selection."""
        if self._initializing:
            print("--- on_provider_changed SKIPPING (during init) ---")
            return
        print("--- on_provider_changed START ---")
        self._update_model_selector() # Update models (saves settings inside)
        # Initialize LLM because provider change implies model change (to default)
        # _initialize_llm will handle saving and appending messages
        self._initialize_llm()
        print("--- on_provider_changed END ---")


    def on_model_changed(self):
        """Handles the change in the model selection."""
        if self._initializing:
            print("--- on_model_changed SKIPPING (during init) ---")
            return
        print("--- on_model_changed START ---")
        # Check if model text is actually valid before initializing
        if self.model_selector.currentText():
             # _initialize_llm will handle saving and appending messages
             self._initialize_llm()
        else:
             print("--- on_model_changed SKIPPING (empty model text) ---")
        print("--- on_model_changed END ---")


    def get_response(self):
        if not self.chatBoxLLM:
            self.response_box.append('<span style="color: red;">LLM not initialized. Please select a valid provider and ensure API key is set.</span>')
            return
        user_text = self.prompt_input.text().strip()
        if not user_text: return
        self.prompt_input.setDisabled(True)
        threading.Thread(target=self._get_response_thread, args=(user_text,), daemon=True).start()

    def _get_response_thread(self, user_text):
        message, action = self.chatBoxLLM.get_response(user_text, not self.enable_kg_memory_checkbox.isChecked())
        action_handler.execute_command(action)
        print(f"Message: {message}")
        print(f"Action: {action}")

        # Call TTS-Provider if enabled
        if self.tts_provider_enabled.isChecked():
            # Run the async TTS function in a separate thread
            threading.Thread(
                target=lambda: asyncio.run(generate_speech_from_provider(message)),
                daemon=True
            ).start()

        self.updateResponse.emit(user_text, message)

    def on_update_response(self, user_text, assistant_message):
        self.response_box.append(f"You: {user_text}")
        self.response_box.append(f"Lily: {assistant_message}")
        self.prompt_input.clear()
        self.prompt_input.setDisabled(False)

    def clear_history(self, notify=True):
        if self.chatBoxLLM:
            self.chatBoxLLM.message_history = []
        if notify:
            self.response_box.append("History cleared.")

    def enable_kg_features(self):
        self.enable_kg_memory_checkbox.setEnabled(True)
        self.kg_status_label.setText("Knowledge graph loaded")
        # Save settings if KG becomes enabled (user might want this persisted)
        self._save_current_settings()

    def record_voice(self):
        threading.Thread(target=self._record_voice_thread, daemon=True).start()

    def _record_voice_thread(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Recording... Please speak now.")
                QMetaObject.invokeMethod(self, "start_recording_ui", Qt.QueuedConnection)
                audio = recognizer.listen(source, phrase_time_limit=5)
                recognized_text = recognizer.recognize_google(audio)
                print("Recognized text:", recognized_text)
                QMetaObject.invokeMethod(self.prompt_input, "setText", Qt.QueuedConnection, Q_ARG(str, recognized_text))
        except Exception as e:
            print("Voice recognition error:", e)
        finally:
            QMetaObject.invokeMethod(self, "reset_record_icon", Qt.QueuedConnection)

    @pyqtSlot()
    def reset_record_icon(self):
        self.record_button.setIcon(QIcon("assets/mic_idle.png"))

    @pyqtSlot()
    def start_recording_ui(self):
        self.record_button.setIcon(QIcon("assets/mic_on.png"))
        self.response_box.append('<span style="color: red;">Recording... Please speak now.</span>')
