import threading

from PyQt5.QtCore import (
    Qt,
    QPropertyAnimation,
    pyqtProperty
)
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QWidget
from discord.bot import DiscordBot


class ColorCircle(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(201, 0, 0)  # Start with red
        self.setFixedSize(50, 50)
        self.updateStyleSheet()

    @pyqtProperty(QColor)
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = color
        self.updateStyleSheet()

    def updateStyleSheet(self):
        self.setStyleSheet(
            f"background-color: rgba({self._color.red()}, {self._color.green()}, "
            f"{self._color.blue()}, {self._color.alpha() / 255.0}); "
            f"border-radius: 25px;"
        )

class DiscordTab(QWidget):
    def __init__(self):
        super().__init__()

        self.bot = DiscordBot()
        self.bot.bot_ready.connect(self.on_bot_ready)
        self.bot.bot_stopped.connect(self.on_bot_stopped)
        self.bot_thread = None
        self.is_bot_running = False

        # Replace QLabel status circle with ColorCircle
        self.status_circle = ColorCircle(self)

        # Create animations
        self.idle_animation = QPropertyAnimation(self.status_circle, b"color")
        self.idle_animation.setDuration(1500)
        self.idle_animation.setLoopCount(-1)  # Infinite loop
        self.setup_idle_animation()

        self.running_animation = QPropertyAnimation(self.status_circle, b"color")
        self.running_animation.setDuration(1500)
        self.running_animation.setLoopCount(-1)
        self.setup_running_animation()

        # Start the idle animation when the app starts
        self.idle_animation.start()

        # Rest of your initialization code remains the same
        self.toggle_bot_button = QPushButton("Start Bot", self)
        self.toggle_bot_button.clicked.connect(self.on_toggle_bot_clicked)
        self.toggle_bot_button.setStyleSheet("width: 200px; height: 40px;")

        self.status_label = QLabel("Not Running", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("text-align: center;")

        self.guild_id_input = QLineEdit(self)
        self.guild_id_input.setPlaceholderText("Enter Guild ID")
        self.guild_id_input.setVisible(True)
        self.guild_id_input.setStyleSheet("width: 300px; height: 30px;")

        self.channel_id_input = QLineEdit(self)
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setVisible(True)
        self.channel_id_input.setStyleSheet("width: 300px; height: 30px;")

        self.message_input = QLineEdit(self)
        self.message_input.setPlaceholderText("Type your message here...")
        self.message_input.setVisible(False)
        self.message_input.setStyleSheet("width: 300px; height: 30px;")

        self.send_message_button = QPushButton("Send Message", self)
        self.send_message_button.clicked.connect(self.on_send_message_clicked)
        self.send_message_button.setVisible(False)
        self.send_message_button.setStyleSheet("width: 200px; height: 40px;")

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.save_button.setStyleSheet("width: 200px; height: 40px;")

        # Status layout with button and status label
        status_layout = QVBoxLayout()
        status_layout.setAlignment(Qt.AlignCenter)

        status_circle_layout = QHBoxLayout()
        status_circle_layout.addStretch()
        status_circle_layout.addWidget(self.status_circle)
        status_circle_layout.addStretch()
        status_layout.addLayout(status_circle_layout)

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

        # Input layout
        input_layout = QVBoxLayout()
        input_layout.setAlignment(Qt.AlignCenter)

        guild_id_layout = QHBoxLayout()
        guild_id_layout.addStretch()
        guild_id_layout.addWidget(self.guild_id_input)
        guild_id_layout.addStretch()
        input_layout.addLayout(guild_id_layout)

        channel_id_layout = QHBoxLayout()
        channel_id_layout.addStretch()
        channel_id_layout.addWidget(self.channel_id_input)
        channel_id_layout.addStretch()
        input_layout.addLayout(channel_id_layout)

        save_button_layout = QHBoxLayout()
        save_button_layout.addStretch()
        save_button_layout.addWidget(self.save_button)
        save_button_layout.addStretch()
        input_layout.addLayout(save_button_layout)

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
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.addLayout(status_layout)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

    def setup_idle_animation(self):
        # Create keyframes for smoother animation
        self.idle_animation.setKeyValueAt(0, QColor(201, 0, 0))    # Red
        self.idle_animation.setKeyValueAt(0.5, QColor(196, 160, 0))  # Yellow
        self.idle_animation.setKeyValueAt(1, QColor(201, 0, 0))    # Back to red

    def setup_running_animation(self):
        # Create keyframes for smoother animation
        self.running_animation.setKeyValueAt(0, QColor(0, 255, 76))      # Green
        self.running_animation.setKeyValueAt(0.5, QColor(0, 196, 186))  # Turquoise
        self.running_animation.setKeyValueAt(1, QColor(0, 255, 76))      # Back to green

    def update_status(self, status):
        self.status_label.setText(status)

        # Stop both animations first
        self.idle_animation.stop()
        self.running_animation.stop()

        if status == "Running":
            self.running_animation.start()
        else:
            self.idle_animation.start()

    def on_toggle_bot_clicked(self):
        if not self.is_bot_running:
            self.update_status("Starting")
            self.toggle_bot_button.setEnabled(False)
            self.bot_thread = threading.Thread(target=self.bot.start_bot)
            self.bot_thread.start()
        else:
            self.update_status("Stopping")
            self.toggle_bot_button.setEnabled(False)
            self.bot.stop_bot()

    def on_bot_ready(self):
        self.is_bot_running = True
        self.update_status("Running")
        self.toggle_bot_button.setText("Stop Bot")
        self.toggle_bot_button.setEnabled(True)
        self.message_input.setVisible(True)
        self.send_message_button.setVisible(True)

    def on_bot_stopped(self):
        self.is_bot_running = False
        self.update_status("Not Running")
        self.toggle_bot_button.setText("Start Bot")
        self.toggle_bot_button.setEnabled(True)
        self.message_input.setVisible(False)
        self.send_message_button.setVisible(False)

    def on_send_message_clicked(self):
        if not self.is_bot_running:
            print("Bot is not running!")
            return

        channel_id_text = self.channel_id_input.text()
        message = self.message_input.text()

        if channel_id_text and message:
            try:
                channel_id = int(channel_id_text)
                self.bot.send_message(channel_id, message)
            except ValueError:
                print("Invalid Channel ID entered.")

        self.message_input.clear()

    def on_save_clicked(self):
        guild_id_text = self.guild_id_input.text()
        channel_id_text = self.channel_id_input.text()

        if guild_id_text:
            try:
                guild_id = int(guild_id_text)
                self.bot.set_guild_id(guild_id)
            except ValueError:
                print("Invalid Guild ID entered.")

        if channel_id_text:
            try:
                channel_id = int(channel_id_text)
                self.bot.set_channel_id(channel_id)
            except ValueError:
                print("Invalid Channel ID entered.")