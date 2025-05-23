from typing import List, Optional, Type
from pydantic import BaseModel
# Import the new argument schemas
from llm.schemas import (
    GetCurrentTimeArgs,
    ReadFileArgs,
    WriteFileArgs,
    FetchMemoryArgs,
    UpdateMemoryArgs,
    SaveMemoryArgs,
    SearchWebArgs
)


class ToolDefinition:
    """Represents an available tool for the LLM."""
    def __init__(self, name: str, description: str, argument_schema: Optional[Type[BaseModel]]):
        """
        Initializes a ToolDefinition.

        Args:
            name: The unique identifier for the tool.
            description: A brief description for the LLM to understand the tool's purpose.
            argument_schema: The Pydantic model for the expected arguments. None if no arguments.
        """
        self.name = name
        self.description = description
        self.argument_schema = argument_schema # Store the Pydantic model

AVAILABLE_TOOLS = [
    ToolDefinition(
        name="get_current_time",
        description="Gets the current date and time.",
        argument_schema=GetCurrentTimeArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="read_file",
        description="Reads the content of a specified file path.",
        argument_schema=ReadFileArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="write_file",
        description="Writes content to a specified file path. Overwrites the file if it exists, creates directories if they don't exist.",
        argument_schema=WriteFileArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="fetch_memory",
        description="Fetches relevant information from long-term memory based on a query, returning facts with their unique IDs. Prioritize using this over 'search_web' and your general knowledge.",
        argument_schema=FetchMemoryArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="update_memory",
        description="Updates the content of an existing memory fact using its unique ID. Prioritize using this over 'save_memory' for existing facts.",
        argument_schema=UpdateMemoryArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="save_memory",
        description="Saves a piece of information to long-term memory for future recall. This is only for new facts.",
        argument_schema=SaveMemoryArgs # Use Pydantic model
    ),
    ToolDefinition(
        name="search_web",
        description="Searches the web for information based on a query and summarizes the findings from multiple relevant pages. Only use this if the information is not available in memory or your general knowledge.",
        argument_schema=SearchWebArgs # Use Pydantic model
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
