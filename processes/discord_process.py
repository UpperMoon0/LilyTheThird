import os
# Removed sys and QCoreApplication imports
from dotenv import load_dotenv
from discord_integration.discord_bot import DiscordBot

# Accept discord_config dictionary
def run_discord_bot(ipc_queue, discord_config):
    # Removed QCoreApplication instantiation

    load_dotenv()  # Load environment variables from .env file (still needed for API keys, token etc.)

    # Instantiate DiscordBot
    bot_instance = DiscordBot(ipc_queue=ipc_queue, config=discord_config)

    # Start the bot. This will run the discord.py event loop.
    # The Qt event loop (app.exec_()) is not explicitly run here,
    # but the QCoreApplication instance ensures QObject initialization is correct.
    bot_instance.start_bot()
