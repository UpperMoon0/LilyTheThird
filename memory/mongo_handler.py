import os
import os
import bson # Added for ObjectId
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
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
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
            list: A list of dictionaries, each containing '_id' (as string) and 'content',
                  ordered by similarity. Returns an empty list if not connected,
                  model not loaded, or error occurs.
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
            # 2. Fetch all 'fact' documents containing embeddings and _id
            #    Note: For large collections, consider fetching in batches or adding filters.
            logging.debug("Fetching facts with embeddings and IDs from local MongoDB...")
            all_facts = list(self.collection.find(
                {"type": "fact", "content_embedding": {"$exists": True}},
                {"_id": 1, "content": 1, "content_embedding": 1} # Project needed fields
            ))
            logging.debug(f"Fetched {len(all_facts)} facts with embeddings and IDs.")

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
                    "_id": str(fact.get("_id")), # Convert ObjectId to string
                    "content": fact.get("content", "N/A"),
                    "score": similarity
                })

            # 4. Sort by similarity score (descending)
            results.sort(key=lambda x: x["score"], reverse=True)

            # 5. Limit results
            top_results = results[:limit]

            logging.info(f"Retrieved {len(top_results)} facts similar to query '{query_text}' (calculated locally).")

            # Format the results as list of dicts with _id and content
            facts_with_ids = [{"_id": m["_id"], "content": m["content"]} for m in top_results]
            return facts_with_ids

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

        # --- Similarity Check Threshold ---
        SIMILARITY_THRESHOLD = 0.95 # Facts with similarity >= this value will be considered duplicates

        try:
            # 1. Generate embedding for the new content
            logging.debug(f"Generating embedding for potential new fact: '{content[:50]}...'")
            new_embedding = np.array(self.embedding_model.encode(content))
            new_norm = np.linalg.norm(new_embedding)
            if new_norm == 0:
                logging.warning("New fact embedding has zero norm. Cannot calculate similarity. Skipping insertion.")
                return None
            logging.debug(f"New fact embedding generated (first few dims): {new_embedding[:5]}...")

            # 2. Fetch existing fact embeddings
            logging.debug("Fetching existing fact embeddings for similarity check...")
            existing_facts = list(self.collection.find(
                {"type": "fact", "content_embedding": {"$exists": True}},
                {"content": 1, "content_embedding": 1, "_id": 1} # Include content and ID for logging
            ))
            logging.debug(f"Fetched {len(existing_facts)} existing facts with embeddings.")

            # 3. Calculate similarity and find the maximum
            max_similarity = 0.0
            most_similar_fact_content = None
            most_similar_fact_id = None

            if existing_facts:
                for fact in existing_facts:
                    fact_embedding = np.array(fact.get("content_embedding", []))
                    fact_norm = np.linalg.norm(fact_embedding)

                    if fact_embedding.size == 0 or fact_norm == 0:
                        continue # Skip facts with invalid embeddings

                    # Calculate cosine similarity
                    similarity = np.dot(new_embedding, fact_embedding) / (new_norm * fact_norm)

                    if similarity > max_similarity:
                        max_similarity = similarity
                        most_similar_fact_content = fact.get("content", "N/A")
                        most_similar_fact_id = fact.get("_id", "N/A")

                logging.debug(f"Maximum similarity found: {max_similarity:.4f} with fact ID: {most_similar_fact_id}")

            # 4. Check against threshold
            if max_similarity >= SIMILARITY_THRESHOLD:
                logging.info(f"Skipping insertion. New fact is too similar (score: {max_similarity:.4f}) to existing fact (ID: {most_similar_fact_id}): '{most_similar_fact_content[:100]}...'")
                return None # Indicate that the fact was not added due to similarity

            # 5. If not too similar, proceed with insertion
            logging.debug("New fact passed similarity check. Proceeding with insertion.")
            fact_unit = {
                "type": "fact", # Differentiate from conversation turns
                "content": content,
                "content_embedding": new_embedding.tolist(), # Store the embedding (already generated)
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
        Removes semantically similar 'fact' documents based on vector embeddings,
        keeping only the oldest entry for each group of similar facts.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot perform semantic cleanup.")
            return
        if not self.embedding_model:
            logging.error("Embedding model not loaded. Cannot perform semantic cleanup.")
            return

        # --- Similarity Threshold for Cleanup ---
        # Consider if this should be the same or different from the add_fact threshold
        SIMILARITY_THRESHOLD = 0.95

        logging.info("Starting semantic duplicate fact cleanup...")
        ids_to_delete = set()
        try:
            # 1. Fetch all facts with necessary fields, sorted by timestamp (oldest first)
            logging.debug("Fetching all facts with embeddings and timestamps for cleanup...")
            all_facts = list(self.collection.find(
                {"type": "fact", "content_embedding": {"$exists": True}},
                {"_id": 1, "timestamp": 1, "content_embedding": 1, "content": 1} # Include content for logging
            ).sort("timestamp", 1)) # Sort ascending by timestamp
            logging.info(f"Fetched {len(all_facts)} facts for semantic cleanup check.")

            if len(all_facts) < 2:
                logging.info("Not enough facts to compare for semantic duplicates.")
                return

            # Convert embeddings to numpy arrays and calculate norms once
            fact_data = []
            for fact in all_facts:
                embedding = np.array(fact.get("content_embedding", []))
                norm = np.linalg.norm(embedding)
                if embedding.size > 0 and norm > 0:
                    fact_data.append({
                        "_id": fact["_id"],
                        "embedding": embedding,
                        "norm": norm,
                        "content": fact.get("content", "N/A") # For logging
                    })
                else:
                     logging.warning(f"Skipping fact ID {fact['_id']} in cleanup due to invalid embedding.")

            # 2. Compare each fact with subsequent facts
            num_facts = len(fact_data)
            for i in range(num_facts):
                if fact_data[i]["_id"] in ids_to_delete:
                    continue # Skip if already marked for deletion

                fact_i = fact_data[i]

                for j in range(i + 1, num_facts):
                    if fact_data[j]["_id"] in ids_to_delete:
                        continue # Skip if already marked for deletion

                    fact_j = fact_data[j]

                    # Calculate cosine similarity
                    similarity = np.dot(fact_i["embedding"], fact_j["embedding"]) / (fact_i["norm"] * fact_j["norm"])

                    # 3. If similar, mark the newer one (fact_j) for deletion
                    if similarity >= SIMILARITY_THRESHOLD:
                        logging.debug(f"Marking fact ID {fact_j['_id']} for deletion (similarity {similarity:.4f} with older fact ID {fact_i['_id']}).")
                        logging.debug(f"  - Older Content: '{fact_i['content'][:100]}...'")
                        logging.debug(f"  - Newer Content: '{fact_j['content'][:100]}...'")
                        ids_to_delete.add(fact_j["_id"])

            # 4. Perform deletion
            if ids_to_delete:
                ids_list = list(ids_to_delete)
                logging.info(f"Identified {len(ids_list)} semantically duplicate fact documents to remove.")
                delete_result = self.collection.delete_many({"_id": {"$in": ids_list}})
                logging.info(f"Successfully removed {delete_result.deleted_count} semantically duplicate fact documents.")
            else:
                logging.info("No semantically duplicate facts found requiring cleanup.")

        except Exception as e:
            logging.error(f"An error occurred during semantic duplicate fact cleanup: {e}", exc_info=True)

    # --- cleanup_duplicate_conversations method removed ---

    def update_fact(self, memory_id: str, new_content: str) -> bool:
        """
        Updates the content and embedding of an existing fact document.

        Args:
            memory_id (str): The string representation of the MongoDB ObjectId of the fact to update.
            new_content (str): The new content for the fact.

        Returns:
            ObjectId | None: The ObjectId of the newly inserted fact if successful, None otherwise.
        """
        if not self.is_connected():
            logging.warning("MongoDB not connected. Cannot replace fact.")
            return None
        if not self.embedding_model:
            logging.error("Embedding model not loaded. Cannot generate embedding for replacement fact.")
            return None

        try:
            # 1. Validate the ObjectId string for deletion
            try:
                object_id_to_delete = bson.ObjectId(memory_id)
            except bson.errors.InvalidId:
                logging.error(f"Invalid memory_id format provided: '{memory_id}'. Cannot find document to delete.")
                return None # Cannot proceed without a valid ID to delete

            # 2. Attempt to delete the old document
            logging.debug(f"Attempting to delete fact with ID: {memory_id}")
            delete_result = self.collection.delete_one({"_id": object_id_to_delete, "type": "fact"})

            if delete_result.deleted_count == 0:
                logging.warning(f"Fact replacement failed: No fact found with ID '{memory_id}' to delete.")
                # Decide if we should still insert? For now, let's say no, as the intent was to *replace*.
                return None
            else:
                logging.info(f"Successfully deleted old fact with ID: {memory_id}")

            # 3. Generate embedding for the new content
            logging.debug(f"Generating embedding for replacement fact content...")
            new_embedding = np.array(self.embedding_model.encode(new_content))
            new_norm = np.linalg.norm(new_embedding)
            if new_norm == 0:
                logging.warning("New fact embedding has zero norm. Skipping insertion.")
                # Even though deletion succeeded, insertion failed. Return None.
                return None
            logging.debug("New embedding generated.")

            # 4. Insert the new document (no similarity check needed here, as we are explicitly replacing)
            fact_unit = {
                "type": "fact",
                "content": new_content,
                "content_embedding": new_embedding.tolist(),
                "timestamp": datetime.utcnow(),
                "metadata": {} # Start with empty metadata for the replacement
            }
            insert_result = self.collection.insert_one(fact_unit)
            new_id = insert_result.inserted_id
            logging.info(f"Successfully inserted replacement fact with new ID: {new_id}")
            return new_id # Return the ID of the newly inserted document

        except Exception as e:
            logging.error(f"Failed during fact replacement process for old ID '{memory_id}': {e}", exc_info=True)
            return None


    def close_connection(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()
            logging.info("MongoDB connection closed.")
