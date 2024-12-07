import sys
import threading

from PyQt5.QtWidgets import QApplication, QMainWindow, QLineEdit, QTextEdit, QVBoxLayout, QWidget, QCheckBox, \
    QPushButton
from PyQt5.QtGui import QFont

from action import action_handler
from llm_api import get_response
from tts import synthesize_speech

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.prompt_input = QLineEdit(self)
        self.response_box = QTextEdit(self)
        self.response_box.setReadOnly(True)
        self.speech_synthesis_enabled = QCheckBox("Enable Speech Synthesis", self)
        self.speech_synthesis_enabled.setChecked(False)
        self.clear_history_button = QPushButton("Clear History", self)
        self.enable_kg_memory_checkbox = QCheckBox("Enable Knowledge Graph Memory", self)
        self.enable_kg_memory_checkbox.setChecked(True)  # By default, the memory is enabled

        # Set the font size for the input box and response box
        font = QFont("Arial", 14)  # Set font family and size (14 points)
        self.prompt_input.setFont(font)
        self.response_box.setFont(font)

        layout = QVBoxLayout()
        layout.addWidget(self.prompt_input)
        layout.addWidget(self.response_box)
        layout.addWidget(self.speech_synthesis_enabled)
        layout.addWidget(self.enable_kg_memory_checkbox)  # Add the checkbox to the layout
        layout.addWidget(self.clear_history_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.prompt_input.returnPressed.connect(self.get_response)
        self.clear_history_button.clicked.connect(self.clear_history)

    def get_response(self):
        threading.Thread(target=self._get_response_thread).start()

    def _get_response_thread(self):
        self.prompt_input.setDisabled(True)
        message, action = get_response(self.prompt_input.text(), not self.enable_kg_memory_checkbox.isChecked())

        action_handler.execute_command(action)

        print(f"Message: {message}")
        print(f"Action: {action}")

        # Run the speech synthesis in a separate thread if enabled
        if self.speech_synthesis_enabled.isChecked():
            threading.Thread(target=synthesize_speech, args=(message,)).start()

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

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec_())
