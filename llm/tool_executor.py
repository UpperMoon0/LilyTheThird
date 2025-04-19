import asyncio
import inspect
import json
import logging
from typing import Dict, Any, Optional

# Import tool implementation functions
from tools import time_tool, file_tool
from tools.web_search_tool import perform_web_search
from memory.mongo_handler import MongoHandler
from .llm_client import LLMClient # Needed for web search summarization

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
            "fetch_memory": self.mongo_handler.retrieve_memories_by_query if self.mongo_handler.is_connected() else self._mongo_unavailable,
            "save_memory": self.mongo_handler.add_fact if self.mongo_handler.is_connected() else self._mongo_unavailable,
        }
        # Filter out unavailable tools (like memory if mongo isn't connected)
        # Although the functions handle it, this makes the available set clearer if needed later.
        # For now, we keep the placeholders.
        return dispatcher

    def _mongo_unavailable(self, *args, **kwargs) -> str:
        """Placeholder function for when MongoDB is not connected."""
        logging.warning("Attempted to use memory tool, but MongoDB is not connected.")
        return "Error: MongoDB connection is not available. Cannot use memory tool."

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Executes the specified tool with the given arguments.

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
            summarization_prompt = f"Please summarize the following web search results and make them easy to read:\n\n{raw_search_results}"
            summary_messages = [{'role': 'user', 'content': summarization_prompt}]
            # Use the stored LLM client to generate the summary
            summarized_result = self.llm_client.generate_final_response(
                messages=summary_messages,
                personality_prompt="You are an expert summarization assistant."
            )

            if summarized_result and not summarized_result.startswith("Error:"):
                logging.info(f"Summarized Result: {summarized_result[:200]}...")
                return summarized_result # Return summary
            else:
                logging.warning("Failed to summarize web search results. Using raw results.")
                return raw_search_results # Return raw results if summarization fails

        # --- Format Memory Fetch Results ---
        elif tool_name == "fetch_memory":
            if isinstance(result, list):
                if result:
                    formatted_string = "Memory Fetch Results:\n\nRelevant Facts:\n"
                    formatted_string += "\n---\n".join(result) # Assumes result is list of strings
                else:
                    formatted_string = "Memory Fetch Results:\n\nNo relevant facts found."
                return formatted_string
            else:
                # Handle error string or unexpected type from retrieve_memories_by_query
                logging.warning(f"Unexpected result type for fetch_memory: {type(result)}. Content: {result}")
                return str(result) # Return the error or unexpected result as string

        # --- Default Formatting ---
        else:
            # Ensure result is always a string for history consistency
            return str(result) if result is not None else "Tool executed successfully, but returned no output."
