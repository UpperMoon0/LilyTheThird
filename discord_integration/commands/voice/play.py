import discord
import yt_dlp


class PlayCommand:
    def __init__(self, bot, song_queue):
        self.bot = bot
        self.song_queue = song_queue

        @self.bot.tree.command(name="play", description="Add a YouTube video's audio to the play queue!")
        async def play_command(interaction: discord.Interaction, url: str):
            """Adds audio from a YouTube video to the play queue."""
            # Check if the bot is in a voice channel
            if interaction.guild.voice_client is None:
                await interaction.response.send_message(
                    "I'm not in a voice channel! Use the `/join` command first.", ephemeral=True
                )
                return

            # Acknowledge the interaction
            await interaction.response.defer()

            # Download audio using yt-dlp
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "outtmpl": "downloads/%(title)s.%(ext)s",
                "quiet": True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    file_path = ydl.prepare_filename(info).replace(".webm", ".mp3")

                # Add song to queue
                await self.song_queue.add_song(file_path, info['title'])

                # If the bot isn't playing anything, start playing
                if not self.song_queue.is_playing:
                    await self.song_queue.play_next_song(interaction.guild)

                # Send follow-up message to acknowledge the command and stop the thinking message
                await interaction.followup.send(f"Now playing: {info['title']}")

            except Exception as e:
                await interaction.followup.send(
                    f"An error occurred while processing the video: {str(e)}", ephemeral=True
                )

