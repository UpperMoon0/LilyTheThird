from pydantic import BaseModel, Field
from typing import List, Type, Union, Dict, Optional # Added Dict

# Define a base type for schemas if needed, or adjust as necessary
PydanticSchemaType = Type[BaseModel]

class ActionExtractionSchema(BaseModel):
    """Schema for extracting the next action."""
    action: str = Field(..., description="The determined action to take (e.g., 'none', 'search_web', 'get_current_time').")
    parameters: Dict = Field(default_factory=dict, description="Parameters for the action, conforming to the specific tool's schema if 'action' is a tool.")

# --- Pydantic Schemas for Tool Arguments ---

class GetCurrentTimeArgs(BaseModel):
    pass # No arguments

class ReadFileArgs(BaseModel):
    file_path: str = Field(..., description="The full path to the file to be read.")

class WriteFileArgs(BaseModel):
    file_path: str = Field(..., description="The full path to the file to be written.")
    content: str = Field(..., description="The full content to write into the file.")

class FetchMemoryArgs(BaseModel):
    query: str = Field(..., description="Keywords or description of the information to retrieve from memory.")

class UpdateMemoryArgs(BaseModel):
    memory_id: str = Field(..., description="The unique ID of the memory fact to update.")
    new_content: str = Field(..., description="The new content for the memory fact.")

class SaveMemoryArgs(BaseModel):
    content: str = Field(..., description="The information to store in long-term memory.")

class SearchWebArgs(BaseModel):
    query: str = Field(..., description="The search query to use for finding information on the web.")

# --- End Pydantic Schemas for Tool Arguments ---

# --- Schema for Tool Selection ---
class ToolSelectionSchema(BaseModel):
    tool_name: Optional[str] = Field(default=None, description="The name of the tool to be called, or null/None if no tool is needed.")
# --- End Schema for Tool Selection ---
