# response.py
import os
import random
from datetime import datetime
import re

import openai
from openai import OpenAI

from dotenv import load_dotenv

load_dotenv()

# Set up OpenAI
openai.api_key = os.getenv('OPENAI_KEY')

# Set the system message based on the current time
current_time = datetime.now()

# Format the current date and time
current_date_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

# Add the greeting and the current date and time to the system message
system_message = f"It's currently {current_date_time}."

# Add a system message to set the bot's personality
system_message += os.getenv('PERSONALITY')
system_message += "When you want to do an action, end the response with <action>action</action>, for example: <action>open the door</action>"

# Initialize the prompt history
prompt_history = []


def get_response(user_message):
    global prompt_history
    client = OpenAI(api_key=os.getenv('OPENAI_KEY'))
    temperature = random.uniform(0.2, 0.8)
    messages = [
        {'role': 'system', 'content': system_message},
        {'role': 'user', 'content': user_message}
    ]

    chat_completion = client.chat.completions.create(
        messages=messages,
        model="gpt-4o",
        max_tokens=500,
        temperature=temperature,
    )

    response = chat_completion.choices[0].message.content

    # Find the action within the response
    action_match = re.search('<action>(.*?)</action>', response)

    # If an action is found, remove it from the response
    if action_match:
        action = action_match.group(1)
        response = re.sub('<action>.*?</action>', '', response)
    else:
        action = None

    # Add the current prompt to the history
    prompt_history.append(user_message)
    # If the history is longer than 3 prompts, remove the oldest one
    if len(prompt_history) > 3:
        prompt_history.pop(0)

    return response, action
