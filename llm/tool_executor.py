import asyncio
import inspect
import logging
from typing import Dict, Any, List

# Import tool implementation functions
from tools import time_tool, file_tool
from tools.web_search_tool import perform_web_search
from memory.mongo_handler import MongoHandler
from .llm_client import LLMClient # Needed for web search summarization
# Import Pydantic models for argument validation (optional but good practice)
from .schemas import (
    GetCurrentTimeArgs,
    ReadFileArgs,
    WriteFileArgs,
    FetchMemoryArgs,
    UpdateMemoryArgs,
    SaveMemoryArgs,
    SearchWebArgs
)
from tools.tools import find_tool # To get argument schemas

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ToolExecutor:
    """Handles the execution of tools based on their names and arguments."""

    def __init__(self, mongo_handler: MongoHandler, llm_client: LLMClient):
        """
        Initializes the ToolExecutor.

        Args:
            mongo_handler: An instance of MongoHandler for memory operations.
            llm_client: An instance of LLMClient, needed for potential post-processing like summarization.
        """
        self.mongo_handler = mongo_handler
        self.llm_client = llm_client # Store LLM client for summarization
        self._tool_dispatcher = self._build_dispatcher()

    def _build_dispatcher(self) -> Dict[str, callable]:
        """Builds the dictionary mapping tool names to their functions."""
        dispatcher = {
            # General tools
            "get_current_time": time_tool.get_current_time,
            "read_file": file_tool.read_file,
            "write_file": file_tool.write_file,
            # Web search tool
            "search_web": perform_web_search,
            # Memory tools (map to mongo_handler methods if connected)
            # Use semantic search (similarity) for fetching memory
            "fetch_memory": (lambda query: self.mongo_handler.retrieve_memories_by_similarity(query_text=query))
                           if self.mongo_handler.is_connected() and self.mongo_handler.embedding_model
                            else self._memory_fetch_unavailable,
            "update_memory": (lambda memory_id, new_content: self.mongo_handler.update_fact(memory_id=memory_id, new_content=new_content))
                        if self.mongo_handler.is_connected() and self.mongo_handler.embedding_model
                        else self._memory_update_unavailable, # Added update tool
            "save_memory": self.mongo_handler.add_fact if self.mongo_handler.is_connected() else self._mongo_unavailable, 
         }
         # Filter out unavailable tools (like memory if mongo isn't connected)
        # Although the functions handle it, this makes the available set clearer if needed later.
        # For now, we keep the placeholders.
        return dispatcher

    def _mongo_unavailable(self, *args, **kwargs) -> str:
        """Placeholder function for when MongoDB is not connected for saving."""
        logging.warning("Attempted to use save_memory tool, but MongoDB is not connected.")
        return "Error: MongoDB connection is not available. Cannot use save_memory tool."

    def _memory_fetch_unavailable(self, *args, **kwargs) -> str:
        """Placeholder function for when memory fetch is unavailable (DB or model issue)."""
        if not self.mongo_handler.is_connected():
            logging.warning("Attempted to use fetch_memory tool, but MongoDB is not connected.")
            return "Error: MongoDB connection is not available. Cannot use fetch_memory tool."
        elif not self.mongo_handler.embedding_model:
            logging.warning("Attempted to use fetch_memory tool, but the embedding model is not loaded.")
            return "Error: Embedding model is not available. Cannot use fetch_memory tool."
        else: # Should not happen with the current logic, but for completeness
         logging.warning("Attempted to use fetch_memory tool, but it's unavailable for an unknown reason.")
         return "Error: fetch_memory tool is currently unavailable." # Corrected indentation

    def _memory_update_unavailable(self, *args, **kwargs) -> str:
        """Placeholder function for when memory update is unavailable (DB or model issue)."""
        if not self.mongo_handler.is_connected():
            logging.warning("Attempted to use update_memory tool, but MongoDB is not connected.")
            return "Error: MongoDB connection is not available. Cannot use update_memory tool."
        elif not self.mongo_handler.embedding_model:
            logging.warning("Attempted to use update_memory tool, but the embedding model is not loaded.")
            return "Error: Embedding model is not available. Cannot use update_memory tool."
        else: # Should not happen with the current logic, but for completeness
             logging.warning("Attempted to use update_memory tool, but it's unavailable for an unknown reason.")
             return "Error: update_memory tool is currently unavailable."

    def get_all_tool_names(self) -> List[str]:
        """Returns a list of names of all tools configured in the dispatcher."""
        # Ensure keys are strings if needed, though they should be
        return list(map(str, self._tool_dispatcher.keys()))


    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Executes the specified tool with the given arguments.
        The 'arguments' dictionary is now expected to be directly usable by the tool
        as it comes from Gemini's function calling (already structured).

        Args:
            tool_name: The name of the tool to execute.
            arguments: A dictionary of arguments for the tool.

        Returns:
            A string representing the result of the tool execution.
        """
        if tool_name not in self._tool_dispatcher:
            logging.error(f"Attempted to execute unknown tool: '{tool_name}'")
            return f"Error: Unknown tool '{tool_name}'."

        action_function = self._tool_dispatcher[tool_name]
        
        # Optional: Validate arguments against Pydantic schema for the tool
        # This adds an extra layer of safety, though Gemini should adhere to the schema.
        tool_definition = find_tool(tool_name)
        if tool_definition and tool_definition.argument_schema:
            try:
                # If arguments is None (e.g. for GetCurrentTimeArgs), provide an empty dict
                args_to_validate = arguments if arguments is not None else {}
                tool_definition.argument_schema(**args_to_validate)
                logging.info(f"Arguments for '{tool_name}' successfully validated against Pydantic schema.")
            except Exception as pydantic_exc: # Catch Pydantic's ValidationError and other potential errors
                logging.error(f"Pydantic validation failed for tool '{tool_name}' with args {arguments}: {pydantic_exc}")
                return f"Error: Invalid arguments received for tool '{tool_name}' after LLM generation. Validation: {pydantic_exc}"

        try:
            # Check if the function is async
            is_async = inspect.iscoroutinefunction(action_function)

            # Execute the function (sync or async)
            logging.info(f"Executing tool '{tool_name}' with arguments: {arguments}")
            if is_async:
                # Run async function using await
                if arguments:
                    result = await action_function(**arguments)
                else:
                    result = await action_function()
            else:
                # Run sync function in a thread to avoid blocking if it's potentially long-running
                # (though current sync tools are fast)
                loop = asyncio.get_running_loop()
                if arguments:
                    result = await loop.run_in_executor(None, lambda: action_function(**arguments))
                else:
                    result = await loop.run_in_executor(None, action_function)

            logging.info(f"Raw result from '{tool_name}': {str(result)[:200]}...") # Log truncated result

            # --- Post-process results ---
            formatted_result = await self._post_process_result(tool_name, arguments, result)

            return formatted_result

        except TypeError as e:
            # Handle cases where arguments don't match function signature
            logging.error(f"Type error calling tool '{tool_name}' with args {arguments}: {e}")
            return f"Error: Invalid arguments provided for tool '{tool_name}'. {e}"
        except Exception as e:
            logging.exception(f"Error executing tool '{tool_name}': {e}") # Log full traceback
            return f"Error: Failed to execute tool '{tool_name}'. {e}"

    async def _post_process_result(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> str:
        """Handles specific formatting or processing after a tool executes."""

        # --- Summarize Web Search Results ---
        if tool_name == "search_web" and isinstance(result, str) and result and not result.startswith("Error:"):
            logging.info(f"--- Summarizing web search results for query: {arguments.get('query', 'N/A')} ---")
            raw_search_results = result
            summarization_prompt = f"Provide a summarization of the information contained within this search result, be careful not to miss any important detail.:\n\n{raw_search_results}"
            summary_messages = [{'role': 'user', 'content': summarization_prompt}]
            # Use the stored LLM client to generate the summary
            summarized_result = await self.llm_client.generate_final_response( # Added await here
                messages=summary_messages,
                personality_prompt="You are an expert summarization assistant."
            )

            if summarized_result and not summarized_result.startswith("Error:"):
                logging.info(f"Result: {summarized_result[:200]}...")
                return summarized_result # Return summary
            else:
                logging.warning("Failed to summarize web search results. Using raw results.")
                return raw_search_results # Return raw results if summarization fails
 
        # --- Format Memory Fetch Results ---
        elif tool_name == "fetch_memory":
             if isinstance(result, list):
                 if result:
                     # Check if the first item is a dictionary (new format)
                     if result and isinstance(result[0], dict) and "_id" in result[0] and "content" in result[0]:
                         formatted_string = "Memory Fetch Results:\n\n"
                         fact_strings = [f"ID: {fact['_id']} | Content: {fact['content']}" for fact in result]
                         formatted_string += "\n---\n".join(fact_strings)
                     else:
                         # Fallback for old format or unexpected list content (shouldn't happen ideally)
                         logging.warning("fetch_memory returned a list, but not in the expected format (list of dicts with _id/content).")
                         formatted_string = "Memory Fetch Results:\n\nRelevant Facts:\n"
                         formatted_string += "\n---\n".join(map(str, result)) # Convert all items to string
                 else:
                     formatted_string = "Memory Fetch Results:\n\nNo relevant facts found."
                 return formatted_string
             else:
                 # Handle error string or unexpected type from retrieve_memories_by_similarity
                 logging.warning(f"Unexpected result type for fetch_memory: {type(result)}. Content: {result}")
                 return str(result) # Return the error or unexpected result as string

        # --- Format Memory Update Results ---
        elif tool_name == "update_memory":
             # update_fact returns the new ObjectId on success, None on failure
             if result is not None:
                 # Successfully updated
                 return f"Memory replaced successfully. New ID: {str(result)}"
             else:
                 # Failed - likely due to invalid/unknown memory_id
                 failed_id = arguments.get('memory_id', 'unknown') # Get the ID that was attempted
                 error_msg = f"Memory replacement failed. The provided memory_id '{failed_id}' was not found or an error occurred during the update process."
                 logging.error(error_msg) # Log the specific error with the failed ID
                 return error_msg # Return the specific error message

        # --- Default Formatting ---
        else:
            # Ensure result is always a string for history consistency
            return str(result) if result is not None else "Tool executed successfully, but returned no output."
