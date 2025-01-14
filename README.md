# Project Documentation

## Overview
This desktop application enables users to interact with a chatbot and a Discord bot. The app supports translation, speech synthesis, and maintains short-term and long-term memory.

## Technologies Used
- Python
- PyQt5
- Discord.py
- asyncio
- threading
- webbrowser
- Speech Recognition
- Edge TTS (Text-to-Speech)
- Deep Translator (for translation)
- OpenAI API (for large language model)
- Knowledge Graph Libraries

## Features
- **Chat Tab**: 
  - Interact with a chatbot powered by OpenAI API.
  - Translate chatbot responses into Japanese using Deep Translator.
  - Convert Japanese responses into speech using Edge TTS and play it.
  - Short-term memory: Keeps track of recent prompts and responses in a prompt history.
  - Long-term memory: Stores information in a knowledge graph for future use.

- **Discord Tab**: 
  - Start and stop a Discord bot that responds to messages.

- **Browser Action**: 
  - Open a web browser to search for keywords.

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.
