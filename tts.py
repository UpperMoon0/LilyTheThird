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
    speaker: int = 0,
    sample_rate: int = 24000,
    model: str = "edge", # Default to edge as per example
    tts_provider_uri: str = TTS_PROVIDER_URI
):
    """
    Connects to the TTS-Provider WebSocket server, generates speech,
    and plays the audio stream.
    """
    print(f"TTS Request: Text='{text}', Speaker={speaker}, SampleRate={sample_rate}, Model='{model}'")

    # Translate the text first (optional, based on previous logic)
    try:
        translated_text = translate_to_japanese(text)
        print(f"Translated Text: '{translated_text}'")
    except Exception as e:
        print(f"Translation failed: {e}. Using original text.")
        translated_text = text # Fallback to original text if translation fails

    request_payload = {
        "text": translated_text,
        "speaker": speaker,
        "sample_rate": sample_rate,
        "response_mode": "stream",
        "model": model
    }

    audio_buffer = io.BytesIO()
    metadata = {}

    try:
        async with websockets.connect(tts_provider_uri) as websocket:
            print(f"Connected to TTS Provider at {tts_provider_uri}")
            await websocket.send(json.dumps(request_payload))
            print("Sent TTS request.")

            while True:
                message = await websocket.recv()

                if isinstance(message, str):
                    # JSON message (metadata or status)
                    data = json.loads(message)
                    print(f"Received JSON: {data}")
                    if data.get("status") == "processing":
                        metadata = data # Store metadata
                        print("TTS Processing started...")
                    elif data.get("status") == "complete":
                        print("TTS Stream complete.")
                        break # Exit loop on completion
                    elif data.get("status") == "error":
                        print(f"TTS Error from server: {data.get('message', 'Unknown error')}")
                        return # Exit on error
                    else:
                        # Could be initial metadata without status=processing
                        metadata.update(data)

                elif isinstance(message, bytes):
                    # Binary audio chunk
                    # print(f"Received audio chunk: {len(message)} bytes")
                    audio_buffer.write(message)

            # --- Audio Playback ---
            if audio_buffer.getbuffer().nbytes > 0 and metadata:
                print("Preparing audio for playback...")
                audio_buffer.seek(0)
                sr = metadata.get("sample_rate", 24000) # Default if not provided
                channels = metadata.get("channels", 1)
                bit_depth = metadata.get("bit_depth", 16)

                # Determine numpy dtype based on bit depth
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

            else:
                print("No audio data received or metadata missing.")

    except websockets.exceptions.ConnectionClosedOK:
        print("WebSocket connection closed normally.")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"WebSocket connection closed with error: {e}")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the TTS-Provider server running at {tts_provider_uri}?")
    except Exception as e:
        print(f"An unexpected error occurred during TTS processing: {e}")

# Example usage (for testing purposes)
async def main_test():
    await generate_speech_from_provider("こんにちは、これはテストです。", speaker=1)

if __name__ == "__main__":
    # To test this script directly: python tts.py
    # Ensure the TTS-Provider server is running on ws://localhost:9000
    print("Running TTS test...")
    asyncio.run(main_test())
