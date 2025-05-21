import os
import json
import sys
from utils.file_utils import get_nstut_lilythethird_app_data_dir

# --- Directory Setup ---
def _get_specific_settings_dir(subfolder_name):
    """
    Gets the path to a specific settings subfolder (e.g., 'chat', 'discord')
    within the main 'NsTut/LilyTheThird' app data directory.
    Ensures the subfolder exists.
    """
    base_app_data_dir = get_nstut_lilythethird_app_data_dir()
    specific_dir = os.path.join(base_app_data_dir, subfolder_name)
    try:
        os.makedirs(specific_dir, exist_ok=True)
    except OSError as e:
        print(f"Error creating settings sub-directory {specific_dir}: {e}")
        # Depending on how critical this is, might raise an exception or return None
    return specific_dir

def get_chat_settings_dir():
    """Gets the 'chat' settings directory."""
    return _get_specific_settings_dir('chat')

def get_discord_settings_dir():
    """Gets the 'discord' settings directory."""
    return _get_specific_settings_dir('discord')

CHAT_SETTINGS_FILE = os.path.join(get_chat_settings_dir(), 'settings.json')
DISCORD_SETTINGS_FILE = os.path.join(get_discord_settings_dir(), 'settings.json')

# --- Default Model Definitions ---
DEFAULT_OPENAI_MODEL = None # Set to None as we will fetch from API
DEFAULT_GEMINI_MODEL = None # Set to None as we will fetch from API

# --- Default Settings Definitions ---
DEFAULT_CHAT_SETTINGS = {
    'tts_provider_enabled': False,
    'selected_tts_model': 'edge', # Default TTS model
    'selected_tts_speaker': 1, # Default TTS speaker ID
    'selected_provider': 'OpenAI', # Default provider for Chat Tab
    'selected_model': DEFAULT_OPENAI_MODEL,
    'temperature': 0.7,
}

DEFAULT_DISCORD_SETTINGS = {
    'discord_token': '',
    'guild_id': '',
    'channel_id': '',
    'master_discord_id': '',
    'lily_discord_id': '',
    'manual_send_channel_id': '', # Added for manual message sending
    'selected_provider': 'OpenAI', # Default provider for Discord Tab
    'selected_model': DEFAULT_OPENAI_MODEL,
    # Temperature for Discord could be added here if needed, e.g., 'temperature': 0.7
}

# --- Helper Functions (Internal) ---
def _initialize_defaults_for_provider(defaults_dict, provider_key='selected_provider', model_key='selected_model'):
    """
    Initializes the default model in a settings dictionary based on the provider.
    Modifies the input dictionary directly.
    """
    provider = defaults_dict.get(provider_key)
    if provider == 'OpenAI':
        defaults_dict[model_key] = None # Set to None
    elif provider == 'Gemini':
        defaults_dict[model_key] = None # Set to None
    # Add other providers here if necessary
    return defaults_dict

def _validate_model_for_provider(settings_dict, provider_key='selected_provider', model_key='selected_model'):
    """
    Validates the model in the settings_dict for the given provider.
    Resets to default if invalid. Modifies the input dictionary.
    """
    provider = settings_dict.get(provider_key)
    model = settings_dict.get(model_key)
    default_model_for_provider = None

    print(f"Skipping model validation against predefined lists for provider '{provider}' and model '{model}'.")

