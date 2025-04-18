import json
import os
import random
import json
from datetime import datetime
import openai
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai
from pydantic import BaseModel, Field # Import Pydantic
from kg import kg_handler

load_dotenv()

# Load API keys
OPENAI_API_KEY = os.getenv('OPENAI_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure clients
openai.api_key = OPENAI_API_KEY
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Define Pydantic models for the desired JSON structure
class KnowledgeTriple(BaseModel):
    subject: str
    predicate: str
    object: str

class GeminiResponseSchema(BaseModel):
    message: str
    actions: str
    new_knowledge: list[KnowledgeTriple] = Field(default_factory=list)


class ChatBoxLLM:
    # Accept model_name in the constructor
    def __init__(self, provider='openai', model_name=None):
        self.personality = os.getenv('PERSONALITY_TO_MASTER')
        self.provider = provider
        self.message_history = []
        self.model = model_name # Store the selected model name

        if not self.model:
             # Set default model if none provided (optional, based on desired behavior)
             if self.provider == 'openai':
                 self.model = "gpt-4o-mini" # Default OpenAI model
             elif self.provider == 'gemini':
                 self.model = "gemini-1.5-flash" # Default Gemini model
             else:
                 raise ValueError("Model name must be provided if provider is not OpenAI or Gemini with defaults.")
             print(f"Warning: No model name provided, using default for {self.provider}: {self.model}")


        if self.provider == 'openai':
            if not OPENAI_API_KEY:
                raise ValueError("OpenAI API key not found in environment variables.")
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            # self.model is already set from constructor or default
        elif self.provider == 'gemini':
            if not GEMINI_API_KEY:
                raise ValueError("Gemini API key not found in environment variables.")
            # Use the provided model_name to initialize the Gemini client
            self.client = genai.GenerativeModel(self.model)
            # Gemini history adaptation remains the same
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def _adapt_history_for_gemini(self, messages):
        """Converts OpenAI-style history to Gemini-style history."""
        gemini_history = []
        for msg in messages:
            role = 'user' if msg['role'] == 'user' else 'model'
            gemini_history.append({'role': role, 'parts': [msg['content']]})
        return gemini_history

    def update_history(self, user_message, assistant_message):
        # Store history in OpenAI format for consistency internally
        self.message_history.append({'role': 'user', 'content': user_message})
        # Ensure assistant message is not None before appending
        if assistant_message is not None:
            self.message_history.append({'role': 'assistant', 'content': assistant_message})
        # Limit history size
        while len(self.message_history) > 20: # Keep last 10 pairs (20 messages)
            self.message_history.pop(0)

    def _get_openai_response(self, main_messages, response_format):
        """Handles the API call to OpenAI."""
        try:
            main_response = self.client.chat.completions.create(
                messages=main_messages,
                model=self.model,
                max_tokens=500,
                temperature=random.uniform(0.2, 0.8),
                response_format=response_format
            )
            # Extract and parse the JSON content from the first choice's message content
            main_res_content = json.loads(main_response.choices[0].message.content)
            message = main_res_content.get("message")
            action = main_res_content.get("actions")
            new_knowledge = main_res_content.get("new_knowledge", []) # Extract new knowledge
            return message, action, new_knowledge # Return new knowledge
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return f"Error: Could not get response from OpenAI. {e}", "none", [] # Return empty list on error

    def _get_gemini_response(self, main_messages):
        """Handles the API call to Gemini."""
        # Adapt system prompts and history for Gemini
        # Gemini prefers system instructions at the start or within the user turn
        system_prompts = [msg['content'] for msg in main_messages if msg['role'] == 'system']
        history = [msg for msg in main_messages if msg['role'] != 'system']
        user_message_content = history.pop()['content'] # Get the last user message

        # Combine system prompts with the first user message or the final user message
        # This is a common pattern for Gemini, adjust as needed
        gemini_formatted_history = self._adapt_history_for_gemini(history)

        # Construct the final prompt parts for Gemini
        prompt_parts = [f"System Instructions:\n{' '.join(system_prompts)}\n\nUser Request:\n{user_message_content}"]

        # Define generation config using the Pydantic model for the schema
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=800,
            temperature=random.uniform(0.2, 0.8),
            response_mime_type="application/json",
            response_schema=GeminiResponseSchema # Use the Pydantic model here
        )

        try:
            # Start chat session if history exists
            chat_session = self.client.start_chat(history=gemini_formatted_history)
            response = chat_session.send_message(
                prompt_parts,
                generation_config=generation_config,
                # stream=False # Ensure non-streaming for single JSON response
            )

            # Gemini response might need specific parsing depending on JSON mode behavior
            # Assuming response.text contains the JSON string if successful
            print(f"--- Raw Gemini Response Text ---") # ADDED: Log raw response
            print(response.text)                      # ADDED: Log raw response
            print(f"------------------------------") # ADDED: Log raw response
            if response.text:
                 try: # ADDED: Try block for JSON parsing
                     main_res_content = json.loads(response.text)
                     message = main_res_content.get("message")
                     action = main_res_content.get("actions")
                     new_knowledge = main_res_content.get("new_knowledge", []) # Extract new knowledge
                     return message, action, new_knowledge # Return new knowledge
                 except json.JSONDecodeError as json_err: # ADDED: Catch JSON specific error
                     print(f"Error decoding Gemini JSON response: {json_err}")
                     print(f"Problematic text: {response.text}") # Log the text that failed
                     return f"Error: Failed to parse Gemini JSON response. {json_err}", "none", []
            else:
                 # Handle cases where Gemini might not return text (e.g., safety blocks)
                 print(f"Gemini response issue: {response.prompt_feedback}")
                 # Check candidates if available
                 if response.candidates:
                     print(f"Gemini candidate: {response.candidates[0].content}") # Log candidate content if available
                 return "Error: Gemini response was empty or blocked.", "none", [] # Return empty list on error

        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            # Attempt to get more details from the exception if possible
            error_details = str(e)
            # if hasattr(e, 'response') and hasattr(e.response, 'text'):
            #     error_details += f" | Response: {e.response.text}" # Be cautious logging full responses
            return f"Error: Could not get response from Gemini. {error_details}", "none", [] # Return empty list on error


    def get_response(self, user_message, disable_kg_memory=False):
        related_info_sentences = []
        # Disable KG if not loaded
        if not kg_handler.knowledge_graph_loaded:
            if not disable_kg_memory:
                 print("Knowledge graph not loaded, disabling KG memory for this request.")
            disable_kg_memory = True

        # Keyword extraction (Preflight) - Needs adaptation for Gemini if used
        keywords = []
        if not disable_kg_memory:
            # --- OpenAI Keyword Extraction ---
            if self.provider == 'openai':
                preflight_messages = [
                    {'role': 'system', 'content': "Do not answer the user message! Provide an array of at most 5 keywords related to the user message."},
                    {'role': 'user', 'content': user_message},
                ]
                try:
                    preflight_response = self.client.chat.completions.create(
                        messages=preflight_messages,
                        model=self.model, # Use the same model or a cheaper/faster one
                        max_tokens=50,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "preflight_response",
                                "strict": True, # Enforce schema
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "keywords": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    },
                                    "required": ["keywords"],
                                    "additionalProperties": False
                                }
                            }
                        }
                    )
                    preflight_res_content = json.loads(preflight_response.choices[0].message.content)
                    keywords = preflight_res_content.get("keywords", []) # Default to empty list
                except Exception as e:
                    print(f"Error during OpenAI keyword extraction: {e}")
                    keywords = [] # Fallback to no keywords on error
            # --- Gemini Keyword Extraction (Placeholder/Example) ---
            elif self.provider == 'gemini':
                 # Gemini keyword extraction might need a different prompt structure
                 # and response parsing. This is a simplified example.
                 print("Keyword extraction for Gemini is not fully implemented, skipping.")
                 # You would need a similar try/except block calling the Gemini API
                 # with a prompt designed for keyword extraction and JSON output.
                 keywords = [] # Fallback

            # --- Get KG Info ---
            if keywords:
                related_info_sentences = kg_handler.get_related_info_from_keywords(keywords)
                for sentence in related_info_sentences:
                    print(f"KG Info: {sentence}") # Log retrieved info
            else:
                 print("No keywords extracted for KG lookup.")

        # --- Prepare Main Request ---
        self.current_time = datetime.now()
        self.current_date_time = self.current_time.strftime("%Y-%m-%d %H:%M:%S")

        main_messages = [
            {'role': 'system', 'content': self.personality},
            {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"},
            # System prompt requesting JSON structure including knowledge extraction
            {'role': 'system', 'content': '''Generate a response with:
1.  "message": Your conversational reply to the user.
2.  "actions": A string indicating a required action ("browse", "none", etc.), use "none" if no specific action is needed.
3.  "new_knowledge": An array of new factual triples (subject, predicate, object) learned from the latest user message and your response, suitable for storing in a knowledge graph. Each triple should be an object like {"subject": "...", "predicate": "...", "object": "..."}. If no new facts are learned, provide an empty array [].

Respond ONLY in JSON format matching this schema:
{
  "type": "object",
  "properties": {
    "message": {"type": "string"},
    "actions": {"type": "string"},
    "new_knowledge": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "subject": {"type": "string"},
          "predicate": {"type": "string"},
          "object": {"type": "string"}
        },
        "required": ["subject", "predicate", "object"]
      }
    }
  },
  "required": ["message", "actions", "new_knowledge"]
}'''},
        ]

        # Add KG context if available and enabled
        if not disable_kg_memory and related_info_sentences:
            # Refined instruction for using KG context
            main_messages.append({'role': 'system', 'content': "Consider the following facts from the Knowledge Graph when formulating your response. Prioritize information directly related to the user's query. Use this context to provide more informed and accurate answers:"})
            for sentence in related_info_sentences:
                main_messages.append({'role': 'system', 'content': f"- {sentence}"}) # Prefix KG sentences

        # Add chat history
        main_messages.extend(self.message_history)

        # Add current user message
        main_messages.append({'role': 'user', 'content': user_message})

        # --- Call Appropriate LLM ---
        message = None
        action = "none" # Default action
        new_knowledge = [] # Default empty knowledge

        if self.provider == 'openai':
            # Updated OpenAI schema to match the prompt
            openai_response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "lily_response_with_knowledge",
                    "strict": True, # Enforce schema
                    "schema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "actions": {"type": "string"},
                            "new_knowledge": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "subject": {"type": "string"},
                                        "predicate": {"type": "string"},
                                        "object": {"type": "string"}
                                    },
                                    "required": ["subject", "predicate", "object"]
                                }
                            }
                        },
                        "required": ["message", "actions", "new_knowledge"],
                        "additionalProperties": False
                    }
                }
            }
            message, action, new_knowledge = self._get_openai_response(main_messages, openai_response_format)
        elif self.provider == 'gemini':
            # Gemini response handling already updated in _get_gemini_response
            message, action, new_knowledge = self._get_gemini_response(main_messages)

        # --- Store New Knowledge in KG ---
        if not disable_kg_memory and new_knowledge:
            try:
                # Ensure kg_handler has the necessary function
                if hasattr(kg_handler, 'add_triples_to_graph'):
                    print(f"Attempting to add {len(new_knowledge)} new triple(s) to KG.")
                    kg_handler.add_triples_to_graph(new_knowledge)
                else:
                    print("Warning: kg_handler.add_triples_to_graph function not found. Cannot store new knowledge.")
            except Exception as e:
                print(f"Error adding new knowledge to KG: {e}")


        # --- Update History and Return ---
        # Ensure message is not None before updating history
        if message is not None:
             self.update_history(user_message, message)
        else:
             # Handle case where message extraction failed (e.g., API error)
             print("LLM response did not contain a message. History not updated with assistant response.")
             # Optionally, update history with an error message for context
             # self.update_history(user_message, "Error: Failed to get valid assistant message.")

        return message, action if action is not None else "none" # Ensure action is never None
