import json
import os
import random
from datetime import datetime
import openai
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from pydantic import ValidationError # Import ValidationError
# Import the specific function needed, or keep importing the handler
from kg import kg_handler # Import kg_handler
# Import schemas from the new module
from .schemas import (
    KnowledgeTriple, KeywordSchema, ActionExtractionSchema,
    SentenceExtractionSchema, KnowledgeExtractionSchema, PydanticSchemaType
)
# Import the action extractor function
from .action_extractor import extract_action
# Import knowledge extraction functions
from .knowledge_extractor import extract_knowledge_sentences, convert_sentences_to_triples
# Import keyword extraction function
from .keyword_extractor import extract_keywords
# Import the history manager
from .history_manager import HistoryManager
# Import the LLM client
from .llm_client import LLMClient

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
        # Store provider and model name locally for convenience if needed elsewhere
        self.provider = self.llm_client.provider # Get actual provider used
        self.model = self.llm_client.get_model_name() # Get actual model used

    def get_response(self, user_message, disable_kg_memory=False):
        related_info_sentences = []
        # Disable KG if not loaded
        # Check if kg_handler and its attribute exist before accessing
        kg_loaded = hasattr(kg_handler, 'knowledge_graph_loaded') and kg_handler.knowledge_graph_loaded
        if not kg_loaded:
            if not disable_kg_memory:
                 print("Knowledge graph not loaded or handler unavailable, disabling KG memory for this request.")
            disable_kg_memory = True

        # --- Keyword extraction ---
        keywords: list[str] = []
        if not disable_kg_memory:
            keywords = extract_keywords(
                provider=self.llm_client.provider,
                client=self.llm_client.client, # Pass the actual client object
                model_name=self.llm_client.get_model_name(),
                user_message=user_message
            )

            # --- Get KG Info ---
            if keywords and hasattr(kg_handler, 'get_related_info_from_keywords'): # Check method existence
                related_info_sentences = kg_handler.get_related_info_from_keywords(keywords)
                for sentence in related_info_sentences:
                    print(f"KG Info: {sentence}") # Log retrieved info
            elif not keywords:
                 print("No keywords extracted for KG lookup.")
            else:
                 print("KG handler or get_related_info_from_keywords method not available.")


        # --- Prepare Base System Messages ---
        self.current_time = datetime.now()
        self.current_date_time = self.current_time.strftime("%Y-%m-%d %H:%M:%S")

        base_system_messages = [
            {'role': 'system', 'content': self.personality},
            {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"},
        ]
        # Add KG context if available and enabled
        if not disable_kg_memory and related_info_sentences:
            base_system_messages.append({'role': 'system', 'content': "Consider the following facts from the Knowledge Graph when formulating your response. Prioritize information directly related to the user's query. Use this context to provide more informed and accurate answers:"})
            for sentence in related_info_sentences:
                base_system_messages.append({'role': 'system', 'content': f"- {sentence}"}) # Prefix KG sentences


        # --- First Call: Generate Message ---
        # Include personality, time, KG context, history for message generation
        # Get current history from the manager
        current_history = self.history_manager.get_history()
        message_generation_messages = base_system_messages + \
                                      current_history + \
                                      [{'role': 'user', 'content': user_message}]

        # Use the LLMClient to generate the message
        message = self.llm_client.generate_message_response(message_generation_messages)

        # Handle potential errors from the first call
        # generate_message_response returns None or an error string
        if message is None or message.startswith("Error:"):
            print(f"Failed to get message response: {message}")
            # Update history via manager even on error (adds user message)
            self.history_manager.update_history(user_message, None)
            return message if message else "Sorry, I encountered an error.", "none" # Return error and default action

        # --- Update History ---
        # Update history *after* getting the message, before action/knowledge calls
        # Use the history manager to update
        self.history_manager.update_history(user_message, message)

        # --- Second Call: Extract Action ---
        action = extract_action(
            provider=self.llm_client.provider,
            client=self.llm_client.client,
            model_name=self.llm_client.get_model_name(),
            user_message=user_message,
            assistant_message=message
        )
        # The function already defaults to "none", so no need for the check below
        # action = action if action is not None else "none" # Ensure action is not None

        # --- Third Call: Extract Knowledge Sentences ---
        # --- Fourth Call: Convert Sentences to Triples ---
        # --- Store New Knowledge in KG ---
        if not disable_kg_memory:
            kg_available = hasattr(kg_handler, 'knowledge_graph_loaded') and kg_handler.knowledge_graph_loaded
            if not kg_available:
                 print("Knowledge graph not loaded or handler unavailable, skipping knowledge extraction.")
            else:
                # Step 3: Extract sentences using the imported function
                learned_sentences = extract_knowledge_sentences(
                    provider=self.llm_client.provider,
                    client=self.llm_client.client,
                    model_name=self.llm_client.get_model_name(),
                    user_message=user_message,
                    assistant_message=message
                )

                if learned_sentences:
                    # Step 4: Convert sentences to triples using the imported function
                    new_knowledge_triples = convert_sentences_to_triples(
                        provider=self.llm_client.provider,
                        client=self.llm_client.client,
                        model_name=self.llm_client.get_model_name(),
                        sentences=learned_sentences
                    )

                    # Step 5: Store triples
                    if new_knowledge_triples: # Check if list is not empty after conversion/validation
                        try:
                            if hasattr(kg_handler, 'add_triples_to_graph'):
                                print(f"Attempting to add {len(new_knowledge_triples)} new triple(s) to KG.")
                                kg_handler.add_triples_to_graph(new_knowledge_triples) # Pass the list of validated triple dicts
                            else:
                                print("Warning: kg_handler.add_triples_to_graph function not found. Cannot store new knowledge.")
                        except Exception as e:
                            print(f"Error adding new knowledge to KG: {e}")
                    else:
                        print("No valid triples were converted from the extracted sentences.")
                else:
                    print("No new knowledge sentences were extracted from the conversation turn.")
        else:
            print("Knowledge Graph memory is disabled, skipping knowledge extraction and storage.")


        # --- Return Generated Message and Extracted Action ---
        return message, action
