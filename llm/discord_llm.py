import os
import random
from datetime import datetime

import openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Set up OpenAI API key
openai.api_key = os.getenv('OPENAI_KEY')

class DiscordLLM:
    def __init__(self, model="gpt-4o-mini-2024-07-18"):
        # Set up initial variables for each instance
        self.model = model
        self.message_history = []
        self.client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

    def update_history(self, user_message, assistant_message, is_master=False, discord_user_name=None):
        """Update message history, keeping only the last 5 message pairs"""
        if is_master:
            self.message_history.append({'role': 'master', 'content': "Your master said: " + user_message})
        else:
            self.message_history.append({'role': 'discord_user_name', 'content': discord_user_name + "said: " + user_message})
        self.message_history.append({'role': 'assistant', 'content': assistant_message})

        # Keep only the last 10 messages (user + assistant pairs)
        if len(self.message_history) > 30:
            self.message_history.pop(0)
            self.message_history.pop(0)

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

        # Add the current user message
        main_messages.append({'role': 'user', 'content': user_message})

        # Request the response from the models
        main_response = self.client.chat.completions.create(
            messages=main_messages,
            model=self.model,
            max_tokens=500,
            temperature=random.uniform(0.2, 0.8)
        ).choices[0].message.content

        # Directly use the response content
        message = main_response

        # Update history with the user message and assistant's message
        if discord_user_id == int(master_id):
            self.update_history(user_message, message, is_master=True)
        else:
            self.update_history(user_message, message, discord_user_name=discord_user_name)

        #print the all the messages in the history
        print("Message History:")
        for history_message in self.message_history:
            print(f"{history_message['role']}: {history_message['content']}")

        return message, None