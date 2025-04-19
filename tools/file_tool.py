import os

def read_file(file_path: str) -> str:
    """
    Reads the content of a specified file.

    Args:
        file_path: The full path to the file to be read.

    Returns:
        The content of the file as a string, or an error message if reading fails.
    """
    try:
        # Basic security check: prevent reading files outside a reasonable scope if needed
        # For now, we assume the LLM provides valid paths, but this could be enhanced.
        # Example: Check if path is within project or allowed directories.
        if not os.path.exists(file_path):
            return f"Error: File not found at '{file_path}'."
        if not os.path.isfile(file_path):
            return f"Error: Path '{file_path}' is a directory, not a file."

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except PermissionError:
        print(f"Permission denied when trying to read '{file_path}'.")
        return f"Error: Permission denied to read file '{file_path}'."
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return f"Error: Could not read file '{file_path}'. {e}"

def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file. Overwrites if exists, creates directories if needed.

    Args:
        file_path: The full path to the file to be written.
        content: The content to write into the file.

    Returns:
        A success message or an error message.
    """
    try:
        # Create parent directories if they don't exist
        dir_name = os.path.dirname(file_path)
        if dir_name: # Ensure dirname is not empty (e.g., for root files)
            os.makedirs(dir_name, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote content to '{file_path}'."
    except PermissionError:
        print(f"Permission denied when trying to write to '{file_path}'.")
        return f"Error: Permission denied to write file '{file_path}'."
    except Exception as e:
        print(f"Error writing file '{file_path}': {e}")
        return f"Error: Could not write file '{file_path}'. {e}"
