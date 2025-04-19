import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError
from dotenv import load_dotenv
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MongoHandler:
    """
    Handles interactions with the MongoDB database for storing and retrieving memories.
    """
    def __init__(self, collection_name="memories"):
        """
        Initializes the MongoDB connection.
        """
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')) # Load .env from project root
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.collection = None

        if not self.mongo_uri or self.mongo_uri == "YOUR_MONGO_CONNECTION_URI":
            logging.warning("MONGO_URI not found or not set in .env file. MongoDB memory functions will be disabled.")
            return # Don't attempt connection if URI is missing/default

        try:
            logging.info(f"Attempting to connect to MongoDB at {self.mongo_uri.split('@')[-1]}...") # Avoid logging credentials
            # Increased timeout settings
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=10000, # 10 seconds timeout for server selection
                connectTimeoutMS=20000 # 20 seconds timeout for initial connection
            )
            # The ismaster command is cheap and does not require auth.
            self.client.admin.command('ismaster')
            # Infer database name from URI if possible, otherwise default
            db_name = self.client.get_database().name if self.client.get_database() else "lily_memory"
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            logging.info(f"Successfully connected to MongoDB. Database: '{db_name}', Collection: '{collection_name}'")
        except ConfigurationError as e:
            logging.error(f"MongoDB configuration error: {e}. Please check your MONGO_URI format.")
            self.client = None # Ensure client is None on error
        except ConnectionFailure as e:
            logging.error(f"MongoDB connection failed: {e}. Check if the server is running and accessible.")
            self.client = None # Ensure client is None on error
        except Exception as e:
            logging.error(f"An unexpected error occurred during MongoDB connection: {e}")
            self.client = None # Ensure client is None on error

    def is_connected(self):
        """Checks if the MongoDB client is connected."""
        return self.client is not None and self.collection is not None

    def add_memory(self, user_input: str, llm_response: str, metadata: dict = None):
        """
        Adds a memory unit to the MongoDB collection.

        Args:
            user_input (str): The user's input text.
            llm_response (str): The LLM's response text.
            metadata (dict, optional): Additional metadata to store. Defaults to None.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot add memory.")
            return None

        memory_unit = {
            "user_input": user_input,
            "llm_response": llm_response,
            "timestamp": datetime.utcnow(), # Store timestamp in UTC
            "metadata": metadata or {} # Ensure metadata is always a dict
        }
        try:
            result = self.collection.insert_one(memory_unit)
            logging.info(f"Memory added with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            logging.error(f"Failed to add memory to MongoDB: {e}")
            return None

    def retrieve_recent_memories(self, limit: int = 10):
        """
        Retrieves the most recent memory units.

        Args:
            limit (int): The maximum number of memories to retrieve. Defaults to 10.

        Returns:
            list: A list of memory documents, or an empty list if not connected or error occurs.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot retrieve memories.")
            return []
        try:
            memories = list(self.collection.find().sort("timestamp", -1).limit(limit))
            logging.info(f"Retrieved {len(memories)} recent memories.")
            return memories
        except Exception as e:
            logging.error(f"Failed to retrieve memories from MongoDB: {e}")
            return []

    # Potential future method:
    # def search_memories(self, query: str, limit: int = 5):
    #     """Searches memories based on a query (requires text index on 'user_input' and 'llm_response')."""
    #     if not self.is_connected():
    #         logging.warning("MongoDB not connected. Cannot search memories.")
    #         return []
    #     try:
    #         # Ensure you have a text index created in MongoDB:
    #         # db.memories.createIndex({ user_input: "text", llm_response: "text" })
    #         memories = list(self.collection.find(
    #             { "$text": { "$search": query } },
    #             { "score": { "$meta": "textScore" } } # Optional: score by relevance
    #         ).sort({ "score": { "$meta": "textScore" } }).limit(limit))
    #         logging.info(f"Found {len(memories)} memories matching query '{query}'.")
    #         return memories
    #     except Exception as e:
    #         logging.error(f"Failed to search memories in MongoDB: {e}")
    #         return []

    def close_connection(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed.")

# Example Usage (for testing)
if __name__ == "__main__":
    print("Testing MongoHandler...")
    handler = MongoHandler()

    if handler.is_connected():
        print("\nAdding a test memory...")
        test_meta = {"source": "test_script", "tags": ["testing", "example"]}
        inserted_id = handler.add_memory("Hello Lily", "Hello Master!", metadata=test_meta)
        if inserted_id:
            print(f"Test memory added with ID: {inserted_id}")

        print("\nRetrieving recent memories...")
        recent = handler.retrieve_recent_memories(5)
        if recent:
            print(f"Found {len(recent)} memories:")
            for mem in recent:
                print(f"- ID: {mem['_id']}, Time: {mem['timestamp']}, User: {mem['user_input'][:30]}...")
        else:
            print("Could not retrieve recent memories.")

        # print("\nSearching memories (requires text index)...")
        # search_results = handler.search_memories("hello")
        # if search_results:
        #     print(f"Found {len(search_results)} search results:")
        #     for mem in search_results:
        #          print(f"- ID: {mem['_id']}, Score: {mem.get('score', 'N/A')}, User: {mem['user_input'][:30]}...")
        # else:
        #     print("Could not perform search or no results found.")

        handler.close_connection()
    else:
        print("Could not connect to MongoDB. Please check your MONGO_URI in .env and ensure the server is running.")
