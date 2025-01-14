from deep_translator import GoogleTranslator

def translate_to_japanese(english_text: str) -> str:
    try:
        translator = GoogleTranslator(source='en', target='ja')
        return translator.translate(english_text)
    except Exception as e:
        raise Exception(f"Translation failed: {str(e)}")