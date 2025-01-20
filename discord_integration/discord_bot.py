import asyncio
import os
import time

import discord
from PyQt5.QtCore import pyqtSignal, QObject
from discord.ext import commands

from discord_integration.commands.gtnh_test.gtnh_test import GTNHIntelligenceTestCommand
from discord_integration.commands.iq_command import IQCommand
from llm import ChatbotManager


class DiscordBot(QObject):
    bot_ready = pyqtSignal()
    bot_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.bot = None
        self.is_running = False
        self.guild_id = None
        self.channel_id = None
        self.chatbot_manager = ChatbotManager()  # Instance of ChatbotManager
        self.last_activity_time = None
        self.cooldown_period = 10 * 60  # 10 minutes in seconds

    def set_guild_id(self, guild_id):
        """Sets the guild ID to sync slash commands with."""
        self.guild_id = guild_id

    def set_channel_id(self, channel_id):
        """Sets the channel ID to listen for messages."""
        self.channel_id = channel_id

    async def setup_hook(self):
        """Called during the bot setup to run asynchronous tasks."""
        # Start the inactivity check background task
        self.bot.loop.create_task(self.check_inactivity())

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

        @self.bot.event
        async def on_message(message):
            """Triggered when a message is sent in a channel."""
            if message.author.bot:
                return  # Ignore messages from bots

            # If last_activity_time is None, check for "Hey Lily" to trigger specific behavior
            if self.last_activity_time is None:
                if message.channel.id == self.channel_id:
                    # Reset last activity time on any new message
                    self.last_activity_time = time.time()  # Reset the last activity time whenever a new message is received

                    if message.content.lower().startswith("hey lily"):
                        user_message = message.content[len("hey lily"):].strip()

                        if user_message:
                            # Get the chatbot's response with user message
                            chatbot_response, _ = self.chatbot_manager.get_response(
                                user_message, disable_kg_memory=True
                            )
                        else:
                            # If no user message is provided, send a default "Hey Lily" to the chatbot
                            chatbot_response, _ = self.chatbot_manager.get_response(
                                "Hey Lily", disable_kg_memory=True
                            )

                        await message.channel.send(chatbot_response)
            else:
                # Process any other message regardless of content, since activity is happening
                if message.channel.id == self.channel_id:
                    user_message = message.content.strip()
                    chatbot_response, _ = self.chatbot_manager.get_response(
                        user_message, disable_kg_memory=True
                    )
                    await message.channel.send(chatbot_response)



        # Start the bot using asyncio.run
        self.bot.run(discord_token)

    async def check_inactivity(self):
        """Check for inactivity and reset the bot if idle for more than the cooldown period."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            if self.last_activity_time and time.time() - self.last_activity_time > self.cooldown_period:
                # No activity for 10 minutes, reset the bot state
                print("Cooldown expired, asking for 'Hey Lily' again.")
                self.last_activity_time = None
                # Add logic here to trigger the bot to request "Hey Lily"

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
