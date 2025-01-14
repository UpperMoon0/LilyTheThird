import asyncio
import os
import threading

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QRegion
from PyQt5.QtWidgets import QLineEdit, QTextEdit, QVBoxLayout, QWidget, QCheckBox, \
    QPushButton, QLabel

from actions import action_handler
from llm import ChatbotManager
from tts import text_to_speech_and_play


def clear_output_folder():
    output_folder = "outputs"  # Adjust this path as needed

    # Check if the outputs folder exists
    if os.path.exists(output_folder):
        # Delete files that start with 'audio' in the outputs folder
        for filename in os.listdir(output_folder):
            if filename.startswith("audio"):
                file_path = os.path.join(output_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")


from PyQt5.QtGui import QPixmap

from PyQt5.QtWidgets import QHBoxLayout

class ChatTab(QWidget):
    def __init__(self):
        super().__init__()

        self.chatbot_manager = ChatbotManager()

        # Create a QLabel for the avatar
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(300, 300)  # Set the size of the avatar
        self.avatar_label.setAlignment(Qt.AlignCenter)  # Center the avatar

        # Load the avatar image
        avatar_pixmap = QPixmap("assets/avatar.png")
        avatar_pixmap = avatar_pixmap.scaled(self.avatar_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Set the avatar image to the QLabel
        self.avatar_label.setPixmap(avatar_pixmap)

        # Create a QRegion to make the image circular
        mask_region = QRegion(0, 0, self.avatar_label.width(), self.avatar_label.height(), QRegion.Ellipse)

        # Apply the mask to the QLabel to clip the image into a circle
        self.avatar_label.setMask(mask_region)

        # Create an HBoxLayout for the avatar and center it
        avatar_layout = QHBoxLayout()
        avatar_layout.setAlignment(Qt.AlignCenter)
        avatar_layout.addWidget(self.avatar_label)

        self.prompt_input = QLineEdit(self)
        self.response_box = QTextEdit(self)
        self.response_box.setReadOnly(True)
        self.speech_synthesis_enabled = QCheckBox("Enable Speech Synthesis", self)
        self.speech_synthesis_enabled.setChecked(True)
        self.clear_history_button = QPushButton("Clear History", self)
        self.enable_kg_memory_checkbox = QCheckBox("Enable Knowledge Graph Memory", self)
        self.enable_kg_memory_checkbox.setChecked(False)

        # Set the font size for the input box and response box
        font = QFont("Arial", 14)  # Set font family and size (14 points)
        self.prompt_input.setFont(font)
        self.response_box.setFont(font)

        layout = QVBoxLayout()
        layout.addLayout(avatar_layout)  # Add the avatar layout to the main layout
        layout.addWidget(self.prompt_input)
        layout.addWidget(self.response_box)
        layout.addWidget(self.speech_synthesis_enabled)
        layout.addWidget(self.enable_kg_memory_checkbox)  # Add the checkbox to the layout
        layout.addWidget(self.clear_history_button)

        self.setLayout(layout)

        self.prompt_input.returnPressed.connect(self.get_response)
        self.clear_history_button.clicked.connect(self.clear_history)

        # Clear the outputs folder when the app starts
        clear_output_folder()

    def get_response(self):
        threading.Thread(target=self._get_response_thread).start()

    def _get_response_thread(self):
        self.prompt_input.setDisabled(True)

        # Use the ChatbotManager instance to get the response
        message, action = self.chatbot_manager.get_response(self.prompt_input.text(), not self.enable_kg_memory_checkbox.isChecked())

        # Execute the action if any
        action_handler.execute_command(action)

        print(f"Message: {message}")
        print(f"Action: {action}")

        # Run the speech synthesis in a separate thread if enabled
        if self.speech_synthesis_enabled.isChecked():
            threading.Thread(target=lambda: asyncio.run(text_to_speech_and_play(message, "ja-JP-NanamiNeural", "+15Hz"))).start()

        # Format and append the user's message and the bot's response to the response_box
        self.response_box.append(f"You: {self.prompt_input.text()}")
        self.response_box.append(f"Lily: {message}")

        # Clear the prompt_input box
        self.prompt_input.clear()
        self.prompt_input.setDisabled(False)

    def clear_history(self):
        global message_history
        message_history = []
        self.response_box.append("History cleared.")

