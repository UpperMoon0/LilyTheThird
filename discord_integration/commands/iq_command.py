import os
import random

import discord
from dotenv import load_dotenv

class IQCommand:
    def __init__(self, bot):
        self.bot = bot

        @self.bot.tree.command(name="iq", description="Get your IQ score!")
        async def iq_command(interaction: discord.Interaction):
            # Load environment variables
            load_dotenv()
            master_id = int(os.getenv('MASTER_DISCORD_ID'))
            lily_id = int(os.getenv('LILY_DISCORD_ID'))

            # Check if the user is the master
            if interaction.user.id == master_id:
                iq = "∞"  # Infinite symbol
                response = f"Of course, my master's IQ is {iq}!"
            elif interaction.user.id == lily_id:
                iq = "∞"
                response = f"Of course, my IQ is {iq}!"
            else:
                iq = random.randint(0, 20)
                response = f"{interaction.user.mention}, your IQ is {iq}!"

            await interaction.response.send_message(response)
