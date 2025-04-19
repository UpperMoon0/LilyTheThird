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

            # --- Duplicate conversation cleanup removed ---

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

    # --- add_memory method removed ---

    # --- retrieve_recent_memories method removed ---

    def retrieve_memories_by_query(self, query: str, fact_limit: int = 5):
        """
        Searches memories (facts) based on a query using a text index.
        Requires a text index on the 'content' field.

        Args:
            query (str): The search query string.
            fact_limit (int): The maximum number of facts to retrieve. Defaults to 5.

        Returns:
            list: A list of fact strings, or an empty list if not connected or error occurs.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot search memories.")
            return [] # Return empty list directly

        try:
            # Search only for documents of type 'fact' using the text index
            memories = list(self.collection.find(
                {
                    "type": "fact", # Ensure we only match facts
                    "$text": { "$search": query }
                },
                { "score": { "$meta": "textScore" } } # Include text score for sorting
            ).sort({ "score": { "$meta": "textScore" } }).limit(fact_limit)) # Limit to fact_limit

            logging.info(f"Retrieved {len(memories)} facts matching query '{query}'.")

            # Format the results as strings
            facts = [f"Fact: {m.get('content', 'N/A')}" for m in memories]

            return facts

        except Exception as e:
            # Handle case where text index might not exist or other errors
            if "text index required" in str(e).lower() or "index not found" in str(e).lower():
                 logging.error("Text index not found or invalid on 'memories' collection (expected on 'content'). Please create one.")
                 logging.error("Mongo Shell Example: db.memories.createIndex({ content: \"text\" }, { name: \"fact_content_search\" })")
            else:
                logging.error(f"Failed to search memories in MongoDB: {e}")
            return [] # Return empty list on error

    def _ensure_text_index(self):
        """Checks if the required text index exists on 'content' and creates it if not."""
        if not self.is_connected():
            logging.warning("Cannot ensure text index: MongoDB not connected.")
            return

        index_name = "fact_content_search" # More specific index name
        # Define fields to be included in the text index - ONLY 'content' now
        index_fields = [("content", "text")]

        try:
            existing_indexes = self.collection.index_information()
            # Check if an index with the desired name already exists
            if index_name not in existing_indexes:
                logging.info(f"Text index '{index_name}' on 'content' field not found. Creating index...")
                # Create the text index with the specified name and fields
                self.collection.create_index(index_fields, name=index_name, default_language='english')
                logging.info(f"Text index '{index_name}' created successfully on field: 'content'.")
            else:
                # Optional: Verify if the existing index *is* the correct text index on 'content'
                index_info = existing_indexes.get(index_name, {})
                is_correct_text_index = any(field == "content" and index_type == "text" for field, index_type in index_info.get("key", []))
                if is_correct_text_index:
                    logging.info(f"Text index '{index_name}' on 'content' field already exists.")
                else:
                    # This case is unlikely if the name matches but indicates a problem
                    logging.warning(f"Index named '{index_name}' exists but doesn't seem to be the correct text index on 'content'. Manual review recommended.")
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

    # --- cleanup_duplicate_conversations method removed ---


    def close_connection(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed.")
