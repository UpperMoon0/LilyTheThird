# Project Documentation

## Overview
Lily is a comprehensive unified platform that integrates multiple powerful tools into one seamless experience. As a single entity, Lily unifies an LLM-powered chatbot, a feature-rich Discord bot, interactive Knowledge Graph visualization, and VTube Studio integration for virtual avatar control. Lily also supports translation and speech synthesis, providing an all-in-one interface for communication, development, and multimedia interaction.

## Technologies Used
- Python
- PyQt5
- Discord.py
- SpeechRecognition
- Edge TTS (Text-to-Speech)
- Deep Translator (for translation)
- OpenAI API (for large language model)
- spaCy and rdflib (for knowledge graph processing)
- websockets (for VTube Studio integration)

## Features
- **Chat Tab**: 
  - Interact with a chatbot powered by the OpenAI API.
  - Translate chatbot responses into Japanese using Deep Translator.
  - Convert Japanese responses into speech using Edge TTS.
  - Short-term memory: Maintains a prompt history.
  - Long-term memory: Stores information in a Knowledge Graph.
  
- **Knowledge Graph Tab**:
  - Visualize and interact with the Knowledge Graph built from user interactions.
  
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

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.
