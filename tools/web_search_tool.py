import asyncio
import requests
import time # Added for sleep on retry
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS # Keep DDGS import
from duckduckgo_search.exceptions import RatelimitException # Correct import path for RatelimitException
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

        # Extract text from the entire body, clean up whitespace, limit length
        # Remove script and style elements first
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose() # Remove these tags and their content

        # Get text from the rest of the body
        content = soup.get_text()

        # Break into lines and remove leading/trailing space on each
        lines = (line.strip() for line in content.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        content = '\n'.join(chunk for chunk in chunks if chunk)

        # Limit the content length to avoid overly long results
        max_content_length = 10000
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
        # Define a helper function to run DDGS().text within the thread with retry logic
        def _ddgs_search_in_thread(q: str, mr: int, retry_delay: int = 5):
            attempt = 1
            max_attempts = 2 # Initial attempt + 1 retry
            while attempt <= max_attempts:
                try:
                    # Instantiate DDGS inside the thread function for each attempt
                    with DDGS() as ddgs:
                        logging.info(f"Attempt {attempt}: Performing DDGS search for '{q}'")
                        results = ddgs.text(q, max_results=mr)
                        logging.info(f"Attempt {attempt}: DDGS search successful for '{q}'")
                        return results
                except RatelimitException as rate_limit_exc:
                    logging.warning(f"Attempt {attempt}: Encountered DDGS rate limit for '{q}': {rate_limit_exc}")
                    if attempt < max_attempts:
                        logging.info(f"Waiting {retry_delay} seconds before retrying...")
                        time.sleep(retry_delay)
                        attempt += 1
                    else:
                        logging.error(f"Attempt {attempt}: DDGS rate limit persisted after retry for '{q}'. Raising exception.")
                        raise rate_limit_exc # Re-raise after final attempt fails
                except Exception as thread_ddg_exc:
                    # Log other errors from within the thread and re-raise
                    logging.error(f"Attempt {attempt}: Error inside DDGS search thread for '{q}': {thread_ddg_exc}")
                    raise # Re-raise the exception to be caught outside
            # Should not be reached if logic is correct, but added for safety
            logging.error(f"Exited DDGS search loop unexpectedly for query '{q}' after {attempt-1} attempts.")
            return None # Or raise an error

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
