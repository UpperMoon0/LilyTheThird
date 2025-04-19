import json
import os
import random
from datetime import datetime
import openai
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from pydantic import ValidationError # Import ValidationError
# Removed KG imports
# Import schemas from the new module
from .schemas import (
    ActionExtractionSchema, PydanticSchemaType # Removed KG-related schemas
)
# Import the action extractor function
from .action_extractor import extract_action
# Removed knowledge extraction import
# Import keyword extraction function (might be used for future Mongo search)
# from .keyword_extractor import extract_keywords
# Import the history manager
from .history_manager import HistoryManager
# Import the LLM client
from .llm_client import LLMClient
# Import MongoHandler
from ..memory.mongo_handler import MongoHandler
# Import settings loader
from ..settings_manager import load_settings

load_dotenv()


class ChatBoxLLM:
    # Accept model_name in the constructor
    def __init__(self, provider='openai', model_name=None):
        """
        Initializes the ChatBoxLLM orchestrator.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use (optional, defaults handled by LLMClient).
        """
        self.personality = os.getenv('PERSONALITY_TO_MASTER')
        # Initialize managers and client
        self.history_manager = HistoryManager()
        # LLMClient handles provider/model logic and client initialization
        self.llm_client = LLMClient(provider=provider, model_name=model_name)
        # Store provider and model name locally
        self.provider = self.llm_client.provider
        self.model = self.llm_client.get_model_name()
        # Load settings to check if MongoDB memory is enabled
        self.settings = load_settings()
        self.mongo_memory_enabled = self.settings.get('enable_mongo_memory', False)
        # Initialize MongoHandler only if enabled
        self.mongo_handler = MongoHandler() if self.mongo_memory_enabled else None
        if self.mongo_memory_enabled and not self.mongo_handler.is_connected():
            print("Warning: MongoDB memory is enabled in settings, but connection failed. Disabling for this session.")
            self.mongo_memory_enabled = False # Disable if connection failed

    def get_response(self, user_message):
        """
        Generates a response to the user message, potentially using MongoDB for context
        and storing the conversation turn if enabled.
        """
        mongo_context_sentences = []

        # --- Retrieve Context from MongoDB (if enabled) ---
        if self.mongo_memory_enabled and self.mongo_handler:
            # Retrieve recent memories (adjust limit as needed)
            recent_memories = self.mongo_handler.retrieve_recent_memories(limit=5)
            if recent_memories:
                print(f"Retrieved {len(recent_memories)} recent memories from MongoDB.")
                # Format memories for context (simple approach: use user input and response)
                for mem in reversed(recent_memories): # Add oldest first
                    mongo_context_sentences.append(f"Past interaction: User said '{mem['user_input']}', You responded '{mem['llm_response']}'")
            # Future: Implement keyword-based search here using mongo_handler.search_memories(keywords)
            # keywords = extract_keywords(...) # If needed
            # search_results = self.mongo_handler.search_memories(keywords) ... add to context

        # --- Prepare Base System Messages ---
        self.current_time = datetime.now()
        self.current_date_time = self.current_time.strftime("%Y-%m-%d %H:%M:%S")

        base_system_messages = [
            {'role': 'system', 'content': self.personality},
            {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"},
        ]

        # Add MongoDB context if available and enabled
        if self.mongo_memory_enabled and mongo_context_sentences:
            base_system_messages.append({'role': 'system', 'content': "Consider the following recent interactions from your long-term memory when formulating your response:"})
            for sentence in mongo_context_sentences:
                base_system_messages.append({'role': 'system', 'content': f"- {sentence}"})

        # --- First Call: Generate Message ---
        # Include personality, time, MongoDB context, history for message generation
        current_history = self.history_manager.get_history()
        message_generation_messages = base_system_messages + \
                                      current_history + \
                                      [{'role': 'user', 'content': user_message}]

        # Use the LLMClient to generate the message
        message = self.llm_client.generate_message_response(message_generation_messages)

        # Handle potential errors from the first call
        if message is None or message.startswith("Error:"):
            print(f"Failed to get message response: {message}")
            self.history_manager.update_history(user_message, None) # Still update history
            # Don't save to MongoDB on error
            return message if message else "Sorry, I encountered an error.", "none"

        # --- Update Short-Term History ---
        self.history_manager.update_history(user_message, message)

        # --- Store Interaction in MongoDB (if enabled) ---
        if self.mongo_memory_enabled and self.mongo_handler:
            print("Attempting to add conversation turn to MongoDB.")
            # Add metadata if needed, e.g., timestamp is added automatically by handler
            metadata = {"provider": self.provider, "model": self.model}
            self.mongo_handler.add_memory(user_input=user_message, llm_response=message, metadata=metadata)
        elif self.mongo_memory_enabled:
            print("MongoDB memory enabled but handler not available, skipping storage.")
        else:
            print("MongoDB memory is disabled, skipping storage.")


        # --- Second Call: Extract Action ---
        action = extract_action(
            provider=self.llm_client.provider,
            client=self.llm_client.client,
            model_name=self.llm_client.get_model_name(),
            user_message=user_message,
            assistant_message=message
        )
        # action defaults to "none" if extraction fails

        # --- Removed Knowledge Graph Extraction/Storage Logic ---

        # --- Return Generated Message and Extracted Action ---
        return message, action

    def __del__(self):
        # Ensure MongoDB connection is closed when the object is destroyed
        if hasattr(self, 'mongo_handler') and self.mongo_handler:
            self.mongo_handler.close_connection()
