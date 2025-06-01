# LLM Orchestration Workflow Documentation

This document outlines the workflow for processing user messages using the LLM orchestration system, covering the base logic and specific implementations for the ChatBox and Discord interfaces.

## Core Components

The system relies on several key components managed by the `BaseLLMOrchestrator`:

*   **`LLMClient`**: Handles communication with the underlying Large Language Model (LLM) provider (e.g., OpenAI, Gemini). It loads API keys from `llm_api_keys.json` (see `llm_api_keys.json.template` for the required format) and uses a round-robin strategy to select keys for each API call, helping to mitigate rate limits. Supports structured tool format provision with upfront schema information for both OpenAI's function calling and Gemini's tool configuration.

*   **`ToolOrchestrator`**: A new core component that manages the complete tool execution cycle. It provides upfront tool schema information to LLMs, handles intelligent error analysis and retry logic, and manages the full workflow from tool selection through execution with enhanced context cleaning for final responses.

*   **`HistoryManager`**: Manages the conversation history for the current interaction, storing user messages, assistant replies, and system messages (including tool results). Now includes LLM-powered summarization capabilities for concise history management.

*   **`ToolExecutor`**: Executes the chosen tools with the arguments provided by the LLM. It interacts with specific tool implementations (e.g., file operations, memory access, web search).

*   **`ErrorAnalyzer`**: Provides intelligent error categorization and retry strategy recommendations. Analyzes tool execution failures to determine if retries are worthwhile and generates enhanced retry guidance.

*   **`MongoHandler`**: Manages the connection to the MongoDB database for long-term memory storage and retrieval (used by memory tools within `ToolExecutor`).

*   **`tools.py`**: Defines the available tools, their descriptions, argument schemas (using Pydantic models), and instructions for the LLM.

## Base Workflow (`BaseLLMOrchestrator._process_message`)

This is the core logic inherited and used by both `ChatBoxLLMOrchestrator` and `DiscordLLMOrchestrator`.

1.  **Get Base System Messages**:
    *   Calls the subclass's `_get_base_system_messages` method to retrieve context-specific initial system messages (e.g., personality, current time, user information).

2.  **Automatic Memory Retrieval**:
    *   Calls `_retrieve_and_add_memory_context` using the raw user message as a query.
    *   Performs a similarity search in the MongoDB memory collection via `MongoHandler`.
    *   If relevant facts are found (up to a limit of 3), they are formatted into a system message string (`retrieved_facts_context_string`) with instructions for the LLM to prioritize them. This string is stored for later use.

3.  **Prepare and Add User Message to History**:
    *   Calls the subclass's `_prepare_user_message_for_history` hook (optional modification, e.g., adding user name).
    *   Adds the (potentially modified) user message to the `HistoryManager`.

4.  **Main Tool Interaction Loop (via ToolOrchestrator)**:
    *   **Tool Schema Provision**: The `ToolOrchestrator` prepares structured tool information including complete schemas for all allowed tools and provides them upfront to the LLM.
    *   **Enhanced Tool Selection**: Uses `ToolOrchestrator.execute_tool_cycle()` which:
        *   Adds instructional prompt (`INSTRUCTIONAL_PROMPT_FOR_SCHEMA`) about strict schema adherence
        *   Calls `LLMClient.get_next_action()` with structured tool definitions including full parameter schemas
        *   Handles both tool calls and direct text responses from the LLM
        *   Implements intelligent retry logic for tool selection failures
    *   **Robust Tool Execution**: For each selected tool:
        *   **Error Analysis**: Uses `ErrorAnalyzer` to categorize errors and determine retry strategies
        *   **Enhanced Retry Logic**: Generates detailed retry messages with specific guidance, tool schema information, and examples
        *   **Pattern Detection**: Tracks error patterns to prevent repeated mistakes
        *   **Argument Regeneration**: For argument-related errors, requests new arguments from the LLM with enhanced context
        *   **Escalating Guidance**: Provides progressively more detailed guidance on repeated failures
        *   **Code-Level Error Detection**: Immediately aborts on systematic code issues (TypeError, API mismatches)
    *   **Tool Result Tracking**: Records successful tool executions with timing and detailed metadata using `ToolCallDetails` objects.

