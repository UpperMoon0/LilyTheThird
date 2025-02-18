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
        file_references = []
        if attached_files:
            for file_path in attached_files:
                try:
                    # Open the file in text mode and read its content
                    with open(file_path, "r") as f:
                        file_content = f.read()
                    file_references.append(f"File: {os.path.basename(file_path)}\nContent:\n{file_content}")
                except Exception as e:
                    file_references.append(f"File: {os.path.basename(file_path)} (Error: {str(e)})")

        # Append file attachment contents to the original prompt
        full_prompt = code_snippet
        if file_references:
            full_prompt += "\n\nAttached Files:\n" + "\n\n".join(file_references)

        messages = [{"role": "user", "content": full_prompt}]

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