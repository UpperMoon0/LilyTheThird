import os
import rdflib
from pyvis.network import Network
from kg import kg_queries

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

def load_knowledge_graph():
    global graph, knowledge_graph_loaded
    graph = graph_init()
    knowledge_graph_loaded = True
    return graph

def clean_keywords(keywords):
    cleaned_keywords = []
    for keyword in keywords:
        keyword = keyword.lower()
        words = keyword.split()
        cleaned_keywords.extend(words)
    return cleaned_keywords

def clean_triple(triple):
    cleaned_part = triple.split('/')[-1]
    cleaned_part = cleaned_part.replace('22-rdf-syntax-ns#type', 'is')
    cleaned_part = cleaned_part.replace('_', ' ')
    cleaned_part = cleaned_part.replace('LOC', 'a location')
    cleaned_part = cleaned_part.replace('FAC', 'a facility')
    return cleaned_part

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