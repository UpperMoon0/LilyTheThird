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

    def _trim_history(self):
        """Internal method to trim history if it exceeds the maximum size."""
        while len(self.message_history) > self.max_messages:
            self.message_history.pop(0) # Remove the oldest message

    def add_message(self, role: str, content: str):
        """
        Adds a single message with the specified role to the history
        and trims the history.

        Args:
            role: The role of the message ('user', 'assistant', 'system', 'tool', etc.).
            content: The content of the message.
        """
        if not isinstance(content, str):
            print(f"Warning: Message content for role '{role}' was not a string: {type(content)}. Converting.")
            content = str(content)
        
        self.message_history.append({'role': role, 'content': content})
        self._trim_history()


    def add_user_assistant_pair(self, user_message: str, assistant_message: Optional[str]):
        """
        Adds the latest user and assistant messages to the history using add_message.
        (Kept for potential compatibility, but direct add_message is preferred).

        Args:
            user_message: The user's message.
            assistant_message: The assistant's response (can be None if an error occurred).
        """
        self.add_message('user', user_message)
        if assistant_message is not None:
             self.add_message('assistant', assistant_message)

    def get_history(self) -> List[Dict[str, str]]:
        """Returns the current message history."""
        return self.message_history.copy() # Return a copy to prevent external modification

    def clear_history(self):
        """Clears the message history."""
        self.message_history = []

    def adapt_history_for_gemini(self, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, List[str]]]:
        """
        Converts OpenAI-style history (user/assistant roles only) to Gemini-style history.
        Filters out non-user/assistant messages as Gemini expects alternating turns.

        Args:
            history: An optional OpenAI-style history list. If None, uses the internal history.

        Returns:
            A Gemini-style history list containing only user/model turns.
        """
        source_history = history if history is not None else self.message_history
        gemini_history = []
        for msg in source_history:
            role = msg.get('role')
            content = msg.get('content')
            
            if role == 'user':
                gemini_history.append({'role': 'user', 'parts': [content]})
            elif role == 'assistant':
                gemini_history.append({'role': 'model', 'parts': [content]})
            # else: skip system, tool, or other roles for Gemini history adaptation
        
        # Ensure history alternates user/model and ends with user if possible?
        # Basic validation/cleanup might be needed depending on Gemini's strictness
        # For now, just return the filtered list.
        return gemini_history
