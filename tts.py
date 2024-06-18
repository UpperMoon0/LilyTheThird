# tts.py
import os
import azure.cognitiveservices.speech as speechsdk

from dotenv import load_dotenv

load_dotenv()

# Set up Azure TTS
tts_key = os.getenv('TTS_KEY')
a_region = os.getenv('REGION')
speech_config = speechsdk.SpeechConfig(subscription=tts_key, region=a_region)
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)


def synthesize_speech(response):
    ssml_string = f"""
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">
        <voice name="fr-FR-VivienneMultilingualNeural">
            <prosody pitch="+25%">
                {response}
            </prosody>
        </voice>
    </speak>
    """
    try:
        result = speech_synthesizer.speak_ssml_async(ssml_string).get()

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print("Speech synthesis canceled: {}".format(cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error and cancellation_details.error_details:
                print("Error details: {}".format(cancellation_details.error_details))
    except Exception as e:
        print(f"An error occurred during speech synthesis: {e}")