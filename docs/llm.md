# LLM Orchestration Workflow Documentation

This document outlines the workflow for processing user messages using the LLM orchestration system, covering the base logic and specific implementations for the ChatBox and Discord interfaces.

## Core Components

The system relies on several key components managed by the `BaseLLMOrchestrator`:

*   **`LLMClient`**: Handles communication with the underlying Large Language Model (LLM) provider (e.g., OpenAI, Gemini). It loads API keys from `llm_api_keys.json` (see `llm_api_keys.json.template` for the required format) and uses a round-robin strategy to select keys for each API call, helping to mitigate rate limits. It's responsible for generating responses, deciding on tool usage, and extracting tool arguments.
*   **`HistoryManager`**: Manages the conversation history for the current interaction, storing user messages, assistant replies, and system messages (including tool results).
*   **`ToolExecutor`**: Executes the chosen tools with the arguments provided by the LLM. It interacts with specific tool implementations (e.g., file operations, memory access, web search).
*   **`MongoHandler`**: Manages the connection to the MongoDB database for long-term memory storage and retrieval (used by memory tools within `ToolExecutor`).
*   **`tools.py`**: Defines the available tools, their descriptions, instructions for the LLM, and argument schemas.

## Base Workflow (`BaseLLMOrchestrator._process_message`)

This is the core logic inherited and used by both `ChatBoxLLM` and `DiscordLLM`.

1.  **Get Base System Messages**:
    *   Calls the subclass's `_get_base_system_messages` method to retrieve context-specific initial system messages (e.g., personality, current time, user information).

2.  **Automatic Memory Retrieval**:
    *   Calls `_retrieve_and_add_memory_context` using the raw user message as a query.
    *   Performs a similarity search in the MongoDB memory collection via `MongoHandler`.
    *   If relevant facts are found (up to a limit of 3), they are formatted into a system message string (`retrieved_facts_context_string`) with instructions for the LLM to prioritize them. This string is stored for later use.

3.  **Prepare and Add User Message to History**:
    *   Calls the subclass's `_prepare_user_message_for_history` hook (optional modification, e.g., adding user name).
    *   Adds the (potentially modified) user message to the `HistoryManager`.

4.  **Main Tool Interaction Loop**:
    *   Retrieves the list of tools allowed by the subclass (`_get_allowed_tools`).
    *   Filters this list to exclude memory tools (`fetch_memory`, `save_memory`, `update_memory`) for this main loop.
    *   Determines the maximum number of tool calls allowed (`_get_max_tool_calls`).
    *   Enters a loop that runs up to `max_tool_calls`:
        *   Gets the current history from `HistoryManager`.
        *   Asks the `LLMClient` for the next action (`get_next_action`), providing the history and the *filtered* list of allowed tools.
        *   **If LLM chooses a tool**:
            *   Retrieves the tool definition from `tools.py`.
            *   Asks `LLMClient` to generate arguments (`get_tool_arguments`) based on the history and tool definition.
            *   Executes the tool via `ToolExecutor.execute` with the generated arguments.
            *   **Retry Logic for `update_memory`**: If `update_memory` fails due to an invalid ID, it retries argument generation and execution once, providing the previously retrieved facts as context.
            *   Adds a system message containing the tool name, arguments, and result (or error) to `HistoryManager`.
            *   Increments the tool call counter.
            *   Breaks the loop if a non-retryable tool error occurs.
        *   **If LLM chooses `null` (no tool)**: Breaks the loop.
        *   **If LLM returns an error or invalid format**: Breaks the loop.
        *   **If max tool calls reached**: Breaks the loop.