5.  **Final Memory Operation Step (Optional: Save or Update)**:
    *   If `_should_perform_final_memory_step()` returns True (ChatBox only, Discord skips this):
        *   Constructs a guidance prompt for memory operation decision
        *   Uses `LLMClient.get_next_action()` forcing choice between `save_memory`, `update_memory`, or `null`
        *   **Enhanced Retry Logic**: Implements retry loop with `FINAL_MEMORY_RETRY` constant:
            *   Uses `ErrorAnalyzer` for intelligent error handling
            *   Provides memory ID references for `update_memory` failures
            *   Tracks retry attempts with escalating delay
            *   Adds retry context messages to help LLM correct mistakes

6.  **Final Response Generation with Context Cleaning**:
    *   **History Filtering**: Processes conversation history to remove tool execution mechanics:
        *   Filters out schema instruction messages (`INSTRUCTIONAL_PROMPT_FOR_SCHEMA`)
        *   Removes tool execution status messages ("System: Calling tool", "System: Retrying tool")
        *   Eliminates raw tool result messages and retry context messages
    *   **Tool Result Summarization**: 
        *   Uses `_summarize_tool_result_for_final_response()` to generate concise, human-readable summaries of tool results
        *   Replaces technical tool outputs with natural language statements (e.g., "I found out that...")
        *   Maintains tool call structure while making results conversational
    *   **Grounding Instruction**: Adds instruction to use provided context and tool outputs appropriately
    *   **Clean Message Construction**: Builds final prompt with:
        *   Primary personality (first base system message)
        *   Other base system messages (excluding tool schema instructions)
        *   Retrieved facts context (if available)
        *   Filtered and summarized conversation history
        *   General grounding instruction
    *   Calls `LLMClient.generate_final_response()` with the cleaned and enhanced context

## Tool Schema Provision and Instruction System

The current system provides comprehensive upfront tool information to LLMs:

*   **Structured Schema Format**: Tools are presented with complete JSON schemas including parameter types, descriptions, and requirements
*   **Provider-Specific Adaptation**: 
    *   **OpenAI**: Uses native function calling format with full parameter schemas
    *   **Gemini**: Converts to `FunctionDeclaration` format with cleaned schemas (removes 'title' fields)
*   **Schema Instruction Prompt**: `INSTRUCTIONAL_PROMPT_FOR_SCHEMA` ensures LLMs understand the importance of strict schema adherence
*   **Context-Specific Guidance**: Adds encouragement for specific tools when forced options are provided

## Error Handling and Retry Strategies

The system implements sophisticated error handling:

*   **Error Categorization**: `ErrorAnalyzer` classifies errors into categories:
    *   `INVALID_ARGUMENT`: Malformed or incorrect argument values
    *   `MISSING_ARGUMENT`: Required arguments not provided
    *   `MEMORY_ID_ERROR`: Invalid memory IDs for update operations
    *   `RESOURCE_NOT_FOUND`: Missing files or resources
    *   `PERMISSION_DENIED`: Access control issues
    *   `CODE_ERROR`: Systematic code-level issues (immediately aborts)
    *   `NETWORK_ERROR`: Connectivity or API issues
    *   `UNKNOWN`: Unclassified errors

*   **Retry Strategy Logic**:
    *   **Pattern Detection**: Tracks recent errors to identify repeated mistakes
    *   **Escalating Guidance**: Provides more detailed help on subsequent failures
    *   **Smart Abort Conditions**: Stops retries for non-recoverable errors
    *   **Enhanced Context**: Includes tool schemas, examples, and specific guidance in retry messages

