# Project Documentation

## Overview
Lily is a comprehensive unified platform that integrates multiple powerful tools into one seamless experience. As a single entity, Lily unifies an LLM-powered chatbot, a feature-rich Discord bot, and VTube Studio integration for virtual avatar control. Lily also supports translation and speech synthesis, providing an all-in-one interface for communication, development, and multimedia interaction. Long-term memory is handled via MongoDB.

## Technologies Used
- Python
- PyQt5
- Discord.py
- SpeechRecognition
- External TTS-Provider (for Text-to-Speech via WebSocket) - Requires separate server.
- Deep Translator (for translation)
- OpenAI and Gemini API (for large language model)
- pymongo (for MongoDB interaction)
- websockets (for VTube Studio integration)

**Note:** Text-to-Speech functionality requires the [TTS-Provider](https://github.com/UpperMoon0/TTS-Provider.git) server to be running locally (default: `ws://localhost:9000`).
**Note:** MongoDB memory requires a running MongoDB instance and the `MONGO_URI` set in the `.env` file.

## Features
- **Chat Tab**: 
  - Interact with a chatbot powered by the OpenAI or Gemini API.
  - Translate chatbot responses into Japanese using Deep Translator.
  - Convert Japanese responses into speech via an external TTS-Provider server.
  - Short-term memory: Maintains a prompt history (in-memory).
  - Long-term memory: Stores conversation history (user input, LLM response, timestamp, metadata) in a MongoDB database, requiring the `MONGO_URI` to be set in the `.env` file.

- **Discord Tab**:
  - Start and stop a Discord bot that responds to messages in a designated channel.
  - The bot utilizes an LLM (configurable via `.env`) to understand and generate responses.
  - The LLM can use specific tools (`fetch_memory`, `search_web`, `get_current_time`) to access information and enhance its replies.

- **VTube Studio Integration (VTube Tab)**:
  - Connect to VTube Studio via websockets to control virtual characters.

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.
