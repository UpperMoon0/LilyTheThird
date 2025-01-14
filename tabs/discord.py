import threading
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget, QLineEdit
from discord.bot import DiscordBot

class DiscordTab(QWidget):
    def __init__(self):
        super().__init__()

        self.bot = DiscordBot()

        # Button to start the bot
        self.start_bot_button = QPushButton("Start Bot", self)
        self.start_bot_button.clicked.connect(self.on_start_bot_clicked)

        # Input field to enter channel ID
        self.channel_id_input = QLineEdit(self)
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setVisible(False)  # Hide channel ID input initially

        # Input field to send a message as the bot
        self.message_input = QLineEdit(self)
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setVisible(False)  # Hide message input initially

        self.send_message_button = QPushButton("Send Message", self)
        self.send_message_button.clicked.connect(self.on_send_message_clicked)
        self.send_message_button.setVisible(False)  # Hide send message button initially

        layout = QVBoxLayout()
        layout.addWidget(self.start_bot_button)
        layout.addWidget(self.channel_id_input)
        layout.addWidget(self.message_input)
        layout.addWidget(self.send_message_button)

        self.setLayout(layout)

    def on_start_bot_clicked(self):
        # Start the bot in a separate thread to avoid UI freezing
        bot_thread = threading.Thread(target=self.bot.start_bot)
        bot_thread.start()

        # Show the message input and send button once the bot starts
        self.channel_id_input.setVisible(True)
        self.message_input.setVisible(True)
        self.send_message_button.setVisible(True)

    def on_send_message_clicked(self):
        # Get the channel ID and message from the input fields
        channel_id_text = self.channel_id_input.text()
        message = self.message_input.text()

        if channel_id_text and message:
            try:
                # Convert the channel ID input to an integer
                channel_id = int(channel_id_text)

                # Get the channel by ID and send the message
                channel = self.bot.bot.get_channel(channel_id)
                if channel:
                    self.bot.send_message(channel, message)
                else:
                    print("Channel not found.")
            except ValueError:
                print("Invalid Channel ID entered.")

        # Keep the channel ID input content but clear the message input
        self.message_input.clear()
