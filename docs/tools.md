# Tool System Documentation

This document describes the tool system used by the LLM orchestrator, including tool definition, registration, execution, and available tools.

## Core Components

*   **`tools/tools.py`**:
    *   Defines the `ToolDefinition` class, which encapsulates a tool's name, description (for LLM), instruction (for LLM argument formatting), and JSON schema (for argument validation/generation).
    *   Contains the `AVAILABLE_TOOLS` list, where all tools are defined using `ToolDefinition`.
    *   Provides helper functions:
        *   `find_tool(name)`: Looks up a `ToolDefinition` by name.
        *   `get_tool_list_for_prompt(allowed_tools)`: Generates a formatted string of available/allowed tools for the LLM prompt.
        *   `get_tool_names(allowed_tools)`: Returns a list of available/allowed tool names.
*   **`llm/tool_executor.py`**:
    *   Defines the `ToolExecutor` class, responsible for executing tools.
    *   Initializes a `_tool_dispatcher` dictionary mapping tool names (strings) to their corresponding implementation functions (callables). This includes functions from `tools/time_tool.py`, `tools/file_tool.py`, `tools/web_search_tool.py`, and methods from the `MongoHandler` instance for memory tools.
    *   Provides placeholder functions (`_mongo_unavailable`, `_memory_fetch_unavailable`, etc.) for tools that depend on external connections (like MongoDB) if the connection is unavailable.
    *   The `execute(tool_name, arguments)` method:
        *   Looks up the tool function in the dispatcher.
        *   Handles both synchronous and asynchronous tool functions.
        *   Calls the function with the arguments provided by the LLM.
        *   Includes error handling for unknown tools or incorrect arguments.
        *   Calls `_post_process_result` after execution.
    *   The `_post_process_result(tool_name, arguments, result)` method:
        *   Performs specific formatting or actions based on the tool and its result.
        *   Summarizes web search results using the `LLMClient`.
        *   Formats memory fetch results into a readable string with IDs.
        *   Formats memory update results to indicate success/failure and provide the new ID or error details.
        *   Ensures all final results are returned as strings.
*   **Tool Implementation Files** (e.g., `tools/time_tool.py`, `tools/file_tool.py`, `tools/web_search_tool.py`):
    *   Contain the actual Python functions that perform the tool's action.

## Tool Execution Flow (within `BaseLLMOrchestrator._process_message`)

1.  **LLM Decides Tool**: The `LLMClient` determines if a tool should be used and which one (`get_next_action`).
2.  **LLM Generates Arguments**: The `LLMClient` generates the necessary arguments for the chosen tool based on its schema and the conversation history (`get_tool_arguments`).
3.  **Executor Executes**: The `ToolExecutor.execute` method is called with the tool name and arguments.
4.  **Dispatcher Calls Function**: The `ToolExecutor` finds the corresponding function in its `_tool_dispatcher` map.
5.  **Function Runs**: The actual tool implementation function (e.g., `file_tool.read_file`) is executed with the provided arguments.
6.  **Post-Processing**: The `ToolExecutor._post_process_result` method formats the raw result from the function (e.g., summarizes web search, formats memory list).
7.  **Result to History**: The final, formatted string result is added as a system message to the `HistoryManager`.

## Available Tools (Defined in `tools/tools.py`)

*   **`get_current_time`**:
    *   **Description**: Gets the current date and time.
    *   **Arguments**: None (`{}`).
    *   **Implementation**: `tools.time_tool.get_current_time`
*   **`read_file`**:
    *   **Description**: Reads the content of a specified file path.
    *   **Arguments**: `{"file_path": "path/to/file"}`
    *   **Implementation**: `tools.file_tool.read_file`
*   **`write_file`**:
    *   **Description**: Writes content to a specified file path. Overwrites if exists, creates directories if needed.
    *   **Arguments**: `{"file_path": "path/to/file", "content": "file content"}`
    *   **Implementation**: `tools.file_tool.write_file`
*   **`fetch_memory`**:
    *   **Description**: Fetches relevant information from long-term memory based on a query using semantic similarity, returning facts with their unique IDs.
    *   **Arguments**: `{"query": "search query for memory"}`
    *   **Implementation**: `MongoHandler.retrieve_memories_by_similarity` (via `ToolExecutor` dispatcher). Requires MongoDB connection and embedding model.
    *   **Post-processing**: Formats the list of results into a string: "Memory Fetch Results:\n\nID: [id1] | Content: [content1]\n---\nID: [id2] | Content: [content2]..." or "No relevant facts found."
*   **`update_memory`**:
    *   **Description**: Updates the content of an existing memory fact using its unique ID. Deletes the old fact and inserts a new one with the updated content and a new ID.
    *   **Arguments**: `{"memory_id": "existing_fact_id", "new_content": "updated content"}`
    *   **Implementation**: `MongoHandler.update_fact` (via `ToolExecutor` dispatcher). Requires MongoDB connection and embedding model.
    *   **Post-processing**: Returns "Memory replaced successfully. New ID: [new_id]" on success, or an error message like "Memory replacement failed. The provided memory_id '[id]' was not found..." on failure.
*   **`save_memory`**:
    *   **Description**: Saves a piece of information (a new fact) to long-term memory for future recall. Includes a check to prevent saving facts that are too semantically similar to existing ones.
    *   **Arguments**: `{"content": "information to save"}`
    *   **Implementation**: `MongoHandler.add_fact` (via `ToolExecutor` dispatcher). Requires MongoDB connection and embedding model.
*   **`search_web`**:
    *   **Description**: Searches the web using DuckDuckGo based on a query. It attempts to fetch detailed content from result URLs by extracting text from the entire HTML body (excluding script and style tags), falling back to snippets if fetching fails. The combined results are then summarized by the LLM.
    *   **Arguments**: `{"query": "web search query"}`
    *   **Implementation**: `tools.web_search_tool.perform_web_search` (uses `duckduckgo_search` library, `requests`, and `BeautifulSoup`).
    *   **Post-processing**: The raw search results (fetched content or snippets) are summarized by the `LLMClient` within the `ToolExecutor` before being returned.
