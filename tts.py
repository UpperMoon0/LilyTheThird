import asyncio
import edge_tts
import pygame
import os
import time

from translator import translate_to_japanese


def wait_for_file_availability(file_path, timeout=5):
    """
    Wait for the audio file to become available to ensure no other process is using it.
    :param file_path: The path to the audio file
    :param timeout: How long to wait before giving up (in seconds)
    :return: True if the file is available, False if it couldn't be accessed within the timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not os.path.exists(file_path):
            return True
        try:
            with open(file_path, 'r'):
                return True
        except IOError:
            time.sleep(0.1)
    return False


async def text_to_speech_and_play(text, voice="ja-JP-NanamiNeural", pitch="+15Hz"):
    """
    Convert text to speech with pitch adjustment using edge-tts and play the audio.
    :param text: Text to synthesize
    :param voice: TTS voice to use
    :param pitch: Pitch adjustment (e.g., "+50Hz", "-50Hz")
    """
    # Translate the text
    translated_text = translate_to_japanese(text)

    # Create a unique filename for each audio file
    output_file = f"outputs/audio_{int(time.time())}.mp3"

    # Wait until the file is available (if another process is using it)
    if not wait_for_file_availability(output_file):
        print("Unable to access the file. Please try again.")
        return

    # Create communicate object with pitch adjustment
    tts = edge_tts.Communicate(
        text=translated_text,
        voice=voice,
        pitch=pitch
    )

    # Save the generated speech to the outputs file
    await tts.save(output_file)
    print(f"Audio saved to {output_file}")

    # Initialize pygame mixer
    pygame.mixer.init()
    pygame.mixer.music.load(output_file)
    pygame.mixer.music.play()

    # Wait until the audio has finished playing
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)

    print("Audio played.")