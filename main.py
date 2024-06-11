import sys
import threading

from PyQt5.QtWidgets import QApplication, QMainWindow, QLineEdit, QTextEdit, QVBoxLayout, QWidget
from command import command_handler

from response import get_response
from tts import synthesize_speech


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.prompt_input = QLineEdit(self)
        self.response_box = QTextEdit(self)
        self.response_box.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self.prompt_input)
        layout.addWidget(self.response_box)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.prompt_input.returnPressed.connect(self.get_response)

    def get_response(self):
        threading.Thread(target=self._get_response_thread).start()

    def _get_response_thread(self):
        self.prompt_input.setDisabled(True)
        try:
            response, action = get_response(self.prompt_input.text())

            command_handler.execute_command(action)

            # Run the speech synthesis in a separate thread
            threading.Thread(target=synthesize_speech, args=(response,)).start()

            # Format and append the user's message and the bot's response to the response_box
            self.response_box.append(f"You: {self.prompt_input.text()}")
            self.response_box.append(f"Lily: {response}")

            # Clear the prompt_input box
            self.prompt_input.clear()
        except Exception as e:
            print(f"An error occurred: {e}")
            self.response_box.setText("An error occurred while getting the response.")
        finally:
            self.prompt_input.setDisabled(False)


app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec_())