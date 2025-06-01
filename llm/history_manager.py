from typing import List, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timezone
import asyncio

# Avoid circular import
if TYPE_CHECKING:
    from .llm_client import LLMClient

# Constants for summarization - OPTIMIZED for better performance
SUMMARIZATION_TRIGGER_COUNT = 15  # Increased to reduce frequent summarization overhead
MESSAGE_TYPE_MESSAGE = "message"
MESSAGE_TYPE_SUMMARY = "summary"
MAX_CONTEXT_SIZE = 8000  # Smart context limit to prevent truncation

class HistoryManager:
    """
    Manages the conversation history for the LLM with automatic summarization.
    
    Features:
    - No max message limit (removed truncation)
    - Automatic summarization every 10 messages
    - History reset with summary preservation after summarization
    - Message type distinction between actual messages and summaries
    """

    def __init__(self, llm_client: Optional['LLMClient'] = None):
        """
        Initializes the HistoryManager with summarization capabilities.

        Args:
            llm_client: Optional LLM client for generating summaries. If None,
                       summarization will be skipped with warnings.
        """
        self.message_history: List[Dict[str, str]] = []
        self.llm_client = llm_client
        self.message_count = 0  # Track total messages added (excluding summaries)
        
        # For debugging and monitoring
        self.summarization_count = 0
        self.last_summarization_at = None
        
        print(f"HistoryManager initialized with summarization every {SUMMARIZATION_TRIGGER_COUNT} messages")

    def set_llm_client(self, llm_client: 'LLMClient'):
        """
        Sets or updates the LLM client for summarization.
        
        Args:
            llm_client: The LLM client instance to use for generating summaries.
        """
        self.llm_client = llm_client
        print("HistoryManager: LLM client set for summarization")

    async def add_message(self, role: str, content: str):
        """
        OPTIMIZED message addition with smart context management and reduced logging.
        """
        if not isinstance(content, str):
            content = str(content)
        
        # Filter out verbose tool system messages to reduce context bloat
        if role == 'system' and self._is_verbose_tool_message(content):
            return  # Skip adding verbose tool messages
        
        # Add the message with type distinction
        message_entry = {
            'role': role,
            'content': content,
            'type': MESSAGE_TYPE_MESSAGE,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.message_history.append(message_entry)
        self.message_count += 1
        
        # Smart summarization based on context size, not just count
        estimated_context_size = self._estimate_context_size()
        if (self.message_count % SUMMARIZATION_TRIGGER_COUNT == 0 or
            estimated_context_size > MAX_CONTEXT_SIZE):
            await self._trigger_summarization()

    def _is_verbose_tool_message(self, content: str) -> bool:
        """Check if a system message is verbose tool scaffolding that can be filtered."""
        verbose_patterns = [
            "System: Calling tool",
            "System: Retrying tool",
            "RETRY CONTEXT:",
            "ENHANCED RETRY CONTEXT:",
            "Tool executed successfully",
            "failed after",
            "Arguments prepared for"
        ]
        return any(pattern in content for pattern in verbose_patterns)
    
    def _estimate_context_size(self) -> int:
        """Estimate total context size to trigger smart summarization."""
        total_chars = sum(len(msg.get('content', '')) for msg in self.message_history)
        return total_chars // 4  # Rough token estimation (4 chars per token)


    async def _trigger_summarization(self):
        """
        OPTIMIZED summarization with smart filtering and reduced overhead.
        """
        try:
            if not self.llm_client:
                return  # Silently skip if no client
            
            # Get messages for summarization, excluding verbose tool messages
            messages_to_summarize = self._get_messages_for_summarization()
            
            if len(messages_to_summarize) < 5:  # Need minimum messages for meaningful summary
                return
            
            # Generate summary only for substantial content
            summary = await self._generate_summary_optimized(messages_to_summarize)
            
            if summary:
                await self._reset_history_with_summary(summary)
                self.summarization_count += 1
                self.last_summarization_at = datetime.now(timezone.utc)
                
        except Exception:
            pass  # Silently handle summarization errors to avoid disrupting main flow

    def _get_messages_for_summarization(self) -> List[Dict[str, str]]:
        """Get meaningful messages for summarization, filtering out noise."""
        meaningful_messages = []
        
        for msg in self.message_history:
            if msg.get('type') == MESSAGE_TYPE_MESSAGE:
                role = msg.get('role', '')
                content = msg.get('content', '')
                
                # Include user and assistant messages always
                if role in ['user', 'assistant']:
                    meaningful_messages.append(msg)
                # Include only meaningful system messages
                elif role == 'system' and not self._is_verbose_tool_message(content):
                    # Only include system messages with substantial content
                    if len(content) > 50 and 'memory' in content.lower():
                        meaningful_messages.append(msg)
        
        # Return last N meaningful messages
        return meaningful_messages[-SUMMARIZATION_TRIGGER_COUNT:]

    async def _generate_summary_optimized(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Optimized summary generation with concise prompts.
        """
        if not messages:
            return None
            
        try:
            # Create more concise conversation text
            conversation_text = self._format_messages_concisely(messages)
            
            # Shorter, more focused summarization prompt
            summarization_prompt = [
                {
                    "role": "system",
                    "content": (
                        "Summarize this conversation in 2-3 sentences. Focus on: "
                        "key facts, user preferences, important decisions, and ongoing context. "
                        "Be concise but preserve essential information for conversation continuity."
                    )
                },
                {
                    "role": "user",
                    "content": f"Conversation:\n{conversation_text}"
                }
            ]
            
            summary_response = await self.llm_client.generate_final_response(
                messages=summarization_prompt,
                personality_prompt="You are a conversation summarizer."
            )
            
            if summary_response and not summary_response.startswith("Error:"):
                return summary_response
            else:
                return None
                
        except Exception:
            return None

    def _format_messages_concisely(self, messages: List[Dict[str, str]]) -> str:
        """Format messages more concisely for summarization."""
        formatted_lines = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # Truncate very long messages for summarization
            if len(content) > 200:
                content = content[:200] + "..."
            
            formatted_lines.append(f"{role.title()}: {content}")
            
        return "\n".join(formatted_lines)

    def _get_last_n_messages(self, n: int, include_summaries: bool = False) -> List[Dict[str, str]]:
        """
        Gets the last N messages from history.
        
        Args:
            n: Number of messages to retrieve
            include_summaries: Whether to include summary-type messages in the count
            
        Returns:
            List of the last N message dictionaries
        """
        if include_summaries:
            return self.message_history[-n:] if len(self.message_history) >= n else self.message_history[:]
        
        # Filter to only actual messages (not summaries)
        actual_messages = [msg for msg in self.message_history if msg.get('type') == MESSAGE_TYPE_MESSAGE]
        return actual_messages[-n:] if len(actual_messages) >= n else actual_messages[:]

    async def _generate_summary(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Generates a summary of the provided messages using the LLM.
        
        Args:
            messages: List of message dictionaries to summarize
            
        Returns:
            Generated summary string or None if generation failed
        """
        if not messages:
            return None
            
        try:
            # Prepare the conversation text for summarization
            conversation_text = self._format_messages_for_summarization(messages)
            
            # Create summarization prompt
            summarization_prompt = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert at creating concise, comprehensive summaries of conversations. "
                        "Your task is to summarize the following conversation chunk, preserving key information, "
                        "context, user preferences, important facts, and the overall flow of the discussion. "
                        "Keep the summary detailed enough to maintain conversation continuity but concise enough "
                        "to save token space. Focus on:\n"
                        "1. Key facts and information shared\n"
                        "2. User preferences and requirements\n"
                        "3. Important decisions or conclusions\n"
                        "4. Context needed for future responses\n"
                        "5. Any ongoing tasks or topics\n\n"
                        "Format your response as a clear, well-structured summary."
                    )
                },
                {
                    "role": "user",
                    "content": f"Please summarize this conversation chunk:\n\n{conversation_text}"
                }
            ]
            
            # Generate summary using LLM
            summary_response = await self.llm_client.generate_final_response(
                messages=summarization_prompt,
                personality_prompt="You are a helpful AI assistant specialized in creating conversation summaries."
            )
            
            if summary_response and not summary_response.startswith("Error:"):
                print(f"Generated summary: {summary_response[:100]}{'...' if len(summary_response) > 100 else ''}")
                return summary_response
            else:
                print(f"Failed to generate summary: {summary_response}")
                return None
                
        except Exception as e:
            print(f"Error generating summary: {e}")
            return None

    def _format_messages_for_summarization(self, messages: List[Dict[str, str]]) -> str:
        """
        Formats messages into a readable text format for summarization.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Formatted conversation text
        """
        formatted_lines = []
        for i, msg in enumerate(messages, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', 'unknown')
            
            # Create readable format
            role_display = role.title()
            formatted_lines.append(f"[{i}] {role_display}: {content}")
            
        return "\n".join(formatted_lines)

    async def _reset_history_with_summary(self, new_summary: str):
        """
        Resets the message history but preserves existing summaries and adds the new summary.
        
        Args:
            new_summary: The newly generated summary to add
        """
        # Extract existing summaries
        existing_summaries = [msg for msg in self.message_history if msg.get('type') == MESSAGE_TYPE_SUMMARY]
        
        # Create new summary entry
        summary_entry = {
            'role': 'system',
            'content': f"[CONVERSATION SUMMARY {self.summarization_count + 1}]: {new_summary}",
            'type': MESSAGE_TYPE_SUMMARY,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'summary_id': self.summarization_count + 1,
            'messages_summarized': SUMMARIZATION_TRIGGER_COUNT
        }
        
        # Reset history with summaries only
        self.message_history = existing_summaries + [summary_entry]
        
        # Reset message count but keep track of summarized messages
        print(f"History reset: Kept {len(existing_summaries)} existing summaries, added 1 new summary")
        print(f"Total messages summarized so far: {(self.summarization_count + 1) * SUMMARIZATION_TRIGGER_COUNT}")

    async def add_user_assistant_pair(self, user_message: str, assistant_message: Optional[str]):
        """
        Adds the latest user and assistant messages to the history using add_message.
        (Kept for backward compatibility, but direct add_message is preferred).

        Args:
            user_message: The user's message.
            assistant_message: The assistant's response (can be None if an error occurred).
        """
        await self.add_message('user', user_message)
        if assistant_message is not None:
            await self.add_message('assistant', assistant_message)

    def get_history(self) -> List[Dict[str, str]]:
        """
        Returns the current message history including summaries.
        
        Returns:
            Copy of the complete message history with both messages and summaries
        """
        return self.message_history.copy()  # Return a copy to prevent external modification

    def get_actual_messages_only(self) -> List[Dict[str, str]]:
        """
        Returns only actual messages (excluding summaries) from the history.
        
        Returns:
            Copy of only the actual conversation messages
        """
        actual_messages = [msg for msg in self.message_history if msg.get('type') == MESSAGE_TYPE_MESSAGE]
        return actual_messages

    def get_summaries_only(self) -> List[Dict[str, str]]:
        """
        Returns only summary messages from the history.
        
        Returns:
            Copy of only the summary messages
        """
        summaries = [msg for msg in self.message_history if msg.get('type') == MESSAGE_TYPE_SUMMARY]
        return summaries

    def clear_history(self):
        """
        Clears the entire message history including summaries.
        Resets all counters.
        """
        self.message_history = []
        self.message_count = 0
        self.summarization_count = 0
        self.last_summarization_at = None
        print("History completely cleared (including summaries)")

    def get_history_stats(self) -> Dict[str, any]:
        """
        Returns statistics about the current history state.
        
        Returns:
            Dictionary with history statistics
        """
        actual_messages = self.get_actual_messages_only()
        summaries = self.get_summaries_only()
        
        return {
            'total_entries': len(self.message_history),
            'actual_messages': len(actual_messages),
            'summaries': len(summaries),
            'message_count': self.message_count,
            'summarization_count': self.summarization_count,
            'last_summarization_at': self.last_summarization_at,
            'next_summarization_at': SUMMARIZATION_TRIGGER_COUNT - (self.message_count % SUMMARIZATION_TRIGGER_COUNT) if self.message_count % SUMMARIZATION_TRIGGER_COUNT != 0 else SUMMARIZATION_TRIGGER_COUNT
        }

    def adapt_history_for_gemini(self, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, List[str]]]:
        """
        Converts OpenAI-style history (user/assistant roles only) to Gemini-style history.
        Filters out non-user/assistant messages as Gemini expects alternating turns.
        Preserves both actual messages and summaries.

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
            msg_type = msg.get('type', MESSAGE_TYPE_MESSAGE)  # Default to message type for backward compatibility
            
            # Include summaries as system messages for Gemini (they'll be filtered but logged)
            if msg_type == MESSAGE_TYPE_SUMMARY:
                # Skip summaries in Gemini adaptation as they are typically system messages
                continue
            
            if role == 'user':
                gemini_history.append({'role': 'user', 'parts': [content]})
            elif role == 'assistant':
                gemini_history.append({'role': 'model', 'parts': [content]})
            # else: skip system, tool, or other roles for Gemini history adaptation
        
        return gemini_history
