from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTextEdit
from llm.ide_llm import IdeLLM

class IDETab(QWidget):
    def __init__(self):
        super().__init__()
        self.ide_llm = IdeLLM()
        self.init_ui()

    def init_ui(self):
        # Create a read-only text area for the chat log
        self.chat_box = QTextEdit(self)
        self.chat_box.setReadOnly(True)

        # Create a prompt input field
        self.prompt_input = QLineEdit(self)
        self.prompt_input.setPlaceholderText("Enter your message...")
        self.prompt_input.returnPressed.connect(self.handle_prompt)

        # Add the chat log and prompt input to the layout
        layout = QVBoxLayout()
        layout.addWidget(self.chat_box)
        layout.addWidget(self.prompt_input)
        self.setLayout(layout)

    def handle_prompt(self):
        prompt = self.prompt_input.text().strip()
        if not prompt:
            return
        # Append the user's message to the chat log
        self.chat_box.append(f"You: {prompt}")
        # Get the response from IdeLLM
        response = self.ide_llm.get_response(prompt)
        # Append the response to the chat log
        self.chat_box.append(f"IDE: {response}")
        # Clear the prompt input for the next message
        self.prompt_input.clear()