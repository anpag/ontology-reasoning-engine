import os
from rdflib import Graph
import tempfile
import owlready2
import logging

class OntologyReasoner:
    """
    Applies deductive reasoning to an ontology graph.
    Designed to be pluggable with different reasoning backends (e.g. C++ FaCT++, HermiT).
    """
    
    def __init__(self, backend="hermit"):
        self.backend = backend
        
    def materialize(self, graph: Graph) -> Graph:
        """
        Takes a base graph, applies reasoning, and returns the expanded graph
        containing both explicit and implicitly inferred triples.
        """
        if self.backend == "hermit":
            return self._run_hermit(graph)
        elif self.backend == "factpp":
            return self._run_factpp(graph)
        else:
            raise ValueError(f"Unknown reasoning backend: {self.backend}")
            
    def _run_hermit(self, graph: Graph) -> Graph:
        """
        Fallback Java-based reasoning via owlready2 (HermiT).
        Requires serializing the rdflib graph to disk temporarily.
        """
        logging.info("Starting HermiT reasoning engine...")
        # Write rdflib graph to temp xml
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as temp_xml:
            graph.serialize(destination=temp_xml.name, format="xml")
            temp_xml_path = temp_xml.name
            
        try:
            # Load into owlready2
            world = owlready2.World()
            onto = world.get_ontology(f"file://{temp_xml_path}").load()
            
            # Reason
            with onto:
                owlready2.sync_reasoner(world, debug=0)
                
            # Save reasoned ontology back to temp
            reasoned_xml_path = temp_xml_path + "_reasoned.xml"
            onto.save(file=reasoned_xml_path, format="rdfxml")
            
            # Load back to rdflib
            expanded_graph = Graph()
            expanded_graph.parse(reasoned_xml_path, format="xml")
            
            # Cleanup
            os.remove(reasoned_xml_path)
            return expanded_graph
            
        finally:
            if os.path.exists(temp_xml_path):
                os.remove(temp_xml_path)

    def _run_factpp(self, graph: Graph) -> Graph:
        """
        Placeholder for the C++ FaCT++ bindings integration.
        """
        logging.info("Starting C++ FaCT++ reasoning engine...")
        # TODO: Implement pyfactxx / owlapy C++ bindings here.
        # For now, raise NotImplemented
        raise NotImplementedError("C++ FaCT++ bindings are not yet compiled in this environment.")
