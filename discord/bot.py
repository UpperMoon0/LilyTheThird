import os
import discord
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QLineEdit, QWidget

class DiscordBot:
    def __init__(self):
        self.bot = None

    def start_bot(self):
        # Retrieve the token from the environment variable
        discord_token = os.getenv("DISCORD_TOKEN")

        if not discord_token:
            print("DISCORD_TOKEN not found in .env file.")
            return

        # Set up the bot client
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)

        @self.bot.event
        async def on_ready():
            print(f"Bot logged in as {self.bot.user}")

        @self.bot.event
        async def on_message(message):
            if message.content.lower() == "hello":
                await message.channel.send("Hello there!")

        # Start the bot using the provided token
        self.bot.run(discord_token)

    def send_message(self, channel, message):
        # Sends a message to a specific channel
        async def send():
            await channel.send(message)

        # Get the event loop and run the send function
        self.bot.loop.create_task(send())