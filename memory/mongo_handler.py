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
            # Get the database object (uses DB from URI or defaults to 'test')
            self.db = self.client.get_database()
            db_name = self.db.name # Get the actual name being used
            self.collection = self.db[collection_name]
            logging.info(f"Successfully connected to MongoDB. Database: '{db_name}', Collection: '{collection_name}'")

            # --- Automatically create text index if it doesn't exist ---
            self._ensure_text_index()

            # --- Automatically clean up duplicate facts on startup ---
            self.cleanup_duplicate_facts()

            # --- Automatically clean up duplicate conversations on startup ---
            self.cleanup_duplicate_conversations()

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

    def retrieve_memories_by_query(self, query: str, fact_limit: int = 5, conversation_limit: int = 5):
        """
        Searches memories based on a query using a text index and separates
        results into facts and conversations.
        Requires a text index on 'user_input', 'llm_response', and 'content' fields.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot search memories.")
            return {"facts": [], "conversations": []}

        # Fetch more results initially to have enough candidates for both lists
        initial_fetch_limit = max(fact_limit, conversation_limit) * 2 # Fetch double the max needed, adjust as needed

        try:
            memories = list(self.collection.find(
                { "$text": { "$search": query } },
                { "score": { "$meta": "textScore" } }
            ).sort({ "score": { "$meta": "textScore" } }).limit(initial_fetch_limit)) # Fetch more initially
            logging.info(f"Retrieved {len(memories)} potential memories matching query '{query}'.")

            facts = []
            conversations = []

            for m in memories:
                # Check for fact type first (using the 'type' field if available, or 'content')
                is_fact = m.get("type") == "fact" or ('content' in m and 'user_input' not in m and 'llm_response' not in m)
                is_conversation = 'user_input' in m and 'llm_response' in m

                if is_fact and len(facts) < fact_limit:
                    facts.append(f"Fact: {m.get('content', 'N/A')}") # Use get for safety
                elif is_conversation and len(conversations) < conversation_limit:
                    conversations.append(f"User: {m.get('user_input', 'N/A')}\nLily: {m.get('llm_response', 'N/A')}") # Use get

                # Stop searching if both lists are full
                if len(facts) >= fact_limit and len(conversations) >= conversation_limit:
                    break

            logging.info(f"Filtered results: {len(facts)} facts, {len(conversations)} conversations.")
            return {"facts": facts, "conversations": conversations} # Return a dictionary

        except Exception as e:
            # Handle case where text index might not exist
            if "text index required" in str(e).lower():
                 logging.error("Text index not found on 'memories' collection. Please create one for searching.")
                 logging.error("Mongo Shell: db.memories.createIndex({ user_input: \"text\", llm_response: \"text\", content: \"text\" })")
            else:
                logging.error(f"Failed to search memories in MongoDB: {e}")
            return {"facts": [], "conversations": []} # Return empty lists on error

    def _ensure_text_index(self):
        """Checks if the required text index exists and creates it if not."""
        if not self.is_connected():
            logging.warning("Cannot ensure text index: MongoDB not connected.")
            return

        index_name = "memory_text_search" # Choose a name for the index
        # Define fields to be included in the text index
        index_fields = [("user_input", "text"), ("llm_response", "text"), ("content", "text")]

        try:
            existing_indexes = self.collection.index_information()
            # Check if an index with the desired name already exists
            if index_name not in existing_indexes:
                logging.info(f"Text index '{index_name}' not found. Creating index...")
                # Create the text index with the specified name
                self.collection.create_index(index_fields, name=index_name, default_language='english')
                logging.info(f"Text index '{index_name}' created successfully on fields: {[f[0] for f in index_fields]}.")
            else:
                # Optional: Verify if the existing index covers the required fields
                # This is more complex, for now, we assume the name match is sufficient
                logging.info(f"Text index '{index_name}' already exists.")
        except Exception as e:
            logging.error(f"Failed to check or create text index '{index_name}': {e}")


    def add_fact(self, content: str, metadata: dict = None):
        """
        Adds an arbitrary piece of information (fact) to the MongoDB collection.

        Args:
            content (str): The information/fact to store.
            metadata (dict, optional): Additional metadata. Defaults to None.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot add fact.")
            return None

        fact_unit = {
            "type": "fact", # Differentiate from conversation turns
            "content": content,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        }
        try:
            result = self.collection.insert_one(fact_unit)
            logging.info(f"Fact added with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            logging.error(f"Failed to add fact to MongoDB: {e}")
            return None

    def cleanup_duplicate_facts(self):
        """
        Removes duplicate 'fact' documents based on the 'content' field,
        keeping only the oldest entry for each unique content.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot perform cleanup.")
            return

        logging.info("Starting duplicate fact cleanup...")
        ids_to_delete = []
        try:
            # Aggregation pipeline to find duplicate facts
            pipeline = [
                {
                    "$match": { "type": "fact" } # Only consider documents marked as facts
                },
                {
                    "$group": {
                        "_id": "$content",  # Group by the fact content
                        "ids": { "$push": "$_id" }, # Collect all ObjectIds for this content
                        "first_timestamp": { "$min": "$timestamp" }, # Find the earliest timestamp
                        "count": { "$sum": 1 } # Count documents per content
                    }
                },
                {
                    "$match": { "count": { "$gt": 1 } } # Filter for groups with more than one document (duplicates)
                }
            ]

            duplicate_groups = list(self.collection.aggregate(pipeline))
            logging.info(f"Found {len(duplicate_groups)} fact content groups with duplicates.")

            if not duplicate_groups:
                logging.info("No duplicate facts found.")
                return

            # Find the ID of the document with the minimum timestamp for each group
            ids_to_keep = set()
            for group in duplicate_groups:
                content = group['_id']
                first_timestamp = group['first_timestamp']
                # Find the specific document matching the content and the earliest timestamp
                # There might be multiple docs with the *exact* same earliest timestamp,
                # in which case we arbitrarily keep one. find_one is sufficient.
                doc_to_keep = self.collection.find_one(
                    {"type": "fact", "content": content, "timestamp": first_timestamp},
                    {"_id": 1} # Only fetch the ID
                )
                if doc_to_keep:
                    ids_to_keep.add(doc_to_keep['_id'])


            # Collect IDs to delete (all IDs in duplicate groups MINUS the ones we keep)
            for group in duplicate_groups:
                for doc_id in group['ids']:
                    if doc_id not in ids_to_keep:
                        ids_to_delete.append(doc_id)

            if ids_to_delete:
                logging.info(f"Identified {len(ids_to_delete)} duplicate fact documents to remove.")
                delete_result = self.collection.delete_many({"_id": {"$in": ids_to_delete}})
                logging.info(f"Successfully removed {delete_result.deleted_count} duplicate fact documents.")
            else:
                # This case might happen if all duplicates shared the exact same earliest timestamp
                # and find_one picked one from each group correctly.
                logging.info("No documents needed deletion after identifying keepers (possibly due to identical timestamps).")


        except Exception as e:
            logging.error(f"An error occurred during duplicate fact cleanup: {e}")

    def cleanup_duplicate_conversations(self):
        """
        Removes duplicate conversation documents based on the combination of
        'user_input' and 'llm_response' fields, keeping only the oldest entry
        for each unique pair.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot perform conversation cleanup.")
            return

        logging.info("Starting duplicate conversation cleanup...")
        ids_to_delete = []
        try:
            # Aggregation pipeline to find duplicate conversations
            pipeline = [
                {
                    # Match documents likely representing conversations
                    # Ensure both fields exist, and optionally exclude 'fact' type if necessary
                    "$match": {
                        "user_input": { "$exists": True },
                        "llm_response": { "$exists": True },
                        # "type": { "$ne": "fact" } # Uncomment if facts might wrongly have user/llm fields
                    }
                },
                {
                    "$group": {
                        "_id": { # Group by the combination of user input and llm response
                            "user": "$user_input",
                            "lily": "$llm_response"
                        },
                        "ids": { "$push": "$_id" }, # Collect all ObjectIds for this pair
                        "first_timestamp": { "$min": "$timestamp" }, # Find the earliest timestamp
                        "count": { "$sum": 1 } # Count documents per pair
                    }
                },
                {
                    "$match": { "count": { "$gt": 1 } } # Filter for groups with more than one document
                }
            ]

            duplicate_groups = list(self.collection.aggregate(pipeline))
            logging.info(f"Found {len(duplicate_groups)} conversation content groups with duplicates.")

            if not duplicate_groups:
                logging.info("No duplicate conversations found.")
                return

            # Find the ID of the document with the minimum timestamp for each group
            ids_to_keep = set()
            for group in duplicate_groups:
                user_input = group['_id']['user']
                llm_response = group['_id']['lily']
                first_timestamp = group['first_timestamp']

                # Find the specific document matching the pair and the earliest timestamp
                doc_to_keep = self.collection.find_one(
                    {
                        "user_input": user_input,
                        "llm_response": llm_response,
                        "timestamp": first_timestamp
                        # "type": { "$ne": "fact" } # Add if needed for disambiguation
                    },
                    {"_id": 1} # Only fetch the ID
                )
                if doc_to_keep:
                    ids_to_keep.add(doc_to_keep['_id'])

            # Collect IDs to delete (all IDs in duplicate groups MINUS the ones we keep)
            for group in duplicate_groups:
                for doc_id in group['ids']:
                    if doc_id not in ids_to_keep:
                        ids_to_delete.append(doc_id)

            if ids_to_delete:
                logging.info(f"Identified {len(ids_to_delete)} duplicate conversation documents to remove.")
                delete_result = self.collection.delete_many({"_id": {"$in": ids_to_delete}})
                logging.info(f"Successfully removed {delete_result.deleted_count} duplicate conversation documents.")
            else:
                logging.info("No conversation documents needed deletion after identifying keepers.")

        except Exception as e:
            logging.error(f"An error occurred during duplicate conversation cleanup: {e}")


    def close_connection(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed.")
