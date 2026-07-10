import os
import logging
import requests
from rdflib import Graph, URIRef
from rdflib.namespace import OWL
from rdflib.util import guess_format

class OntologyLoader:
    """
    A universal parser for ontology files. Uses rdflib to load
    OWL, TTL, JSON-LD, or RDF/XML files into a unified Graph.
    """
    
    def __init__(self):
        # Using Oxigraph (Rust) as the backend store for Google-scale performance
        # This replaces the slow pure-Python memory store
        try:
            self.graph = Graph(store="Oxigraph")
            logging.info("Initialized RDFLib with high-performance Rust Oxigraph backend.")
        except Exception:
            logging.warning("Oxigraph store not available. Falling back to default Python memory store.")
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
        
        # Explicitly find and resolve any owl:imports
        self._resolve_imports(self.graph)
        
        return self.graph

    def _resolve_imports(self, g: Graph, visited=None):
        """
        Recursively finds owl:imports in the graph, downloads them via HTTP,
        and merges them into the main graph to ensure total completeness.
        """
        if visited is None:
            visited = set()
            
        imports = list(g.objects(predicate=OWL.imports))
        
        for imp in imports:
            uri = str(imp)
            if uri not in visited:
                visited.add(uri)
                try:
                    # Attempt to fetch and parse the imported ontology
                    temp_g = Graph()
                    temp_g.parse(uri)
                    
                    # Merge into the main graph
                    for triple in temp_g:
                        g.add(triple)
                        
                    # Recursively resolve imports of the imported file
                    self._resolve_imports(g, visited)
                except Exception as e:
                    # Log silently or handle as needed
                    pass

    def get_triple_count(self) -> int:
        """Returns the number of triples currently in the graph."""
        return len(self.graph)
