import discord


class SkipCommand:
    def __init__(self, bot, song_queue):
        self.bot = bot
        self.song_queue = song_queue

        @self.bot.tree.command(name="skip", description="Skip the currently playing song")
        async def skip_command(interaction: discord.Interaction):
            """Skips the currently playing song and moves to the next one in queue."""
            # Check if the bot is in a voice channel
            if interaction.guild.voice_client is None:
                await interaction.response.send_message(
                    "I'm not in a voice channel! Use the `/join` command first.", ephemeral=True
                )
                return

            # Check if something is playing
            if not self.song_queue.is_playing:
                await interaction.response.send_message(
                    "Nothing is currently playing.", ephemeral=True
                )
                return

            # Acknowledge the interaction
            await interaction.response.defer()

            # Stop the current song, which will trigger the callback to play the next song
            interaction.guild.voice_client.stop()

            await interaction.followup.send("Skipped the current song.")