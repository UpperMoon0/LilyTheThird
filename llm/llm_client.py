import os
import random
import json
# Import the updated functions from tools.py
from tools.tools import ToolDefinition, get_tool_list_for_prompt, get_tool_names, find_tool
import google.generativeai as genai
from openai import OpenAI
from typing import List, Dict, Optional, Any

# Assuming history manager is in the same directory or adjust import path
from .history_manager import HistoryManager

class LLMClient:
    """Handles communication with the underlying LLM provider (OpenAI or Gemini)."""

    def __init__(self, provider: str, model_name: Optional[str] = None):
        """
        Initializes the LLM client based on the provider.

        Args:
            provider: The LLM provider ('openai' or 'gemini').
            model_name: The specific model name to use.
        """
        self.provider = provider
        self.model = model_name
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Loads API keys and initializes the appropriate client."""
        openai_api_key = os.getenv('OPENAI_KEY')
        gemini_api_key = os.getenv('GEMINI_API_KEY')

        if not self.model:
            # Set default model if none provided
            if self.provider == 'openai':
                self.model = "gpt-4o-mini" # Default OpenAI model
            elif self.provider == 'gemini':
                self.model = "gemini-1.5-flash" # Default Gemini model
            else:
                # If provider is unknown and no model is given, we can't proceed
                raise ValueError(f"Model name must be provided for unsupported provider: {self.provider}")
            print(f"Warning: No model name provided, using default for {self.provider}: {self.model}")

        if self.provider == 'openai':
            if not openai_api_key:
                raise ValueError("OpenAI API key not found in environment variables.")
            self.client = OpenAI(api_key=openai_api_key)
        elif self.provider == 'gemini':
            if not gemini_api_key:
                raise ValueError("Gemini API key not found in environment variables.")
            genai.configure(api_key=gemini_api_key)
            self.client = genai.GenerativeModel(self.model)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        print(f"LLM Client initialized for provider: {self.provider}, model: {self.model}")

    def get_model_name(self) -> str:
        """Returns the name of the model being used."""
        return self.model

    # --- Core LLM Call for JSON ---
    def _call_llm_for_json(self, messages: List[Dict], purpose: str) -> Optional[Dict]:
        """
        Internal helper to call the LLM and expect a JSON response.

        Args:
            messages: The list of messages for the prompt.
            purpose: A string describing the purpose (e.g., "Tool Selection", "Argument Generation") for logging.

        Returns:
            A dictionary parsed from the JSON response, or None if an error occurs or parsing fails.
        """
        max_retries = 2
        for attempt in range(max_retries):
            print(f"--- Attempt {attempt + 1}/{max_retries} for {purpose} JSON ---")
            # print(f"Messages sent for JSON:\n{json.dumps(messages, indent=2)}") # DEBUG

            if self.provider == 'openai':
                try:
                    # Instruct OpenAI to return JSON
                    response = self.client.chat.completions.create(
                        messages=messages,
                        model=self.model,
                        max_tokens=300, # Adjust as needed for expected JSON size
                        temperature=0.1, # Lower temperature for more deterministic JSON
                        response_format={"type": "json_object"} # Request JSON mode
                    )
                    content = response.choices[0].message.content.strip()
                    print(f"Raw OpenAI JSON response for {purpose}: {content}")
                    # Clean potential markdown code block fences
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip() # Clean again after removing fences
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"Error decoding OpenAI JSON response for {purpose} (Attempt {attempt + 1}): {e}\nRaw content: {content}")
                except Exception as e:
                    print(f"Error calling OpenAI API ({purpose} - Attempt {attempt + 1}): {e}")
                    # Break on non-JSON errors for now
                    return None # Or raise?

            elif self.provider == 'gemini':
                # Adapt messages for Gemini (similar to generate_final_response)
                system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
                history_openai_format = [msg for msg in messages if msg['role'] != 'system']
                user_message_content = history_openai_format.pop()['content'] # Get the last user message

                temp_history_manager = HistoryManager() # Consider making adaptation static/util
                gemini_formatted_history = temp_history_manager.adapt_history_for_gemini(history_openai_format)

                # Combine system prompts and user message, explicitly asking for JSON
                prompt_parts = [
                    f"System Instructions:\n{' '.join(system_prompts)}\n\nUser Request:\n{user_message_content}\n\n"
                    f"IMPORTANT: Respond ONLY with a valid JSON object based on the request. Do not include any other text or explanations."
                ]

                generation_config = genai.types.GenerationConfig(
                    # Ensure Gemini knows we want JSON - response_mime_type might work
                    # response_mime_type="application/json", # Check if supported by model/API version
                    max_output_tokens=300, # Adjust as needed
                    temperature=0.1, # Lower temperature for JSON
                )
                try:
                    chat_session = self.client.start_chat(history=gemini_formatted_history)
                    response = chat_session.send_message(
                        prompt_parts,
                        generation_config=generation_config,
                    )
                    content = response.text.strip()
                    print(f"Raw Gemini JSON response for {purpose}: {content}")
                     # Clean potential markdown code block fences
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip() # Clean again after removing fences
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"Error decoding Gemini JSON response for {purpose} (Attempt {attempt + 1}): {e}\nRaw content: {content}")
                except Exception as e:
                    print(f"Error calling Gemini API ({purpose} - Attempt {attempt + 1}): {e}")
                    # Break on non-JSON errors for now
                    return None # Or raise?
            else:
                print(f"Unsupported provider '{self.provider}' for JSON generation.")
                return None

            # If JSON decoding failed, wait briefly before retrying (optional)
            # time.sleep(1)

        print(f"Failed to get valid JSON response for {purpose} after {max_retries} attempts.")
        return None

    # --- Tool Interaction Methods ---

    def get_next_action(self, messages: List[Dict], allowed_tools: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Prompts the LLM to decide the next action: use a tool or respond directly.

        Args:
            messages: The current conversation history in OpenAI format.
            allowed_tools: An optional list of tool names allowed in this context. If None, all tools are allowed.

        Returns:
            A dictionary like {"action_type": "tool_choice", "tool_name": "tool_name_here" or None},
            or None if an error occurred.
        """
        # Use the updated functions, passing allowed_tools
        tool_list_prompt = get_tool_list_for_prompt(allowed_tools=allowed_tools)
        available_tool_names = get_tool_names(allowed_tools=allowed_tools) # Get only the names of allowed tools

        if not available_tool_names:
            # If no tools are allowed or available, don't even ask the LLM
            print("No tools allowed or available in this context. Skipping tool check.")
            return {"action_type": "tool_choice", "tool_name": None}

        system_prompt = (
            "You are an AI assistant that can use tools to help the user. "
            "Analyze the user's latest message and the conversation history. "
            "Decide if you need to use one of the available tools *from the list below* to fulfill the request. " # Emphasize the provided list
            f"{tool_list_prompt}\n" # This now contains only allowed tools
            "Respond ONLY with a JSON object containing the key 'tool_name'. "
            "The value should be the name of the tool you want to use (must be one of the tools listed above) " # Refer to the list above
            "or null if no tool is needed and you should respond directly."
            "Example for using a tool: {\"tool_name\": \"search_web\"}" # Keep example generic
            "Example for not using a tool: {\"tool_name\": null}"
        )

        # Prepare messages for the LLM
        request_messages = [msg for msg in messages] # Create a copy
        # Insert the system prompt for tool selection
        # Find the first user message and insert before it, or append if none?
        # Let's just prepend it for simplicity for now.
        request_messages.insert(0, {"role": "system", "content": system_prompt})

        json_response = self._call_llm_for_json(request_messages, "Tool Selection")

        if json_response and isinstance(json_response, dict) and "tool_name" in json_response:
            tool_name = json_response["tool_name"]
            # Check for None (JSON null), the string "null", or a valid tool name
            if tool_name is None or tool_name == "null" or tool_name in available_tool_names:
                 # If the tool name is the string "null", treat it as None (no tool)
                 actual_tool_name = None if tool_name == "null" else tool_name
                 return {"action_type": "tool_choice", "tool_name": actual_tool_name}
            else:
                 print(f"Error: LLM chose an invalid tool name: {tool_name}")
                 # Fallback: Default to no tool if the name is invalid
                 return {"action_type": "tool_choice", "tool_name": None}
        else:
            print(f"Error: Failed to get valid tool selection JSON. Response: {json_response}")
            # Fallback: Assume no tool needed if JSON is invalid/missing
            return {"action_type": "tool_choice", "tool_name": None} # Or return None to indicate error?

    def get_tool_arguments(self, tool: ToolDefinition, messages: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        Prompts the LLM to provide arguments for the chosen tool.

        Args:
            tool: The ToolDefinition object for the chosen tool.
            messages: The current conversation history in OpenAI format.

        Returns:
            A dictionary like {"action_type": "tool_arguments", "arguments": {...}},
            or None if an error occurred or arguments are invalid.
            The arguments dictionary should match the tool's json_schema.
        """
        # --- Check if the tool requires arguments ---
        # If the schema defines no properties and no required fields, assume no arguments needed.
        if not tool.json_schema.get("properties") and not tool.json_schema.get("required"):
            print(f"Tool '{tool.name}' requires no arguments. Returning empty dict.")
            return {"action_type": "tool_arguments", "arguments": {}}

        # --- If arguments are needed, prompt the LLM ---
        system_prompt = (
            f"You have decided to use the '{tool.name}' tool.\n"
            f"Tool Description: {tool.description}\n"
            f"Instructions: {tool.instruction}\n"
            f"Based on the conversation history and the user's request, provide the necessary arguments for this tool.\n"
            f"Respond ONLY with a valid JSON object containing the arguments, matching this structure: {json.dumps(tool.json_schema)}"
        )

        request_messages = [msg for msg in messages] # Create a copy
        request_messages.insert(0, {"role": "system", "content": system_prompt})

        json_response = self._call_llm_for_json(request_messages, f"Argument Generation for {tool.name}")

        if json_response and isinstance(json_response, dict):
            # TODO: Add JSON schema validation here using jsonschema library if needed
            print(f"Received arguments for {tool.name}: {json_response}")
            return {"action_type": "tool_arguments", "arguments": json_response}
        else:
            print(f"Error: Failed to get valid arguments JSON for tool {tool.name}. Response: {json_response}")
            return None # Indicate error

    # --- Final Response Generation ---

    def generate_final_response(self, messages: List[Dict], personality_prompt: str) -> Optional[str]:
        """
        Generates the final conversational response after tool use (or if no tool was needed).

        Args:
            messages: The complete list of messages (including history, tool calls/results,
                      and the final user message) in OpenAI format.
            personality_prompt: The system prompt defining the chatbot's personality.

        Returns:
            The generated message string, or None if an error occurs.
        """
        # Ensure personality prompt is included, followed by the full history
        final_messages = [{"role": "system", "content": personality_prompt}]
        # Add the rest of the conversation history, preserving all roles including 'system' for tool results
        final_messages.extend(messages) # Pass the full history

        # --- Call the appropriate provider ---
        if self.provider == 'openai':
            return self._generate_openai_response(final_messages)
        elif self.provider == 'gemini':
            return self._generate_gemini_response(final_messages)
        else:
            print(f"Unsupported provider '{self.provider}' for final response generation.")
            return "Error: Unsupported provider."

    def _generate_openai_response(self, messages: List[Dict]) -> Optional[str]:
        """Handles the actual OpenAI API call for message generation."""
        try:
            print(f"--- Generating Final OpenAI Response ---")
            # print(f"Messages sent for final response:\n{json.dumps(messages, indent=2)}") # DEBUG
            response = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    max_tokens=450, # Keep original max_tokens for final response
                    temperature=random.uniform(0.2, 0.8), # Keep original temperature range
                    # No JSON format needed here
                )
            message = response.choices[0].message.content.strip()
            print(f"Final OpenAI Response: {message}")
            return message
        except Exception as e:
            print(f"Error calling OpenAI API (Final Response Generation): {e}")
            return f"Error: Could not get final response from OpenAI. {e}"

    def _generate_gemini_response(self, messages: List[Dict]) -> Optional[str]:
        """Handles the actual Gemini API call for message generation."""
        try:
            print(f"--- Generating Final Gemini Response ---")
            # Adapt system prompts and history for Gemini
            system_prompts = [msg['content'] for msg in messages if msg['role'] == 'system']
            history_openai_format = [msg for msg in messages if msg['role'] != 'system']

            if not history_openai_format:
                 # Should not happen if called correctly, but handle defensively
                 print("Warning: No user/model messages found for Gemini final response.")
                 final_user_content = "Please respond." # Placeholder
                 gemini_history_to_pass = []
            else:
                final_user_content = history_openai_format.pop()['content'] # Assume last is user/tool result to prompt response
                temp_history_manager = HistoryManager()
                gemini_history_to_pass = temp_history_manager.adapt_history_for_gemini(history_openai_format)

            prompt_parts = [
                f"System Instructions:\n{' '.join(system_prompts)}\n\n"
                f"User Request/Context:\n{final_user_content}\n\n"
                f"IMPORTANT: Generate your final response based *only* on the information provided in the System Instructions and the preceding conversation history (including any Tool results shown). Synthesize the information accurately."
            ]

            generation_config = genai.types.GenerationConfig(
                max_output_tokens=1000, 
                temperature=random.uniform(0.2, 0.7),
            )

            chat_session = self.client.start_chat(history=gemini_history_to_pass)
            response = chat_session.send_message(
                prompt_parts,
                generation_config=generation_config,
            )
            print(f"--- Raw Gemini Final Response Text ---\n{response.text}\n----------------------------------------")
            if response.text:
                message = response.text.strip()
                return message
            else:
                feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else "Unknown reason"
                print(f"Gemini final response issue: {feedback}")
                return "Error: Gemini final response was empty or blocked."
        except Exception as e:
            print(f"Error calling Gemini API (Final Response Generation): {e}")
            import traceback
            traceback.print_exc() # Print stack trace for Gemini errors
            return f"Error: Could not get final response from Gemini. {e}"
