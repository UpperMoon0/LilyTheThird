import os
import json
import sys
# Import model lists
from config.models import OPENAI_MODELS, GEMINI_MODELS

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
# Define default models based on default providers
DEFAULT_OPENAI_MODEL = OPENAI_MODELS[0] if OPENAI_MODELS else None
DEFAULT_GEMINI_MODEL = GEMINI_MODELS[0] if GEMINI_MODELS else None

DEFAULT_SETTINGS = {
    # Chat Tab Settings
    'tts_provider_enabled': False,
    'selected_provider': 'OpenAI',
    'selected_model': DEFAULT_OPENAI_MODEL, # Use default OpenAI model
    'temperature': 0.7, # Default temperature for Chat Tab
    # Discord Tab Settings
    'discord_guild_id': '', # Default Guild ID
    'discord_channel_id': '', # Default Channel ID
    'discord_selected_provider': 'OpenAI', # Default Discord provider
    'discord_selected_model': DEFAULT_OPENAI_MODEL # Default Discord model
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
    # Initialize defaults dynamically based on provider
    def initialize_defaults(defaults):
        from config.models import OPENAI_MODELS, GEMINI_MODELS
        if defaults['selected_provider'] == 'OpenAI':
            defaults['selected_model'] = OPENAI_MODELS[0] if OPENAI_MODELS else None
        elif defaults['selected_provider'] == 'Gemini':
            defaults['selected_model'] = GEMINI_MODELS[0] if GEMINI_MODELS else None

        if defaults['discord_selected_provider'] == 'OpenAI':
            defaults['discord_selected_model'] = OPENAI_MODELS[0] if OPENAI_MODELS else None
        elif defaults['discord_selected_provider'] == 'Gemini':
            defaults['discord_selected_model'] = GEMINI_MODELS[0] if GEMINI_MODELS else None
        return defaults

    if not os.path.exists(SETTINGS_FILE):
        print(f"Settings file not found at {SETTINGS_FILE}. Using defaults.")
        # Initialize and return a copy of potentially modified defaults
        return initialize_defaults(DEFAULT_SETTINGS.copy())

    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            print(f"Settings loaded from {SETTINGS_FILE}")

            # Validate loaded settings against defaults (add missing keys)
            final_settings = DEFAULT_SETTINGS.copy()
            # Only update with keys that exist in defaults to avoid loading old settings
            for key in DEFAULT_SETTINGS:
                if key in settings:
                    final_settings[key] = settings[key]

            # --- Model Validation Logic ---
            def validate_model(settings, provider_key, model_key):
                from config.models import OPENAI_MODELS, GEMINI_MODELS
                provider = settings.get(provider_key)
                model = settings.get(model_key)
                valid_models = []
                default_model = None

                if provider == 'OpenAI':
                    valid_models = OPENAI_MODELS
                    default_model = valid_models[0] if valid_models else None
                elif provider == 'Gemini':
                    valid_models = GEMINI_MODELS
                    default_model = valid_models[0] if valid_models else None
                else: # Handle case where provider might be missing or invalid
                    print(f"Warning: Invalid or missing provider '{provider}' for key '{provider_key}'. Cannot validate model.")
                    return # Cannot validate without a valid provider

                if model not in valid_models:
                    print(f"Warning: Loaded model '{model}' (key: {model_key}) not valid for provider '{provider}' (key: {provider_key}). Resetting to default '{default_model}'.")
                    settings[model_key] = default_model
                    # Optionally save the corrected settings back immediately
                    # save_settings(settings) # Be careful about potential loops if save fails

            # Validate models for both chat and discord settings
            validate_model(final_settings, 'selected_provider', 'selected_model')
            validate_model(final_settings, 'discord_selected_provider', 'discord_selected_model')

            return final_settings
    except json.JSONDecodeError as e:
        print(f"Error decoding settings file {SETTINGS_FILE}: {e}. Using defaults.")
        # Initialize and return a copy of potentially modified defaults
        return initialize_defaults(DEFAULT_SETTINGS.copy())
    except IOError as e:
        print(f"Error reading settings file {SETTINGS_FILE}: {e}. Using defaults.")
        return initialize_defaults(DEFAULT_SETTINGS.copy())
    except Exception as e:
        print(f"An unexpected error occurred while loading settings: {e}. Using defaults.")
        return initialize_defaults(DEFAULT_SETTINGS.copy())
