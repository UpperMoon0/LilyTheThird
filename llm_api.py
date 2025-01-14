import json
import os
import random
from datetime import datetime
import openai
from dotenv import load_dotenv
from openai import OpenAI
from kg import kg_handler

load_dotenv()

# Set up OpenAI
openai.api_key = os.getenv('OPENAI_KEY')

# Set the system message based on the current time
current_time = datetime.now()

# Format the current date and time
current_date_time = current_time.strftime("%Y-%m-%d %H:%M:%S")

# Add the greeting and the current date and time to the system message
personality = os.getenv('PERSONALITY')

model = "gpt-4o-mini-2024-07-18"

# History of last 5 user-assistant messages
message_history = []

def update_history(user_message, assistant_message):
    """Update message history, keeping only the last 5 message pairs"""
    message_history.append({'role': 'user', 'content': user_message})
    message_history.append({'role': 'assistant', 'content': assistant_message})

    # Keep only the last 10 messages (user + assistant pairs)
    if len(message_history) > 20:
        message_history.pop(0)

def get_response(user_message, disable_kg_memory=False):
    client = OpenAI(api_key=os.getenv('OPENAI_KEY'))
    related_info_sentences = []

    # If knowledge graph memory is disabled, skip the preflight request and related info search
    if not disable_kg_memory:
        # Preflight request to ask for keywords related to the user message
        preflight_messages = [
            {'role': 'system', 'content': "Do not answer the user message! Provide an array of at most 5 keywords related to the user message."},
            {'role': 'user', 'content': user_message},
        ]

        preflight_response = client.chat.completions.create(
            messages=preflight_messages,
            model=model,
            max_tokens=50,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "preflight_response",
                    "strict": True,
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
        keywords = preflight_res_content.get("keywords")
        related_info_sentences = kg_handler.get_related_info_from_keywords(keywords)
        for sentence in related_info_sentences:
            print(sentence)

    # Collect messages for the main request
    main_messages = [
        {'role': 'system', 'content': personality},
        {'role': 'system', 'content': f"Current date and time: {current_date_time}"}
    ]

    if not disable_kg_memory:
        main_messages.append({'role': 'system', 'content': "Here is some information that might be related to the user message, however, not all of them are relevant:"})
        for sentence in related_info_sentences:
            main_messages.append({'role': 'system', 'content': sentence})

    # Add historical user-assistant pairs
    for message in message_history:
        main_messages.append(message)

    # Add the current user message
    main_messages.append({'role': 'user', 'content': user_message})

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "custom_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "actions": {"type": "string"},
                },
                "required": ["message", "actions"],
                "additionalProperties": False
            }
        }
    }

    # Request the response from the model
    main_response = client.chat.completions.create(
        messages=main_messages,
        model=model,
        max_tokens=500,
        temperature=random.uniform(0.2, 0.8),
        response_format=response_format
    ).choices[0].message.content

    print("Main response: ", main_response)

    # Parse the JSON response
    main_res_content = json.loads(main_response)

    message = main_res_content.get("message")
    action = main_res_content.get("actions")

    # Update history with the user message and assistant's message
    update_history(user_message, message)

    return message, action
