import json
from typing import Dict, List, Optional, Type
from pydantic import ValidationError, BaseModel
import google.generativeai as genai
from openai import OpenAI

# Define PydanticSchemaType more robustly if needed, for now Type[BaseModel] works
PydanticSchemaType = Type[BaseModel]

def call_llm_for_json(
    provider: str,
    client: object, # The initialized OpenAI or Gemini client/model object
    model_name: str,
    messages: List[Dict], # Primarily for OpenAI structure
    prompt_content: str, # Primarily for Gemini structure (can be derived from messages if needed)
    pydantic_schema: PydanticSchemaType,
    schema_name: str, # Name for logging/error messages
    max_tokens: int = 150,
    temperature: float = 0.2,
    skip_validation: bool = False # Add parameter to skip validation
) -> Optional[Dict]:
    """
    Calls the appropriate LLM provider, requesting a JSON response that conforms
    to the provided Pydantic schema.

    Args:
        provider: 'openai' or 'gemini'.
        client: Initialized LLM client object (OpenAI() or GenerativeModel()).
        model_name: The specific model name.
        messages: List of message dictionaries (OpenAI format).
        prompt_content: Single string prompt (often used for Gemini).
        pydantic_schema: The Pydantic model class for validation.
        schema_name: A descriptive name for the schema (for logging).
        max_tokens: Maximum tokens for the response.
        temperature: Sampling temperature.

    Returns:
        A dictionary containing the validated JSON data, or None if an error occurs
        (API error, JSON decoding error, or Pydantic validation error).
    """
    response_text = None
    try:
        if provider == 'openai':
            # Ensure the last message instructs JSON output based on the schema
            # Add schema description to the prompt if not already there
            schema_json_str = pydantic_schema.model_json_schema()
            instruction = f"Respond ONLY with a valid JSON object matching the following schema. Do not include explanations or markdown formatting:\n```json\n{json.dumps(schema_json_str, indent=2)}\n```"

            # Check if instruction is already in the last message, if not, append/modify
            if messages[-1]['role'] == 'system':
                 messages[-1]['content'] += f"\n\n{instruction}"
            else:
                 # Append a new system message with the instruction
                 messages.append({'role': 'system', 'content': instruction})

            # Make sure the client object is the OpenAI client
            if not isinstance(client, OpenAI):
                print(f"Error: Expected OpenAI client, got {type(client)}")
                return None

            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"} # Use OpenAI's JSON mode
            )
            response_text = response.choices[0].message.content

        elif provider == 'gemini':
            # Ensure the prompt instructs JSON output based on the schema
            schema_json_str = pydantic_schema.model_json_schema()
            instruction = f"Respond ONLY with a valid JSON object matching the following schema. Do not include explanations or markdown formatting (like ```json ... ```):\n```json\n{json.dumps(schema_json_str, indent=2)}\n```"

            # Combine the original prompt content with the JSON instruction
            full_prompt = f"{prompt_content}\n\n{instruction}"

            # Make sure the client object is the Gemini model
            if not isinstance(client, genai.GenerativeModel):
                 print(f"Error: Expected Gemini GenerativeModel, got {type(client)}")
                 return None

            # Gemini doesn't have a dedicated JSON mode via start_chat like OpenAI
            # We rely on prompt engineering.
            # Note: History adaptation for Gemini JSON calls might need specific handling
            # if context from previous turns is crucial for the JSON structure.
            # For simplicity here, we assume a single prompt is sufficient.
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                # Gemini might support response_mime_type="application/json" in future or specific models
                # response_mime_type="application/json" # Uncomment if/when supported
            )
            gemini_response = client.generate_content(
                contents=[full_prompt], # Send as list of parts
                generation_config=generation_config,
            )
            # Handle potential blocks or empty responses
            if not gemini_response.parts:
                 feedback = gemini_response.prompt_feedback if hasattr(gemini_response, 'prompt_feedback') else "Unknown reason (empty parts)"
                 print(f"Gemini JSON response issue: {feedback}")
                 return None
            response_text = gemini_response.text # Access text directly

        else:
            print(f"Unsupported provider for JSON call: {provider}")
            return None

        # --- Process the response ---
        if response_text:
            print(f"--- Raw LLM JSON Response ({schema_name}) ---\n{response_text}\n------------------------------------------")
            # Clean potential markdown fences if Gemini added them despite instructions
            if provider == 'gemini':
                response_text = response_text.strip().removeprefix("```json").removesuffix("```").strip()

            try:
                # Parse the JSON string
                parsed_json = json.loads(response_text)

                if skip_validation:
                    print(f"Skipping Pydantic validation for {schema_name}.")
                    return parsed_json # Return raw parsed JSON

                # Validate with Pydantic
                validated_data = pydantic_schema(**parsed_json)
                print(f"Successfully validated JSON for {schema_name}.")
                return validated_data.model_dump() # Return as dict

            except json.JSONDecodeError as e:
                print(f"JSON Decode Error for {schema_name}: {e}\nRaw text: '{response_text}'")
                return None
            except ValidationError as e:
                print(f"Pydantic Validation Error for {schema_name}: {e}\nParsed JSON: {parsed_json}")
                return None
        else:
            print(f"LLM returned empty response for {schema_name}.")
            return None

    except Exception as e:
        print(f"Error calling {provider} API for {schema_name}: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return None
