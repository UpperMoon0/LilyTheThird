import json
from pydantic import ValidationError
from typing import Dict, List, Optional

# Assuming schemas and utils are in the same directory or adjust import path
from .schemas import SentenceExtractionSchema, KnowledgeExtractionSchema, KnowledgeTriple
from .llm_utils import call_llm_for_json

MAX_FIELD_LENGTH = 75 # Define max length for triple fields

def extract_knowledge_sentences(
    provider: str,
    client: object,
    model_name: str,
    user_message: str,
    assistant_message: str
) -> List[str]:
    """
    Calls the LLM to extract learned factual sentences from the conversation turn.

    Args:
        provider: The LLM provider ('openai' or 'gemini').
        client: The initialized client object for the provider.
        model_name: The specific model name (required for OpenAI).
        user_message: The user's last message.
        assistant_message: The assistant's last response.

    Returns:
        A list of extracted sentences, or an empty list if extraction fails.
    """
    sentence_prompt = f'''Analyze the following user message and assistant response. Extract ALL distinct factual statements learned or confirmed *only* in this specific exchange. Present these facts as concise, self-contained sentences.

User Message: "{user_message}"
Assistant Response: "{assistant_message}"

Task: Extract all newly learned facts as short sentences.

Constraints:
1.  **Format:** Respond ONLY with a JSON object containing a key "learned_sentences" whose value is an array of strings (the sentences).
2.  **Content:** Each string in the array should be a complete sentence representing a single fact.
3.  **Novelty:** Extract ONLY facts newly established or confirmed in THIS specific user/assistant turn. Do not include information from previous turns unless reiterated here.
4.  **Conciseness:** Keep sentences short and to the point.
5.  **Accuracy:** Base sentences strictly on the provided text. Do NOT infer or invent information.
6.  **Empty:** If NO new facts were learned, the value for "learned_sentences" MUST be an empty array `[]`. Example: `{{"learned_sentences": []}}`.

Example of valid output: `{{"learned_sentences": ["User likes coffee.", "The user's name is Alex.", "Lily provided the weather forecast."]}}`
Example of NO new knowledge: `{{"learned_sentences": []}}`

Output ONLY the required JSON object.'''

    messages: List[Dict] = [{'role': 'system', 'content': sentence_prompt}]
    prompt_content: str = sentence_prompt # For Gemini

    content = call_llm_for_json(
        provider=provider,
        client=client,
        model_name=model_name,
        messages=messages,
        prompt_content=prompt_content,
        pydantic_schema=SentenceExtractionSchema,
        schema_name="sentence_extraction",
        max_tokens=300, # Allow more tokens for potentially multiple sentences
        temperature=0.1
    )

    if content and isinstance(content, dict):
        try:
            validated_data = SentenceExtractionSchema(**content)
            print(f"Extracted Sentences: {validated_data.learned_sentences}")
            return validated_data.learned_sentences
        except ValidationError as e:
            print(f"Validation Error during sentence extraction: {e}")
            return []
    else:
        print("Failed to extract sentences or received invalid format.")
        return []

def convert_sentences_to_triples(
    provider: str,
    client: object,
    model_name: str,
    sentences: List[str]
) -> List[Dict[str, str]]:
    """
    Calls the LLM to convert a list of sentences into knowledge triples.

    Args:
        provider: The LLM provider ('openai' or 'gemini').
        client: The initialized client object for the provider.
        model_name: The specific model name (required for OpenAI).
        sentences: A list of factual sentences to convert.

    Returns:
        A list of validated knowledge triples (as dictionaries), or an empty list.
    """
    if not sentences:
        return []

    triple_prompt = f'''Convert the following list of factual sentences into knowledge triples (subject, predicate, object).

Sentences to Convert:
{json.dumps(sentences, indent=2)}

Task: For each sentence, create one or more corresponding knowledge triples.

Constraints:
1.  **Format:** Respond ONLY with a JSON object containing a key "new_knowledge" whose value is an array of triple objects. Each triple object MUST be `{{"subject": "...", "predicate": "...", "object": "..."}}`.
2.  **Completeness:** ALL three fields (subject, predicate, object) MUST be present and contain non-empty strings for each triple.
3.  **Conciseness:** Keep the strings for subject, predicate, and object SHORT and to the point (e.g., ideally under 10 words each, MAX {MAX_FIELD_LENGTH} chars).
4.  **Accuracy:** Base triples strictly on the meaning of the provided sentences. Do NOT infer or invent information beyond the sentences.
5.  **Empty:** If a sentence cannot be meaningfully converted into a valid triple, omit it. If NO sentences can be converted, the value for "new_knowledge" MUST be an empty array `[]`. Example: `{{"new_knowledge": []}}`.

Example Input Sentences: ["User likes coffee.", "The user's name is Alex."]
Example Output:
`{{"new_knowledge": [
    {{"subject": "User", "predicate": "likes", "object": "coffee"}},
    {{"subject": "User", "predicate": "has name", "object": "Alex"}}
]}}`

Output ONLY the required JSON object.'''

    messages: List[Dict] = [{'role': 'system', 'content': triple_prompt}]
    prompt_content: str = triple_prompt # For Gemini

    content = call_llm_for_json(
        provider=provider,
        client=client,
        model_name=model_name,
        messages=messages,
        prompt_content=prompt_content,
        pydantic_schema=KnowledgeExtractionSchema, # Reusing this schema
        schema_name="triple_conversion",
        max_tokens=400, # Allow more tokens for multiple triples
        temperature=0.1
    )

    final_triples: List[Dict[str, str]] = []
    if content and isinstance(content, dict):
        try:
            validated_data = KnowledgeExtractionSchema(**content)
            # Additional validation for field length and non-empty strings
            for triple_model in validated_data.new_knowledge:
                # triple_dict = triple_model.model_dump() # Convert Pydantic model to dict
                s = triple_model.subject.strip()
                p = triple_model.predicate.strip()
                o = triple_model.object.strip()

                if s and p and o and \
                   len(s) <= MAX_FIELD_LENGTH and \
                   len(p) <= MAX_FIELD_LENGTH and \
                   len(o) <= MAX_FIELD_LENGTH:
                    final_triples.append({"subject": s, "predicate": p, "object": o})
                else:
                    print(f"Warning: Skipping invalid or too long triple: {triple_model.model_dump()}")

            print(f"Converted Triples: {final_triples}")
            return final_triples
        except ValidationError as e:
            print(f"Validation Error during triple conversion: {e}")
            return []
    else:
        print("Failed to convert sentences to triples or received invalid format.")
        return []
