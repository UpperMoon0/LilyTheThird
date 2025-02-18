import os
from dotenv import load_dotenv
from discord_integration.discord_bot import DiscordBot

def run_discord_bot(ipc_queue):
    load_dotenv()  # Load environment variables from .env file
    bot_instance = DiscordBot(ipc_queue=ipc_queue)
    bot_instance.start_bot()