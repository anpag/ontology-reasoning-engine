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
        elif self.backend == "custom":
            return self._run_custom_cpp(graph)
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

    def _run_custom_cpp(self, graph: Graph) -> Graph:
        """
        Executes our custom-built, highly optimized C++ reasoning engine.
        It uses N-Triples for fast I/O and computes transitive closures using BFS.
        """
        logging.info("Starting Custom C++ reasoning engine...")
        import subprocess
        
        # 1. Serialize the graph to N-Triples (NT) format for lightning-fast C++ parsing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nt") as temp_in:
            graph.serialize(destination=temp_in.name, format="nt")
            in_path = temp_in.name
            
        out_path = in_path + "_reasoned.nt"
        
        try:
            # 2. Invoke our compiled C++ binary
            # Assuming the binary is built in the 'cpp_engine' folder
            engine_binary = os.path.join(os.path.dirname(__file__), "..", "cpp_engine", "custom_reasoner")
            
            if not os.path.exists(engine_binary):
                raise FileNotFoundError(f"Custom C++ engine not found at {engine_binary}. Please compile it first.")
                
            cmd = [engine_binary, in_path, out_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logging.error(f"Custom C++ Engine Failed:\n{result.stderr}")
                raise RuntimeError("Custom C++ Reasoning Engine failed to execute.")
                
            # 3. Load the newly inferred N-Triples back into the graph
            # This merges the newly inferred triples with the existing ones
            if os.path.exists(out_path):
                graph.parse(out_path, format="nt")
            
            return graph
            
        finally:
            if os.path.exists(in_path):
                os.remove(in_path)
            if os.path.exists(out_path):
                os.remove(out_path)
