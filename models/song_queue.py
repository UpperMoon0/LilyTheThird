import asyncio

import discord


class SongQueue:
    def __init__(self, bot):
        self.bot = bot
        self.queue = []  # Holds songs in the queue
        self.is_playing = False  # Indicates if a song is currently playing

    async def add_song(self, file_path, title):
        """Adds a song to the queue and sends a message to the channel."""
        self.queue.append((file_path, title))
        channel = self.bot.bot.get_channel(int(self.bot.get_channel_id()))  # Correct usage of get_channel
        if channel:
            await channel.send(f"Added to queue: {title}")  # Send message to the correct channel
        else:
            print(f"Channel with ID {self.bot.get_channel_id()} not found.")

    async def play_next_song(self, guild):
        """Plays the next song in the queue."""
        if not self.queue:
            self.is_playing = False
            return  # No more songs to play

        # Get the next song from the queue
        file_path, title = self.queue.pop(0)

        # Get the voice client
        vc = guild.voice_client
        if vc and not vc.is_playing():
            self.is_playing = True
            vc.play(
                discord.FFmpegPCMAudio(executable="ffmpeg", source=file_path),
                after=lambda _: asyncio.run_coroutine_threadsafe(self.song_finished(guild), self.bot.bot.loop),
            )
            channel = self.bot.bot.get_channel(int(self.bot.get_channel_id()))
            if channel:
                await channel.send(f"Now playing: {title}")
            else:
                print(f"Channel with ID {self.bot.get_channel_id()} not found.")

    async def song_finished(self, guild):
        """Callback when a song finishes."""
        asyncio.run_coroutine_threadsafe(self.play_next_song(guild), self.bot.loop)

