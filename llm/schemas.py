from pydantic import BaseModel, Field
from typing import List, Type, Union

# Define a base type for schemas if needed, or adjust as necessary
PydanticSchemaType = Type[BaseModel]

class KnowledgeTriple(BaseModel):
    """Represents a Subject-Predicate-Object triple for the knowledge graph."""
    subject: str = Field(..., description="The subject entity of the triple.")
    predicate: str = Field(..., description="The relationship or property connecting the subject and object.")
    object: str = Field(..., description="The object entity or value related to the subject.")

class KeywordSchema(BaseModel):
    """Schema for extracting keywords."""
    keywords: List[str] = Field(..., description="A list of extracted keywords.")

class ActionExtractionSchema(BaseModel):
    """Schema for extracting the next action."""
    action: str = Field(..., description="The determined action to take (e.g., 'none', 'search_web').")
    parameters: dict = Field(default_factory=dict, description="Optional parameters for the action.")

class SentenceExtractionSchema(BaseModel):
    """Schema for extracting relevant sentences for knowledge."""
    learned_sentences: List[str] = Field(..., description="List of sentences containing potential new knowledge.")

class KnowledgeExtractionSchema(BaseModel):
    """Schema for extracting structured knowledge triples from sentences."""
    triples: List[KnowledgeTriple] = Field(..., description="A list of extracted knowledge triples.")

# You might need other schemas or adjustments based on actual usage.
