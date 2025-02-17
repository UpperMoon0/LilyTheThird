import os
import openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class IdeLLM:
    def __init__(self):
        self.model = "gpt-4o-mini-2024-07-18"
        self.client = OpenAI(api_key=os.getenv('OPENAI_KEY'))

    def get_response(self, code_snippet: str, attached_files: list = None) -> str:
        # Prepare file attachments if any
        file_attachments = []
        if attached_files:
            for file_path in attached_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_attachments.append({
                        "filename": os.path.basename(file_path),
                        "content": content
                    })
                except Exception as e:
                    file_attachments.append({
                        "filename": os.path.basename(file_path),
                        "content": f"Error reading file: {str(e)}"
                    })

        messages = [
            {"role": "user", "content": code_snippet, "files": file_attachments}
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