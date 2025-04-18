import os
import re # Import re for cleaning URIs
import rdflib
from rdflib import URIRef, Literal # Import URIRef and Literal
from pyvis.network import Network
from kg import kg_queries

# Helper function to create consistent URIs
def create_uri(text):
    # Simple cleaning: lowercase, replace spaces with underscores, remove non-alphanumeric (except _)
    clean_text = re.sub(r'[^a-z0-9_]', '', text.lower().replace(" ", "_"))
    # Basic check to avoid empty URIs after cleaning
    if not clean_text:
        clean_text = "unknown_entity" # Fallback for empty strings
    return URIRef(f"http://lilykg.org/entity/{clean_text}")

def create_predicate_uri(text):
     # Simple cleaning for predicates
    clean_text = re.sub(r'[^a-z0-9_]', '', text.lower().replace(" ", "_"))
    if not clean_text:
        clean_text = "unknown_relation"
    return URIRef(f"http://lilykg.org/relation/{clean_text}")


def visualize_graph(graph):
    net = Network(notebook=True, height="800px", width="100%", directed=True)
    for subj, pred, obj in graph:
        net.add_node(str(subj))
        net.add_node(str(obj))
        net.add_edge(str(subj), str(obj), title=str(pred))
    net.show("knowledge_graph.html")

def create_graph(rdf_path):
    graph = rdflib.Graph()
    print("New empty graph created:", graph)
    graph.serialize(rdf_path, format="xml")
    print(f"Empty knowledge graph saved as '{rdf_path}'.")
    visualize_graph(graph)
    return graph

def graph_init():
    rdf_path = os.path.join(os.path.dirname(__file__), "knowledge_graph.rdf")
    if not os.path.exists(rdf_path):
        print("No RDF file found, creating a new graph.")
        return create_graph(rdf_path)
    else:
        try:
            graph = rdflib.Graph()
            graph.parse(rdf_path, format="xml")
            print(f"Graph contains {len(graph)} triples.")
            print("Graph loaded successfully.")
            return graph
        except Exception as e:
            print(f"Error loading graph: {e}")
            return create_graph(rdf_path)

# Remove automatic loading on app start.
graph = None
knowledge_graph_loaded = False
rdf_file_path = os.path.join(os.path.dirname(__file__), "knowledge_graph.rdf") # Store path globally

def load_knowledge_graph():
    global graph, knowledge_graph_loaded, rdf_file_path
    graph = graph_init() # graph_init already uses the path
    knowledge_graph_loaded = True
    return graph

# Function to add triples extracted by the LLM
def add_triples_to_graph(triples):
    global graph, knowledge_graph_loaded, rdf_file_path
    if not knowledge_graph_loaded or graph is None:
        print("Error: Knowledge graph is not loaded. Cannot add triples.")
        return

    added_count = 0
    for triple_dict in triples:
        try:
            subj_text = triple_dict.get("subject")
            pred_text = triple_dict.get("predicate")
            obj_text = triple_dict.get("object")

            if subj_text and pred_text and obj_text:
                # Create URIs for subject and predicate
                subj_uri = create_uri(subj_text)
                pred_uri = create_predicate_uri(pred_text)

                # Object can be a URI or a Literal. Let's treat it as Literal for simplicity now,
                # unless it looks like an entity already processed (heuristic needed if complex).
                # For now, assume objects are mostly descriptive values.
                obj_node = Literal(obj_text) # Treat object as Literal by default

                # Add the triple to the graph
                graph.add((subj_uri, pred_uri, obj_node))
                added_count += 1
                print(f"Added to KG: ({subj_text}, {pred_text}, {obj_text})")
            else:
                print(f"Skipping invalid triple dict: {triple_dict}")

        except Exception as e:
            print(f"Error processing triple {triple_dict}: {e}")

    if added_count > 0:
        try:
            # Save the updated graph back to the file
            graph.serialize(rdf_file_path, format="xml")
            print(f"Successfully added {added_count} triple(s) and saved the knowledge graph.")
            # Optionally re-visualize if needed, might be slow
            # visualize_graph(graph)
        except Exception as e:
            print(f"Error saving updated knowledge graph: {e}")


def clean_keywords(keywords):
    cleaned_keywords = []
    for keyword in keywords:
        keyword = keyword.lower()
        words = keyword.split()
        cleaned_keywords.extend(words)
    return cleaned_keywords

def clean_triple(triple_part): # Renamed from clean_triple to avoid confusion
    # Improved cleaning to handle URIs and Literals
    if isinstance(triple_part, URIRef):
        cleaned_part = str(triple_part).split('/')[-1]
        cleaned_part = cleaned_part.replace('22-rdf-syntax-ns#type', 'is_a') # More descriptive predicate
        cleaned_part = cleaned_part.replace('_', ' ')
        # Add more specific replacements if needed (e.g., entity types)
        if str(triple_part).startswith("http://lilykg.org/entity/"):
             # Keep entity names relatively clean
             pass
        elif str(triple_part).startswith("http://lilykg.org/relation/"):
             # Keep relation names relatively clean
             pass
        else: # Generic URI cleaning
             cleaned_part = cleaned_part.split('#')[-1] # Handle fragment identifiers

    elif isinstance(triple_part, Literal):
        cleaned_part = str(triple_part) # Just use the literal value
    else: # Fallback for unexpected types
        cleaned_part = str(triple_part)

    # General replacements (apply carefully)
    # cleaned_part = cleaned_part.replace('LOC', 'location') # Example
    # cleaned_part = cleaned_part.replace('FAC', 'facility') # Example
    return cleaned_part.strip()


def triples_to_sentences(triples):
    sentences = []
    for subj, pred, obj in triples:
        subj_clean = clean_triple(subj)
        pred_clean = clean_triple(pred)
        obj_clean = clean_triple(obj)
        sentence = f"{subj_clean} {pred_clean} {obj_clean}"
        sentences.append(sentence)
    return sentences

def get_related_info_from_keywords(keywords):
    if graph is None:
        return []
    return triples_to_sentences(kg_queries.get_triples_from_keywords(graph, clean_keywords(keywords)))