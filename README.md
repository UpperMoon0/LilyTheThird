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
- OpenAI API (for large language model)
- pymongo (for MongoDB interaction)
- websockets (for VTube Studio integration)

**Note:** Text-to-Speech functionality requires the [TTS-Provider](https://github.com/UpperMoon0/TTS-Provider.git) server to be running locally (default: `ws://localhost:9000`).
**Note:** MongoDB memory requires a running MongoDB instance and the `MONGO_URI` set in the `.env` file.

## Features
- **Chat Tab**: 
  - Interact with a chatbot powered by the OpenAI API.
  - Translate chatbot responses into Japanese using Deep Translator.
  - Convert Japanese responses into speech via an external TTS-Provider server.
  - Short-term memory: Maintains a prompt history (in-memory).
  - Long-term memory: Stores conversation turns (user input, LLM response, timestamp, metadata) in a MongoDB database (if enabled and configured).

- **Discord Tab**:
  - Start and stop a Discord bot that responds to messages.
  
- **VTube Studio Integration (VTube Tab)**:
  - Connect to VTube Studio via websockets to control virtual characters.
  
- **Browser Action**: 
  - Open a web browser to search for keywords.

You will need to set the following variables in your .env file for Lily to function correctly:
- `OPENAI_KEY`: Your OpenAI API key.
- `PERSONALITY_TO_MASTER`: Personality instructions for Lily when interacting with your master.
- `PERSONALITY_TO_STRANGER_1`: Personality instructions for Lily when interacting with strangers (part 1).
- `PERSONALITY_TO_STRANGER_2`: Personality instructions for Lily when interacting with strangers (part 2).
- `DISCORD_TOKEN`: The Discord token for your bot.
- `DISCORD_GUILD_ID`: The Discord guild (server) ID where Lily operates.
- `DISCORD_CHANNEL_ID`: The Discord channel ID for communication.
- `MASTER_DISCORD_ID`: Your Discord user ID as Lily's master.
- `LILY_DISCORD_ID`: Lily's assigned Discord user ID.
- `MONGO_URI`: The connection string for your MongoDB database (required for long-term memory). Example: `mongodb+srv://user:pass@cluster.mongodb.net/myDatabase?retryWrites=true&w=majority`

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.
