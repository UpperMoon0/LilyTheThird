import json
from pydantic import ValidationError # Assuming pydantic might be useful here too, or just use dict checks
from typing import Union # Import Union

# --- Existing kg_handler code ---
# Placeholder for knowledge graph handling functions
knowledge_graph_loaded = False

def load_knowledge_graph():
    global knowledge_graph_loaded
    # ... implementation ...
    knowledge_graph_loaded = True
    print("Knowledge graph loaded.")

def add_triples_to_graph(triples):
    if not knowledge_graph_loaded:
        print("Warning: Knowledge graph not loaded. Cannot add triples.")
        return
    # ... implementation ...
    print(f"Added {len(triples)} triples to graph.") # Assuming this exists

def get_related_info_from_keywords(keywords):
    if not knowledge_graph_loaded:
        print("Warning: Knowledge graph not loaded. Cannot retrieve info.")
        return []
    # ... implementation ...
    print(f"Retrieving info for keywords: {keywords}") # Assuming this exists
    # Replace with actual implementation if available
    return [f"Info related to {kw}" for kw in keywords if kw]


# --- New Triple Processing Function ---

def process_raw_knowledge_response(raw_content: dict, previously_extracted_triples: list, max_field_length: int) -> Union[dict, list, None]: # Use Union
    """
    Processes the raw JSON dictionary from the LLM for knowledge extraction.

    Args:
        raw_content: The parsed JSON dictionary from the LLM response.
        previously_extracted_triples: A list of triples already extracted in this session.
        max_field_length: Maximum allowed character length for subject, predicate, object.

    Returns:
        - dict: A single, validated, truncated, non-duplicate triple if found.
        - list: An empty list [] if the LLM response explicitly indicates no more triples.
        - None: If the input is invalid, malformed, contains a duplicate,
                or doesn't adhere to the expected format (0 or 1 triple).
    """
    try:
        if not isinstance(raw_content, dict) or "new_knowledge" not in raw_content or not isinstance(raw_content["new_knowledge"], list):
            print(f"Warning: Invalid structure in raw LLM response: {raw_content}")
            return None # Invalid structure

        knowledge_list = raw_content["new_knowledge"]

        if len(knowledge_list) == 0:
            print("Info: LLM indicated no more triples.")
            return [] # Signal no more triples found

        if len(knowledge_list) > 1:
            print(f"Warning: LLM returned {len(knowledge_list)} triples, expected 0 or 1. Stopping extraction.")
            return None # Incorrect number of triples

        # Process the single triple
        triple_dict = knowledge_list[0]
        if not isinstance(triple_dict, dict) or not all(k in triple_dict for k in ["subject", "predicate", "object"]):
            print(f"Warning: Skipping malformed triple object: {triple_dict}")
            return None # Malformed triple

        subj = str(triple_dict.get("subject", "")).strip()
        pred = str(triple_dict.get("predicate", "")).strip()
        obj = str(triple_dict.get("object", "")).strip()

        # Truncate if necessary
        if len(subj) > max_field_length: subj = subj[:max_field_length] + "..."
        if len(pred) > max_field_length: pred = pred[:max_field_length] + "..."
        if len(obj) > max_field_length: obj = obj[:max_field_length] + "..."

        # Check for completeness after processing
        if not (subj and pred and obj):
            print(f"Warning: Skipping incomplete triple after processing: {triple_dict}")
            return None # Incomplete triple after processing

        processed_triple = {"subject": subj, "predicate": pred, "object": obj}

        # Check for duplicates
        for existing_triple in previously_extracted_triples:
            if existing_triple == processed_triple:
                print(f"Info: Duplicate triple found: {processed_triple}")
                return None # Duplicate found

        # If all checks pass, return the processed triple
        return processed_triple

    except Exception as e:
        print(f"Error during raw knowledge processing: {e}")
        return None # General processing error
