import re

import discord
import yt_dlp


def _is_valid_url(url):
    """Check if the provided string is a valid URL."""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+$'
    return re.match(youtube_regex, url) is not None


class PlayCommand:
    def __init__(self, bot, song_queue):
        self.bot = bot
        self.song_queue = song_queue
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:96.0) Gecko/20100101 Firefox/96.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
        ]

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

            # Validate URL format
            if not _is_valid_url(url):
                await interaction.followup.send(
                    "Invalid URL. Please provide a valid YouTube URL.", ephemeral=True
                )
                return

            # Use the alternative extractor method
            success = await self.download(interaction, url)

            if not success:
                await interaction.followup.send(
                    "Download failed. This video might be heavily restricted or unavailable.",
                    ephemeral=True
                )

    async def download(self, interaction, url):
        try:
            ydl_opts = self._get_base_ydl_opts()
            # Use settings from the alternative extractor method
            ydl_opts["extractor_args"]["youtube"] = {"skip": ["dash", "hls"]}
            ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info:
                    info = info['entries'][0]

                file_path = ydl.prepare_filename(info)
                file_path = self._fix_file_extension(file_path)

            # Add song to queue
            await self.song_queue.add_song(file_path, info['title'])

            # If the bot isn't playing anything, start playing
            if not self.song_queue.is_playing:
                await self.song_queue.play_next_song(interaction.guild)

            print(f"✅ SUCCESS: alternative_extractor method worked for URL: {url}")
            await interaction.followup.send(f"Added to queue: {info['title']}")
            return True

        except Exception as e:
            print(f"Alternative extractor method failed: {str(e)}")
            return False

    def _get_base_ydl_opts(self):
        """Get the base yt-dlp options"""
        return {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "outtmpl": "downloads/%(title)s.%(ext)s",
            "quiet": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Referer": "https://www.youtube.com/"
            },
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "socket_timeout": 15,
            "extractor_args": {
                "youtube": {
                    "nocheckcertificate": True,
                    "player_client": ["android", "web"],
                }
            },
            "force_ipv4": True,
            "nocheckcertificate": True,
            "noplaylist": False,
            "ignoreerrors": True,
            "logtostderr": False,
            "no_warnings": True,
            "default_search": "auto",
            "source_address": "0.0.0.0",
            "update": True
        }

    def _fix_file_extension(self, file_path):
        """Fix the file extension for processed audio files"""
        if file_path.endswith('.webm'):
            file_path = file_path.replace('.webm', '.mp3')
        elif file_path.endswith('.m4a'):
            file_path = file_path.replace('.m4a', '.mp3')
        elif not file_path.endswith('.mp3'):
            file_path = file_path.rsplit('.', 1)[0] + '.mp3'
        return file_path