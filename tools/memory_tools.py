
# -*- coding: utf-8 -*-
"""
Defines tools related to interacting with the MongoDB long-term memory.
Includes prompts for the LLM regarding memory usage during the conversation flow.
"""

class ToolDefinition:
    """Represents an available tool for the LLM."""
    def __init__(self, name: str, description: str, instruction: str, json_schema: dict):
        """
        Initializes a ToolDefinition.

        Args:
            name: The unique identifier for the tool.
            description: A brief description for the LLM to understand the tool's purpose.
            instruction: Detailed instructions for the LLM on how to format the arguments for this tool.
            json_schema: A dictionary representing the JSON schema for the expected arguments.
        """
        self.name = name
        self.description = description
        self.instruction = instruction # Detailed prompt for how to use the tool
        self.json_schema = json_schema # Expected JSON format for arguments

# Define Memory-Specific Tools
AVAILABLE_TOOLS = [
    ToolDefinition(
        name="fetch_memory",
        description="Fetches relevant information from long-term memory based on a query.",
        instruction="Provide a query describing the information you need from long-term memory. Respond with a JSON object containing the 'query' key. Example: {\"query\": \"details about project X discussed last week\"}",
        json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords or description of the information to retrieve from memory."
                }
            },
            "required": ["query"]
        }
    ),
    ToolDefinition(
        name="save_memory",
        description="Saves a piece of information to long-term memory for future recall.",
        instruction="Provide the specific information you want to save to long-term memory. Respond with a JSON object containing the 'content' key. Example: {\"content\": \"User prefers concise answers.\"}",
        json_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to store in long-term memory."
                }
            },
            "required": ["content"]
        }
    ),
    # Add other general tools if they should be available alongside memory tools
    # Example: Copying from the 'tools' file content if needed
    # ToolDefinition(
    #     name="get_current_time",
    #     description="Gets the current date and time.",
    #     instruction="Indicate you want the current time. Respond with an empty JSON object {}.",
    #     json_schema={
    #         "type": "object",
    #         "properties": {},
    #         "required": []
    #     }
    # ),
]

# --- Prompt Integration ---

MEMORY_FETCH_PROMPT = "Before formulating your response, do you need to fetch any specific information from your long-term memory based on the user's message or the conversation history? If yes, use the 'fetch_memory' tool."
# Note: The prompt to ask the LLM about *saving* memory should ideally be presented *after* it has generated its primary response
# but *before* finalizing the turn. This logic usually resides in the main chat processing loop (e.g., in chatbox_llm.py or views/chat_tab.py).

def get_tool_list_for_prompt() -> str:
    """
    Formats the memory fetch prompt and the list of tools for inclusion in the LLM prompt.
    """
    prompt_lines = [MEMORY_FETCH_PROMPT]

    if not AVAILABLE_TOOLS:
        prompt_lines.append("No tools available.")
    else:
        prompt_lines.append("\nAvailable Tools:")
        for tool in AVAILABLE_TOOLS:
            prompt_lines.append(f"- {tool.name}: {tool.description}")

    # Add instructions on how to use tools in general (optional but helpful)
    prompt_lines.append("\nTo use a tool, respond ONLY with a JSON object matching the tool's instruction format.")
    prompt_lines.append("Example for fetch_memory: {\"tool_name\": \"fetch_memory\", \"arguments\": {\"query\": \"search terms\"}}")
    prompt_lines.append("Example for save_memory: {\"tool_name\": \"save_memory\", \"arguments\": {\"content\": \"information to save\"}}")

    return "\n".join(prompt_lines)

# --- Tool Lookup ---

def find_tool(name: str) -> ToolDefinition | None:
    """
    Finds a tool definition by its name.

    Args:
        name: The name of the tool to find.

    Returns:
        The ToolDefinition object if found, otherwise None.
    """
    for tool in AVAILABLE_TOOLS:
        if tool.name == name:
            return tool
    return None

def get_tool_names() -> list[str]:
    """Returns a list of names of all available tools."""
    return [tool.name for tool in AVAILABLE_TOOLS]

# --- Placeholder for Tool Execution Logic ---
# This file defines the tools. The actual execution logic (calling MongoHandler)
# would typically be in a separate module or within the main application logic
# that handles tool calls identified by the LLM.
