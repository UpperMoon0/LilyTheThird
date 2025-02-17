import json
import os
import random
from datetime import datetime
import openai
from dotenv import load_dotenv
from openai import OpenAI
from kg import kg_handler

load_dotenv()

openai.api_key = os.getenv('OPENAI_KEY')

class ChatBoxLLM:
    def __init__(self):
        self.personality = os.getenv('PERSONALITY_TO_MASTER')
        self.model = "gpt-4o-mini-2024-07-18"
        self.message_history = []
        self.client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

    def update_history(self, user_message, assistant_message):
        self.message_history.append({'role': 'user', 'content': user_message})
        self.message_history.append({'role': 'assistant', 'content': assistant_message})
        if len(self.message_history) > 20:
            self.message_history.pop(0)

    def get_response(self, user_message, disable_kg_memory=False):
        related_info_sentences = []
        # If KG is supposed to be used but not yet loaded, disable it.
        if not disable_kg_memory and not kg_handler.knowledge_graph_loaded:
            print("Knowledge graph has to be enabled to use this feature")
            disable_kg_memory = True

        if not disable_kg_memory:
            preflight_messages = [
                {'role': 'system', 'content': "Do not answer the user message! Provide an array of at most 5 keywords related to the user message."},
                {'role': 'user', 'content': user_message},
            ]
            preflight_response = self.client.chat.completions.create(
                messages=preflight_messages,
                model=self.model,
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
        self.current_time = datetime.now()
        self.current_date_time = self.current_time.strftime("%Y-%m-%d %H:%M:%S")
        main_messages = [
            {'role': 'system', 'content': self.personality},
            {'role': 'system', 'content': f"Current date and time: {self.current_date_time}"},
            {'role': 'system', 'content': "Provide a short action query, including action and object (e.g., 'play voice'):"}
        ]
        if not disable_kg_memory:
            main_messages.append({'role': 'system', 'content': "Here is some information that might be related to the user message, however, not all of them are relevant:"})
            for sentence in related_info_sentences:
                main_messages.append({'role': 'system', 'content': sentence})
        for message in self.message_history:
            main_messages.append(message)
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
        main_response = self.client.chat.completions.create(
            messages=main_messages,
            model=self.model,
            max_tokens=500,
            temperature=random.uniform(0.2, 0.8),
            response_format=response_format
        )
        main_res_content = json.loads(main_response)
        message = main_res_content.get("message")
        action = main_res_content.get("actions")
        self.update_history(user_message, message)
        return message, action