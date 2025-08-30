import asyncio
import websockets
import json
import numpy as np
import sounddevice as sd
import io
import uuid
import threading
from translator import translate_to_japanese  # Keep translator for now
from settings_manager import load_chat_settings

LILY_CORE_URI = "ws://localhost:8000/ws/tts"

class LilyCoreWebSocketClient:
    """WebSocket client for communicating with Lily-Core TTS service."""

    def __init__(self, client_id: str = None):
        """Initialize WebSocket client for Lily-Core."""
        self.client_id = client_id if client_id else str(uuid.uuid4())
        self.websocket = None
        self.is_connected = False
        self.audio_buffer = io.BytesIO()
        self.current_settings = None
        self.audio_metadata = {}
        self.logger_prefix = f"[LilyCoreTTS-{self.client_id[:8]}]"

        # Thread synchronization
        self._connection_lock = asyncio.Lock()
        self._shutdown_event = threading.Event()

        print(f"{self.logger_prefix} Initialized client with ID: {self.client_id}")

    async def _connect(self) -> bool:
        """Establish WebSocket connection to Lily-Core."""
        async with self._connection_lock:
            if self.is_connected:
                return True

            try:
                uri = f"{LILY_CORE_URI}/{self.client_id}"
                print(f"{self.logger_prefix} Connecting to Lily-Core at {uri}")

                self.websocket = await websockets.connect(
                    uri,
                    max_size=10*1024*1024,  # Match server max size
                    ping_interval=30,  # Keep connection alive
                    close_timeout=5
                )

                self.is_connected = True
                print(f"{self.logger_prefix} ✅ Connected to Lily-Core successfully")

                # Send current TTS settings if available
                await self._send_settings_on_connect()

                return True

            except Exception as e:
                print(f"{self.logger_prefix} ❌ Failed to connect: {e}")
                self.is_connected = False
                self.websocket = None
                return False

    async def _send_settings_on_connect(self):
        """Send TTS settings to Lily-Core on connection."""
        try:
            settings = load_chat_settings()
            settings_payload = {
                "speaker": settings.get('selected_tts_speaker', 1),
                "sample_rate": 24000,  # Use default, can be made configurable
                "model": settings.get('selected_tts_model', 'edge'),
                "lang": "ja-JP"  # Translated text is Japanese
            }

            message = {
                "type": "settings.update",
                "payload": settings_payload
            }

            if self.websocket:
                await self.websocket.send(json.dumps(message))
                print(f"{self.logger_prefix} Sent settings to Lily-Core: {settings_payload}")

            self.current_settings = settings_payload

        except Exception as e:
            print(f"{self.logger_prefix} Error sending settings: {e}")

    async def _reconnect_with_backoff(self) -> bool:
        """Attempt reconnection with exponential backoff."""
        backoff_times = [1, 2, 4, 8, 16]  # Max ~30 seconds wait

        for attempt, delay in enumerate(backoff_times, 1):
            print(f"{self.logger_prefix} Reconnection attempt {attempt}/5 in {delay}s...")

            await asyncio.sleep(delay)
            if await self._connect():
                print(f"{self.logger_prefix} ✅ Reconnected successfully")
                return True

            if self._shutdown_event.is_set():
                break

        print(f"{self.logger_prefix} ❌ Failed to reconnect after {len(backoff_times)} attempts")
        return False

    async def _handle_message_loop(self):
        """Handle incoming messages from Lily-Core WebSocket."""
        while not self._shutdown_event.is_set() and self.websocket:
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=30.0  # Timeout to check for shutdown
                )

                if isinstance(message, str):
                    # JSON message
                    await self._handle_json_message(message)
                elif isinstance(message, bytes):
                    # Binary audio data
                    await self._handle_audio_chunk(message)
                else:
                    print(f"{self.logger_prefix} Received unexpected message type: {type(message)}")

            except asyncio.TimeoutError:
                # Keep-alive check
                continue
            except websockets.exceptions.ConnectionClosedOK:
                print(f"{self.logger_prefix} WebSocket connection closed normally")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                print(f"{self.logger_prefix} WebSocket connection closed with error: {e}")
                # Attempt reconnection
                if await self._reconnect_with_backoff():
                    continue
                break
            except Exception as e:
                print(f"{self.logger_prefix} Error handling message: {e}")
                break

        print(f"{self.logger_prefix} Message handling loop ended")

    async def _handle_json_message(self, message_str: str):
        """Handle JSON WebSocket message."""
        try:
            message = json.loads(message_str)
            msg_type = message.get('type')

            if msg_type == 'tts.response':
                await self._handle_tts_response(message)
            elif msg_type == 'audio.stream.end':
                await self._handle_stream_end()
            elif msg_type == 'error':
                await self._handle_error(message)
            else:
                print(f"{self.logger_prefix} Received unhandled message type: {msg_type}")

        except json.JSONDecodeError as e:
            print(f"{self.logger_prefix} Invalid JSON message: {message_str[:100]}... Error: {e}")

    async def _handle_tts_response(self, message: dict):
        """Handle TTS response message."""
        payload = message.get('payload', {})
        status = payload.get('status')

        print(f"{self.logger_prefix} TTS Response - Status: {status}")

        if status == 'success':
            # Store audio metadata for playback
            self.audio_metadata = {
                'sample_rate': payload.get('sample_rate', 24000),
                'channels': payload.get('channels', 1),
                'bit_depth': payload.get('bit_depth', 16)
            }

        elif status == 'error':
            error_msg = payload.get('message', 'Unknown error')
            print(f"{self.logger_prefix} TTS Error: {error_msg}")

    async def _handle_audio_chunk(self, audio_data: bytes):
        """Handle binary audio chunk."""
        print(f"{self.logger_prefix} Received audio chunk: {len(audio_data)} bytes")
        self.audio_buffer.write(audio_data)

    async def _handle_stream_end(self):
        """Handle audio stream termination."""
        print(f"{self.logger_prefix} Audio stream ended")

        # Process and play the collected audio
        if self.audio_buffer.getbuffer().nbytes > 0:
            await self._play_collected_audio()

        # Reset for next request
        self.audio_buffer = io.BytesIO()

    async def _handle_error(self, message: dict):
        """Handle error message from Lily-Core."""
        payload = message.get('payload', {})
        error_code = payload.get('code', 'UNKNOWN')
        error_msg = payload.get('message', 'Unknown error')

        print(f"{self.logger_prefix} Error from Lily-Core: [{error_code}] {error_msg}")

    async def _play_collected_audio(self):
        """Play the collected audio buffer."""
        try:
            audio_buffer = self.audio_buffer
            audio_buffer.seek(0)

            # Get metadata
            sr = self.audio_metadata.get('sample_rate', 24000)
            channels = self.audio_metadata.get('channels', 1)
            bit_depth = self.audio_metadata.get('bit_depth', 16)

            print(f"{self.logger_prefix} Playing audio: {audio_buffer.getbuffer().nbytes} bytes, "
                  f"SR={sr}, Channels={channels}, BitDepth={bit_depth}")

            # Determine numpy dtype based on bit depth
            if bit_depth == 16:
                dtype = np.int16
            elif bit_depth == 32:
                dtype = np.int32
            elif bit_depth == 8:
                dtype = np.uint8
            else:
                print(f"{self.logger_prefix} Unsupported bit depth: {bit_depth}")
                return

            # Read raw PCM data into numpy array
            pcm_data = np.frombuffer(audio_buffer.read(), dtype=dtype)

            if channels > 1:
                pcm_data = pcm_data.reshape(-1, channels)

            print(f"{self.logger_prefix} Playing {len(pcm_data)} samples...")
            sd.play(pcm_data, samplerate=sr)
            sd.wait()  # Wait for playback to finish
            print(f"{self.logger_prefix} Audio playback completed")

        except Exception as e:
            print(f"{self.logger_prefix} Error playing audio: {e}")
            import traceback
            traceback.print_exc()

    async def request_tts(self, text: str, speaker: int = None, model: str = None) -> bool:
        """
        Send TTS request to Lily-Core and handle the response.

        Args:
            text: Text to convert to speech
            speaker: Speaker ID (optional, uses current settings if None)
            model: TTS model to use (optional, uses current settings if None)

        Returns:
            True if request was sent successfully
        """
        if not self.is_connected and not await self._connect():
            print(f"{self.logger_prefix} Cannot send TTS request - not connected to Lily-Core")
            return False

        try:
            # Translate text to Japanese
            translated_text = text
            try:
                translated_text = translate_to_japanese(text)
                print(f"{self.logger_prefix} Translated '{text}' to '{translated_text}'")
            except Exception as e:
                print(f"{self.logger_prefix} Translation failed, using original: {e}")

            # Send TTS request
            message = {
                "type": "tts.request",
                "payload": {
                    "text": translated_text
                }
            }

            await self.websocket.send(json.dumps(message))
            print(f"{self.logger_prefix} Sent TTS request for: {translated_text[:50]}...")

            return True

        except websockets.exceptions.ConnectionClosed:
            print(f"{self.logger_prefix} Connection lost during TTS request")
            # Attempt reconnection
            if await self._reconnect_with_backoff():
                # Retry the request
                return await self.request_tts(text, speaker, model)
            return False

        except Exception as e:
            print(f"{self.logger_prefix} Error sending TTS request: {e}")
            return False

    async def update_settings(self, speaker: int = None, model: str = None):
        """Update TTS settings on Lily-Core."""
        if not self.is_connected and not await self._connect():
            print(f"{self.logger_prefix} Cannot update settings - not connected")
            return

        try:
            # Get current settings and merge updates
            settings = load_chat_settings()

            # Update settings with provided values or use current
            if speaker is not None:
                settings['selected_tts_speaker'] = speaker
            if model is not None:
                settings['selected_tts_model'] = model

            settings_payload = {
                "speaker": settings.get('selected_tts_speaker', 1),
                "sample_rate": 24000,
                "model": settings.get('selected_tts_model', 'edge'),
                "lang": "ja-JP"
            }

            message = {
                "type": "settings.update",
                "payload": settings_payload
            }

            await self.websocket.send(json.dumps(message))
            print(f"{self.logger_prefix} Updated settings: {settings_payload}")

            self.current_settings = settings_payload

        except Exception as e:
            print(f"{self.logger_prefix} Error updating settings: {e}")

    async def start_message_loop(self):
        """Start the message handling loop in background."""
        await self._handle_message_loop()

    async def close(self):
        """Close WebSocket connection and cleanup."""
        print(f"{self.logger_prefix} Closing WebSocket client...")

        self._shutdown_event.set()

        async with self._connection_lock:
            if self.websocket:
                try:
                    await self.websocket.close()
                    print(f"{self.logger_prefix} WebSocket closed")
                except Exception as e:
                    print(f"{self.logger_prefix} Error closing WebSocket: {e}")

            self.is_connected = False
            self.websocket = None


