import asyncio
from duckduckgo_search import DDGS 
from typing import List, Dict, Optional

async def perform_web_search(query: str, max_results: int = 5) -> str:
    """
    Performs a web search using DuckDuckGo and returns a formatted string
    of the top results.

    Args:
        query: The search query string.
        max_results: The maximum number of results to return.

    Returns:
        A string containing the search results, or an error message.
    """
    print(f"Performing web search for: {query}")
    results_str = f"Web search results for '{query}':\n\n"
    try:
        # DDGS().text() appears to return a list directly, even in async context.
        # We'll call it and iterate normally.
        search_results: Optional[List[Dict]] = DDGS().text(query, max_results=max_results)

        if not search_results:
            return f"No web search results found for '{query}'."

        for i, result in enumerate(search_results):
            title = result.get('title', 'N/A')
            href = result.get('href', 'N/A')
            # Corrected indentation for lines within the loop
            body = result.get('body', 'N/A').replace('\n', ' ') # Clean up body
            results_str += f"{i+1}. Title: {title}\n"
            results_str += f"   URL: {href}\n"
            results_str += f"   Snippet: {body}\n\n"

        # Corrected indentation for print and return
        print(f"Web search completed. Returning {len(search_results)} results.")
        return results_str.strip()

    except Exception as e:
        print(f"Error during web search for '{query}': {e}")
        return f"Error performing web search: {e}"

# Example usage (for testing)
async def main_test():
    search_query = "What is the capital of France?"
    results = await perform_web_search(search_query)
    print("\n--- Search Results ---")
    print(results)
    print("--------------------")

if __name__ == "__main__":
    # To test this script directly: python -m tools.web_search_tool
    # Note: Running with `python -m` ensures correct relative imports if needed later.
    print("Running web search tool test...")
    asyncio.run(main_test())