def _save_settings_to_file(settings_dict, file_path, settings_type_name="settings"):
    """Generic function to save a settings dictionary to a specified file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(settings_dict, f, indent=4)
        print(f"{settings_type_name.capitalize()} saved to {file_path}")
    except IOError as e:
        print(f"Error saving {settings_type_name} to {file_path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving {settings_type_name}: {e}")

def _load_settings_from_file(file_path, default_settings_template, settings_type_name="settings"):
    """Generic function to load settings from a file, falling back to defaults."""
    
    # Create a fresh copy of defaults, then initialize provider-specific models
    current_defaults = default_settings_template.copy()
    _initialize_defaults_for_provider(current_defaults) # Initializes based on default provider in template

    if not os.path.exists(file_path):
        print(f"{settings_type_name.capitalize()} file not found at {file_path}. Using defaults.")
        return current_defaults

    try:
        with open(file_path, 'r') as f:
            loaded_settings_from_file = json.load(f)
        print(f"{settings_type_name.capitalize()} loaded from {file_path}")

        # Start with a fresh copy of defaults for merging
        final_settings = current_defaults.copy()

        # Update with values from file, only for keys present in the default template
        for key in default_settings_template: # Iterate over template keys
            if key in loaded_settings_from_file:
                final_settings[key] = loaded_settings_from_file[key]
            # If a key from defaults is NOT in the loaded file, it keeps its default value from current_defaults

        # Crucially, validate the model based on the *loaded* provider.
        # The _validate_model_for_provider function will reset to default if the loaded model is invalid.
        _validate_model_for_provider(final_settings) # Validates the potentially loaded model

        return final_settings
        
    except json.JSONDecodeError as e:
        print(f"Error decoding {settings_type_name} file {file_path}: {e}. Using defaults.")
        return current_defaults # Return initialized defaults
    except IOError as e:
        print(f"Error reading {settings_type_name} file {file_path}: {e}. Using defaults.")
        return current_defaults
    except Exception as e:
        print(f"An unexpected error occurred while loading {settings_type_name}: {e}. Using defaults.")
        return current_defaults

# --- Public API for Chat Settings ---
def save_chat_settings(settings_dict):
    """Saves the Chat Tab settings."""
    _save_settings_to_file(settings_dict, CHAT_SETTINGS_FILE, "chat settings")

def load_chat_settings():
    """Loads the Chat Tab settings."""
    return _load_settings_from_file(CHAT_SETTINGS_FILE, DEFAULT_CHAT_SETTINGS, "chat settings")

# --- Public API for Discord Settings ---
def save_discord_settings(settings_dict):
    """Saves the Discord Tab settings."""
    _save_settings_to_file(settings_dict, DISCORD_SETTINGS_FILE, "discord settings")

def load_discord_settings():
    """Loads the Discord Tab settings."""
    return _load_settings_from_file(DISCORD_SETTINGS_FILE, DEFAULT_DISCORD_SETTINGS, "discord settings")

if __name__ == '__main__':
    print("Testing settings manager...")

    # Test Chat Settings
    print("\n--- Chat Settings Test ---")
    chat_settings = load_chat_settings()
    print(f"Initial loaded chat settings: {chat_settings}")
    chat_settings['temperature'] = 0.99
    chat_settings['selected_provider'] = 'Gemini' # Change provider
    # The model should auto-adjust if Gemini models are available
    save_chat_settings(chat_settings)
    reloaded_chat_settings = load_chat_settings()
    print(f"Reloaded chat settings: {reloaded_chat_settings}")
    # Test with a deliberately bad model for chat
    if reloaded_chat_settings.get('selected_provider') == 'OpenAI': # MODIFIED - removed OPENAI_MODELS check
        reloaded_chat_settings['selected_model'] = 'invalid-openai-model-for-test'
        save_chat_settings(reloaded_chat_settings)
        final_chat_settings = load_chat_settings()
        print(f"Chat settings after invalid model test: {final_chat_settings}")


    # Test Discord Settings
    print("\n--- Discord Settings Test ---")
    discord_settings = load_discord_settings()
    print(f"Initial loaded discord settings: {discord_settings}")
    discord_settings['guild_id'] = '1234567890'
    discord_settings['channel_id'] = '0987654321'
    discord_settings['selected_provider'] = 'Gemini'
    save_discord_settings(discord_settings)
    reloaded_discord_settings = load_discord_settings()
    print(f"Reloaded discord settings: {reloaded_discord_settings}")
    # Test with a deliberately bad model for discord
    if reloaded_discord_settings.get('selected_provider') == 'Gemini': # MODIFIED - removed GEMINI_MODELS check
         reloaded_discord_settings['selected_model'] = 'invalid-gemini-model-for-test'
         save_discord_settings(reloaded_discord_settings)
         final_discord_settings = load_discord_settings()
         print(f"Discord settings after invalid model test: {final_discord_settings}")

    print("\nTo verify, check the following directories/files:")
    print(f"Chat settings file: {CHAT_SETTINGS_FILE}")
    print(f"Discord settings file: {DISCORD_SETTINGS_FILE}")
