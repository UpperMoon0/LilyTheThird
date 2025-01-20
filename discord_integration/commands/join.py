import discord


class JoinCommand:
    def __init__(self, bot):
        self.bot = bot

        @self.bot.tree.command(name="join", description="Make the bot join your current voice channel!")
        async def join_command(interaction: discord.Interaction):
            """Joins the user's current voice channel."""
            # Check if the user is in a voice channel
            if interaction.user.voice is None:
                await interaction.response.send_message(
                    "You need to be in a voice channel for me to join!", ephemeral=True
                )
                return

            # Get the voice channel the user is in
            voice_channel = interaction.user.voice.channel

            # Check if the bot is already in the voice channel
            if interaction.guild.voice_client is not None:
                if interaction.guild.voice_client.channel == voice_channel:
                    await interaction.response.send_message(
                        "I'm already in your voice channel!", ephemeral=True
                    )
                    return

            # Join the voice channel
            try:
                await voice_channel.connect()
                await interaction.response.send_message(
                    f"Joined {voice_channel.name}!"
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"Failed to join the voice channel: {str(e)}", ephemeral=True
                )
