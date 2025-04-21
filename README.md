# Project Documentation

## Overview
Lily is a comprehensive unified platform that integrates multiple powerful tools into one seamless experience. As a single entity, Lily unifies an LLM-powered chatbot, a feature-rich Discord bot, and VTube Studio integration for virtual avatar control. Lily also supports translation and speech synthesis, providing an all-in-one interface for communication, development, and multimedia interaction. Long-term memory is handled via MongoDB, utilizing **vector embeddings and semantic search** for intelligent information retrieval.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment**:
    *   Copy `.env.template` to `.env`.
    *   Fill in the required values in `.env` (Discord tokens, MongoDB URI, personality settings, etc.).
3.  **Configure LLM API Keys**:
    *   Copy `llm_api_keys.json.template` to `llm_api_keys.json`.
    *   Open `llm_api_keys.json` and add your API keys for the desired providers (e.g., "gemini", "openai"). You can add multiple keys per provider as a list of strings. The application will cycle through these keys using a round-robin strategy.
    ```json
    {
      "gemini": [
        "YOUR_GEMINI_API_KEY_1",
        "YOUR_GEMINI_API_KEY_2"
      ],
      "openai": [
        "YOUR_OPENAI_API_KEY_1"
      ]
    }
    ```
    *   **Important**: Ensure `llm_api_keys.json` is added to your `.gitignore` file to prevent accidentally committing your keys.
4.  **Run TTS Provider (Optional)**: If using Text-to-Speech, ensure the [TTS-Provider](https://github.com/UpperMoon0/TTS-Provider.git) server is running.
5.  **Run MongoDB (Optional)**: If using long-term memory, ensure your MongoDB instance is running and accessible via the `MONGO_URI` in your `.env` file.
6.  **Run Application**:
    ```bash
    python main.py
    ```

## Technologies Used
- Python
- PyQt5
- Discord.py
- SpeechRecognition
- External TTS-Provider (for Text-to-Speech via WebSocket) - Requires separate server.
- Deep Translator (for translation)
- OpenAI and/or Gemini API (via `llm_api_keys.json`)
- pymongo (for MongoDB interaction)
- sentence-transformers (for memory embeddings and semantic search)
- websockets (for VTube Studio integration)

**Note:** Text-to-Speech functionality requires the [TTS-Provider](https://github.com/UpperMoon0/TTS-Provider.git) server to be running locally (default: `ws://localhost:9000`).
**Note:** MongoDB memory requires a running MongoDB instance and the `MONGO_URI` set in the `.env` file.

## Features
- **Chat Tab**:
  - Interact with a chatbot powered by the configured LLM provider (OpenAI or Gemini, keys managed in `llm_api_keys.json`).
  - Translate chatbot responses into Japanese using Deep Translator.
  - Convert Japanese responses into speech via an external TTS-Provider server.
  - Short-term memory: Maintains a prompt history (in-memory).
  - Long-term memory: Stores and retrieves information ("facts") in a MongoDB database using **vector embeddings** (`sentence-transformers`) for **semantic search**. This allows recalling relevant information based on meaning, not just keywords. Requires `MONGO_URI` in `.env`. The LLM can interact with this memory using the `save_memory` and `fetch_memory` tools. Duplicate facts are automatically detected and handled based on semantic similarity.

- **Discord Tab**:
  - Start and stop a Discord bot that responds to messages in a designated channel.
  - The bot utilizes an LLM (provider and model configurable via `.env`, keys managed in `llm_api_keys.json`) to understand and generate responses.
  - The LLM can use specific tools (defined in `llm/discord_llm.py`) to enhance its replies during the main interaction loop, including:
    - `fetch_memory`: Retrieves relevant information from memory using semantic search, returning facts with their unique IDs.
    - `search_web`: Performs web searches.
    - `get_current_time`: Gets the current time.
    # Note: The Discord LLM now explicitly skips the final memory save/update step.

- **VTube Studio Integration (VTube Tab)**:
  - Connect to VTube Studio via websockets to control virtual characters.
