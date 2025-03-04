import discord


class ClearQueueCommand:
    def __init__(self, bot, song_queue):
        self.bot = bot
        self.song_queue = song_queue

        @self.bot.tree.command(name="clear", description="Clear the song queue")
        async def clear_command(interaction: discord.Interaction):
            """Clears all songs from the queue except the currently playing one."""
            # Check if the bot is in a voice channel
            if interaction.guild.voice_client is None:
                await interaction.response.send_message(
                    "I'm not in a voice channel! Use the `/join` command first.", ephemeral=True
                )
                return

            # Clear the queue
            queue_size = len(self.song_queue.queue)
            self.song_queue.queue.clear()

            # Respond based on whether anything was cleared
            if queue_size > 0:
                await interaction.response.send_message(f"Cleared {queue_size} songs from the queue.")
            else:
                await interaction.response.send_message("The queue is already empty.")