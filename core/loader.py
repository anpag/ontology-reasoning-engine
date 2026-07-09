import os
from rdflib import Graph
from rdflib.util import guess_format

class OntologyLoader:
    """
    A universal parser for ontology files. Uses rdflib to load
    OWL, TTL, JSON-LD, or RDF/XML files into a unified Graph.
    """
    
    def __init__(self):
        self.graph = Graph()
        
    def load_file(self, file_path: str) -> Graph:
        """
        Loads an ontology file into the graph. Autodetects format based
        on file extension or rdflib's guess_format.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Ontology file not found: {file_path}")
            
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Explicit format mapping for speed and accuracy
        format_map = {
            ".ttl": "turtle",
            ".owl": "xml",
            ".rdf": "xml",
            ".jsonld": "json-ld",
            ".nt": "nt"
        }
        
        file_format = format_map.get(file_ext)
        if not file_format:
            # Fallback to guessing based on content
            file_format = guess_format(file_path)
            
        if not file_format:
            raise ValueError(f"Could not determine format for file: {file_path}")
            
        print(f"Loading {file_path} as {file_format}...")
        self.graph.parse(file_path, format=file_format)
        
        return self.graph

    def get_triple_count(self) -> int:
        """Returns the number of triples currently in the graph."""
        return len(self.graph)
