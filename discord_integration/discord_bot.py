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

    def __init__(self):
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

    async def setup_hook(self):
        """Called during the bot setup to run asynchronous tasks."""
        # Start the inactivity check background task
        self.bot.loop.create_task(self.check_inactivity())

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
