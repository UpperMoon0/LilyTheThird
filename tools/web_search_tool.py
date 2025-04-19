import asyncio
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from typing import List, Dict, Optional
import logging # Added for better error logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to fetch and extract text from a URL using requests.Session
def fetch_url_content(url: str, timeout: int = 10) -> Optional[str]:
    """Fetches content from a URL and extracts text using BeautifulSoup and requests.Session."""
    headers = { # Add headers to mimic a browser
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        # Use a session for potentially better connection management
        with requests.Session() as session:
            session.headers.update(headers) # Set headers for the session
            response = session.get(url, timeout=timeout)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        # Check content type to avoid parsing non-HTML content (after getting response)
        if 'text/html' not in response.headers.get('Content-Type', ''):
            logging.warning(f"Skipping non-HTML content at {url}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract text from paragraph tags, join them, limit length
        paragraphs = soup.find_all('p')
        content = ' '.join(p.get_text() for p in paragraphs)
        
        # Limit the content length to avoid overly long results
        max_content_length = 2000 
        return content[:max_content_length] + "..." if len(content) > max_content_length else content

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching URL {url} with requests.Session: {e}")
        return None
    except Exception as e:
        logging.error(f"Error parsing URL {url}: {e}")
        return None

async def perform_web_search(query: str, max_results: int = 5) -> str:
    """
    Performs a web search using DuckDuckGo and returns a formatted string
    of the top results. Attempts to fetch detailed content for all results,
    falling back to snippets if fetching fails.

    Args:
        query: The search query string.
        max_results: The maximum number of results to return from DDG.

    Returns:
        A string containing the search results, or an error message.
    """
    logging.info(f"Performing web search for: '{query}' (max_results={max_results}, attempting detail fetch for all)")
    results_str = f"Web search results for '{query}':\n\n"
    try:
        # Define a helper function to run DDGS().text within the thread
        # This ensures a fresh DDGS instance is potentially used each time
        def _ddgs_search_in_thread(q: str, mr: int):
            try:
                # Instantiate DDGS inside the thread function
                with DDGS() as ddgs: # Use context manager if available (check library docs)
                    # If DDGS() doesn't support context manager, just instantiate: ddgs = DDGS()
                    return ddgs.text(q, max_results=mr)
            except Exception as thread_ddg_exc:
                # Log the error from within the thread if possible, or re-raise
                logging.error(f"Error inside DDGS search thread for '{q}': {thread_ddg_exc}")
                raise # Re-raise the exception to be caught outside

        try:
            # Run the helper function in a separate thread
            search_results: Optional[List[Dict]] = await asyncio.to_thread(
                _ddgs_search_in_thread, query, max_results
            )
        except Exception as ddg_exc:
            # Catch exceptions raised from the thread helper
            logging.exception(f"Error executing DDGS search thread for '{query}': {ddg_exc}")
            return f"Error performing web search (DDG call failed): {ddg_exc}"

        if not search_results:
            logging.warning(f"No web search results found for '{query}'.")
            return f"No web search results found for '{query}'."

        processed_results = 0
        for i, result in enumerate(search_results):
            title = result.get('title', 'N/A')
            href = result.get('href', 'N/A')
            original_snippet = result.get('body', 'N/A').replace('\n', ' ') # Clean up snippet

            display_body = f"Snippet: {original_snippet}" # Default to original snippet

            # Always attempt to fetch detailed content if URL is valid
            if href and href.startswith(('http://', 'https://')):
                logging.info(f"Attempting to fetch detailed content for result {i+1}: {href}")
                # Run synchronous fetch_url_content in a separate thread
                # to avoid blocking the async event loop.
                detailed_content = await asyncio.to_thread(fetch_url_content, href)

                if detailed_content:
                    display_body = f"Summary: {detailed_content}"
                    logging.info(f"Successfully fetched and summarized content for {href}")
                else:
                    logging.warning(f"Failed to fetch detailed content for {href}, using snippet.")
                    # Fallback to original snippet is already handled by default
            else:
                 # Log if URL is invalid or missing, snippet will be used by default
                 if not href:
                     logging.warning(f"Result {i+1} ('{title}') has no URL. Using snippet.")
                 elif not href.startswith(('http://', 'https://')):
                     logging.warning(f"Result {i+1} ('{title}') has an invalid URL: {href}. Using snippet.")


            results_str += f"{i+1}. Title: {title}\n"
            results_str += f"   URL: {href}\n"
            results_str += f"   {display_body}\n\n" # Use the determined body (snippet or summary)
            processed_results += 1

        logging.info(f"Web search completed. Returning {processed_results} results.")
        return results_str.strip()

    except Exception as e:
        logging.exception(f"Error during web search processing for '{query}': {e}") # Use logging.exception for stack trace
        return f"Error performing web search: {e}"

# Example usage (for testing)
async def main_test():
    search_query = "What is the latest news on Python 4?"
    # Test fetching detail (default behavior now)
    results = await perform_web_search(search_query, max_results=3)
    print("\n--- Search Results (Attempting Detail Fetch for All) ---")
    print(results)
    print("-------------------------------------------------------")


if __name__ == "__main__":
    # To test this script directly: python -m LilyTheThird.tools.web_search_tool
    # Run from the project root directory (d:/Dev/Workspace/Python)
    print("Running web search tool test...")
    asyncio.run(main_test())
