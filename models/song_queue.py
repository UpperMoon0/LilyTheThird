import asyncio
import discord
import os


class SongQueue:
    def __init__(self, bot):
        self.bot = bot
        self.queue = []  # Holds songs in the queue
        self.is_playing = False  # Indicates if a song is currently playing
        self.volume = 0.5  # Default volume (0.0 to 1.0)

    async def add_song(self, file_path, title):
        """Adds a song to the queue and sends a message to the channel."""
        self.queue.append((file_path, title))
        channel = self.bot.bot.get_channel(int(self.bot.get_channel_id()))
        if channel:
            await channel.send(f"Added to queue: {title}")
        else:
            print(f"Channel with ID {self.bot.get_channel_id()} not found.")

    async def play_next_song(self, guild):
        """Plays the next song in the queue with improved audio settings."""
        if not self.queue:
            self.is_playing = False
            return  # No more songs to play

        # Get the next song from the queue
        file_path, title = self.queue.pop(0)

        # Ensure file exists and path is correct
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            self.is_playing = False
            return

        print(f"Playing file: {file_path}")

        # Get the voice client
        vc = guild.voice_client
        if vc and not vc.is_playing():
            # Simplified FFmpeg options that work on most systems
            ffmpeg_options = {
                'options': '-vn -b:a 192k'
            }

            try:
                self.is_playing = True

                # Create audio source with proper file path
                audio_source = discord.FFmpegPCMAudio(
                    source=file_path,
                    **ffmpeg_options
                )

                # Use PCMVolumeTransformer for better volume control
                volume_controlled = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

                # Play the audio with proper callback
                vc.play(
                    volume_controlled,
                    after=lambda e: self._play_next_song_callback(e, guild)
                )

                # Send now playing message
                channel = self.bot.bot.get_channel(int(self.bot.get_channel_id()))
                if channel:
                    await channel.send(f"Now playing: {title}")
                else:
                    print(f"Channel with ID {self.bot.get_channel_id()} not found.")

            except Exception as e:
                print(f"Error playing audio: {e}")
                self.is_playing = False
                # Try to play next song if this one fails
                await self.play_next_song(guild)

    def _play_next_song_callback(self, error, guild):
        """Safe callback handler for when a song finishes."""
        if error:
            print(f"Error in playback: {error}")

        # Schedule the next song using the bot's event loop
        if self.bot.bot and hasattr(self.bot.bot, 'loop') and self.bot.bot.loop:
            coro = self.play_next_song(guild)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.bot.loop)
            try:
                fut.result(timeout=60)  # 60 second timeout
            except asyncio.TimeoutError:
                print("Timeout waiting for next song to start")
            except Exception as e:
                print(f"Error scheduling next song: {e}")

    async def song_finished(self, guild):
        """Legacy callback method, kept for compatibility."""
        await self.play_next_song(guild)

    def set_volume(self, volume):
        """Sets the volume of the audio player (0.0 to 1.0)."""
        if 0.0 <= volume <= 1.0:
            self.volume = volume
            # If currently playing, adjust the volume
            for vc in self.bot.bot.voice_clients:
                if vc.is_playing() and isinstance(vc.source, discord.PCMVolumeTransformer):
                    vc.source.volume = volume