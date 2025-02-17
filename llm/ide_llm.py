import os
import openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class IdeLLM:
    def __init__(self):
        self.model = "gpt-4o-mini-2024-07-18"
        self.client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

    def get_response(self, code_snippet: str) -> str:
        messages = [
            {"role": "user", "content": code_snippet},
        ]
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                max_tokens=300,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"