# discord/discord_bot.py
import asyncio
import os
import discord
from PyQt5.QtCore import pyqtSignal, QObject
from discord.ext import commands

from discord_integration.commands.iq_command import IQCommand
from discord_integration.commands.gtnh_test import GTNHIntelligenceTestCommand


class DiscordBot(QObject):
    bot_ready = pyqtSignal()
    bot_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.bot = None
        self.is_running = False
        self.guild_id = None
        self.channel_id = None

    def set_guild_id(self, guild_id):
        """Sets the guild ID to sync slash commands with."""
        self.guild_id = guild_id

    def set_channel_id(self, channel_id):
        """Sets the channel ID to send messages to."""
        self.channel_id = channel_id

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

        # Register the IQ command
        IQCommand(self.bot)
        # Register the GTNH Intelligence Test command
        GTNHIntelligenceTestCommand(self.bot)

        # Start the bot
        self.bot.run(discord_token)

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
        """Stops the bot gracefully."""
        if self.bot and self.is_running:
            async def close_bot():
                """Closes the bot connection."""
                await self.bot.close()
                self.is_running = False
                self.bot_stopped.emit()
                print("Bot has been stopped")

            if hasattr(self.bot, "loop") and self.bot.loop.is_running():
                asyncio.run_coroutine_threadsafe(close_bot(), self.bot.loop)

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
            asyncio.run_coroutine_threadsafe(send(), self.bot.loop)
        else:
            print("Bot is not running. Unable to send message.")