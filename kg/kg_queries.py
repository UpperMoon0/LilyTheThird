def clean(keywords):
    cleaned_keywords = []
    for keyword in keywords:
        # Convert to lowercase
        keyword = keyword.lower()

        # Split by spaces into multiple words
        words = keyword.split()

        # Add split words to the cleaned_keywords list
        cleaned_keywords.extend(words)

    return cleaned_keywords

def get_triples_from_keywords(graph, keywords):
    # Clean keywords
    keyword_filter = " || ".join([f"CONTAINS(LCASE(str(?subj)), '{kw}') || CONTAINS(LCASE(str(?pred)), '{kw}') || CONTAINS(LCASE(str(?obj)), '{kw}')" for kw in keywords])

    # SPARQL query
    query = f"""
    SELECT ?subj ?pred ?obj
    WHERE {{
        ?subj ?pred ?obj.
        FILTER ({keyword_filter})
    }}
    """

    # Execute the query
    results = graph.query(query)

    # Collect the results
    matching_triples = [(str(subj), str(pred), str(obj)) for subj, pred, obj in results]
    return matching_triples