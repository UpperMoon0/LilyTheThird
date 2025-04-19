import asyncio
import websockets
import json
import numpy as np
import sounddevice as sd
import io
import wave # For saving/handling WAV data if needed
from translator import translate_to_japanese # Keep translator for now

TTS_PROVIDER_URI = "ws://localhost:9000"

async def generate_speech_from_provider(
    text: str,
    speaker: int = 1, 
    sample_rate: int = 24000,
    model: str = "edge", 
    tts_provider_uri: str = TTS_PROVIDER_URI
):
    """
    Connects to the TTS-Provider WebSocket server, generates speech,
    and plays the audio stream.
    """
    print(f"TTS Request: Text='{text}', Speaker={speaker}, SampleRate={sample_rate}, Model='{model}'")

    # Translate the text to Japanese first
    try:
        translated_text = translate_to_japanese(text)
        print(f"Translated Text for TTS: '{translated_text}'")
    except Exception as e:
        print(f"Translation failed: {e}. Using original text.")
        translated_text = text # Fallback to original text if translation fails

    request_payload = {
        "text": translated_text,
        "speaker": speaker,
        "sample_rate": sample_rate,
        "response_mode": "stream",
        "model": model,
        "lang": "ja-JP" # Added language parameter since text is translated
    }

    audio_buffer = io.BytesIO()
    metadata = {}
    metadata_str = "" # To store the raw metadata string for error reporting

    try:
        async with websockets.connect(
            tts_provider_uri,
            max_size=10*1024*1024, # Match client/server max size
            ping_interval=None # Disable auto-ping if server handles it
        ) as websocket:
            print(f"Connected to TTS Provider at {tts_provider_uri}")
            await websocket.send(json.dumps(request_payload))
            print("Sent TTS request.")

            # --- Receive initial metadata ---
            metadata_str = await websocket.recv()
            if not isinstance(metadata_str, str):
                print("Error: Expected initial metadata (JSON string), received bytes.")
                return
            metadata = json.loads(metadata_str)
            print(f"Received initial response: {metadata}")

            # Handle loading/queued status
            while metadata.get("status") in ["loading", "queued"]:
                queue_pos = metadata.get("queue_position", "N/A")
                print(f"Server status: {metadata.get('status')}. Queue position: {queue_pos}. Waiting...")
                metadata_str = await websocket.recv()
                if not isinstance(metadata_str, str):
                    print("Error: Expected status update (JSON string), received bytes.")
                    return
                metadata = json.loads(metadata_str)
                print(f"Received update: {metadata}")

            # Check for success status after loading/queueing
            if metadata.get("status") != "success":
                print(f"TTS Error from server: {metadata.get('message', 'Unknown error')}")
                return

            print("TTS Processing successful according to metadata. Receiving audio stream...")
            # Store necessary info from metadata before receiving audio
            sr = metadata.get("sample_rate", 24000) # Default if not provided
            channels = metadata.get("channels", 1) # Default if not provided (server doesn't send this yet)
            bit_depth = metadata.get("bit_depth", 16) # Default if not provided (server doesn't send this yet)

            # --- Receive audio stream ---
            while True:
                try:
                    message = await websocket.recv()
                    if isinstance(message, bytes):
                        # print(f"Received audio chunk: {len(message)} bytes") # Optional debug
                        audio_buffer.write(message)
                    elif isinstance(message, str):
                        # Unexpected JSON message during audio stream? Log it.
                        print(f"Warning: Received unexpected JSON during audio stream: {message}")
                    # The loop will break naturally when the server closes the connection
                    # after sending all audio data, or if an error occurs.

                except websockets.exceptions.ConnectionClosedOK:
                    print("Audio stream finished (connection closed by server).")
                    break
                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"Audio stream interrupted (connection closed with error): {e}")
                    # Decide if partial audio is usable or not
                    # For now, we'll try to play what we received
                    break # Exit loop on connection error

            # --- Audio Playback ---
            if audio_buffer.getbuffer().nbytes > 0:
                print(f"Preparing audio for playback (using sr={sr}, channels={channels}, bit_depth={bit_depth})...")
                audio_buffer.seek(0)

                # Determine numpy dtype based on bit depth (already extracted from metadata)
                if bit_depth == 16:
                    dtype = np.int16
                elif bit_depth == 32:
                    dtype = np.int32
                elif bit_depth == 8:
                    dtype = np.uint8 # Or int8 depending on PCM format (uint8 is common)
                else:
                    print(f"Unsupported bit depth: {bit_depth}. Cannot play audio.")
                    return

                # Read raw PCM data into numpy array
                try:
                    pcm_data = np.frombuffer(audio_buffer.read(), dtype=dtype)
                    if channels > 1:
                         # Reshape for multi-channel audio if necessary
                         pcm_data = pcm_data.reshape(-1, channels)

                    print(f"Playing audio: {len(pcm_data)} samples, Sample Rate={sr}, Channels={channels}, Dtype={dtype}")
                    sd.play(pcm_data, samplerate=sr)
                    sd.wait() # Wait for playback to finish
                    print("Audio playback finished.")

                except Exception as e:
                    print(f"Error processing or playing audio: {e}")
                    import traceback
                    traceback.print_exc()

            else:
                print("No audio data received.")

    except websockets.exceptions.ConnectionClosedOK:
        # This might happen if the connection closes before receiving the first metadata
        print("WebSocket connection closed before receiving expected data.")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"WebSocket connection closed with error: {e}")
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from server. Received: {metadata_str}")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the TTS-Provider server running at {tts_provider_uri}?")
    except Exception as e:
        print(f"An unexpected error occurred during TTS processing: {e}")
        import traceback
        traceback.print_exc() # More detailed error for debugging

# Example usage (for testing purposes)
async def main_test():
    await generate_speech_from_provider("こんにちは、これはテストです。", speaker=1)

if __name__ == "__main__":
    # To test this script directly: python tts.py
    # Ensure the TTS-Provider server is running on ws://localhost:9000
    print("Running TTS test...")
    asyncio.run(main_test())