5.  **Final Memory Operation Step (Optional: Save or Update)**:
    *   Gets the current history.
    *   Creates a specific system prompt guiding the LLM:
        *   Use `save_memory` for new information.
        *   Use `update_memory` for existing information (referencing retrieved facts if available).
        *   Choose `null` if no memory operation is needed.
    *   Appends this guidance prompt (and retrieved facts context, if any) to the messages.
    *   Asks `LLMClient` for the next action (`get_next_action`), forcing the choice between `save_memory`, `update_memory`, or `null`. The full list of tools allowed by the subclass (`allowed_tools_overall`) is considered here.
    *   **If LLM chooses `save_memory` or `update_memory`**:
        *   Retrieves the tool definition.
        *   Retrieves the tool definition.
        *   **Retry Logic**: Enters a retry loop controlled by the `FINAL_MEMORY_RETRY` constant (defined in `base_llm.py`).
            *   Asks `LLMClient` for arguments (`get_tool_arguments`) using the history *including* the guidance prompt and any previous error context from this step.
            *   Executes the chosen memory tool via `ToolExecutor.execute`.
            *   If argument generation or execution fails, it retries up to `FINAL_MEMORY_RETRY` times, adding error context for the LLM on subsequent attempts.
        *   Adds a system message with the tool name, arguments, and final result (or error after retries) to `HistoryManager`.
    *   **If LLM chooses `null`**: Logs that no final memory operation was needed.

6.  **Final Response Generation**:
    *   Gets the final history (including results from Step 5).
    *   Constructs the final list of messages for the LLM:
        *   Primary personality (first message from Step 1).
        *   Other base system messages (time, user info, etc.).
        *   Main conversation history (user messages, assistant replies, tool results from Step 4 & 5).
        *   The `retrieved_facts_context_string` (from Step 2), if any.
    *   Calls `LLMClient.generate_final_response` with the constructed messages.
    *   Adds the final assistant message to `HistoryManager`.
    *   Returns the final assistant message string.

## ChatBox Workflow (`ChatBoxLLM`)

*   **Inheritance**: Inherits from `BaseLLMOrchestrator`.
*   **Context Name**: `"chatbox"`
*   **Initialization**: Uses `CHATBOX_LLM_PROVIDER` and `CHATBOX_LLM_MODEL` environment variables. API keys are loaded from `llm_api_keys.json`.
*   **System Messages (`_get_base_system_messages`)**:
    *   Provides only the master personality defined in `PERSONALITY_TO_MASTER`.
*   **Allowed Tools (`_get_allowed_tools`)**:
    *   Returns `None`, meaning *all* tools defined in `tools.py` are potentially available (subject to filtering in the main loop and final step).
*   **Max Tool Calls (`_get_max_tool_calls`)**:
    *   Uses `CHATBOX_MAX_TOOL_CALLS` environment variable (default: 5).
*   **User Message Preparation (`_prepare_user_message_for_history`)**:
    *   Uses the default implementation (no modification).
*   **Entry Point**: `get_response(user_message)` which calls the base `_process_message`.

## Discord Workflow (`DiscordLLM`)

*   **Inheritance**: Inherits from `BaseLLMOrchestrator`.
*   **Context Name**: `"discord"`
*   **Initialization**:
    *   Uses `DISCORD_LLM_PROVIDER` and `DISCORD_LLM_MODEL` environment variables. API keys are loaded from `llm_api_keys.json`.
    *   Checks `MASTER_DISCORD_ID` for personality switching.
*   **System Messages (`_get_base_system_messages`)**:
    *   Determines personality based on whether the `discord_user_id` matches `MASTER_DISCORD_ID` (using `PERSONALITY_TO_MASTER` or `PERSONALITY_TO_STRANGER_1`/`_2`).
    *   Includes the current date and time.
    *   Includes the interacting user's name, ID, and whether they are the Master.
*   **Allowed Tools (`_get_allowed_tools`)**:
    *   Returns a specific list: `DISCORD_ALLOWED_TOOLS` (currently defined as `['fetch_memory', 'search_web', 'get_current_time']`).
    *   *Note*: The `DiscordLLM` overrides the base `_process_message` method to explicitly *skip* the final memory save/update step (Step 5), ensuring only the tools listed in `DISCORD_ALLOWED_TOOLS` (excluding `fetch_memory` during the main loop) are ever considered or executed in the Discord context.
*   **Max Tool Calls (`_get_max_tool_calls`)**:
    *   Uses `DISCORD_MAX_TOOL_CALLS` environment variable (default: 3).
*   **User Message Preparation (`_prepare_user_message_for_history`)**:
    *   Prepends the message with "`discord_user_name` said: ".
*   **Entry Point**: `get_response(user_message, discord_user_id, discord_user_name)` which calls the base `_process_message`, passing the Discord-specific user details.
