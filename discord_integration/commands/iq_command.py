import random

import discord


class IQCommand:
    def __init__(self, bot):
        self.bot = bot
        @self.bot.tree.command(name="iq", description="Get your random IQ score!")
        async def iq_command(interaction: discord.Interaction):
            """Generates a random IQ score between 0 and 200."""
            iq = random.randint(1000, 2000)
            await interaction.response.send_message(
                f"{interaction.user.mention}, your IQ is {iq}!"
            )
