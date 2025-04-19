from typing import List, Dict, Optional

MAX_HISTORY_MESSAGES = 20 # Keep last 10 pairs

class HistoryManager:
    """Manages the conversation history for the LLM."""

    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES):
        """
        Initializes the HistoryManager.

        Args:
            max_messages: The maximum number of messages (user + assistant) to keep.
        """
        self.message_history: List[Dict[str, str]] = []
        self.max_messages = max_messages

    def update_history(self, user_message: str, assistant_message: Optional[str]):
        """
        Adds the latest user and assistant messages to the history
        and trims it if it exceeds the maximum size.

        Args:
            user_message: The user's message.
            assistant_message: The assistant's response (can be None if an error occurred).
        """
        # Store history in OpenAI format for consistency internally
        self.message_history.append({'role': 'user', 'content': user_message})

        # Ensure assistant message is not None before appending
        if assistant_message is not None:
            # Ensure assistant message is a string before appending
            if isinstance(assistant_message, str):
                self.message_history.append({'role': 'assistant', 'content': assistant_message})
            else:
                # Log or handle cases where assistant_message might not be a string
                # For now, convert to string representation and log a warning
                print(f"Warning: Assistant message was not a string: {type(assistant_message)}. Converting.")
                self.message_history.append({'role': 'assistant', 'content': str(assistant_message)})
        # If assistant_message is None (e.g., due to an error), we don't add an assistant turn for it.

        # Limit history size
        while len(self.message_history) > self.max_messages:
            self.message_history.pop(0) # Remove the oldest message

    def get_history(self) -> List[Dict[str, str]]:
        """Returns the current message history."""
        return self.message_history.copy() # Return a copy to prevent external modification

    def clear_history(self):
        """Clears the message history."""
        self.message_history = []

    def adapt_history_for_gemini(self, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, List[str]]]:
        """
        Converts OpenAI-style history to Gemini-style history.

        Args:
            history: An optional OpenAI-style history list. If None, uses the internal history.

        Returns:
            A Gemini-style history list.
        """
        source_history = history if history is not None else self.message_history
        gemini_history = []
        for msg in source_history:
            # Gemini expects 'model' instead of 'assistant'
            role = 'user' if msg['role'] == 'user' else 'model'
            # Gemini expects 'parts' to be a list containing the content
            gemini_history.append({'role': role, 'parts': [msg['content']]})
        return gemini_history
