from typing import List, Optional


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

AVAILABLE_TOOLS = [
    ToolDefinition(
        name="get_current_time",
        description="Gets the current date and time.",
        instruction="Indicate you want the current time. Respond with an empty JSON object {}.",
        json_schema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    ToolDefinition(
        name="read_file",
        description="Reads the content of a specified file path.",
        instruction="Provide the exact path of the file you want to read. Respond with a JSON object containing the 'file_path' key. Example: {\"file_path\": \"C:/Users/Example/Documents/notes.txt\"}",
        json_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The full path to the file to be read."
                }
            },
            "required": ["file_path"]
        }
    ),
    ToolDefinition(
        name="write_file",
        description="Writes content to a specified file path. Overwrites the file if it exists, creates directories if they don't exist.",
        instruction="Provide the exact path of the file you want to write to and the full content to write. Respond with a JSON object containing the 'file_path' and 'content' keys. Example: {\"file_path\": \"C:/Users/Example/Documents/new_notes.txt\", \"content\": \"This is the content of the file.\"}",
        json_schema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The full path to the file to be written."
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write into the file."
                }
            },
            "required": ["file_path", "content"]
        }
    ),
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
    ToolDefinition(
        name="search_web",
        description="Searches the web for information based on a query and summarizes the findings from multiple relevant pages.",
        instruction="Provide a clear and concise search query. Respond with a JSON object containing the 'query' key. Example: {\"query\": \"latest advancements in AI research\"}",
        json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to use for finding information on the web."
                }
            },
            "required": ["query"]
        }
    ),
# Add more tools here as needed
]

# Global map for quick lookup
_TOOL_MAP = {tool.name: tool for tool in AVAILABLE_TOOLS}

def get_tool_list_for_prompt(allowed_tools: Optional[List[str]] = None) -> str:
    """
    Formats the list of tools (name and description) for inclusion in the initial LLM prompt,
    optionally filtering by a list of allowed tool names.

    Args:
        allowed_tools: An optional list of tool names to include. If None, all tools are included.

    Returns:
        A formatted string describing the available (and allowed) tools.
    """
    tools_to_describe = AVAILABLE_TOOLS
    if allowed_tools is not None:
        allowed_set = set(allowed_tools)
        tools_to_describe = [tool for tool in AVAILABLE_TOOLS if tool.name in allowed_set]

    if not tools_to_describe:
        return "No tools available or allowed for this context."

    tool_descriptions = ["Available Tools:"]
    for tool in tools_to_describe:
        tool_descriptions.append(f"- {tool.name}: {tool.description}")
    return "\n".join(tool_descriptions)

def find_tool(name: str) -> Optional[ToolDefinition]:
    """
    Finds a tool definition by its name.

    Args:
        name: The name of the tool to find.

    Returns:
        The ToolDefinition object if found, otherwise None.
    """
    # Use the pre-built map for faster lookup
    return _TOOL_MAP.get(name)


def get_tool_names(allowed_tools: Optional[List[str]] = None) -> List[str]:
    """
    Returns a list of names of available tools, optionally filtered.

    Args:
        allowed_tools: An optional list of tool names to include. If None, all tool names are returned.

    Returns:
        A list of available (and allowed) tool names.
    """
    if allowed_tools is None:
        return list(_TOOL_MAP.keys())
    else:
        # Ensure we only return names that actually exist in our defined tools
        allowed_set = set(allowed_tools)
        return [name for name in _TOOL_MAP if name in allowed_set]
