import asyncio
import os
import time

import discord
# Removed QObject and pyqtSignal imports as they are no longer needed for cross-process signals
from discord.ext import commands
from dotenv import load_dotenv

from discord_integration.commands.gtnh_test.gtnh_test import GTNHIntelligenceTestCommand
from discord_integration.commands.iq_command import IQCommand
from discord_integration.commands.voice.clear_queue import ClearQueueCommand
from discord_integration.commands.voice.join import JoinCommand
from discord_integration.commands.voice.play import PlayCommand
from discord_integration.commands.voice.skip_song import SkipCommand
# ... (other imports remain the same) ...

from llm.discord_llm import DiscordLLM
from models.song_queue import SongQueue


class DiscordBot: # Removed QObject inheritance
    # Removed signal definitions:
    # bot_ready = pyqtSignal()
    # bot_stopped = pyqtSignal()

    def __init__(self, ipc_queue=None, config=None):
        # Removed super().__init__()
        load_dotenv()
        self.bot = None
        self.is_running = False
        self.config = config if config else {}

        self.guild_id = self.config.get('guild_id', os.getenv("DISCORD_GUILD_ID"))
        self.channel_id = self.config.get('channel_id', os.getenv("DISCORD_CHANNEL_ID"))
        self.master_id = os.getenv("MASTER_DISCORD_ID") # Load master ID

        # Extract LLM settings from config, default to None if not found
        llm_provider = self.config.get('discord_llm_provider', None)
        llm_model = self.config.get('discord_llm_model', None)

        try:
            # Pass provider and model from config to DiscordLLM constructor
            self.discordLLM = DiscordLLM(provider=llm_provider, model=llm_model)
        except ValueError as e:
            print(f"FATAL: Could not initialize DiscordLLM: {e}")
            self.discordLLM = None

        self.last_activity_time = None
        self.cooldown_period = 10 * 60  # 10 minutes

        self.song_queue = SongQueue(self)
        self.ipc_queue = ipc_queue

        print(f"DiscordBot initialized with Guild: {self.guild_id}, Channel: {self.channel_id}")
        if self.discordLLM:
            print(f"DiscordBot LLM: Provider={self.discordLLM.provider}, Model={self.discordLLM.model}")
        if self.master_id:
            print(f"Master Discord ID: {self.master_id}")
        else:
            print("Warning: MASTER_DISCORD_ID not set in .env file.")


    # ... (setup_hook, set_guild_id, set_channel_id, get_channel_id remain the same) ...

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
            print(f"Bot logged in as {self.bot.user}")
            self.is_running = True
            # Send status update via IPC queue instead of emitting signal
            if self.ipc_queue:
                try:
                    self.ipc_queue.put({'status': 'ready', 'user': str(self.bot.user)})
                    print("Sent 'ready' status via IPC queue.")
                except Exception as e:
                    print(f"Error putting 'ready' status on IPC queue: {e}")
            else:
                print("IPC queue not available to send 'ready' status.")

            # Schedule background tasks (inactivity check and IPC listener)
            # Ensure tasks are not duplicated if bot reconnects
            if not hasattr(self.bot, '_inactivity_task') or self.bot._inactivity_task.done():
                 self.bot._inactivity_task = self.bot.loop.create_task(self.check_inactivity())
            if self.ipc_queue is not None and (not hasattr(self.bot, '_ipc_task') or self.bot._ipc_task.done()):
                 self.bot._ipc_task = self.bot.loop.create_task(self.ipc_listener_task())
            await self.sync_commands()


        # ... (command registrations remain the same) ...

        # Register commands
        IQCommand(self.bot)
        GTNHIntelligenceTestCommand(self.bot)
        JoinCommand(self.bot)
        PlayCommand(self.bot, self.song_queue)
        SkipCommand(self.bot, self.song_queue)
        ClearQueueCommand(self.bot, self.song_queue)

        @self.bot.event
        async def on_message(message):
            # 1. Ignore messages from the bot itself
            if message.author == self.bot.user:
                return

            # 2. Check if the message is in the designated channel
            if str(message.channel.id) != str(self.channel_id):
                return # Ignore messages from other channels

            # 3. Conversation Trigger/State Check
            is_active_conversation = self.last_activity_time is not None and \
                                     (time.time() - self.last_activity_time <= self.cooldown_period)
            trigger_phrase = "hey lily"
            is_triggered = message.content.lower().startswith(trigger_phrase)

            # Proceed only if triggered or conversation is active
            if not is_triggered and not is_active_conversation:
                # print("Ignoring message: Not triggered and conversation inactive.") # Optional debug log
                return

            # Ensure LLM is initialized
            if not self.discordLLM:
                print("LLM not initialized, cannot process message.")
                # Maybe send a message back?
                # await message.channel.send("Sorry, my brain isn't working right now.")
                return

            # 4. Prepare message for LLM (Use the full message content)
            user_prompt = message.content

            # Indicate bot is thinking
            async with message.channel.typing():
                # 5. Call LLM
                try:
                    print(f"Calling LLM for user {message.author.display_name} ({message.author.id})...")
                    response, _ = self.discordLLM.get_response(
                        user_message=user_prompt,
                        discord_user_id=message.author.id,
                        discord_user_name=message.author.display_name # Use display name
                    )
                except Exception as e:
                    print(f"Error getting LLM response: {e}")
                    response = "Sorry, I encountered an error trying to process that."

                # 6. Send Response (Handle long messages)
                if response:
                    if len(response) <= 2000:
                        await message.channel.send(response)
                    else:
                        # Split the response into chunks of 2000 characters
                        print(f"Response length ({len(response)}) exceeds 2000 chars, splitting...")
                        chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
                        for chunk in chunks:
                            await message.channel.send(chunk)
                            await asyncio.sleep(0.5) # Small delay between chunks to avoid rate limits
                else:
                    print("LLM returned an empty response.") # Log if response is empty

            # 7. Update Activity Time
            self.last_activity_time = time.time()
            print(f"Updated last activity time for channel {self.channel_id}.")


        # Start the bot
        discord_token = os.getenv("DISCORD_TOKEN")
        if not discord_token:
             print("DISCORD_TOKEN not found in .env file.")
             return
        # Use asyncio.run() in a way that integrates with PyQt event loop if needed,
        # but typically bot.run() handles its own loop.
        # Consider running this in a separate thread if it blocks the main GUI thread.
        # For now, assuming direct call is okay or handled by the process management.
        try:
            self.bot.run(discord_token)
        except Exception as e:
            print(f"Error running bot: {e}")
            self.is_running = False
            # Removed self.bot_stopped.emit() as signals are no longer used for IPC


    async def check_inactivity(self):
        """Check for inactivity and reset the conversation state if idle."""
        while self.is_running: # Check if bot should still be running
            await asyncio.sleep(60)  # Check every minute
            if self.last_activity_time is not None:
                time_since_last_activity = time.time() - self.last_activity_time
                if time_since_last_activity > self.cooldown_period:
                    print(f"Conversation cooldown expired in channel {self.channel_id}. Resetting state.")
                    self.last_activity_time = None # Reset activity time, requiring trigger phrase again
                    # Optionally clear LLM history here if desired
                    # if self.discordLLM:
                    #     self.discordLLM.message_history.clear()
                    #     print("Cleared LLM message history due to inactivity.")
            # else: # No need to print this every minute
                # print("No activity time set, waiting for first message.")
            # Add a small delay even if not running to prevent tight loop on exit
            if not self.is_running:
                 await asyncio.sleep(1)


    # ... (ipc_listener_task, async_send_message, sync_commands, stop_bot, send_message remain the same) ...
    # Make sure stop_bot properly cancels background tasks if needed.

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

                # Check for shutdown command
                if message.get("command") == "shutdown":
                    print("Shutdown command received, closing bot gracefully...")
                    await self.bot.close()
                    return

                # Regular message handling
                if "channel_id" in message and "content" in message:
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
        """Syncs the command tree with Discord both globally and with the specific guild."""
        # Always sync globally first
        await self.bot.tree.sync()
        print("Commands synced globally")

        # Additionally sync with the specific guild if guild_id is provided
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            await self.bot.tree.sync(guild=guild)
            print(f"Commands additionally synced with guild ID {self.guild_id}")

    def stop_bot(self):
        """Gracefully stops the bot and cancels background tasks."""
        if self.bot and self.is_running:
            self.is_running = False # Signal tasks to stop
            print("Attempting to stop bot...")

            # Cancel background tasks
            if hasattr(self.bot, '_inactivity_task') and not self.bot._inactivity_task.done():
                self.bot._inactivity_task.cancel()
                print("Cancelled inactivity check task.")
            if hasattr(self.bot, '_ipc_task') and not self.bot._ipc_task.done():
                self.bot._ipc_task.cancel()
                print("Cancelled IPC listener task.")

            # Disconnect signals before closing - REMOVED as signals are removed

            # Schedule bot close
            # Ensure bot.loop exists and is running before scheduling close
            if self.bot and hasattr(self.bot, 'loop') and self.bot.loop.is_running():
                 asyncio.run_coroutine_threadsafe(self.bot.close(), self.bot.loop)
                 print("Scheduled bot close.")
            else:
                 print("Bot loop not available or not running, cannot schedule close.")


            # Send 'stopped' status via IPC queue *before* exiting the function
            if self.ipc_queue:
                try:
                    # Use put_nowait or handle potential blocking if queue is full
                    self.ipc_queue.put({'status': 'stopped'})
                    print("Sent 'stopped' status via IPC queue.")
                except Exception as e:
                    print(f"Error putting 'stopped' status on IPC queue: {e}")
            else:
                 print("IPC queue not available to send 'stopped' status.")

            print("Bot stop process initiated.")
        else:
            print("Bot is not running or already stopped.")


    # ... (if __name__ == '__main__': block remains the same) ...

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