*   **Retry Constants**:
    *   `TOOL_SELECT_RETRY = 5`: Max retries for tool selection failures
    *   `TOOL_EXECUTION_RETRY = 3`: Max retries for tool execution errors
    *   `FINAL_MEMORY_RETRY = 10`: Max retries for final memory operations
    *   `TOOL_RETRY_DELAY_SECONDS = 2`: Delay between retry attempts

## ChatBox Workflow (`ChatBoxLLMOrchestrator`)

*   **Inheritance**: Inherits from `BaseLLMOrchestrator`
*   **Context Name**: `"chatbox"`
*   **Initialization**: Uses `CHATBOX_LLM_PROVIDER` and `CHATBOX_LLM_MODEL` environment variables. API keys are loaded from `llm_api_keys.json`.
*   **System Messages (`_get_base_system_messages`)**:
    *   Provides only the master personality defined in `PERSONALITY_TO_MASTER`
*   **Allowed Tools (`_get_allowed_tools`)**:
    *   Returns `None`, meaning *all* tools defined in `tools.py` are potentially available
*   **Max Tool Calls (`_get_max_tool_calls`)**:
    *   Uses `CHATBOX_MAX_TOOL_CALLS` environment variable (default: 5)
*   **Tool Exclusions**: Excludes `fetch_memory` and `save_memory` from main loop (handled at specific stages)
*   **Final Memory Step**: Performs final memory save/update check using enhanced retry logic
*   **User Message Preparation (`_prepare_user_message_for_history`)**:
    *   Uses the default implementation (no modification)
*   **Entry Point**: `get_response(user_message)` which calls the base `_process_message` and returns both response and successful tool call details

## Discord Workflow (`DiscordLLMOrchestrator`)

*   **Inheritance**: Inherits from `BaseLLMOrchestrator`
*   **Context Name**: `"discord"`
*   **Initialization**:
    *   Uses `DISCORD_LLM_PROVIDER` and `DISCORD_LLM_MODEL` environment variables. API keys are loaded from `llm_api_keys.json`.
    *   Checks `MASTER_DISCORD_ID` for personality switching.
*   **System Messages (`_get_base_system_messages`)**:
    *   Determines personality based on whether the `discord_user_id` matches `MASTER_DISCORD_ID` (using `PERSONALITY_TO_MASTER` or `PERSONALITY_TO_STRANGER_1`/`_2`)
    *   Includes the interacting user's name, ID, and whether they are the Master
*   **Allowed Tools (`_get_allowed_tools`)**:
    *   Returns a specific list: `DISCORD_ALLOWED_TOOLS` (currently `['fetch_memory', 'search_web', 'get_current_time']`)
*   **Max Tool Calls (`_get_max_tool_calls`)**:
    *   Uses `DISCORD_MAX_TOOL_CALLS` environment variable (default: 3)
*   **Tool Exclusions**: Excludes `fetch_memory`, `save_memory`, and `update_memory` from main loop
*   **Final Memory Step**: **Disabled** - `_should_perform_final_memory_step()` returns `False`, ensuring no memory save/update operations
*   **User Message Preparation (`_prepare_user_message_for_history`)**:
    *   Prepends the message with "`discord_user_name` said: "
*   **Entry Point**: `get_response(user_message, discord_user_id, discord_user_name)` which calls the base `_process_message` with Discord-specific context parameters

## Key Improvements in Current Implementation

1. **Upfront Schema Provision**: LLMs receive complete tool schemas before making decisions, reducing argument generation failures
2. **Enhanced Error Analysis**: Intelligent categorization and retry strategies based on error types
3. **Tool Result Summarization**: Clean, human-readable summaries replace technical tool outputs in final responses
4. **Context Cleaning**: Final responses exclude tool execution mechanics, providing cleaner conversation history
5. **Pattern Detection**: System learns from repeated errors and provides targeted guidance
6. **Code Error Detection**: Immediate abort on systematic issues prevents futile retry attempts
7. **Comprehensive Logging**: Detailed logging across tool orchestration, execution, error analysis, and retry logic
8. **Provider-Specific Optimization**: Tailored approaches for OpenAI and Gemini function calling capabilities
