import os
import random
from datetime import datetime

import openai
from dotenv import load_dotenv
from openai import OpenAI
import google.generativeai as genai # Import Gemini

load_dotenv()

# Load API keys
OPENAI_API_KEY = os.getenv('OPENAI_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure clients if keys exist
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class DiscordLLM:
    # Accept provider and model, fall back to env vars
    def __init__(self, provider=None, model=None):
        # Prioritize passed arguments, then environment variables, then defaults
        self.provider = (provider or os.getenv('DISCORD_LLM_PROVIDER', 'openai')).lower()
        self.model = model or os.getenv('DISCORD_LLM_MODEL', 'gpt-4o-mini') # Default model depends on provider, adjust if needed
        self.message_history = [] # Internal history uses OpenAI format

        print(f"Initializing DiscordLLM - Provider: {self.provider}, Model: {self.model}")

        # Initialize the correct client
        if self.provider == 'openai':
            if not OPENAI_API_KEY:
                raise ValueError("OpenAI API key not found in environment variables for Discord LLM.")
            self.client = OpenAI(api_key=OPENAI_API_KEY)
        elif self.provider == 'gemini':
            if not GEMINI_API_KEY:
                raise ValueError("Gemini API key not found in environment variables for Discord LLM.")
            # Ensure the model name is valid for Gemini, error handling might be needed in generate_content
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported Discord LLM provider: {self.provider}")

    def _adapt_history_for_gemini(self, messages):
        """Converts OpenAI-style history (including custom roles) to Gemini-style history."""
        gemini_history = []
        for msg in messages:
            role = 'model' if msg['role'] == 'assistant' else 'user'
            prefix = ""
            content_text = "" # Initialize content_text

            if msg['role'] == 'master':
                prefix = "Master said: "
                content_text = msg['content']
            elif msg['role'] == 'discord_user_name':
                # Attempt to extract name if present in content (e.g., "Nhat said: Hello")
                # Ensure the content exists before splitting
                if isinstance(msg.get('content'), str):
                    parts = msg['content'].split(" said: ", 1)
                    if len(parts) == 2:
                        prefix = f"{parts[0]}: " # Use extracted name
                        content_text = parts[1]
                    else:
                        prefix = "User: " # Fallback if name isn't in the expected format
                        content_text = msg['content']
                else:
                     # Handle cases where content might not be a string or is missing
                     prefix = "User: "
                     content_text = str(msg.get('content', '')) # Default to empty string
            elif msg['role'] == 'assistant':
                # No prefix needed for assistant
                content_text = msg['content']
            else: # Handle other potential user roles like 'user'
                prefix = "User: "
                content_text = msg['content']

            # Ensure content_text is a string before concatenation
            if not isinstance(content_text, str):
                content_text = str(content_text)

            gemini_history.append({'role': role, 'parts': [prefix + content_text]})
        return gemini_history

    def update_history(self, user_message, assistant_message, is_master=False, discord_user_name=None):
        """Update message history, keeping only the last 15 message pairs (30 total)"""
        if is_master:
            self.message_history.append({'role': 'master', 'content': "Your master said: " + user_message})
        else:
            self.message_history.append({'role': 'discord_user_name', 'content': discord_user_name + "said: " + user_message})
        self.message_history.append({'role': 'assistant', 'content': assistant_message})

        # Keep only the last 10 messages (user + assistant pairs)
        if len(self.message_history) > 30:
            self.message_history.pop(0) # Remove oldest user message
            self.message_history.pop(0) # Remove oldest assistant message

    def get_response(self, user_message, discord_user_id, discord_user_name):
        self.current_time = datetime.now()
        self.current_date_time = self.current_time.strftime("%Y-%m-%d %H:%M:%S")

        master_id = os.getenv('MASTER_DISCORD_ID')
        if discord_user_id == int(master_id):
            personality = os.getenv('PERSONALITY_TO_MASTER')
        else:
            personality_part_1 = os.getenv('PERSONALITY_TO_STRANGER_1')
            personality_part_2 = os.getenv('PERSONALITY_TO_STRANGER_2')
            personality = personality_part_1 + discord_user_name + personality_part_2

        # Collect messages for the main request
        main_messages = [
            {'role': 'system', 'content': personality},
            {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"},
        ]

        # Add historical user-assistant pairs
        for message in self.message_history:
            main_messages.append(message)

        # Add historical messages (already in OpenAI format)
        main_messages.extend(self.message_history)

        # Add the current user message (role determined by is_master)
        current_user_role = 'master' if discord_user_id == int(master_id) else 'discord_user_name'
        # For OpenAI, add directly. For Gemini, adaptation happens later.
        main_messages.append({'role': current_user_role, 'content': user_message})

        # --- Call Appropriate LLM ---
        message = f"Error: Provider '{self.provider}' not recognized or failed." # Default error

        try:
            if self.provider == 'openai':
                # Request the response from OpenAI
                openai_response = self.client.chat.completions.create(
                    messages=main_messages, # Uses OpenAI format directly
                    model=self.model,
                    max_tokens=500,
                    temperature=random.uniform(0.2, 0.8)
                )
                message = openai_response.choices[0].message.content

            elif self.provider == 'gemini':
                # Adapt messages for Gemini API call
                # Separate system prompts from history
                system_prompts_content = [msg['content'] for msg in main_messages if msg['role'] == 'system']
                history_messages = [msg for msg in main_messages if msg['role'] != 'system']

                # Adapt history including custom roles
                gemini_history = self._adapt_history_for_gemini(history_messages[:-1]) # History excluding the last user message
                last_user_message_adapted = self._adapt_history_for_gemini([history_messages[-1]]) # Adapt only the last message

                # Construct prompt parts for Gemini
                # Combine system prompts and the last user message content
                prompt_parts = [
                    f"System Instructions:\n{' '.join(system_prompts_content)}\n\n{last_user_message_adapted[0]['parts'][0]}" # Use adapted content
                ]

                # Start chat session if history exists
                chat_session = self.client.start_chat(history=gemini_history)
                gemini_response = chat_session.send_message(
                    prompt_parts,
                    # generation_config=... # Add config if needed (e.g., temperature)
                    stream=False
                )
                message = gemini_response.text # Extract text response

        except Exception as e:
             print(f"Error calling {self.provider} API: {e}")
             message = f"Sorry, there was an error contacting the {self.provider} API."


        # --- Update History ---
        # Update history with the original user message and the obtained assistant message
        if discord_user_id == int(master_id):
            self.update_history(user_message, message, is_master=True)
        else:
            self.update_history(user_message, message, discord_user_name=discord_user_name)

        #print the all the messages in the history
        print("Message History:")
        for history_message in self.message_history:
            print(f"{history_message['role']}: {history_message['content']}")

        return message, None
