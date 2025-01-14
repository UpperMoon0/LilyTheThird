import threading
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QPushButton, QLineEdit, QWidget
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

        self.channel_id_input = QLineEdit(self)
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setVisible(False)

        self.message_input = QLineEdit(self)
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setVisible(False)

        self.send_message_button = QPushButton("Send Message", self)
        self.send_message_button.clicked.connect(self.on_send_message_clicked)
        self.send_message_button.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(self.toggle_bot_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.channel_id_input)
        layout.addWidget(self.message_input)
        layout.addWidget(self.send_message_button)

        self.setLayout(layout)

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