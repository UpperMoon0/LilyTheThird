import threading
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QWidget
from discord.bot import DiscordBot

class DiscordTab(QWidget):
    def __init__(self):
        super().__init__()

        self.bot = DiscordBot()
        self.bot.bot_ready.connect(self.on_bot_ready)
        self.bot.bot_stopped.connect(self.on_bot_stopped)
        self.bot_thread = None
        self.is_bot_running = False

        self.toggle_bot_button = QPushButton("Start Bot", self)
        self.toggle_bot_button.clicked.connect(self.on_toggle_bot_clicked)

        self.status_label = QLabel("Not Running", self)
        self.status_label.setAlignment(Qt.AlignCenter)

        self.channel_id_input = QLineEdit(self)
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setVisible(False)

        self.message_input = QLineEdit(self)
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setVisible(False)

        self.send_message_button = QPushButton("Send Message", self)
        self.send_message_button.clicked.connect(self.on_send_message_clicked)
        self.send_message_button.setVisible(False)

        # Status layout with button and status label
        status_layout = QVBoxLayout()
        status_layout.setAlignment(Qt.AlignCenter)

        toggle_button_layout = QHBoxLayout()
        toggle_button_layout.addStretch()
        toggle_button_layout.addWidget(self.toggle_bot_button)
        toggle_button_layout.addStretch()
        status_layout.addLayout(toggle_button_layout)

        status_label_layout = QHBoxLayout()
        status_label_layout.addStretch()
        status_label_layout.addWidget(self.status_label)
        status_label_layout.addStretch()
        status_layout.addLayout(status_label_layout)

        # Input layout with input fields and send button
        input_layout = QVBoxLayout()
        input_layout.setAlignment(Qt.AlignCenter)

        channel_id_layout = QHBoxLayout()
        channel_id_layout.addStretch()
        channel_id_layout.addWidget(self.channel_id_input)
        channel_id_layout.addStretch()
        input_layout.addLayout(channel_id_layout)

        message_input_layout = QHBoxLayout()
        message_input_layout.addStretch()
        message_input_layout.addWidget(self.message_input)
        message_input_layout.addStretch()
        input_layout.addLayout(message_input_layout)

        send_button_layout = QHBoxLayout()
        send_button_layout.addStretch()
        send_button_layout.addWidget(self.send_message_button)
        send_button_layout.addStretch()
        input_layout.addLayout(send_button_layout)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.addLayout(status_layout)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

        # Load and apply the QSS file
        self.load_stylesheet()

    def load_stylesheet(self):
        qss_file = os.path.join(os.path.dirname(__file__), 'discord.qss')
        try:
            with open(qss_file, 'r') as file:
                self.setStyleSheet(file.read())
        except FileNotFoundError:
            print(f"Style sheet file '{qss_file}' not found.")

    def on_toggle_bot_clicked(self):
        if not self.is_bot_running:
            self.update_status("Starting")
            self.toggle_bot_button.setEnabled(False)
            self.bot_thread = threading.Thread(target=self.start_bot)
            self.bot_thread.start()
        else:
            self.update_status("Stopping")
            self.toggle_bot_button.setEnabled(False)
            self.bot.stop_bot()

    def start_bot(self):
        self.bot.start_bot()

    def on_bot_ready(self):
        self.is_bot_running = True
        self.update_status("Running")
        self.toggle_bot_button.setText("Stop Bot")
        self.toggle_bot_button.setEnabled(True)
        self.channel_id_input.setVisible(True)
        self.message_input.setVisible(True)
        self.send_message_button.setVisible(True)

    def on_bot_stopped(self):
        self.is_bot_running = False
        self.update_status("Not Running")
        self.toggle_bot_button.setText("Start Bot")
        self.toggle_bot_button.setEnabled(True)
        self.channel_id_input.setVisible(False)
        self.message_input.setVisible(False)
        self.send_message_button.setVisible(False)

    def update_status(self, status):
        self.status_label.setText(status)

    def on_send_message_clicked(self):
        if not self.is_bot_running:
            print("Bot is not running!")
            return

        channel_id_text = self.channel_id_input.text()
        message = self.message_input.text()

        if channel_id_text and message:
            try:
                channel_id = int(channel_id_text)
                channel = self.bot.bot.get_channel(channel_id)
                if channel:
                    self.bot.send_message(channel, message)
                else:
                    print("Channel not found.")
            except ValueError:
                print("Invalid Channel ID entered.")

        self.message_input.clear()