# Global client instance
_global_client = None
_client_lock = threading.Lock()

def get_lily_core_tts_client() -> LilyCoreWebSocketClient:
    """Get or create the global LilyCore TTS client instance."""
    global _global_client

    with _client_lock:
        if _global_client is None:
            _global_client = LilyCoreWebSocketClient()

        return _global_client

async def generate_speech_from_lily_core(text: str, speaker: int = 1, model: str = "edge") -> bool:
    """
    Generate speech using Lily-Core WebSocket client.

    Args:
        text: Text to convert to speech
        speaker: Speaker ID
        model: TTS model to use

    Returns:
        True if TTS request was sent successfully
    """
    client = get_lily_core_tts_client()
    return await client.request_tts(text, speaker, model)

# Legacy compatibility function - maps to new WebSocket implementation
async def generate_speech_from_provider(
    text: str,
    speaker: int = 1,
    sample_rate: int = 24000,
    model: str = "edge",
    tts_provider_uri: str = None  # Ignored, kept for compatibility
):
    """
    Legacy function that now uses Lily-Core WebSocket instead of direct provider connection.
    This function maintains the same interface for backward compatibility.
    """
    # Log that we're using the new implementation
    print(f"TTS: Using new Lily-Core WebSocket implementation instead of direct provider")

    # Use the new WebSocket client
    success = await generate_speech_from_lily_core(text, speaker, model)

    return success

# Example usage and testing functions
async def test_lily_core_connection():
    """Test function to verify Lily-Core WebSocket connection."""
    client = get_lily_core_tts_client()

    print("Testing Lily-Core connection...")

    # Test connection
    if await client._connect():
        print("✅ Connection successful")

        # Test TTS request
        success = await client.request_tts("こんにちは、テストです。")
        if success:
            print("✅ TTS request sent successfully")
        else:
            print("❌ TTS request failed")
    else:
        print("❌ Connection failed")

    # Close connection
    await client.close()

if __name__ == "__main__":
    print("Lily-Core TTS WebSocket Test")
    print("Ensure Lily-Core server is running at ws://localhost:8000")
    asyncio.run(test_lily_core_connection())