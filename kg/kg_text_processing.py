import os
import re
import rdflib
import spacy
from rdflib import URIRef, RDF

from kg import kg_handler


def process_text_and_populate_graph(data_folder, existing_graph=None):
    """
    Processes all text files in the data folder, extracts named entities and relations, and populates the knowledge graph.
    """
    nlp = spacy.load("en_core_web_trf")

    if existing_graph is None:
        graph = rdflib.Graph()
    else:
        graph = existing_graph

    def create_uri(group, name):
        clean_name = re.sub(r'[^\w\s]', '', name.strip().replace(" ", "_").replace('"', '').lower())
        return URIRef(f"http://lilykg.org/{group}/{clean_name}")

    for file_name in os.listdir(data_folder):
        if file_name.endswith('.txt'):
            file_path = os.path.join(data_folder, file_name)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                text = file.read()

            doc = nlp(text)

            for ent in doc.ents:
                entity_uri = create_uri(ent.label_, ent.text)
                graph.add((entity_uri, RDF.type, URIRef(f"http://lilykg.org/ENTITY/{ent.label_}")))

            for token in doc:
                if token.dep_ == 'nsubj' and token.head.pos_ == 'VERB':
                    subject = token.text
                    predicate = token.head.text
                    object_ = [child.text for child in token.head.children if child.dep_ == 'dobj']

                    if object_:
                        subject_uri = create_uri("ENTITY", subject)
                        object_uri = create_uri("ENTITY", " ".join(object_))

                        graph.add((subject_uri, URIRef(f"http://lilykg.org/RELATION/{predicate.lower()}"), object_uri))

    graph.serialize("knowledge_graph.rdf", format="xml")
    print("Knowledge graph populated and saved as 'knowledge_graph.rdf'.")

    kg_handler.visualize_graph(graph)
    print("Knowledge graph visualized.")

# Example usage
data_folder = 'data'
process_text_and_populate_graph(data_folder)
