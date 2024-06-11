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
if 0 <= datetime.now().hour < 12:
    system_message = "Good morning!"
elif 12 <= datetime.now().hour < 18:
    system_message = "Good afternoon!"
else:
    system_message = "Good evening!"

# Add a system message to set the bot's personality
system_message += os.getenv('PERSONALITY')
system_message += "When you want to do an action, end the response with <action>action</action>, for example: <action>open the door</action>"


def get_response(user_message):
    client = OpenAI(api_key=os.getenv('OPENAI_KEY'))
    temperature = random.uniform(0.2, 0.8)
    messages = [
        {'role': 'system', 'content': system_message},
        {'role': 'user', 'content': user_message}
    ]

    chat_completion = client.chat.completions.create(
        messages=messages,
        model="gpt-3.5-turbo",
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

    return response, action
