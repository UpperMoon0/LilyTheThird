import asyncio
import os
import time

import discord
from PyQt5.QtCore import pyqtSignal, QObject
from discord.ext import commands
from dotenv import load_dotenv

from discord_integration.commands.gtnh_test.gtnh_test import GTNHIntelligenceTestCommand
from discord_integration.commands.iq_command import IQCommand
from discord_integration.commands.voice.join import JoinCommand
from discord_integration.commands.voice.play import PlayCommand
from llm.discord_llm import DiscordLLM
from models.song_queue import SongQueue


class DiscordBot(QObject):
    bot_ready = pyqtSignal()
    bot_stopped = pyqtSignal()

    def __init__(self, ipc_queue=None):
        super().__init__()
        load_dotenv()  # Load environment variables from .env file
        self.bot = None
        self.is_running = False
        self.guild_id = os.getenv("DISCORD_GUILD_ID")
        self.channel_id = os.getenv("DISCORD_CHANNEL_ID")
        self.discordLLM = DiscordLLM()
        self.last_activity_time = None
        self.cooldown_period = 10 * 60  # 10 minutes in seconds
        self.song_queue = SongQueue(self)  # Initialize song queue for PlayCommand
        self.ipc_queue = ipc_queue  # IPC queue for inter-process communication

    async def setup_hook(self):
        """Called during the bot setup to run asynchronous tasks."""
        # Start the inactivity check background task
        self.bot.loop.create_task(self.check_inactivity())
        # Start the IPC listener task if an IPC queue is provided
        if self.ipc_queue is not None:
            self.bot.loop.create_task(self.ipc_listener_task())

    def set_guild_id(self, guild_id: int):
        """Sets the guild ID."""
        self.guild_id = guild_id
        print(f"Guild ID set to {self.guild_id}")

    def set_channel_id(self, channel_id: int):
        """Sets the channel ID."""
        self.channel_id = channel_id
        print(f"Channel ID set to {self.channel_id}")

    def get_channel_id(self):
        """Returns the channel ID."""
        return self.channel_id

    def start_bot(self):
        """Starts the Discord bot and logs in using the token."""
        discord_token = os.getenv("DISCORD_TOKEN")

        if not discord_token:
            print("DISCORD_TOKEN not found in .env file.")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            """Triggered when the bot is logged in and ready."""
            print(f"Bot logged in as {self.bot.user}")
            self.is_running = True
            self.bot_ready.emit()
            # Schedule background tasks (inactivity check and IPC listener)
            self.bot.loop.create_task(self.check_inactivity())
            if self.ipc_queue is not None:
                self.bot.loop.create_task(self.ipc_listener_task())
            await self.sync_commands()

        # Register commands
        IQCommand(self.bot)
        GTNHIntelligenceTestCommand(self.bot)
        JoinCommand(self.bot)
        PlayCommand(self.bot, self.song_queue)

        # Start the bot (without asyncio.run)
        self.bot.run(discord_token)

    async def check_inactivity(self):
        """Check for inactivity and reset the bot if idle for more than the cooldown period."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            if self.last_activity_time is not None:
                time_since_last_activity = time.time() - self.last_activity_time
                if time_since_last_activity > self.cooldown_period:
                    # No activity for 10 minutes, reset the bot state
                    print("Cooldown expired, asking for 'Hey Lily' again.")
                    self.last_activity_time = None
            else:
                print("No activity time set, waiting for first message.")

    async def ipc_listener_task(self):
        """Listens for messages from the IPC queue and sends them to Discord."""
        print("IPC listener started.")
        loop = asyncio.get_running_loop()
        while self.is_running:
            try:
                # This is a blocking call executed in a thread so as not to block the event loop.
                message = await loop.run_in_executor(None, self.ipc_queue.get)
                if message is None:
                    continue
                print(f"Received IPC message: {message}")
                # Expecting a dict with keys 'channel_id' and 'content'
                await self.async_send_message(message.get("channel_id"), message.get("content"))
            except Exception as e:
                print("Error in ipc_listener_task:", e)
                await asyncio.sleep(0.1)

    async def async_send_message(self, channel_id, message):
        """Asynchronously sends a message to the specified channel."""
        if not self.bot or not self.is_running:
            print("Bot is not running. Cannot send message.")
            return
        try:
            # Convert channel_id to integer if necessary
            channel_id = int(channel_id)
        except Exception as e:
            print("Invalid channel id provided:", channel_id)
            return

        channel = self.bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send(message)
            except Exception as e:
                print("Failed to send message:", e)
        else:
            print(f"Channel with ID {channel_id} not found.")

    async def sync_commands(self):
        """Syncs the command tree with Discord."""
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            await self.bot.tree.sync(guild=guild)
            print(f"Commands synced with guild ID {self.guild_id}")
        else:
            await self.bot.tree.sync()
            print("Commands synced globally")

    def stop_bot(self):
        """Gracefully stops the bot."""
        if self.bot and self.is_running:
            # Stop background tasks
            self.is_running = False
            self.bot_ready.disconnect()  # Disconnect the signal if it's connected
            self.bot.loop.create_task(self.bot.close())  # Asynchronously close the bot
            print("Bot is shutting down...")
            self.bot_stopped.emit()  # Emit stop signal after shutting down
        else:
            print("Bot is not running or already stopped.")

    def send_message(self, channel_id, message):
        """Sends a message to a specified channel."""
        async def send():
            """Helper function to send the message asynchronously."""
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(message)
            else:
                print(f"Channel with ID {channel_id} not found.")

        if self.bot and self.is_running:
            if self.bot.loop.is_running():
                asyncio.create_task(send())  # Use asyncio.create_task to send the message
            else:
                print("Bot loop is not running. Unable to send message.")

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()

    from PyQt5.QtWidgets import QApplication
    from views.discord_tab import DiscordTab
    import sys

    app = QApplication(sys.argv)
    win = DiscordTab()
    win.show()
    sys.exit(app.exec_())