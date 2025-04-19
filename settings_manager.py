import os
import json
import sys

def get_settings_dir():
    """Gets the application-specific settings directory within AppData."""
    if sys.platform == 'win32':
        app_data = os.getenv('APPDATA')
    elif sys.platform == 'darwin': # macOS
        app_data = os.path.expanduser('~/Library/Application Support')
    else: # Linux and other Unix-like
        app_data = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))

    if not app_data: # Fallback if environment variable isn't set
         app_data = os.path.expanduser('~')

    settings_dir = os.path.join(app_data, 'NsTut', 'LilyTheThird')
    os.makedirs(settings_dir, exist_ok=True)
    return settings_dir

SETTINGS_FILE = os.path.join(get_settings_dir(), 'settings.json')
DEFAULT_SETTINGS = {
    'tts_provider_enabled': False,
    # Removed 'enable_mongo_memory' as memory is now tool-based
    'selected_provider': 'OpenAI',
    'selected_model': None # Will be populated based on provider
}

def save_settings(settings_dict):
    """Saves the provided settings dictionary to the JSON file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_dict, f, indent=4)
        print(f"Settings saved to {SETTINGS_FILE}")
    except IOError as e:
        print(f"Error saving settings to {SETTINGS_FILE}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving settings: {e}")


def load_settings():
    """Loads settings from the JSON file. Returns defaults if file not found or invalid."""
    if not os.path.exists(SETTINGS_FILE):
        print(f"Settings file not found at {SETTINGS_FILE}. Using defaults.")
        # Ensure default model is set based on default provider
        # (Keep this logic as it's unrelated to memory type)
        if DEFAULT_SETTINGS['selected_provider'] == 'OpenAI':
            from config.models import OPENAI_MODELS
            DEFAULT_SETTINGS['selected_model'] = OPENAI_MODELS[0] if OPENAI_MODELS else None
        elif DEFAULT_SETTINGS['selected_provider'] == 'Gemini':
             from config.models import GEMINI_MODELS
             DEFAULT_SETTINGS['selected_model'] = GEMINI_MODELS[0] if GEMINI_MODELS else None
        # Removed migration logic for enable_kg_memory/enable_mongo_memory
        return DEFAULT_SETTINGS.copy() # Return a copy

    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            print(f"Settings loaded from {SETTINGS_FILE}")

            # Removed migration logic for enable_kg_memory/enable_mongo_memory

            # Validate loaded settings against defaults (add missing keys)
            final_settings = DEFAULT_SETTINGS.copy()
            # Only update with keys that exist in defaults to avoid loading old settings
            for key in DEFAULT_SETTINGS:
                if key in settings:
                    final_settings[key] = settings[key]

            # Ensure 'selected_model' is valid for the loaded 'selected_provider'
            # (Keep this validation logic)
            provider = final_settings.get('selected_provider')
            model = final_settings.get('selected_model')
            valid_models = []
            if provider == 'OpenAI':
                from config.models import OPENAI_MODELS
                valid_models = OPENAI_MODELS
            elif provider == 'Gemini':
                 from config.models import GEMINI_MODELS
                 valid_models = GEMINI_MODELS

            if model not in valid_models:
                 print(f"Warning: Loaded model '{model}' not valid for provider '{provider}'. Resetting to default.")
                 final_settings['selected_model'] = valid_models[0] if valid_models else None
                 # Optionally save the corrected settings back
                 # save_settings(final_settings)

            return final_settings
    # Removed duplicate try-except block for JSONDecodeError
    except json.JSONDecodeError as e:
        print(f"Error decoding settings file {SETTINGS_FILE}: {e}. Using defaults.")
        # Return a fresh copy of potentially corrected defaults
        if DEFAULT_SETTINGS['selected_provider'] == 'OpenAI':
            from config.models import OPENAI_MODELS
            DEFAULT_SETTINGS['selected_model'] = OPENAI_MODELS[0] if OPENAI_MODELS else None
        elif DEFAULT_SETTINGS['selected_provider'] == 'Gemini':
             from config.models import GEMINI_MODELS
             DEFAULT_SETTINGS['selected_model'] = GEMINI_MODELS[0] if GEMINI_MODELS else None
        return DEFAULT_SETTINGS.copy()
    except IOError as e:
        print(f"Error reading settings file {SETTINGS_FILE}: {e}. Using defaults.")
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"An unexpected error occurred while loading settings: {e}. Using defaults.")
        return DEFAULT_SETTINGS.copy()
