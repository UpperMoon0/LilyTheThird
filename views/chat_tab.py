import asyncio
import os
import threading
import speech_recognition as sr  

from PyQt5.QtCore import Qt, pyqtSignal, QMetaObject, Q_ARG
from PyQt5.QtGui import QFont, QRegion, QPixmap
from PyQt5.QtWidgets import QLineEdit, QTextEdit, QVBoxLayout, QWidget, QCheckBox, QPushButton, QLabel, QHBoxLayout
from actions import action_handler
from llm.chatbox_llm import ChatBoxLLM
from tts import text_to_speech_and_play
from kg import kg_handler

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

        self.chatBoxLLM = ChatBoxLLM()

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

        self.record_button = QPushButton("Record", self)
        self.record_button.setStyleSheet("width: 100px; height: 30px;")
        self.record_button.clicked.connect(self.record_voice)  # Connect record button to voice recording

        # Layout for text input and record button
        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addWidget(self.record_button)

        # Create response box and other controls
        self.response_box = QTextEdit(self)
        self.response_box.setReadOnly(True)
        self.speech_synthesis_enabled = QCheckBox("Enable Speech Synthesis", self)
        self.speech_synthesis_enabled.setChecked(True)
        self.clear_history_button = QPushButton("Clear History", self)

        # Knowledge Graph Memory checkbox and status display
        self.enable_kg_memory_checkbox = QCheckBox("Enable Knowledge Graph Memory", self)
        self.enable_kg_memory_checkbox.setChecked(False)
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
        layout.addWidget(self.speech_synthesis_enabled)
        layout.addWidget(self.enable_kg_memory_checkbox)
        layout.addWidget(self.kg_status_label)
        layout.addWidget(self.clear_history_button)
        self.setLayout(layout)

        # Connect signal for handling user input and clearing chat history
        self.prompt_input.returnPressed.connect(self.get_response)
        self.clear_history_button.clicked.connect(self.clear_history)
        self.updateResponse.connect(self.on_update_response)
        clear_output_folder()

    def get_response(self):
        # Retrieve user input and start processing in a background thread.
        user_text = self.prompt_input.text().strip()
        if not user_text:
            return
        self.prompt_input.setDisabled(True)
        threading.Thread(target=self._get_response_thread, args=(user_text,), daemon=True).start()

    def _get_response_thread(self, user_text):
        # Obtain the response from the chatbot LLM and execute any actions.
        message, action = self.chatBoxLLM.get_response(user_text, not self.enable_kg_memory_checkbox.isChecked())
        action_handler.execute_command(action)
        print(f"Message: {message}")
        print(f"Action: {action}")
        # Optionally use text-to-speech to play the response.
        if self.speech_synthesis_enabled.isChecked():
            threading.Thread(
                target=lambda: asyncio.run(
                    text_to_speech_and_play(message, "ja-JP-NanamiNeural", "+15Hz")
                ),
                daemon=True
            ).start()
        self.updateResponse.emit(user_text, message)

    def on_update_response(self, user_text, assistant_message):
        # Append the conversation and reset the input.
        self.response_box.append(f"You: {user_text}")
        self.response_box.append(f"Lily: {assistant_message}")
        self.prompt_input.clear()
        self.prompt_input.setDisabled(False)

    def clear_history(self):
        # Clear the global message history and update UI.
        global message_history
        message_history = []
        self.response_box.append("History cleared.")

    def enable_kg_features(self):
        # Enable knowledge graph features after loading.
        self.enable_kg_memory_checkbox.setEnabled(True)
        self.kg_status_label.setText("Knowledge graph loaded")

    def record_voice(self):
        # Initiate voice recording in a separate thread.
        threading.Thread(target=self._record_voice_thread, daemon=True).start()

    def _record_voice_thread(self):
        # Record voice from the microphone and update the prompt with the recognized text.
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Recording... Please speak now.")
                audio = recognizer.listen(source, phrase_time_limit=5)
                recognized_text = recognizer.recognize_google(audio)
                print("Recognized text:", recognized_text)
                # Safely update the UI element from the background thread.
                from PyQt5.QtCore import QMetaObject, Q_ARG, Qt
                QMetaObject.invokeMethod(self.prompt_input, "setText", Qt.QueuedConnection, Q_ARG(str, recognized_text))
        except Exception as e:
            print("Voice recognition error:", e)