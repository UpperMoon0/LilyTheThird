import os
import sys

def get_nstut_lilythethird_app_data_dir():
    """
    Gets the application-specific 'NsTut/LilyTheThird' directory 
    within the appropriate user data location for the current OS.
    Ensures the directory exists.
    """
    if sys.platform == 'win32':
        app_data_root = os.getenv('APPDATA')
    elif sys.platform == 'darwin':  # macOS
        app_data_root = os.path.expanduser('~/Library/Application Support')
    else:  # Linux and other Unix-like
        app_data_root = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))

    if not app_data_root:  # Fallback if environment variable isn't set (should be rare)
        # This fallback might lead to inconsistent locations if the primary env vars are missing.
        # However, it mirrors the original settings_manager logic for a last resort.
        app_data_root = os.path.expanduser('~')
        print(f"Warning: Standard application data environment variables not found. Using home directory: {app_data_root}")

    nstut_lilythethird_dir = os.path.join(app_data_root, 'NsTut', 'LilyTheThird')
    
    try:
        os.makedirs(nstut_lilythethird_dir, exist_ok=True)
    except OSError as e:
        print(f"Error creating application data directory {nstut_lilythethird_dir}: {e}")
        # Depending on how critical this is, might raise an exception or return None
        # For now, let it proceed, subsequent operations might fail if dir creation failed.
        
    return nstut_lilythethird_dir

if __name__ == '__main__':
    # For testing the function directly
    test_path = get_nstut_lilythethird_app_data_dir()
    print(f"NsTut/LilyTheThird App Data Directory: {test_path}")
    
    # Example of creating a subdirectory
    chat_dir = os.path.join(test_path, "chat")
    os.makedirs(chat_dir, exist_ok=True)
    print(f"Chat directory (example): {chat_dir}, Exists: {os.path.exists(chat_dir)}")

    vtube_anim_dir = os.path.join(test_path, "vtube", "animations")
    os.makedirs(vtube_anim_dir, exist_ok=True)
    print(f"VTube Animations directory (example): {vtube_anim_dir}, Exists: {os.path.exists(vtube_anim_dir)}")
