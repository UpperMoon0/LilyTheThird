import os
import discord
import asyncio
from PyQt5.QtCore import pyqtSignal, QObject

class DiscordBot(QObject):
    bot_ready = pyqtSignal()
    bot_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.bot = None
        self.is_running = False

    def start_bot(self):
        discord_token = os.getenv("DISCORD_TOKEN")

        if not discord_token:
            print("DISCORD_TOKEN not found in .env file.")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)

        @self.bot.event
        async def on_ready():
            print(f"Bot logged in as {self.bot.user}")
            self.is_running = True
            self.bot_ready.emit()

        @self.bot.event
        async def on_message(message):
            if message.content.lower() == "hello":
                await message.channel.send("Hello there!")

        self.bot.run(discord_token)

    def stop_bot(self):
        if self.bot and self.is_running:
            async def close_bot():
                await self.bot.close()
                self.is_running = False
                self.bot_stopped.emit()
                print("Bot has been stopped")

            if hasattr(self.bot, 'loop') and self.bot.loop.is_running():
                asyncio.run_coroutine_threadsafe(close_bot(), self.bot.loop)