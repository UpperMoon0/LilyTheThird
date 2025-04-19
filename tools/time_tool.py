from datetime import datetime

def get_current_time() -> str:
    """
    Gets the current date and time.

    Returns:
        A string representing the current date and time in ISO format.
    """
    try:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error getting current time: {e}")
        return f"Error: Could not retrieve current time. {e}"
