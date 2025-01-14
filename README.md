# Project Documentation

## Overview
This project is a desktop application built using Python and PyQt5. It features two main tabs: a Chat tab and a Discord tab. The Chat tab allows users to interact with a chatbot that can translate responses into Japanese, convert them to speech using Edge TTS, and play them. The Discord tab integrates a Discord bot that can respond to messages. The application also includes a short-term memory feature for prompt history and a long-term memory feature in the form of a knowledge graph.

## Technologies Used
- Python
- PyQt5
- Discord.py
- asyncio
- threading
- webbrowser
- Speech Recognition
- Edge TTS (Text-to-Speech)
- Translation API (for Japanese translation)
- Knowledge Graph Libraries

## Features
- **Chat Tab**: 
  - Interact with a chatbot.
  - Translate the chatbot’s response into Japanese.
  - Convert the Japanese response into speech using Edge TTS and play it.
  - Short-term memory: Keeps track of recent prompts and responses in a prompt history.
  - Long-term memory: Maintains a knowledge graph that stores information for future use.

- **Discord Tab**: 
  - Start and stop a Discord bot that can respond to messages.

- **Browser Action**: 
  - Open a web browser to search for keywords.

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.
