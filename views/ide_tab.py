import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSizePolicy
)
from llm.ide_llm import IdeLLM

class IDETab(QWidget):
    def __init__(self):
        super().__init__()
        self.ide_llm = IdeLLM()
        self.attached_files = []  # List to store file paths
        self.init_ui()

    def init_ui(self):
        # Chat log (read-only)
        self.chat_box = QTextEdit(self)
        self.chat_box.setReadOnly(True)

        # Attachments container (horizontal layout)
        self.attachments_layout = QHBoxLayout()
        # The '+' button for file attachments
        self.add_attachment_button = QPushButton("+", self)
        self.add_attachment_button.setFixedSize(30, 30)
        self.add_attachment_button.clicked.connect(self.choose_files)
        self.attachments_layout.addWidget(self.add_attachment_button)
        self.attachments_layout.addStretch()  # Push any file widget to left

        # Prompt input box (taller than a line edit)
        self.prompt_input = QTextEdit(self)
        self.prompt_input.setPlaceholderText("Enter your message...")
        self.prompt_input.setFixedHeight(100)  # Adjust height as needed

        # Send button
        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self.handle_prompt)

        # Main layout setup
        layout = QVBoxLayout()
        layout.addWidget(self.chat_box)
        # Add the attachments container above the prompt input
        layout.addLayout(self.attachments_layout)
        layout.addWidget(self.prompt_input)
        layout.addWidget(self.send_button)
        self.setLayout(layout)

    def choose_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Files (*)")
        if file_paths:
            for file_path in file_paths:
                if file_path not in self.attached_files:
                    self.attached_files.append(file_path)
                    self.add_attachment_widget(file_path)

    def add_attachment_widget(self, file_path):
        # Create a small widget to represent the file attachment
        attachment_widget = QWidget(self)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        file_label = QLabel(os.path.basename(file_path), self)
        remove_button = QPushButton("x", self)
        remove_button.setFixedSize(20, 20)
        # Use a lambda to pass the widget and file_path to the remover method
        remove_button.clicked.connect(lambda: self.remove_attachment(attachment_widget, file_path))
        layout.addWidget(file_label)
        layout.addWidget(remove_button)
        attachment_widget.setLayout(layout)
        # Add the widget to the attachments layout (after the add_attachment_button)
        self.attachments_layout.addWidget(attachment_widget)

    def remove_attachment(self, widget, file_path):
        if file_path in self.attached_files:
            self.attached_files.remove(file_path)
        widget.setParent(None)
        widget.deleteLater()

    def handle_prompt(self):
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            return
        # Display the user's message
        self.chat_box.append(f"You: {prompt}")
        # Get the response from IdeLLM, including file attachments
        response = self.ide_llm.get_response(prompt, self.attached_files)
        self.chat_box.append(f"IDE: {response}")
        # Clear the input and file attachments
        self.prompt_input.clear()

        # Remove all attachment widgets from the layout except the add_attachment_button
        # (assuming the add_attachment_button is the first item in the attachments_layout)
        while self.attachments_layout.count() > 1:
            item = self.attachments_layout.takeAt(1)
            if item.widget():
                item.widget().setParent(None)
        self.attached_files = []