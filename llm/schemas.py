from pydantic import BaseModel, Field
from typing import List, Type, Union

# Define a base type for schemas if needed, or adjust as necessary
PydanticSchemaType = Type[BaseModel]

class ActionExtractionSchema(BaseModel):
    """Schema for extracting the next action."""
    action: str = Field(..., description="The determined action to take (e.g., 'none', 'search_web').")
    parameters: dict = Field(default_factory=dict, description="Optional parameters for the action.")
