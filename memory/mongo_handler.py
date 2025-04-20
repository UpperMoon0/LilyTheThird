import os
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError
from dotenv import load_dotenv
from datetime import datetime
import logging
from sentence_transformers import SentenceTransformer # Added for embeddings
import numpy as np # Added for embedding operations

# Configure logging
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the embedding model name
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'

class MongoHandler:
    """
    Handles interactions with the MongoDB database for storing and retrieving memories,
    including semantic search using vector embeddings.
    """
    def __init__(self, collection_name="memories"):
        """
        Initializes the MongoDB connection and the sentence transformer model.
        """
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')) # Load .env from project root
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.collection = None
        self.embedding_model = None # Initialize embedding model attribute

        if not self.mongo_uri or self.mongo_uri == "YOUR_MONGO_CONNECTION_URI":
            logging.warning("MONGO_URI not found or not set in .env file. MongoDB memory functions will be disabled.")
            # Still try to load the embedding model even if DB connection fails,
            # as it might be used independently or connection restored later.
            self._load_embedding_model()
            return # Don't attempt DB connection if URI is missing/default

        try:
            logging.info(f"Attempting to connect to MongoDB at {self.mongo_uri.split('@')[-1]}...") # Avoid logging credentials
            # Increased timeout settings (remains the same)
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

            # --- Load Embedding Model ---
            self._load_embedding_model() # Load the model after confirming DB connection possibility

            # --- Ensure Indexes ---
            self._ensure_text_index() # Keep text index for potential keyword fallback or other uses
            # Vector index check removed as it's not applicable for local MongoDB similarity search implementation

            # --- Automatically clean up duplicate facts on startup ---
            self.cleanup_duplicate_facts() # Keep cleanup logic

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
        finally:
             # Ensure model is loaded even if DB connection fails initially
             if not self.embedding_model:
                 self._load_embedding_model()


    def _load_embedding_model(self):
        """Loads the Sentence Transformer model."""
        if self.embedding_model: # Avoid reloading if already loaded
            return
        try:
            logging.info(f"Loading sentence transformer model: {EMBEDDING_MODEL_NAME}...")
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            # Perform a dummy encoding to check if model loaded correctly
            _ = self.embedding_model.encode("test")
            logging.info(f"Sentence transformer model '{EMBEDDING_MODEL_NAME}' loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load sentence transformer model '{EMBEDDING_MODEL_NAME}': {e}", exc_info=True)
            self.embedding_model = None # Ensure model is None on error

    def is_connected(self):
        """Checks if the MongoDB client is connected."""
        return self.client is not None and self.collection is not None

    # --- add_memory method removed ---

    # --- retrieve_recent_memories method removed ---

    # retrieve_memories_by_query function removed as requested.

    def retrieve_memories_by_similarity(self, query_text: str, limit: int = 5):
        """
        Searches memories (facts) based on semantic similarity using vector embeddings,
        performing calculations locally (suitable for non-Atlas MongoDB).

        Args:
            query_text (str): The query text to search for.
            limit (int): The maximum number of similar facts to retrieve. Defaults to 5.

        Returns:
            list: A list of fact strings (content only) ordered by similarity,
                  or an empty list if not connected, model not loaded, or error occurs.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot perform similarity search.")
            return []
        if not self.embedding_model:
            logging.error("Embedding model not loaded. Cannot perform similarity search.")
            return []

        try:
            # 1. Generate embedding for the query text
            logging.debug(f"Generating embedding for query: '{query_text}'")
            query_embedding = np.array(self.embedding_model.encode(query_text))
            query_norm = np.linalg.norm(query_embedding)
            if query_norm == 0:
                logging.warning("Query embedding has zero norm, cannot calculate similarity.")
                return []
            logging.debug(f"Query embedding generated (first few dims): {query_embedding[:5]}...")

            # 2. Fetch all 'fact' documents containing embeddings
            #    Note: For large collections, consider fetching in batches or adding filters.
            logging.debug("Fetching facts with embeddings from local MongoDB...")
            all_facts = list(self.collection.find(
                {"type": "fact", "content_embedding": {"$exists": True}},
                {"content": 1, "content_embedding": 1} # Project only needed fields
            ))
            logging.debug(f"Fetched {len(all_facts)} facts with embeddings.")

            if not all_facts:
                logging.info("No facts with embeddings found in the database.")
                return []

            # 3. Calculate cosine similarity locally
            results = []
            for fact in all_facts:
                fact_embedding = np.array(fact.get("content_embedding", []))
                fact_norm = np.linalg.norm(fact_embedding)

                if fact_embedding.size == 0 or fact_norm == 0:
                    logging.warning(f"Skipping fact due to empty or zero-norm embedding: {fact.get('_id', 'N/A')}")
                    continue

                # Cosine Similarity = dot(A, B) / (norm(A) * norm(B))
                similarity = np.dot(query_embedding, fact_embedding) / (query_norm * fact_norm)
                results.append({
                    "content": fact.get("content", "N/A"),
                    "score": similarity
                })

            # 4. Sort by similarity score (descending)
            results.sort(key=lambda x: x["score"], reverse=True)

            # 5. Limit results
            top_results = results[:limit]

            logging.info(f"Retrieved {len(top_results)} facts similar to query '{query_text}' (calculated locally).")

            # Format the results as strings (content only)
            facts = [m["content"] for m in top_results]
            return facts

        except Exception as e:
            logging.error(f"Failed to perform local similarity search: {e}", exc_info=True)
            return []


    def _ensure_text_index(self):
        """Checks if the required text index exists on 'content' and creates it if not."""
        if not self.is_connected():
            logging.warning("Cannot ensure text index: MongoDB not connected.")
            return

        desired_index_name = "fact_content_search"
        desired_index_key = [("content", "text")] # Only index 'content'

        try:
            existing_indexes = self.collection.index_information()
            found_text_index = None
            conflicting_text_index = None

            # Check existing indexes for text indexes
            for name, info in existing_indexes.items():
                if isinstance(info.get('key'), list) and any(val == 'text' for _, val in info['key']):
                    # Found a text index
                    if name == desired_index_name:
                        # Check if the key matches exactly
                        if info['key'] == desired_index_key:
                            found_text_index = name
                            break # Found the exact index we want
                        else:
                            conflicting_text_index = (name, info) # Name matches, but config differs
                            break
                    else:
                        # Found a text index with a different name
                        conflicting_text_index = (name, info)
                        # Don't break here, keep checking if the desired one also exists

            if found_text_index:
                logging.info(f"Correct text index '{found_text_index}' on 'content' field already exists.")
            elif conflicting_text_index:
                name, info = conflicting_text_index
                logging.warning(f"Conflicting text index found: Name='{name}', Configuration={info}. "
                                f"This conflicts with the desired index '{desired_index_name}' ({desired_index_key}).")
                logging.warning(f"Automatically dropping conflicting index '{name}'...")
                try:
                    self.collection.drop_index(name)
                    logging.info(f"Successfully dropped conflicting index '{name}'.")
                    # Now, attempt to create the desired index again in the 'else' block logic
                    conflicting_text_index = None # Clear the conflict flag
                except Exception as drop_error:
                    logging.error(f"Failed to automatically drop conflicting index '{name}': {drop_error}", exc_info=True)
                    logging.error("Manual intervention might be required.")
                    # Do not proceed to create index if drop failed
                    return # Exit the function

            # If no index was found, or if a conflict was found and successfully dropped
            if not found_text_index and not conflicting_text_index:
                logging.info(f"Creating desired text index '{desired_index_name}' on 'content' field...")
                self.collection.create_index(desired_index_key, name=desired_index_name, default_language='english')
                logging.info(f"Text index '{desired_index_name}' created successfully on field: 'content'.")

        except Exception as e:
            # Catch potential errors during index creation or checking, including the original conflict error
            logging.error(f"Failed to ensure text index '{desired_index_name}': {e}", exc_info=True) # Add exc_info for more details


    # _ensure_vector_index method removed as it's not applicable for local MongoDB similarity search implementation

    def add_fact(self, content: str, metadata: dict = None):
        """
        Adds an arbitrary piece of information (fact) to the MongoDB collection,
        including its vector embedding.

        Args:
            content (str): The information/fact to store.
            metadata (dict, optional): Additional metadata. Defaults to None.

        Returns:
            ObjectId: The inserted document's ID, or None if an error occurred.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot add fact.")
            return None
        if not self.embedding_model:
             logging.error("Embedding model not loaded. Cannot generate embedding for fact.")
             return None

        try:
            # Generate embedding for the content
            logging.debug(f"Generating embedding for fact content: '{content[:50]}...'")
            content_embedding = self.embedding_model.encode(content).tolist()
            logging.debug(f"Fact embedding generated (first few dims): {content_embedding[:5]}...")

            fact_unit = {
                "type": "fact", # Differentiate from conversation turns
                "content": content,
                "content_embedding": content_embedding, # Store the embedding
                "timestamp": datetime.utcnow(),
                "metadata": metadata or {}
            }

            result = self.collection.insert_one(fact_unit)
            logging.info(f"Fact added with ID: {result.inserted_id} (embedding included).")
            return result.inserted_id
        except Exception as e:
            logging.error(f"Failed to add fact with embedding to MongoDB: {e}", exc_info=True)
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
